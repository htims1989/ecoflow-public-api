"""EcoFlow IoT Open (Public API) REST client.

Handles HMAC-SHA256 request signing, MQTT credential retrieval, device
discovery and the historical energy aggregate endpoint (``/device/quota/data``).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import random
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class EcoflowApiError(Exception):
    """Raised when the EcoFlow API returns a non-success response."""


class EcoflowAuthError(EcoflowApiError):
    """Raised when credentials are rejected by the API."""


class EcoflowUnsupportedError(EcoflowApiError):
    """Raised when a device/endpoint combination is not supported (code 1006).

    For example, a Smart Meter has no historical energy aggregates, so
    ``/device/quota/data`` returns ``1006`` for it.
    """


@dataclass(slots=True)
class MqttCredentials:
    """Credentials for the EcoFlow MQTT broker returned by /certification."""

    account: str
    password: str
    host: str
    port: int


@dataclass(slots=True)
class DeviceInfo:
    """Minimal device descriptor returned by /device/list."""

    sn: str
    name: str
    online: bool


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten a nested dict into dotted keys for signing POST bodies."""
    items: dict[str, Any] = {}
    for key, value in data.items():
        new_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            items.update(_flatten(value, new_key))
        else:
            items[new_key] = value
    return items


class EcoflowPublicApi:
    """Thin async wrapper over the EcoFlow IoT Open REST API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        access_key: str,
        secret_key: str,
    ) -> None:
        self._session = session
        self._host = host
        self._access_key = access_key
        self._secret_key = secret_key

    def _headers(self, params_str: str) -> dict[str, str]:
        nonce = str(random.randint(10000, 1000000))
        timestamp = str(int(time.time() * 1000))
        base = (
            f"accessKey={self._access_key}&nonce={nonce}&timestamp={timestamp}"
        )
        target = f"{params_str}&{base}" if params_str else base
        sign = hmac.new(
            self._secret_key.encode("utf-8"),
            target.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "accessKey": self._access_key,
            "nonce": nonce,
            "timestamp": timestamp,
            "sign": sign,
        }

    @staticmethod
    def _sorted_query(params: dict[str, Any]) -> str:
        return "&".join(f"{k}={params[k]}" for k in sorted(params))

    async def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        params_str = self._sorted_query(params)
        headers = self._headers(params_str)
        url = f"https://{self._host}/iot-open/sign{endpoint}"
        if params_str:
            url = f"{url}?{params_str}"
        async with self._session.get(url, headers=headers) as resp:
            return await self._parse(resp)

    async def _post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        params_str = self._sorted_query(_flatten(body))
        headers = self._headers(params_str)
        headers["Content-Type"] = "application/json"
        url = f"https://{self._host}/iot-open/sign{endpoint}"
        async with self._session.post(url, headers=headers, json=body) as resp:
            return await self._parse(resp)

    @staticmethod
    async def _parse(resp: aiohttp.ClientResponse) -> dict[str, Any]:
        if resp.status == 401:
            raise EcoflowAuthError("Unauthorized (HTTP 401)")
        resp.raise_for_status()
        payload = await resp.json(content_type=None)
        code = str(payload.get("code", ""))
        if code not in ("0", ""):
            message = payload.get("message", "Unknown error")
            if code in ("6042", "6043", "401"):
                raise EcoflowAuthError(f"{code}: {message}")
            if code == "1006":
                raise EcoflowUnsupportedError(f"{code}: {message}")
            raise EcoflowApiError(f"{code}: {message}")
        return payload

    async def certification(self) -> MqttCredentials:
        """Fetch MQTT broker credentials."""
        payload = await self._get("/certification")
        data = payload.get("data", {})
        return MqttCredentials(
            account=data["certificateAccount"],
            password=data["certificatePassword"],
            host=data["url"],
            port=int(data["port"]),
        )

    async def device_list(self) -> list[DeviceInfo]:
        """List all devices bound to the developer account."""
        payload = await self._get("/device/list")
        result: list[DeviceInfo] = []
        for device in payload.get("data", []):
            sn = device.get("sn")
            if not sn:
                continue
            result.append(
                DeviceInfo(
                    sn=sn,
                    name=device.get("deviceName") or f"EcoFlow {sn}",
                    online=bool(int(device.get("online", 0))),
                )
            )
        return result

    async def quota_all(self, sn: str) -> dict[str, Any]:
        """Fetch the real-time quota snapshot (limited field set)."""
        payload = await self._get("/device/quota/all", {"sn": sn})
        return payload.get("data", {}) or {}

    async def energy_aggregate(
        self, sn: str, code: str, begin_time: str, end_time: str
    ) -> list[dict[str, Any]]:
        """Fetch a historical energy aggregate (Wh) for a code and window.

        Returns the raw ``data`` list; each item has ``indexValue`` (Wh) and an
        optional ``extra`` ("1"/"2") that splits directional flows such as grid
        import/export or battery charge/discharge.
        """
        body = {
            "sn": sn,
            "params": {"code": code, "beginTime": begin_time, "endTime": end_time},
        }
        payload = await self._post("/device/quota/data", body)
        data = payload.get("data")
        # The endpoint nests a second envelope: {"data": {"data": [...]}}.
        if isinstance(data, dict):
            return data.get("data", []) or []
        return data or []

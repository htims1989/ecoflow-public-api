"""Config flow for the EcoFlow Stream (Public API) integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .api import DeviceInfo, EcoflowApiError, EcoflowAuthError, EcoflowPublicApi
from .const import (
    API_HOSTS,
    CONF_ACCESS_KEY,
    CONF_API_HOST,
    CONF_DEVICES,
    CONF_GROUP,
    CONF_SECRET_KEY,
    DEFAULT_API_HOST,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _device_label(device: DeviceInfo) -> str:
    """Human-friendly label for a discovered device."""
    status = "online" if device.online else "offline"
    return f"{device.name} ({device.sn}) — {status}"


class EcoflowStreamXConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EcoFlow Stream (Public API)."""

    VERSION = 1

    def __init__(self) -> None:
        self._base_data: dict[str, Any] = {}
        self._discovered: list[DeviceInfo] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = API_HOSTS.get(user_input[CONF_API_HOST], DEFAULT_API_HOST)
            access_key = user_input[CONF_ACCESS_KEY].strip()
            secret_key = user_input[CONF_SECRET_KEY].strip()
            group = user_input[CONF_GROUP].strip()

            await self.async_set_unique_id(f"{access_key}-{group}")
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            api = EcoflowPublicApi(session, host, access_key, secret_key)
            try:
                devices = await api.device_list()
            except EcoflowAuthError:
                errors["base"] = "invalid_auth"
            except EcoflowApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating EcoFlow credentials")
                errors["base"] = "unknown"
            else:
                if not devices:
                    errors["base"] = "no_devices"
                else:
                    self._base_data = {
                        CONF_API_HOST: host,
                        CONF_ACCESS_KEY: access_key,
                        CONF_SECRET_KEY: secret_key,
                        CONF_GROUP: group,
                    }
                    self._discovered = devices
                    return await self.async_step_devices()

        schema = vol.Schema(
            {
                vol.Required(CONF_ACCESS_KEY): str,
                vol.Required(CONF_SECRET_KEY): str,
                vol.Required(CONF_GROUP, default="Home"): str,
                vol.Required(
                    CONF_API_HOST, default=next(iter(API_HOSTS))
                ): vol.In(list(API_HOSTS)),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick which discovered devices to set up."""
        errors: dict[str, str] = {}
        options = {d.sn: _device_label(d) for d in self._discovered}

        if user_input is not None:
            selected = user_input[CONF_DEVICES]
            if not selected:
                errors["base"] = "no_devices_selected"
            else:
                by_sn = {d.sn: d for d in self._discovered}
                chosen = [
                    {"sn": sn, "name": by_sn[sn].name}
                    for sn in selected
                    if sn in by_sn
                ]
                group = self._base_data[CONF_GROUP]
                return self.async_create_entry(
                    title=f"EcoFlow Stream ({group})",
                    data={**self._base_data, CONF_DEVICES: chosen},
                )

        # Default to every online device, or all devices if none report online.
        default = [d.sn for d in self._discovered if d.online] or list(options)
        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICES, default=default): cv.multi_select(
                    options
                )
            }
        )
        return self.async_show_form(
            step_id="devices", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> EcoflowStreamXOptionsFlow:
        return EcoflowStreamXOptionsFlow(config_entry)


class EcoflowStreamXOptionsFlow(OptionsFlow):
    """Allow re-scanning the account and changing the enabled devices."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        data = self._entry.data

        # Devices already configured on the entry (fallback + name source).
        stored: dict[str, str] = {
            d["sn"]: d["name"] for d in data[CONF_DEVICES]
        }

        # Try to refresh the live device list so newly-added hardware shows up.
        session = async_get_clientsession(self.hass)
        api = EcoflowPublicApi(
            session,
            data[CONF_API_HOST],
            data[CONF_ACCESS_KEY],
            data[CONF_SECRET_KEY],
        )
        live: list[DeviceInfo] = []
        try:
            live = await api.device_list()
        except EcoflowApiError as err:
            _LOGGER.debug("Options device_list refresh failed: %s", err)

        # Build the option set: every live device plus any still-stored device
        # (so a device that has vanished from the API can still be removed).
        options: dict[str, str] = {d.sn: _device_label(d) for d in live}
        live_names = {d.sn: d.name for d in live}
        for sn, name in stored.items():
            options.setdefault(sn, f"{name} ({sn})")

        if user_input is not None:
            selected = user_input[CONF_DEVICES]
            if not selected:
                errors["base"] = "no_devices_selected"
            else:
                chosen = [
                    {"sn": sn, "name": live_names.get(sn, stored.get(sn, sn))}
                    for sn in selected
                    if sn in options
                ]
                self.hass.config_entries.async_update_entry(
                    self._entry, data={**data, CONF_DEVICES: chosen}
                )
                return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DEVICES, default=list(stored)
                ): cv.multi_select(options)
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )

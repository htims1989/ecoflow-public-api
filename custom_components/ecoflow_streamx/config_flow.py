"""Config flow for the EcoFlow Stream (Public API) integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EcoflowApiError, EcoflowAuthError, EcoflowPublicApi
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


class EcoflowStreamXConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EcoFlow Stream (Public API)."""

    VERSION = 1

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
                    return self.async_create_entry(
                        title=f"EcoFlow Stream ({group})",
                        data={
                            CONF_API_HOST: host,
                            CONF_ACCESS_KEY: access_key,
                            CONF_SECRET_KEY: secret_key,
                            CONF_GROUP: group,
                            CONF_DEVICES: [
                                {"sn": d.sn, "name": d.name} for d in devices
                            ],
                        },
                    )

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

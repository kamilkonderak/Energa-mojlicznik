"""Config flow for Energa Mój Licznik."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import EnergaAuthError, EnergaClient, EnergaConnectionError, EnergaError
from .const import (
    CONF_IMPORT_STATISTICS,
    CONF_SCAN_INTERVAL,
    CONF_STAT_PREFIX,
    DEFAULT_IMPORT_STATISTICS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .parser import MeterData

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
        vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    }
)
REAUTH_SCHEMA = vol.Schema(
    {vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
)


async def async_validate(hass: HomeAssistant, username: str, password: str) -> MeterData:
    """Log in once and return the meter data. Raises EnergaError subclasses."""
    session = async_create_clientsession(hass, auto_cleanup=False, cookie_jar=aiohttp.CookieJar())
    try:
        return await EnergaClient(session, username, password, hass.async_add_executor_job).async_fetch()
    finally:
        session.detach()


def _errors_for(err: EnergaError) -> dict[str, str]:
    if isinstance(err, EnergaAuthError):
        return {"base": "invalid_auth"}
    if isinstance(err, EnergaConnectionError):
        return {"base": "cannot_connect"}
    return {"base": "unknown_page"}


class EnergaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Energa Mój Licznik."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> EnergaOptionsFlow:
        """Return the options flow."""
        return EnergaOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the Mój licznik login."""
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            try:
                data = await async_validate(self.hass, username, user_input[CONF_PASSWORD])
            except EnergaError as err:
                _LOGGER.debug("Validation failed: %s", err)
                errors = _errors_for(err)
            else:
                ppe = data.supplier.get("ppe")
                await self.async_set_unique_id(ppe or username.lower())
                self._abort_if_unique_id_configured()
                tariff = data.supplier.get("tariff")
                title = f"Licznik Energa {tariff}" if tariff else "Licznik Energa"
                # The first meter gets short statistic ids that dashboards can use as-is.
                prefix = (ppe or username) if self._async_current_entries() else ""
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_STAT_PREFIX: prefix,
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input or {}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start reauthentication after the password stopped working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the new password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await async_validate(self.hass, entry.data[CONF_USERNAME], user_input[CONF_PASSWORD])
            except EnergaError as err:
                errors = _errors_for(err)
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={"username": entry.data[CONF_USERNAME]},
        )


class EnergaOptionsFlow(OptionsFlow):
    """Polling interval and statistics import."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options."""
        if user_input is not None:
            user_input[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL, default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        unit_of_measurement="h",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_IMPORT_STATISTICS,
                    default=options.get(CONF_IMPORT_STATISTICS, DEFAULT_IMPORT_STATISTICS),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

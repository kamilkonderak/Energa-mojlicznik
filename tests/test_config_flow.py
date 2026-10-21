"""Config flow tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.energa_mojlicznik.api import EnergaAuthError, EnergaConnectionError, EnergaParseError
from custom_components.energa_mojlicznik.const import (
    CONF_IMPORT_STATISTICS,
    CONF_SCAN_INTERVAL,
    CONF_STAT_PREFIX,
    DOMAIN,
)

VALIDATE = "custom_components.energa_mojlicznik.config_flow.async_validate"
SETUP = "custom_components.energa_mojlicznik.async_setup_entry"
USER = {CONF_USERNAME: " jan@example.com ", CONF_PASSWORD: "tajne"}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """The integration depends on recorder, which must start before hass."""
    yield


async def test_user_flow_creates_entry(hass: HomeAssistant, meter_data) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    with patch(VALIDATE, return_value=meter_data), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Licznik Energa G12W"
    assert result["data"] == {CONF_USERNAME: "jan@example.com", CONF_PASSWORD: "tajne", CONF_STAT_PREFIX: ""}
    assert result["result"].unique_id == "000000000000000000"


async def test_second_meter_gets_prefixed_statistics(hass: HomeAssistant, meter_data) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="111", data=USER).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch(VALIDATE, return_value=meter_data), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["data"][CONF_STAT_PREFIX] == "000000000000000000"


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (EnergaAuthError("x"), "invalid_auth"),
        (EnergaConnectionError("x"), "cannot_connect"),
        (EnergaParseError("x"), "unknown_page"),
    ],
)
async def test_user_flow_errors(hass: HomeAssistant, meter_data, error, key) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch(VALIDATE, side_effect=error):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": key}
    # Recovers once the problem is fixed.
    with patch(VALIDATE, return_value=meter_data), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_meter_aborts(hass: HomeAssistant, meter_data) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="000000000000000000", data=USER).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch(VALIDATE, return_value=meter_data):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(hass: HomeAssistant, meter_data) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="000000000000000000",
        data={CONF_USERNAME: "jan@example.com", CONF_PASSWORD: "stare"},
    )
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    with patch(VALIDATE, side_effect=EnergaAuthError("x")):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "zle"})
    assert result["errors"] == {"base": "invalid_auth"}
    with patch(VALIDATE, return_value=meter_data), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "nowe"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "nowe"


async def test_options(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="x", data=USER)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: 6.0, CONF_IMPORT_STATISTICS: False}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_SCAN_INTERVAL: 6, CONF_IMPORT_STATISTICS: False}

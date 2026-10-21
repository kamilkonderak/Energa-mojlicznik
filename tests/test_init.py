"""Setup, sensors and statistics import."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import get_last_statistics
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.components.recorder.common import async_wait_recording_done

from custom_components.energa_mojlicznik.api import EnergaAuthError
from custom_components.energa_mojlicznik.const import DOMAIN

FETCH = "custom_components.energa_mojlicznik.api.EnergaClient.async_fetch"
STAT_ID = f"{DOMAIN}:pobor_strefa_1"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """The integration depends on recorder, which must start before hass."""
    yield


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="000000000000000000",
        data={CONF_USERNAME: "jan@example.com", CONF_PASSWORD: "tajne"},
    )
    entry.add_to_hass(hass)
    return entry


async def _stats(hass: HomeAssistant) -> list[dict]:
    await async_wait_recording_done(hass)
    rows = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, STAT_ID, True, {"state", "sum"}
    )
    return rows.get(STAT_ID, [])


async def test_setup_creates_sensors_and_statistics(recorder_mock, hass: HomeAssistant, entry, meter_data) -> None:
    await hass.config.async_set_time_zone("Europe/Warsaw")
    with patch(FETCH, return_value=meter_data):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    z1 = hass.states.get("sensor.energa_pobor_strefa_1")
    assert z1 is not None
    assert float(z1.state) == pytest.approx(43753.514)
    assert z1.attributes["state_class"] == "total_increasing"
    assert z1.attributes["device_class"] == "energy"
    assert z1.attributes["nazwa_strefy"] == "dzienna"
    z2 = hass.states.get("sensor.energa_pobor_strefa_2")
    total = hass.states.get("sensor.energa_pobor_razem")
    assert float(total.state) == pytest.approx(float(z1.state) + float(z2.state))
    assert hass.states.get("sensor.energa_oddanie_razem") is not None
    tariff = hass.states.get("sensor.energa_taryfa")
    assert tariff.state == "G12W"
    assert "ppe_address" not in tariff.attributes
    odczyt = dt_util.parse_datetime(hass.states.get("sensor.energa_odczyt").state)
    assert dt_util.as_local(odczyt).hour == 0

    # First reading: sum starts at 0, booked in the hour before midnight.
    rows = await _stats(hass)
    assert len(rows) == 1
    assert rows[0]["sum"] == 0
    start = dt_util.as_local(dt_util.utc_from_timestamp(rows[0]["start"]))
    assert (start.day, start.hour) == (17, 23)

    # The next day's reading adds its delta to the sum, on the day it belongs to.
    reg = meter_data.registers["pobor_strefa_1"]
    nxt = replace(reg, value=reg.value + 12.5, read_at=reg.read_at + timedelta(days=1))
    data2 = replace(meter_data, registers={**meter_data.registers, "pobor_strefa_1": nxt})
    with patch(FETCH, return_value=data2):
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=5))
        await hass.async_block_till_done()
    rows = await _stats(hass)
    assert rows[0]["sum"] == pytest.approx(12.5)
    assert rows[0]["state"] == pytest.approx(nxt.value)
    start = dt_util.as_local(dt_util.utc_from_timestamp(rows[0]["start"]))
    assert (start.day, start.hour) == (18, 23)

    # The same reading again is not imported twice.
    with patch(FETCH, return_value=data2):
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=10))
        await hass.async_block_till_done()
    assert (await _stats(hass))[0]["sum"] == pytest.approx(12.5)


async def test_auth_failure_starts_reauth(recorder_mock, hass: HomeAssistant, entry) -> None:
    with patch(FETCH, side_effect=EnergaAuthError("bad")):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_diagnostics_redacted(recorder_mock, hass: HomeAssistant, entry, meter_data) -> None:
    from custom_components.energa_mojlicznik.diagnostics import async_get_config_entry_diagnostics

    with patch(FETCH, return_value=meter_data):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["entry"]["data"][CONF_PASSWORD] == "**REDACTED**"
    assert diag["supplier"]["ppe"] == "**REDACTED**"
    assert diag["supplier"]["ppe_address"] == "**REDACTED**"

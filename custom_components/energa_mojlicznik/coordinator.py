"""Data update coordinator for Energa Mój Licznik."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics, get_last_statistics
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import EnergaAuthError, EnergaClient, EnergaError
from .const import (
    CONF_IMPORT_STATISTICS,
    CONF_SCAN_INTERVAL,
    CONF_STAT_PREFIX,
    DEFAULT_IMPORT_STATISTICS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .parser import KNOWN_WEB_VERSION, MeterData, Register

try:  # HA 2025.4+
    from homeassistant.components.recorder.models import StatisticMeanType
except ImportError:  # pragma: no cover - older cores
    StatisticMeanType = None  # type: ignore[assignment,misc]

_LOGGER = logging.getLogger(__name__)

type EnergaConfigEntry = ConfigEntry[EnergaCoordinator]


def local_read_time(register: Register) -> datetime:
    """Reading time as an aware datetime in Home Assistant's time zone."""
    return register.read_at.replace(tzinfo=dt_util.get_default_time_zone())


def statistic_id(entry: ConfigEntry, key: str) -> str:
    """External statistic id for a register, e.g. energa_mojlicznik:pobor_strefa_1."""
    prefix = re.sub(r"[^0-9a-z]", "", str(entry.data.get(CONF_STAT_PREFIX, "")).lower())
    return f"{DOMAIN}:{prefix}_{key}" if prefix else f"{DOMAIN}:{key}"


def _metadata(statistic_id: str, name: str) -> StatisticMetaData:
    meta: dict[str, Any] = {
        "has_sum": True,
        "name": name,
        "source": DOMAIN,
        "statistic_id": statistic_id,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
    }
    if StatisticMeanType is not None:
        meta["mean_type"] = StatisticMeanType.NONE
    else:  # pragma: no cover
        meta["has_mean"] = False
    if "unit_class" in StatisticMetaData.__annotations__:
        meta["unit_class"] = "energy"
    return StatisticMetaData(**meta)  # type: ignore[typeddict-item]


class EnergaCoordinator(DataUpdateCoordinator[MeterData]):
    """Fetches the meter page every few hours."""

    config_entry: EnergaConfigEntry

    def __init__(self, hass: HomeAssistant, entry: EnergaConfigEntry) -> None:
        hours = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(hours=hours),
        )
        # Own cookie jar: the Energa session must not mix with other integrations.
        session = async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar())
        self.client = EnergaClient(
            session,
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            hass.async_add_executor_job,
        )
        self._version_warned = False

    async def _async_update_data(self) -> MeterData:
        try:
            data = await self.client.async_fetch()
        except EnergaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except EnergaError as err:
            raise UpdateFailed(str(err)) from err

        if data.web_version and data.web_version != KNOWN_WEB_VERSION and not self._version_warned:
            self._version_warned = True
            _LOGGER.warning(
                "Energa page version is %s (parser checked against %s). "
                "If readings look wrong, the page structure may have changed",
                data.web_version,
                KNOWN_WEB_VERSION,
            )

        if self.config_entry.options.get(CONF_IMPORT_STATISTICS, DEFAULT_IMPORT_STATISTICS):
            try:
                await self._async_import_statistics(data)
            except Exception:  # noqa: BLE001 - statistics are a bonus, never fail the update
                _LOGGER.exception("Could not import Energa statistics")
        return data

    async def _async_import_statistics(self, data: MeterData) -> None:
        """Store each reading as an hourly statistic in the hour before the reading.

        Energa's reading at 00:00 closes the previous day, but it arrives hours
        later. The entity's own statistics would book it on the day it arrived;
        these external statistics book it on the right day, so use them in the
        Energy dashboard.
        """
        for reg in data.registers.values():
            stat_id = statistic_id(self.config_entry, reg.key)
            start = dt_util.as_utc(local_read_time(reg).replace(minute=0, second=0)) - timedelta(hours=1)
            last = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics, self.hass, 1, stat_id, True, {"state", "sum"}
            )
            rows = last.get(stat_id) or []
            if rows:
                prev = rows[0]
                if prev["start"] >= start.timestamp():
                    continue
                delta = reg.value - float(prev.get("state") or 0)
                # A negative delta means a new meter: continue the sum from its reading.
                new_sum = float(prev.get("sum") or 0) + max(delta, 0.0)
            else:
                new_sum = 0.0
            name = f"Energa {'pobór' if reg.direction == '+' else 'oddanie'}"
            if reg.zone is not None:
                name += f" strefa {reg.zone}"
            async_add_external_statistics(
                self.hass,
                _metadata(stat_id, name),
                [StatisticData(start=start, state=reg.value, sum=new_sum)],
            )

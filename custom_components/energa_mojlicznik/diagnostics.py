"""Diagnostics for Energa Mój Licznik."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import EnergaConfigEntry

TO_REDACT = {CONF_USERNAME, CONF_PASSWORD, "ppe", "ppe_address", "unique_id", "title"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: EnergaConfigEntry) -> dict[str, Any]:
    """Return redacted diagnostics."""
    data = entry.runtime_data.data
    return async_redact_data(
        {
            "entry": entry.as_dict(),
            "web_version": data.web_version,
            "supplier": data.supplier,
            "registers": {key: asdict(reg) for key, reg in data.registers.items()},
        },
        TO_REDACT,
    )

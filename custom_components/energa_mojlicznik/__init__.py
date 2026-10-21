"""Energa Mój Licznik integration: daily meter readings from mojlicznik.energa-operator.pl."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import EnergaConfigEntry, EnergaCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: EnergaConfigEntry) -> bool:
    """Set up from a config entry."""
    coordinator = EnergaCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EnergaConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: EnergaConfigEntry) -> None:
    """Reload after the options change."""
    await hass.config_entries.async_reload(entry.entry_id)

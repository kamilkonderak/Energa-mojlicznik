"""Sensors for Energa Mój Licznik."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONFIGURATION_URL, DOMAIN
from .coordinator import EnergaConfigEntry, EnergaCoordinator, local_read_time

# Register keys with a translated name; others (e.g. a third zone) use the page label.
TRANSLATED_KEYS = {
    "pobor",
    "pobor_strefa_1",
    "pobor_strefa_2",
    "pobor_razem",
    "oddanie",
    "oddanie_strefa_1",
    "oddanie_strefa_2",
    "oddanie_razem",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnergaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one sensor per register found on the first refresh."""
    coordinator = entry.runtime_data
    registers = coordinator.data.registers
    entities: list[SensorEntity] = [EnergaRegisterSensor(coordinator, key) for key in sorted(registers)]
    for direction, base in (("+", "pobor"), ("-", "oddanie")):
        if len([r for r in registers.values() if r.direction == direction and r.zone is not None]) > 1:
            entities.append(EnergaTotalSensor(coordinator, direction, f"{base}_razem"))
    entities += [EnergaReadingTimeSensor(coordinator), EnergaTariffSensor(coordinator)]
    async_add_entities(entities)


class EnergaEntity(CoordinatorEntity[EnergaCoordinator]):
    """Common device and naming."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EnergaCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        supplier = coordinator.data.supplier
        base_id = entry.unique_id or entry.entry_id
        self._key = key
        self._attr_unique_id = f"{base_id}_{key}"
        # Fixed, language-independent entity ids so dashboards can rely on them.
        # A second meter gets the usual _2 suffix from Home Assistant.
        self.entity_id = f"sensor.energa_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, base_id)},
            name="Licznik Energa",
            manufacturer="Energa-Operator",
            model=f"Taryfa {supplier['tariff']}" if supplier.get("tariff") else None,
            serial_number=supplier.get("ppe"),
            configuration_url=CONFIGURATION_URL,
        )


class EnergaRegisterSensor(EnergaEntity, SensorEntity):
    """A meter register (kWh, only ever grows)."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: EnergaCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        register = coordinator.data.registers[key]
        if key in TRANSLATED_KEYS:
            self._attr_translation_key = key
        else:
            self._attr_name = register.label
        self._attr_icon = (
            "mdi:transmission-tower-import" if register.direction == "+" else "mdi:transmission-tower-export"
        )

    @property
    def available(self) -> bool:
        return super().available and self._key in self.coordinator.data.registers

    @property
    def native_value(self) -> float | None:
        register = self.coordinator.data.registers.get(self._key)
        return register.value if register else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        register = self.coordinator.data.registers.get(self._key)
        if register is None:
            return None
        return {
            "odczyt": local_read_time(register).isoformat(),
            "strefa": register.zone,
            "nazwa_strefy": register.zone_name,
            "etykieta": register.label,
        }


class EnergaTotalSensor(EnergaEntity, SensorEntity):
    """Sum of all zones for one direction."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: EnergaCoordinator, direction: str, key: str) -> None:
        super().__init__(coordinator, key)
        self._direction = direction
        self._attr_translation_key = key
        self._attr_icon = "mdi:transmission-tower-import" if direction == "+" else "mdi:transmission-tower-export"

    @property
    def native_value(self) -> float | None:
        values = [r.value for r in self.coordinator.data.registers.values() if r.direction == self._direction]
        return round(sum(values), 4) if values else None


class EnergaReadingTimeSensor(EnergaEntity, SensorEntity):
    """When Energa took the latest reading (usually midnight)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "odczyt"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: EnergaCoordinator) -> None:
        super().__init__(coordinator, "odczyt")

    @property
    def native_value(self) -> datetime | None:
        registers = self.coordinator.data.registers.values()
        return max((local_read_time(r) for r in registers), default=None)


class EnergaTariffSensor(EnergaEntity, SensorEntity):
    """Tariff and contract details (the PPE address is deliberately not exposed)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "taryfa"
    _attr_icon = "mdi:file-document-outline"

    def __init__(self, coordinator: EnergaCoordinator) -> None:
        super().__init__(coordinator, "taryfa")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.supplier.get("tariff")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        s = self.coordinator.data.supplier
        return {
            "sprzedawca": s.get("supplier"),
            "umowa_od": s.get("contract_period_from"),
            "typ_odbiorcy": s.get("customer_type"),
            "wersja_strony": self.coordinator.data.web_version,
        }

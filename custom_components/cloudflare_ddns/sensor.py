from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_RECORD_NAME, CONF_UPDATE_IPV4, CONF_UPDATE_IPV6
from .coordinator import CloudflareDDNSCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: CloudflareDDNSCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    if entry.data.get(CONF_UPDATE_IPV4):
        entities.append(CloudflareIPSensor(coordinator, entry, "ipv4", "IPv4"))
    if entry.data.get(CONF_UPDATE_IPV6):
        entities.append(CloudflareIPSensor(coordinator, entry, "ipv6", "IPv6"))

    entities.append(CloudflareLastUpdatedSensor(coordinator, entry))
    async_add_entities(entities)


class CloudflareIPSensor(CoordinatorEntity, SensorEntity):
    _attr_icon = "mdi:ip-network"

    def __init__(self, coordinator, entry, key: str, label: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._key = key
        record = entry.data[CONF_RECORD_NAME]
        self._attr_name = f"{record} {label}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get(self._key)


class CloudflareLastUpdatedSensor(CoordinatorEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        record = entry.data[CONF_RECORD_NAME]
        self._attr_name = f"{record} Last Updated"
        self._attr_unique_id = f"{entry.entry_id}_last_updated"

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("last_updated")

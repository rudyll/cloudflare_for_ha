from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_RECORD_NAME
from .coordinator import CloudflareDDNSCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: CloudflareDDNSCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CloudflareForceUpdateButton(coordinator, entry)])


class CloudflareForceUpdateButton(CoordinatorEntity, ButtonEntity):
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: CloudflareDDNSCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        record = entry.data[CONF_RECORD_NAME]
        self._attr_name = f"{record} Force Update"
        self._attr_unique_id = f"{entry.entry_id}_force_update"

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()

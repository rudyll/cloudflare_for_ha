from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    CONF_API_TOKEN,
    CONF_ZONE_ID,
    CONF_RECORD_NAME,
    CONF_UPDATE_IPV4,
    CONF_UPDATE_IPV6,
    CF_BASE,
    IPV4_URL,
    IPV6_URL,
    UPDATE_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)


class CloudflareDDNSCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )
        self._entry = entry

    @property
    def _token(self) -> str:
        return self._entry.data[CONF_API_TOKEN]

    @property
    def _zone_id(self) -> str:
        return self._entry.data[CONF_ZONE_ID]

    @property
    def _record_name(self) -> str:
        return self._entry.data[CONF_RECORD_NAME]

    def _cf_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    async def _async_update_data(self) -> dict:
        session = async_get_clientsession(self.hass)
        data = self.data or {}
        last_updated = data.get("last_updated")

        ipv4: str | None = None
        ipv6: str | None = None

        if self._entry.data.get(CONF_UPDATE_IPV4):
            ipv4 = await self._detect_ip(session, IPV4_URL, "IPv4")

        if self._entry.data.get(CONF_UPDATE_IPV6):
            ipv6 = await self._detect_ip(session, IPV6_URL, "IPv6")

        changed = False
        if ipv4:
            changed = await self._sync_record(session, "A", ipv4) or changed
        if ipv6:
            changed = await self._sync_record(session, "AAAA", ipv6) or changed

        if changed:
            last_updated = datetime.now().astimezone()

        return {"ipv4": ipv4, "ipv6": ipv6, "last_updated": last_updated}

    async def _detect_ip(self, session, url: str, label: str) -> str | None:
        try:
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"Failed to detect {label}: HTTP {resp.status}")
                body = await resp.json()
                return body.get("ip")
        except Exception as err:
            raise UpdateFailed(f"Error detecting {label}: {err}") from err

    async def _sync_record(self, session, record_type: str, ip: str) -> bool:
        """Update or create the DNS record. Returns True if a change was made."""
        list_url = (
            f"{CF_BASE}/zones/{self._zone_id}/dns_records"
            f"?type={record_type}&name={self._record_name}"
        )
        try:
            async with session.get(list_url, headers=self._cf_headers()) as resp:
                body = await resp.json()
        except Exception as err:
            raise UpdateFailed(f"Cloudflare list {record_type} failed: {err}") from err

        records = body.get("result", [])

        if not records:
            return await self._create_record(session, record_type, ip)

        record = records[0]
        if record["content"] == ip:
            return False

        return await self._update_record(session, record["id"], record_type, ip)

    async def _create_record(self, session, record_type: str, ip: str) -> bool:
        url = f"{CF_BASE}/zones/{self._zone_id}/dns_records"
        payload = {
            "type": record_type,
            "name": self._record_name,
            "content": ip,
            "ttl": 1,
            "proxied": False,
        }
        try:
            async with session.post(url, headers=self._cf_headers(), json=payload) as resp:
                body = await resp.json()
                if not body.get("success"):
                    raise UpdateFailed(f"Cloudflare create {record_type} failed: {body.get('errors')}")
        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Cloudflare create {record_type} error: {err}") from err
        _LOGGER.info("Created %s record %s → %s", record_type, self._record_name, ip)
        return True

    async def _update_record(self, session, record_id: str, record_type: str, ip: str) -> bool:
        url = f"{CF_BASE}/zones/{self._zone_id}/dns_records/{record_id}"
        payload = {
            "type": record_type,
            "name": self._record_name,
            "content": ip,
            "ttl": 1,
            "proxied": False,
        }
        try:
            async with session.patch(url, headers=self._cf_headers(), json=payload) as resp:
                body = await resp.json()
                if not body.get("success"):
                    raise UpdateFailed(f"Cloudflare update {record_type} failed: {body.get('errors')}")
        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Cloudflare update {record_type} error: {err}") from err
        _LOGGER.info("Updated %s record %s → %s", record_type, self._record_name, ip)
        return True

from __future__ import annotations

import ipaddress
import logging
import re
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
    IPV4_SOURCES,
    IPV6_SOURCES,
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
            ipv4 = await self._detect_ip_with_fallback(session, IPV4_SOURCES, 4)

        if self._entry.data.get(CONF_UPDATE_IPV6):
            ipv6 = _get_local_stable_ipv6()
            if ipv6 is None:
                ipv6 = await self._detect_ip_with_fallback(session, IPV6_SOURCES, 6)
            else:
                _LOGGER.debug("IPv6 detected from local interface: %s", ipv6)

        changed = False
        if ipv4:
            changed = await self._sync_record(session, "A", ipv4) or changed
        if ipv6:
            changed = await self._sync_record(session, "AAAA", ipv6) or changed

        if changed:
            last_updated = datetime.now().astimezone()

        return {"ipv4": ipv4, "ipv6": ipv6, "last_updated": last_updated}

    async def _detect_ip_with_fallback(self, session, sources: list[str], version: int) -> str | None:
        """Try each source in order; return the first valid IP of the given version."""
        label = f"IPv{version}"
        for url in sources:
            try:
                async with session.get(url, timeout=8) as resp:
                    if resp.status != 200:
                        _LOGGER.debug("%s: %s returned HTTP %s, trying next", label, url, resp.status)
                        continue
                    text = await resp.text()
                ip = self._extract_ip(text, version)
                if ip:
                    _LOGGER.debug("%s detected via %s: %s", label, url, ip)
                    return ip
                _LOGGER.debug("%s: no valid IP in response from %s", label, url)
            except Exception as err:
                _LOGGER.debug("%s: %s failed (%s), trying next", label, url, err)
        raise UpdateFailed(f"All {label} sources failed: {sources}")

    @staticmethod
    def _extract_ip(text: str, version: int) -> str | None:
        """Extract the first valid IPv4 or IPv6 address from arbitrary response text."""
        # Try JSON {"ip": "..."} first
        try:
            import json
            data = json.loads(text)
            candidate = data.get("ip") or data.get("address") or data.get("query")
            if candidate:
                return _validate_ip(candidate, version)
        except (ValueError, AttributeError):
            pass

        # Fall back to regex scan
        if version == 4:
            pattern = r'\b(\d{1,3}(?:\.\d{1,3}){3})\b'
        else:
            pattern = r'([0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{0,4}){2,7})'

        for match in re.finditer(pattern, text):
            result = _validate_ip(match.group(1), version)
            if result:
                return result
        return None

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


def _get_local_stable_ipv6() -> str | None:
    """Read the first stable (non-temporary) global IPv6 from /proc/net/if_inet6.

    Temporary privacy-extension addresses (IFA_F_TEMPORARY = 0x01) are used for
    outbound connections, so external IP-detection services return them. For DDNS
    we want the stable EUI-64 address that accepts inbound connections.
    """
    try:
        with open("/proc/net/if_inet6") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 6:
                    continue
                addr_hex, _idx, _prefix, scope_hex, flags_hex, _iface = parts
                if int(scope_hex, 16) != 0:        # must be global scope
                    continue
                if int(flags_hex, 16) & 0x01:      # skip IFA_F_TEMPORARY
                    continue
                addr = ipaddress.IPv6Address(int(addr_hex, 16))
                if not addr.is_private and not addr.is_loopback and not addr.is_link_local:
                    return str(addr)
    except OSError:
        pass
    return None


def _validate_ip(candidate: str, version: int) -> str | None:
    try:
        addr = ipaddress.ip_address(candidate.strip())
        if addr.version == version and not addr.is_private and not addr.is_loopback:
            return str(addr)
    except ValueError:
        pass
    return None

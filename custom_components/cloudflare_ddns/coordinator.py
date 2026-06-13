from __future__ import annotations

import asyncio
import ipaddress
import json
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
    CONF_CUSTOM_IPV4_URLS,
    CONF_CUSTOM_IPV6_URLS,
    CONF_TARGET_MAC,
    CONF_TARGET_IPV6,
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

    @property
    def _target_mac(self) -> str:
        return self._entry.data.get(CONF_TARGET_MAC, "").strip()

    @property
    def _target_ipv6(self) -> str:
        return self._entry.data.get(CONF_TARGET_IPV6, "").strip()

    def _ipv4_sources(self) -> list[str]:
        raw = self._entry.options.get(CONF_CUSTOM_IPV4_URLS, "").strip()
        if raw:
            return [u.strip() for u in raw.split(",") if u.strip()]
        return IPV4_SOURCES

    def _ipv6_sources(self) -> list[str]:
        raw = self._entry.options.get(CONF_CUSTOM_IPV6_URLS, "").strip()
        if raw:
            return [u.strip() for u in raw.split(",") if u.strip()]
        return IPV6_SOURCES

    def _cf_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    async def _async_update_data(self) -> dict:
        session = async_get_clientsession(self.hass)
        data = self.data or {}
        last_updated = data.get("last_updated")

        ipv4: str | None = None
        ipv6: str | None = None

        if self._entry.data.get(CONF_UPDATE_IPV4):
            ipv4 = await self._detect_ip_with_fallback(session, self._ipv4_sources(), 4)

        if self._entry.data.get(CONF_UPDATE_IPV6):
            ipv6 = await self._detect_ipv6()

        changed = False
        if ipv4:
            changed = await self._sync_record(session, "A", ipv4) or changed
        if ipv6:
            changed = await self._sync_record(session, "AAAA", ipv6) or changed

        if changed:
            last_updated = datetime.now().astimezone()

        return {"ipv4": ipv4, "ipv6": ipv6, "last_updated": last_updated}

    async def _detect_ipv6(self) -> str | None:
        # 1. Manually fixed address — most reliable, works for any device/OS
        manual = self._target_ipv6
        if manual:
            _LOGGER.debug("IPv6 using fixed address from config: %s", manual)
            return manual

        # 2. Another LAN device, resolved from its MAC (EUI-64 devices only)
        mac = self._target_mac
        if mac:
            ipv6 = await _get_ipv6_from_neigh_cache(mac)
            if ipv6:
                _LOGGER.debug("IPv6 for %s found in neighbour cache: %s", mac, ipv6)
                return ipv6
            ipv6 = _calculate_eui64_address(mac)
            if ipv6:
                _LOGGER.debug("IPv6 for %s calculated via EUI-64: %s", mac, ipv6)
                return ipv6
            _LOGGER.warning(
                "Could not determine IPv6 for MAC %s — not in neighbour cache and "
                "EUI-64 prefix unavailable. Modern devices (phones, Macs, Windows) "
                "use RFC 7217 addresses that cannot be derived from the MAC; set a "
                "fixed Target IPv6 address for those.",
                mac,
            )
            return None

        # 3. This machine (HA host)
        ipv6 = _get_local_stable_ipv6()
        if ipv6:
            _LOGGER.debug("IPv6 detected from local interface: %s", ipv6)
            return ipv6
        return await self._detect_ip_with_fallback(
            async_get_clientsession(self.hass), self._ipv6_sources(), 6
        )

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
                ip = _extract_ip(text, version)
                if ip:
                    _LOGGER.debug("%s detected via %s: %s", label, url, ip)
                    return ip
                _LOGGER.debug("%s: no valid IP in response from %s", label, url)
            except Exception as err:
                _LOGGER.debug("%s: %s failed (%s), trying next", label, url, err)
        raise UpdateFailed(f"All {label} sources failed: {sources}")

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


# ---------------------------------------------------------------------------
# IPv6 helpers
# ---------------------------------------------------------------------------

def _get_local_stable_ipv6() -> str | None:
    """Read the first stable (non-temporary) global IPv6 from /proc/net/if_inet6."""
    try:
        with open("/proc/net/if_inet6") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 6:
                    continue
                addr_hex, _idx, _prefix, scope_hex, flags_hex, _iface = parts
                if int(scope_hex, 16) != 0:    # global scope only
                    continue
                if int(flags_hex, 16) & 0x01:  # skip IFA_F_TEMPORARY
                    continue
                addr = ipaddress.IPv6Address(int(addr_hex, 16))
                if not addr.is_private and not addr.is_loopback and not addr.is_link_local:
                    return str(addr)
    except OSError:
        pass
    return None


async def _get_ipv6_from_neigh_cache(mac: str) -> str | None:
    """Look up a device's global IPv6 in the NDP neighbour cache by MAC address.

    Runs `ip -6 neigh show` and returns the first non-link-local address
    whose lladdr matches *mac* (case-insensitive, colon-normalised).

    A device may have several global addresses (stable + temporary privacy).
    The neighbour table carries no temporary/stable flag, so when more than one
    is present we prefer the address whose lower 64 bits match the EUI-64 ID
    derived from the MAC — that one is provably the stable address. This only
    helps EUI-64 devices; for RFC 7217 devices both addresses are opaque and we
    fall back to the first match (which may be a rotating temporary address).
    """
    normalised_mac = mac.lower().replace("-", ":")
    try:
        proc = await asyncio.create_subprocess_exec(
            "ip", "-6", "neigh", "show",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
    except Exception as err:
        _LOGGER.debug("ip -6 neigh show failed: %s", err)
        return None

    candidates: list[str] = []
    for line in stdout.decode().splitlines():
        # format: <ipv6> dev <iface> lladdr <mac> [router] <state>
        parts = line.lower().split()
        if normalised_mac not in parts:
            continue
        candidate = _validate_ip(parts[0], 6)
        if candidate:
            candidates.append(candidate)

    if not candidates:
        return None

    suffix = _eui64_suffix(mac)
    if suffix:
        for candidate in candidates:
            if _matches_eui64_suffix(candidate, suffix):
                return candidate
    return candidates[0]


def _matches_eui64_suffix(addr_str: str, suffix: str) -> bool:
    """Whether the lower 64 bits of *addr_str* equal the EUI-64 *suffix*."""
    groups = ipaddress.IPv6Address(addr_str).exploded.lower().split(":")
    return ":".join(groups[4:]) == suffix.lower()


def _calculate_eui64_address(mac: str) -> str | None:
    """Derive a device's stable global IPv6 from its MAC using EUI-64.

    Takes the /64 prefix from this host's own stable global address and
    combines it with the EUI-64 interface identifier computed from *mac*.
    Requires that both devices share the same /64 prefix.
    """
    prefix = _get_local_prefix64()
    if not prefix:
        return None
    suffix = _eui64_suffix(mac)
    if not suffix:
        return None
    try:
        return str(ipaddress.IPv6Address(f"{prefix}:{suffix}"))
    except ValueError:
        return None


def _get_local_prefix64() -> str | None:
    """Return the first 64-bit prefix of this host's stable global IPv6."""
    addr_str = _get_local_stable_ipv6()
    if not addr_str:
        return None
    groups = ipaddress.IPv6Address(addr_str).exploded.split(":")
    return ":".join(groups[:4])


def _eui64_suffix(mac: str) -> str | None:
    """Convert a MAC address to an EUI-64 interface identifier (4 hex groups)."""
    try:
        parts = mac.lower().replace("-", ":").split(":")
        if len(parts) != 6:
            return None
        b = [int(x, 16) for x in parts]
        b[0] ^= 0x02                    # flip universal/local bit
        b = b[:3] + [0xFF, 0xFE] + b[3:]  # insert ff:fe
        return f"{b[0]:02x}{b[1]:02x}:{b[2]:02x}{b[3]:02x}:{b[4]:02x}{b[5]:02x}:{b[6]:02x}{b[7]:02x}"
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Generic IP helpers
# ---------------------------------------------------------------------------

def _extract_ip(text: str, version: int) -> str | None:
    """Extract the first valid public IP of *version* from arbitrary response text."""
    try:
        data = json.loads(text)
        candidate = data.get("ip") or data.get("address") or data.get("query")
        if candidate:
            return _validate_ip(candidate, version)
    except (ValueError, AttributeError):
        pass

    pattern = (
        r'\b(\d{1,3}(?:\.\d{1,3}){3})\b'
        if version == 4
        else r'([0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{0,4}){2,7})'
    )
    for match in re.finditer(pattern, text):
        result = _validate_ip(match.group(1), version)
        if result:
            return result
    return None


def _validate_ip(candidate: str, version: int) -> str | None:
    try:
        addr = ipaddress.ip_address(candidate.strip())
        if addr.version == version and not addr.is_private and not addr.is_loopback:
            return str(addr)
    except ValueError:
        pass
    return None

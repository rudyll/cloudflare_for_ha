from __future__ import annotations

import re

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_API_TOKEN,
    CONF_ZONE_NAME,
    CONF_ZONE_ID,
    CONF_RECORD_NAME,
    CONF_UPDATE_IPV4,
    CONF_UPDATE_IPV6,
    CONF_CUSTOM_IPV4_URLS,
    CONF_CUSTOM_IPV6_URLS,
    CONF_TARGET_MAC,
    CF_BASE,
)

_MAC_RE = re.compile(r'^([0-9a-fA-F]{2}[:\-]){5}[0-9a-fA-F]{2}$')


class CloudflareDDNSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return CloudflareDDNSOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        errors: dict = {}

        if user_input is not None:
            token = user_input[CONF_API_TOKEN].strip()
            zone_name = user_input[CONF_ZONE_NAME].strip().lower()
            record_name = user_input[CONF_RECORD_NAME].strip().lower()
            target_mac = user_input.get(CONF_TARGET_MAC, "").strip()

            if target_mac and not _MAC_RE.match(target_mac):
                errors[CONF_TARGET_MAC] = "invalid_mac"
            else:
                zone_id, error = await self._validate_token_and_zone(token, zone_name)
                if error:
                    errors["base"] = error
                else:
                    # Prevent duplicate entries for the same DNS record
                    await self.async_set_unique_id(record_name)
                    self._abort_if_unique_id_configured()

                    self._data = {
                        CONF_API_TOKEN: token,
                        CONF_ZONE_NAME: zone_name,
                        CONF_ZONE_ID: zone_id,
                        CONF_RECORD_NAME: record_name,
                        CONF_TARGET_MAC: target_mac,
                    }
                    return await self.async_step_record_type()

        schema = vol.Schema(
            {
                vol.Required(CONF_API_TOKEN): str,
                vol.Required(CONF_ZONE_NAME): str,
                vol.Required(CONF_RECORD_NAME): str,
                vol.Optional(CONF_TARGET_MAC, default=""): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_record_type(self, user_input=None):
        errors: dict = {}

        if user_input is not None:
            update_ipv4 = user_input.get(CONF_UPDATE_IPV4, False)
            update_ipv6 = user_input.get(CONF_UPDATE_IPV6, False)

            if not update_ipv4 and not update_ipv6:
                errors["base"] = "select_at_least_one"
            else:
                self._data[CONF_UPDATE_IPV4] = update_ipv4
                self._data[CONF_UPDATE_IPV6] = update_ipv6
                title = self._data[CONF_RECORD_NAME]
                return self.async_create_entry(title=title, data=self._data)

        schema = vol.Schema(
            {
                vol.Optional(CONF_UPDATE_IPV4, default=True): bool,
                vol.Optional(CONF_UPDATE_IPV6, default=True): bool,
            }
        )
        return self.async_show_form(
            step_id="record_type", data_schema=schema, errors=errors
        )

    async def _validate_token_and_zone(
        self, token: str, zone_name: str
    ) -> tuple[str | None, str | None]:
        session = async_get_clientsession(self.hass)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            async with session.get(
                f"{CF_BASE}/zones?name={zone_name}", headers=headers, timeout=10
            ) as resp:
                if resp.status == 403:
                    return None, "invalid_token"
                body = await resp.json()
        except Exception:
            return None, "cannot_connect"

        if not body.get("success"):
            return None, "invalid_token"

        results = body.get("result", [])
        if not results:
            return None, "zone_not_found"

        return results[0]["id"], None


class CloudflareDDNSOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self._entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_CUSTOM_IPV4_URLS,
                    default=current.get(CONF_CUSTOM_IPV4_URLS, ""),
                ): str,
                vol.Optional(
                    CONF_CUSTOM_IPV6_URLS,
                    default=current.get(CONF_CUSTOM_IPV6_URLS, ""),
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

"""高德天气 config flow"""
from __future__ import annotations

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
import homeassistant.helpers.config_validation as cv

from . import DOMAIN

CONF_ADCODE = "adcode"
CONF_LOCATION_MODE = "location_mode"

MODE_HA = "ha_location"
MODE_IP = "ip_location"
MODE_MANUAL = "manual"

AMAP_BASE = "https://restapi.amap.com/v3"


async def _get_adcode_from_latlng(session, api_key, lat, lng) -> tuple[str, str] | None:
    url = f"{AMAP_BASE}/geocode/regeo?key={api_key}&location={lng},{lat}&extensions=base"
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
        data = await r.json(content_type=None)
    if data.get("status") != "1":
        return None
    info = data["regeocode"]["addressComponent"]
    adcode = info.get("adcode") or info.get("citycode")
    city = info.get("city") or info.get("province", "")
    if isinstance(city, list):
        city = info.get("province", "")
    return adcode, city


async def _get_adcode_from_ip(session, api_key) -> tuple[str, str] | None:
    url = f"{AMAP_BASE}/ip?key={api_key}"
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
        data = await r.json(content_type=None)
    if data.get("status") != "1":
        return None
    adcode = data.get("adcode")
    city = data.get("city", "")
    return adcode, city


async def _search_city(session, api_key, city_name) -> list[dict]:
    url = f"{AMAP_BASE}/geocode/geo?key={api_key}&address={city_name}&city="
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
        data = await r.json(content_type=None)
    if data.get("status") != "1" or not data.get("geocodes"):
        return []
    return [
        {"adcode": g["adcode"], "label": g["formatted_address"]}
        for g in data["geocodes"][:5]
    ]


class AmapWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._api_key = None
        self._candidates = []

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            self._api_key = user_input[CONF_API_KEY]
            mode = user_input[CONF_LOCATION_MODE]
            try:
                async with aiohttp.ClientSession() as session:
                    if mode == MODE_HA:
                        result = await _get_adcode_from_latlng(
                            session, self._api_key,
                            self.hass.config.latitude,
                            self.hass.config.longitude,
                        )
                        if result:
                            adcode, city = result
                            return self.async_create_entry(
                                title=f"高德天气·{city}",
                                data={CONF_API_KEY: self._api_key, CONF_ADCODE: adcode},
                            )
                        errors["base"] = "cannot_connect"

                    elif mode == MODE_IP:
                        result = await _get_adcode_from_ip(session, self._api_key)
                        if result:
                            adcode, city = result
                            return self.async_create_entry(
                                title=f"高德天气·{city}",
                                data={CONF_API_KEY: self._api_key, CONF_ADCODE: adcode},
                            )
                        errors["base"] = "cannot_connect"

                    elif mode == MODE_MANUAL:
                        return await self.async_step_search()

            except Exception:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY): cv.string,
                vol.Required(CONF_LOCATION_MODE, default=MODE_HA): vol.In({
                    MODE_HA: "使用 HA 配置的位置",
                    MODE_IP: "根据 IP 自动判断",
                    MODE_MANUAL: "手动搜索城市",
                }),
            }),
            errors=errors,
        )

    async def async_step_search(self, user_input=None):
        errors = {}
        if user_input is not None:
            if "adcode" in user_input:
                # 用户从候选列表选择
                adcode = user_input["adcode"]
                label = next((c["label"] for c in self._candidates if c["adcode"] == adcode), adcode)
                return self.async_create_entry(
                    title=f"高德天气·{label[:10]}",
                    data={CONF_API_KEY: self._api_key, CONF_ADCODE: adcode},
                )
            # 用户输入城市名搜索
            city_name = user_input.get("city_name", "")
            try:
                async with aiohttp.ClientSession() as session:
                    self._candidates = await _search_city(session, self._api_key, city_name)
                if self._candidates:
                    return self.async_show_form(
                        step_id="search",
                        data_schema=vol.Schema({
                            vol.Required("adcode"): vol.In({
                                c["adcode"]: c["label"] for c in self._candidates
                            }),
                        }),
                    )
                errors["base"] = "no_results"
            except Exception:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="search",
            data_schema=vol.Schema({
                vol.Required("city_name"): cv.string,
            }),
            errors=errors,
        )

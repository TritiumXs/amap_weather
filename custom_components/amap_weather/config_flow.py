"""高德天气 config flow"""
import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
import homeassistant.helpers.config_validation as cv

from . import DOMAIN

CONF_ADCODE = "adcode"

STEP_SCHEMA = vol.Schema({
    vol.Required(CONF_API_KEY): cv.string,
    vol.Required(CONF_ADCODE): cv.string,
    vol.Optional("name", default="高德天气"): cv.string,
})


class AmapWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # 验证 key 和 adcode 是否有效
            try:
                url = (
                    "https://restapi.amap.com/v3/weather/weatherInfo"
                    f"?key={user_input[CONF_API_KEY]}&city={user_input[CONF_ADCODE]}&extensions=base"
                )
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        data = await resp.json()
                if data.get("status") != "1":
                    errors["base"] = "invalid_auth"
                else:
                    return self.async_create_entry(title=user_input["name"], data=user_input)
            except Exception:
                errors["base"] = "cannot_connect"

        return self.async_show_form(step_id="user", data_schema=STEP_SCHEMA, errors=errors)

"""高德天气 WeatherEntity — 对齐 met.no 接口"""
from __future__ import annotations

import aiohttp
import logging
from datetime import timedelta

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_API_KEY,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from . import DOMAIN
from .config_flow import CONF_ADCODE

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(minutes=30)

# 高德天气现象 → HA condition 映射
CONDITION_MAP = {
    "晴": "sunny",
    "少云": "partlycloudy",
    "晴间多云": "partlycloudy",
    "多云": "cloudy",
    "阴": "cloudy",
    "有风": "windy",
    "平静": "sunny",
    "微风": "sunny",
    "和风": "windy",
    "清风": "windy",
    "强风": "windy-variant",
    "疾风": "windy-variant",
    "大风": "exceptional",
    "烈风": "exceptional",
    "风暴": "exceptional",
    "狂爆风": "exceptional",
    "飓风": "exceptional",
    "热带风暴": "exceptional",
    "阵雨": "rainy",
    "雷阵雨": "lightning-rainy",
    "雷阵雨并伴有冰雹": "hail",
    "小雨": "rainy",
    "中雨": "rainy",
    "大雨": "pouring",
    "暴雨": "pouring",
    "大暴雨": "pouring",
    "特大暴雨": "exceptional",
    "强阵雨": "pouring",
    "强雷阵雨": "lightning-rainy",
    "极端降雨": "exceptional",
    "毛毛雨": "rainy",
    "雨": "rainy",
    "小雪": "snowy",
    "中雪": "snowy",
    "大雪": "snowy",
    "暴雪": "snowy",
    "雨夹雪": "snowy-rainy",
    "雪": "snowy",
    "冻雨": "snowy-rainy",
    "雨雪天气": "snowy-rainy",
    "阵雪": "snowy",
    "霾": "fog",
    "中度霾": "fog",
    "重度霾": "fog",
    "严重霾": "fog",
    "雾": "fog",
    "浓雾": "fog",
    "强浓雾": "fog",
    "轻雾": "fog",
    "大雾": "fog",
    "特强浓雾": "fog",
    "扬沙": "exceptional",
    "浮尘": "exceptional",
    "沙尘暴": "exceptional",
    "强沙尘暴": "exceptional",
    "龙卷风": "exceptional",
    "热": "sunny",
    "冷": "clear-night",
    "未知": "exceptional",
}


def _map_condition(weather_str: str) -> str:
    for key, val in CONDITION_MAP.items():
        if key in weather_str:
            return val
    return "exceptional"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    api_key = entry.data[CONF_API_KEY]
    adcode = entry.data[CONF_ADCODE]

    async def _fetch():
        try:
            async with aiohttp.ClientSession() as session:
                base_url = (
                    f"https://restapi.amap.com/v3/weather/weatherInfo"
                    f"?key={api_key}&city={adcode}"
                )
                async with session.get(base_url + "&extensions=base", timeout=aiohttp.ClientTimeout(total=10)) as r:
                    live = await r.json()
                async with session.get(base_url + "&extensions=all", timeout=aiohttp.ClientTimeout(total=10)) as r:
                    forecast = await r.json()
            if live.get("status") != "1" or forecast.get("status") != "1":
                raise UpdateFailed("高德 API 返回错误")
            return {"live": live["lives"][0], "forecast": forecast["forecasts"][0]}
        except UpdateFailed:
            raise
        except Exception as e:
            raise UpdateFailed(f"请求失败: {e}") from e

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="amap_weather",
        update_method=_fetch,
        update_interval=SCAN_INTERVAL,
    )
    await coordinator.async_config_entry_first_refresh()
    async_add_entities([AmapWeatherEntity(coordinator, entry)])


class AmapWeatherEntity(CoordinatorEntity, WeatherEntity):
    _attr_attribution = "数据来源：高德天气"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_supported_features = WeatherEntityFeature.FORECAST_DAILY

    def __init__(self, coordinator: DataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = entry.data.get("name", "高德天气")
        self._attr_unique_id = f"amap_weather_{entry.data[CONF_ADCODE]}"

    @property
    def _live(self):
        return self.coordinator.data["live"]

    @property
    def _casts(self):
        return self.coordinator.data["forecast"]["casts"]

    @property
    def condition(self) -> str:
        return _map_condition(self._live.get("weather", ""))

    @property
    def native_temperature(self) -> float | None:
        try:
            return float(self._live["temperature"])
        except (KeyError, ValueError):
            return None

    @property
    def humidity(self) -> float | None:
        try:
            return float(self._live["humidity"])
        except (KeyError, ValueError):
            return None

    @property
    def wind_bearing(self) -> str | None:
        return self._live.get("winddirection")

    @property
    def native_wind_speed(self) -> float | None:
        # 高德风力是级别(1-12)，转换为近似 km/h（蒲福风级中位值）
        _beaufort_to_kmh = [1, 5, 12, 20, 29, 39, 50, 62, 75, 89, 103, 118, 134]
        try:
            level = int(self._live["windpower"].replace("≤", "").strip())
            return float(_beaufort_to_kmh[min(level, 12)])
        except (KeyError, ValueError, IndexError):
            return None

    async def async_forecast_daily(self) -> list[Forecast] | None:
        forecasts = []
        for cast in self._casts:
            try:
                forecasts.append(Forecast(
                    datetime=cast["date"] + "T00:00:00",
                    condition=_map_condition(cast.get("dayweather", "")),
                    native_temperature=float(cast["daytemp"]),
                    native_templow=float(cast["nighttemp"]),
                    wind_bearing=cast.get("daywind"),
                ))
            except (KeyError, ValueError):
                continue
        return forecasts

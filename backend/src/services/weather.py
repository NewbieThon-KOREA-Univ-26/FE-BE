"""출발지 기준 현재 날씨 (F6).

키가 없거나 조회에 실패하면 None 을 돌려주고, 비교 결과는 날씨 없이 그대로 나갑니다.
날씨 때문에 경로 비교가 실패하는 일은 없어야 하기 때문입니다.
같은 1km 격자는 10분 동안 다시 묻지 않습니다 (무료 할당량 절약).
"""

import time

import httpx

from src.config.settings import Settings
from src.services.compare import WeatherInfo

CACHE_SECONDS = 600


class Weather:
    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client, self.settings = client, settings
        self._cache: dict[tuple[float, float], tuple[float, WeatherInfo | None]] = {}

    async def current(self, x: float, y: float) -> WeatherInfo | None:
        key = self.settings.weather_api_key.get_secret_value()
        if not key:
            return None
        cell = (round(y, 2), round(x, 2))
        cached = self._cache.get(cell)
        if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1]
        try:
            fetch = self.openweather if self.settings.weather_provider == 'openweather' else self.weatherapi
            info = await fetch(key, x, y)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
            # 키가 URL 에 실리므로 예외 문장은 어디에도 남기지 않습니다.
            info = None
        self._cache[cell] = (time.monotonic(), info)
        return info

    async def weatherapi(self, key: str, x: float, y: float) -> WeatherInfo:
        """WeatherAPI.com — 한국어 날씨 문구, 오늘 강수확률, 아이콘."""
        response = await self.client.get(
            'https://api.weatherapi.com/v1/forecast.json',
            params={'key': key, 'q': f'{y},{x}', 'days': 1, 'lang': 'ko', 'aqi': 'no', 'alerts': 'no'},
            timeout=self.settings.weather_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        current = data['current']
        condition = current.get('condition') or {}
        icon = condition.get('icon')
        if isinstance(icon, str) and icon.startswith('//'):
            icon = 'https:' + icon
        day = ((data.get('forecast') or {}).get('forecastday') or [{}])[0].get('day') or {}
        chance = day.get('daily_chance_of_rain')
        return WeatherInfo(
            condition=str(condition.get('text') or '알 수 없음').strip(),
            temperatureC=current.get('temp_c'),
            precipitationProbability=float(chance) if chance is not None else None,
            iconUrl=icon if isinstance(icon, str) else None,
        )

    async def openweather(self, key: str, x: float, y: float) -> WeatherInfo:
        """OpenWeatherMap — 3시간 예보의 첫 칸. 강수확률(pop)은 예보 API 에만 있습니다."""
        response = await self.client.get(
            'https://api.openweathermap.org/data/2.5/forecast',
            params={'lat': y, 'lon': x, 'appid': key, 'units': 'metric', 'lang': 'kr', 'cnt': 1},
            timeout=self.settings.weather_timeout_seconds,
        )
        response.raise_for_status()
        item = response.json()['list'][0]
        weather = (item.get('weather') or [{}])[0]
        icon = weather.get('icon')
        return WeatherInfo(
            condition=str(weather.get('description') or '알 수 없음').strip(),
            temperatureC=(item.get('main') or {}).get('temp'),
            precipitationProbability=round(float(item.get('pop', 0)) * 100),
            iconUrl=f'https://openweathermap.org/img/wn/{icon}@2x.png' if icon else None,
        )

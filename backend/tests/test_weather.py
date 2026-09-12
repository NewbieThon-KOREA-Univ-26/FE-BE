"""F6 날씨 — 조회·해석·추천 반영. 날씨는 실패해도 비교를 막지 않아야 합니다."""
import unittest

import httpx
from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.main import create_app
from src.services.compare import Transit, Walk, WeatherInfo, build_comparison, weather_penalty
from tests.test_kakao import PARAMS, transit_route, walk_route

WEATHERAPI_BODY = {
    'current': {'temp_c': 23.4, 'condition': {'text': '맑음', 'icon': '//cdn.weatherapi.com/weather/64x64/day/113.png'}},
    'forecast': {'forecastday': [{'day': {'daily_chance_of_rain': 10}}]},
}
OPENWEATHER_BODY = {'list': [{'main': {'temp': 18.2}, 'pop': 0.35,
                              'weather': [{'description': '실 비', 'icon': '10d'}]}]}


class WeatherServiceTests(unittest.TestCase):
    def setUp(self):
        self.weather_calls = []
        self.weather_body = WEATHERAPI_BODY
        self.weather_status = 200

    def handler(self, request):
        if request.url.host in ('api.weatherapi.com', 'api.openweathermap.org'):
            self.weather_calls.append(request)
            return httpx.Response(self.weather_status, json=self.weather_body)
        return httpx.Response(200, json=walk_route() if request.url.path.endswith(('/pedestrian', '/walk')) else transit_route())

    def client(self, **overrides):
        settings = Settings(**{'_env_file': None, 'route_provider': 'kakao', 'kakao_rest_api_key': 'k',
                               'weather_api_key': 'weather-secret', **overrides})
        return TestClient(create_app(settings, httpx.MockTransport(self.handler)))

    def test_weatherapi_is_parsed_and_attached(self):
        with self.client() as client:
            body = client.get('/api/compare', params=PARAMS).json()
        self.assertEqual(body['weather'], {'condition': '맑음', 'temperatureC': 23.4, 'precipitationProbability': 10,
                                           'iconUrl': 'https://cdn.weatherapi.com/weather/64x64/day/113.png'})
        self.assertNotIn('weatherReason', body['recommendation'])
        request = self.weather_calls[0]
        self.assertEqual(request.url.params['q'], f"{PARAMS['startY']},{PARAMS['startX']}")
        self.assertEqual(request.url.params['lang'], 'ko')

    def test_openweather_is_parsed(self):
        self.weather_body = OPENWEATHER_BODY
        with self.client(weather_provider='openweather') as client:
            body = client.get('/api/compare', params=PARAMS).json()
        self.assertEqual(body['weather']['condition'], '실 비')
        self.assertEqual(body['weather']['precipitationProbability'], 35)
        self.assertEqual(body['weather']['iconUrl'], 'https://openweathermap.org/img/wn/10d@2x.png')
        self.assertEqual(self.weather_calls[0].url.host, 'api.openweathermap.org')

    def test_no_key_means_no_weather_and_no_call(self):
        with self.client(weather_api_key='') as client:
            body = client.get('/api/compare', params=PARAMS).json()
        self.assertNotIn('weather', body)
        self.assertEqual(self.weather_calls, [])

    def test_weather_failure_never_breaks_compare(self):
        self.weather_status = 401
        with self.client() as client:
            response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('weather', response.json())
        self.assertNotIn('weather-secret', response.text)

    def test_same_cell_is_cached(self):
        with self.client() as client:
            client.get('/api/compare', params=PARAMS)
            client.get('/api/compare', params=PARAMS)
        self.assertEqual(len(self.weather_calls), 1)

    def test_rain_lowers_walk_threshold_and_explains(self):
        self.weather_body = {'current': {'temp_c': 20, 'condition': {'text': '가벼운 비'}},
                             'forecast': {'forecastday': [{'day': {'daily_chance_of_rain': 80}}]}}
        with self.client() as client:
            body = client.get('/api/compare', params=PARAMS).json()
        # 픽스처 도보는 16분·1180m: 평소 기준(30분·2000m)은 통과, 절반 기준(15분·1000m)은 초과 → 타기
        self.assertEqual(body['recommendation']['choice'], 'transit')
        self.assertEqual(body['recommendation']['weatherReason'], '지금 가벼운 비라 오늘은 타는 걸 권해요')
        self.assertIn('오늘 날씨에는 걷기를 권하지 않아요', body['recommendation']['reason'])


class WeatherRuleTests(unittest.TestCase):
    def build(self, weather, minutes=8, meters=600):
        walk = Walk(distance=meters, duration=minutes, paths=[])
        transit = Transit(duration=6, fare=1400, transfers=0, walkDistance=0, walkDuration=0, paths=[])
        return build_comparison(walk, transit, Settings(_env_file=None), weather)

    def test_penalty_reasons(self):
        self.assertIsNone(weather_penalty(None))
        self.assertIsNone(weather_penalty(WeatherInfo(condition='맑음', temperatureC=24, precipitationProbability=10)))
        self.assertEqual(weather_penalty(WeatherInfo(condition='흐림', precipitationProbability=60)), '강수확률 60%')
        self.assertEqual(weather_penalty(WeatherInfo(condition='맑음', temperatureC=31)), '31°C 더위')
        self.assertEqual(weather_penalty(WeatherInfo(condition='맑음', temperatureC=-6)), '-6°C 추위')
        self.assertEqual(weather_penalty(WeatherInfo(condition='눈')), '지금 눈')

    def test_short_walk_stays_recommended_in_rain(self):
        body = self.build(WeatherInfo(condition='비', temperatureC=15))
        self.assertEqual(body.recommendation.choice, 'walk')
        self.assertEqual(body.recommendation.weatherReason, '지금 비지만 짧은 거리라 걸을 만해요')

    def test_clear_weather_changes_nothing(self):
        body = self.build(WeatherInfo(condition='맑음', temperatureC=22, precipitationProbability=0), minutes=25, meters=1800)
        self.assertEqual(body.recommendation.choice, 'walk')
        self.assertIsNone(body.recommendation.weatherReason)
        self.assertEqual(body.weather.condition, '맑음')


if __name__ == '__main__':
    unittest.main()

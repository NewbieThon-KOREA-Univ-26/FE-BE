"""공식 문서와 운영 응답에서 확인한 카카오맵 JSON 구조의 회귀 테스트."""
import unittest

import httpx
from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.main import create_app


class OfficialResponseTests(unittest.TestCase):
    def setUp(self):
        self.points = [[127.0276, 37.4979], [127.03, 37.50]]
        self.second = [[127.035, 37.505], [127.04, 37.51]]
        self.walk = {'status': 'OK', 'route': {
            'properties': {'totalDistance': 2373, 'totalTime': 2290},
            'legs': [{'properties': {'distance': 2373, 'time': 2290}, 'steps': [
                {'properties': {'time': 120}, 'path': {'points': self.points}},
                {'properties': {'time': 2170}, 'path': {'points': self.second}},
            ]}],
        }}
        self.transit = {'status': 'OK', 'properties': {'total': 15}, 'routes': [{
            'properties': {'totalTime': 975, 'transfers': 1, 'fare': {'value': 2250}},
            'steps': [
                {'properties': {'type': 'SUBWAY', 'time': 795}, 'path': {'points': self.points}},
                {'properties': {'type': 'WALK', 'time': 180, 'distance': 240},
                 'path': {'points': self.second}},
            ],
        }]}

    def compare(self):
        def handler(request):
            return httpx.Response(200, json=self.walk if request.url.path.endswith('/walk') else self.transit)
        settings = Settings(_env_file=None, route_provider='kakao', kakao_rest_api_key='test',
                            kakao_walk_path='/v2/routing/walk')
        with TestClient(create_app(settings, httpx.MockTransport(handler))) as client:
            return client.post('/api/compare', json={
                'start': {'x': 127.0276, 'y': 37.4979}, 'end': {'x': 127.04, 'y': 37.51},
            })

    def test_live_response_shape_produces_comparison_and_separate_paths(self):
        response = self.compare()
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['walk']['distance'], 2373)
        self.assertAlmostEqual(body['walk']['duration'], 2290 / 60)
        self.assertEqual(body['transit']['duration'], 16.25)
        self.assertEqual(body['transit']['fare'], 2250)
        self.assertEqual(body['transit']['transfers'], 1)
        self.assertEqual(body['transit']['walkDistance'], 240)
        self.assertEqual(body['transit']['walkDuration'], 3)
        self.assertEqual(body['savings']['amount'], 2250)
        for mode in ('walk', 'transit'):
            self.assertEqual(body[mode]['paths'], [
                [{'x': x, 'y': y} for x, y in points] for points in (self.points, self.second)
            ])

    def test_short_times_are_seconds_too(self):
        for seconds in (0, 59, 300, 600):
            with self.subTest(seconds=seconds):
                self.walk['route']['properties']['totalTime'] = seconds
                self.transit['routes'][0]['properties']['totalTime'] = seconds
                response = self.compare()
                self.assertEqual(response.status_code, 200, response.text)
                for mode in ('walk', 'transit'):
                    self.assertAlmostEqual(response.json()[mode]['duration'], seconds / 60)

    def test_missing_fare_is_not_read_from_result_count(self):
        del self.transit['routes'][0]['properties']['fare']
        response = self.compare()
        self.assertEqual(response.status_code, 502, response.text)
        self.assertEqual(response.json()['error']['code'], 'UPSTREAM_ERROR')

    def test_missing_geometry_keeps_totals(self):
        self.walk['route']['legs'] = []
        self.transit['routes'][0]['steps'] = []
        response = self.compare()
        self.assertEqual(response.status_code, 200, response.text)
        for mode in ('walk', 'transit'):
            self.assertEqual(response.json()[mode]['paths'], [])

    def test_empty_routes_remain_no_route(self):
        self.walk['route'] = None
        self.transit['routes'] = []
        response = self.compare()
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()['error']['code'], 'NO_ROUTE')

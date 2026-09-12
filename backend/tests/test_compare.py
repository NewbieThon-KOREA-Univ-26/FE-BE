import copy
import unittest

import httpx
from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.main import create_app


PARAMS = dict(startX=127.0276, startY=37.4979, endX=127.04, endY=37.51)


def transit_path(minutes, fare):
    return {'info': {'totalTime': minutes, 'payment': fare, 'totalWalk': 320,
                     'mapObj': f'126:37@{fare}:1:0:3'},
            'subPath': [{'trafficType': 3, 'sectionTime': 2},
                        {'trafficType': 1, 'sectionTime': 3},
                        {'trafficType': 3, 'sectionTime': 3},
                        {'trafficType': 2, 'sectionTime': 2}]}


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.walk = {'result': {'path': [{'hasPathResult': True, 'recommend': {
            'summary': {'distance': 1180, 'duration': 901}}}]}}
        self.transit = {'result': {'searchType': 0, 'path': [
            transit_path(20, 1000), transit_path(10, 1700), transit_path(10, 1400)]}}
        self.points = [{'x': 127.0276, 'y': 37.4979}, {'x': 127.04, 'y': 37.51}]
        self.walk['result']['path'][0]['recommend']['routes'] = [
            {'coordinate': point} for point in self.points]
        self.geometry = {'result': {'lane': [{'section': [{'graphPos': self.points}]}]}}
        self.calls = []
        self.failure = None

    def handler(self, request):
        self.calls.append(request)
        if self.failure:
            return self.failure(request)
        if request.url.path.endswith('loadLane'):
            return httpx.Response(200, json=copy.deepcopy(self.geometry))
        return httpx.Response(200, json=copy.deepcopy(
            self.walk if request.url.path.endswith('searchWalkPathV2') else self.transit))

    def client(self, key='test-key'):
        # 이 파일은 ODsay 제공자를 검증합니다. 카카오 제공자는 KakaoTests 에서 봅니다.
        return TestClient(create_app(
            Settings(_env_file=None, route_provider='odsay', odsay_api_key=key),
            httpx.MockTransport(self.handler)))

    def test_comparison_and_provider_contract(self):
        with self.client() as client:
            response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['walk'], {'distance': 1180, 'duration': 16,
                                      'paths': [self.points]})
        self.assertEqual(body['transit'], {'duration': 10, 'fare': 1400,
                         'transfers': 1, 'walkDistance': 320, 'walkDuration': 5,
                         'paths': [self.points]})
        self.assertEqual(body['savings'], {'amount': 1400, 'extraMinutes': 6})
        self.assertEqual(body['recommendation']['choice'], 'walk')
        for request in self.calls:
            self.assertEqual(request.url.params['apiKey'], 'test-key')
            if request.url.path.endswith('searchWalkPathV2'):
                self.assertEqual(request.url.params['loc'], '127.0276,37.4979,127.04,37.51')
            elif request.url.path.endswith('loadLane'):
                self.assertEqual(request.url.params['mapObject'], '0:0@1400:1:0:3')
            else:
                self.assertEqual(request.url.params['SX'], '127.0276')

    def test_missing_geometry_preserves_comparison(self):
        self.geometry = {'error': {'code': '500'}}
        self.walk['result']['path'][0]['recommend']['routes'] = []
        with self.client() as client:
            response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.status_code, 200)
        for mode in ('walk', 'transit'):
            self.assertEqual(response.json()[mode]['paths'], [])
            self.assertTrue(response.json()[mode]['geometryWarning'])

    def test_load_lane_keeps_every_map_object_section(self):
        self.transit['result']['path'] = [transit_path(10, 1400)]
        self.transit['result']['path'][0]['info']['mapObj'] = (
            '12018:1:3:7@5:2:310:329'
        )
        with self.client() as client:
            client.get('/api/compare', params=PARAMS)
        load_lane = next(
            request for request in self.calls
            if request.url.path.endswith('loadLane')
        )
        self.assertEqual(
            load_lane.url.params['mapObject'],
            '0:0@12018:1:3:7@5:2:310:329',
        )

    def test_disconnected_geometry_is_not_joined(self):
        second = [{'x': 127.05, 'y': 37.52}, {'x': 127.06, 'y': 37.53}]
        self.geometry['result']['lane'][0]['section'].append({'graphPos': second})
        with self.client() as client:
            body = client.get('/api/compare', params=PARAMS).json()
        self.assertEqual(body['transit']['paths'], [self.points, second])

    def test_invalid_geometry_does_not_break_comparison(self):
        self.geometry['result']['lane'][0]['section'][0]['graphPos'][0]['x'] = 999
        with self.client() as client:
            response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['transit']['paths'], [])

    def test_invalid_input_never_calls_provider(self):
        with self.client() as client:
            for params in ({}, {**PARAMS, 'startX': 181}, {**PARAMS, 'endY': 'nan'},
                           {**PARAMS, 'startY': 'inf'}, {**PARAMS, 'endX': 'abc'}):
                response = client.get('/api/compare', params=params)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['error']['code'], 'INVALID_INPUT')
            response = client.get('/api/compare', params={**PARAMS, 'endX': PARAMS['startX'],
                                                         'endY': PARAMS['startY']})
            self.assertEqual(response.json()['error']['code'], 'SAME_LOCATION')
        self.assertEqual(self.calls, [])

    def test_faster_walk_preserves_negative_difference(self):
        self.walk['result']['path'][0]['recommend']['summary']['duration'] = 300
        with self.client() as client:
            body = client.get('/api/compare', params=PARAMS).json()
        self.assertEqual(body['savings']['extraMinutes'], -5)
        self.assertIn('5분 더 빠르고', body['recommendation']['reason'])

    def test_long_walk_is_success_not_error(self):
        self.walk['result']['path'][0]['recommend']['summary']['distance'] = 3000
        with self.client() as client:
            response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['recommendation']['choice'], 'transit')

    def test_no_route(self):
        self.walk = {'result': {'path': [{'hasPathResult': False, 'errorCode': '414'}]}}
        with self.client() as client:
            response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.status_code, 404)

    def test_transit_no_route_and_short_distance(self):
        for code in ('-98', '-99'):
            self.transit = {'error': {'code': code}}
            with self.client() as client:
                response = client.get('/api/compare', params=PARAMS)
            self.assertEqual(response.json()['error']['code'], 'NO_ROUTE')

    def test_bad_provider_responses(self):
        for status, content in [(502, b'bad gateway'), (200, b'not json'),
                                (200, b'{}'), (200, b'[]')]:
            self.failure = lambda req: httpx.Response(status, content=content)
            with self.client() as client:
                response = client.get('/api/compare', params=PARAMS)
            self.assertEqual(response.status_code, 502)
            self.assertNotIn('test-key', response.text)

    def test_rate_limit(self):
        self.failure = lambda req: httpx.Response(429)
        with self.client() as client:
            response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.json()['error']['code'], 'RATE_LIMITED')

    def test_auth_failure_explains_endpoint_without_leaking_secret(self):
        self.failure = lambda req: httpx.Response(200, json={
            'error': [{'code': '500', 'message': '[ApiKeyAuthFailed] test-key'}]})
        with self.client() as client:
            response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.status_code, 502)
        self.assertIn('도보 경로 인증', response.json()['error']['message'])
        self.assertNotIn('test-key', response.text)

    def test_timeout(self):
        def timeout(request):
            raise httpx.ReadTimeout('secret test-key', request=request)
        self.failure = timeout
        with self.client() as client:
            response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('test-key', response.text)

    def test_missing_key_and_health(self):
        with self.client(key='') as client:
            self.assertEqual(client.get('/api/health').status_code, 200)
            self.assertEqual(client.get('/api/compare', params=PARAMS).status_code, 503)
        self.assertEqual(self.calls, [])


class PathTests(CompareTests):
    """경로 선 좌표(F: 지도 경로 표시)가 응답에 실리는지 확인합니다."""

    def test_transit_path_from_stations(self):
        self.transit['result']['path'][2]['subPath'][1]['passStopList'] = {'stations': [
            {'x': '127.03', 'y': '37.50'}, {'x': '127.035', 'y': '37.505'},
        ]}
        with self.client() as client:
            body = client.get('/api/compare', params=PARAMS).json()
        self.assertEqual(body['transit']['path'], [
            {'x': 127.03, 'y': 37.5}, {'x': 127.035, 'y': 37.505},
        ])

    def test_transit_path_falls_back_to_section_endpoints(self):
        section = self.transit['result']['path'][2]['subPath'][1]
        section.update(startX=127.0, startY=37.5, endX=127.01, endY=37.51)
        with self.client() as client:
            body = client.get('/api/compare', params=PARAMS).json()
        self.assertEqual(body['transit']['path'], [
            {'x': 127.0, 'y': 37.5}, {'x': 127.01, 'y': 37.51},
        ])

    def test_path_is_omitted_when_provider_has_no_coordinates(self):
        with self.client() as client:
            body = client.get('/api/compare', params=PARAMS).json()
        self.assertNotIn('path', body['transit'])
        self.assertNotIn('path', body['walk'])

    def test_walk_path_is_read_when_present(self):
        self.walk['result']['path'][0]['recommend']['sections'] = [
            {'points': [{'x': 127.0276, 'y': 37.4979}, {'x': 127.03, 'y': 37.50}]},
            {'points': [{'x': 127.04, 'y': 37.51}]},
        ]
        with self.client() as client:
            body = client.get('/api/compare', params=PARAMS).json()
        self.assertEqual(body['walk']['path'], [
            {'x': 127.0276, 'y': 37.4979}, {'x': 127.03, 'y': 37.5}, {'x': 127.04, 'y': 37.51},
        ])

    def test_broken_coordinates_never_break_the_response(self):
        self.transit['result']['path'][2]['subPath'][1]['passStopList'] = {'stations': [
            # httpx 는 float('inf') 를 직렬화하지 못하므로 실제 API 처럼 문자열로 둡니다.
            {'x': 'abc', 'y': None}, {'x': 'inf', 'y': 37.5}, {'y': 37.5},
        ]}
        self.walk['result']['path'][0]['recommend']['sections'] = 'not a list'
        with self.client() as client:
            response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertNotIn('path', body['transit'])
        self.assertNotIn('path', body['walk'])
        self.assertEqual(body['savings']['amount'], 1400)

    def test_single_point_is_not_a_line(self):
        self.transit['result']['path'][2]['subPath'][1]['passStopList'] = {'stations': [
            {'x': 127.03, 'y': 37.5}, {'x': 127.03, 'y': 37.5},
        ]}
        with self.client() as client:
            body = client.get('/api/compare', params=PARAMS).json()
        self.assertNotIn('path', body['transit'])


class FormattingTests(unittest.TestCase):
    """소요시간이 초/60 같은 소수로 와도 사람에게 보이는 값은 분 단위로 깔끔해야 합니다."""

    def test_reason_and_extra_minutes_are_rounded(self):
        from src.config.settings import Settings
        from src.services.compare import Transit, Walk, build_comparison
        walk = Walk(distance=19274, duration=18734 / 60, paths=[])
        transit = Transit(duration=4685 / 60, fare=1750, transfers=2,
                          walkDistance=1200, walkDuration=15.3, paths=[])
        body = build_comparison(walk, transit, Settings(_env_file=None))
        self.assertEqual(body.savings.extraMinutes, 234)
        self.assertEqual(body.recommendation.reason, '도보 5시간 12분·19.3km로 걷기 추천 기준을 초과합니다')

    def test_walk_reason_uses_rounded_minutes(self):
        from src.config.settings import Settings
        from src.services.compare import Transit, Walk, build_comparison, format_distance, format_minutes
        walk = Walk(distance=1180, duration=901 / 60, paths=[])
        transit = Transit(duration=10.4, fare=1400, transfers=0, walkDistance=0, walkDuration=0, paths=[])
        body = build_comparison(walk, transit, Settings(_env_file=None))
        self.assertEqual(body.recommendation.choice, 'walk')
        self.assertEqual(body.savings.extraMinutes, 5)
        self.assertEqual(body.recommendation.reason, '걸으면 5분 더 걸리지만 1,400원을 아낍니다')
        self.assertEqual(format_minutes(60), '1시간')
        self.assertEqual(format_minutes(0.4), '0분')
        self.assertEqual(format_distance(999.6), '1000m')
        self.assertEqual(format_distance(1000), '1.0km')


if __name__ == '__main__':
    unittest.main()

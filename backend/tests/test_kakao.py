"""카카오맵 REST 제공자 테스트.

실제 응답 형식을 문서로 확인하지 못해, 여기 픽스처는 "이런 모양이면 이렇게 읽는다"
를 고정하는 용도입니다. 진짜 응답을 받아 보고 형식이 다르면
src/services/kakao.py 의 *_KEYS 목록과 이 픽스처를 함께 고치세요.
"""

import copy
import unittest

import httpx
from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.main import create_app

PARAMS = dict(startX=127.0276, startY=37.4979, endX=127.04, endY=37.51)


def transit_route(minutes=10, fare=1400):
    return {'routes': [{
        'duration': minutes, 'fare': fare, 'transfers': 1,
        'totalWalk': 320, 'totalWalkTime': 5,
        'sections': [
            {'points': [{'x': 127.0276, 'y': 37.4979}, {'x': 127.03, 'y': 37.50}]},
            {'points': [{'x': 127.035, 'y': 37.505}, {'x': 127.04, 'y': 37.51}]},
        ],
    }]}


def walk_route(distance=1180, minutes=16):
    return {'routes': [{
        'distance': distance, 'duration': minutes,
        'sections': [{'points': [{'x': 127.0276, 'y': 37.4979}, {'x': 127.04, 'y': 37.51}]}],
    }]}


class KakaoTests(unittest.TestCase):
    def setUp(self):
        self.walk = walk_route()
        self.transit = transit_route()
        self.calls = []
        self.failure = None

    def handler(self, request):
        self.calls.append(request)
        if self.failure:
            return self.failure(request)
        body = self.walk if 'pedestrian' in request.url.path else self.transit
        return httpx.Response(200, json=copy.deepcopy(body))

    def client(self, key='kakao-key'):
        return TestClient(create_app(
            Settings(_env_file=None, route_provider='kakao', kakao_rest_api_key=key),
            httpx.MockTransport(self.handler)))

    def test_compare_and_request_contract(self):
        with self.client() as client:
            response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['walk']['distance'], 1180)
        self.assertEqual(body['walk']['duration'], 16)
        self.assertEqual(body['transit'], {
            'duration': 10, 'fare': 1400, 'transfers': 1,
            'walkDistance': 320, 'walkDuration': 5,
            'paths': [
                [{'x': 127.0276, 'y': 37.4979}, {'x': 127.03, 'y': 37.5}],
                [{'x': 127.035, 'y': 37.505}, {'x': 127.04, 'y': 37.51}],
            ],
        })
        self.assertEqual(body['savings'], {'amount': 1400, 'extraMinutes': 6})
        self.assertEqual(body['recommendation']['choice'], 'walk')
        for request in self.calls:
            self.assertEqual(request.headers['Authorization'], 'KakaoAK kakao-key')
            self.assertEqual(request.url.host, 'dapi.kakao.com')
            self.assertEqual(request.url.params['sx'], '127.0276')
            self.assertEqual(request.url.params['ey'], '37.51')

    def test_seconds_are_converted_to_minutes(self):
        # 초로 오는 API 도 있어 큰 값은 초로 보고 분으로 바꿉니다.
        self.walk = walk_route(minutes=960)
        with self.client() as client:
            body = client.get('/api/compare', params=PARAMS).json()
        self.assertEqual(body['walk']['duration'], 16)

    def test_flat_coordinate_array_is_read(self):
        self.walk['routes'][0]['sections'] = [{'vertexes': [127.0276, 37.4979, 127.04, 37.51]}]
        with self.client() as client:
            body = client.get('/api/compare', params=PARAMS).json()
        self.assertEqual(body['walk']['paths'],
                         [[{'x': 127.0276, 'y': 37.4979}, {'x': 127.04, 'y': 37.51}]])

    def test_missing_key_returns_503_without_calling_kakao(self):
        with self.client(key='') as client:
            response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'SERVICE_NOT_CONFIGURED')
        self.assertEqual(self.calls, [])

    def test_rejected_key_is_reported_as_configuration_problem(self):
        self.failure = lambda req: httpx.Response(401, json={'message': 'unauthorized'})
        with self.client() as client:
            response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'SERVICE_NOT_CONFIGURED')

    def test_rate_limit(self):
        self.failure = lambda req: httpx.Response(429)
        with self.client() as client:
            self.assertEqual(client.get('/api/compare', params=PARAMS).json()['error']['code'],
                             'RATE_LIMITED')

    def test_unknown_shape_reports_the_keys_it_received(self):
        # 형식이 다르면 어떤 이름으로 왔는지 메시지에 담아 고치기 쉽게 합니다.
        self.transit = {'routes': [{'somethingElse': 1}]}
        with self.client() as client:
            response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.status_code, 502)
        self.assertIn('받은 항목', response.json()['error']['message'])

    def test_no_route(self):
        self.transit = {'errorType': 'NO_RESULT', 'message': '경로 없음'}
        with self.client() as client:
            response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['error']['code'], 'NO_ROUTE')

    def test_key_never_leaks_into_error_messages(self):
        def timeout(request):
            raise httpx.ReadTimeout('secret kakao-key', request=request)
        self.failure = timeout
        with self.client() as client:
            response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('kakao-key', response.text)

    def test_endpoint_paths_are_configurable(self):
        with TestClient(create_app(
            Settings(_env_file=None, route_provider='kakao', kakao_rest_api_key='k',
                     kakao_walk_path='/v2/routing/walk', kakao_transit_path='/v2/routing/transit'),
            httpx.MockTransport(self.handler),
        )) as client:
            client.get('/api/compare', params=PARAMS)
        paths = sorted(request.url.path for request in self.calls)
        self.assertEqual(paths, ['/v2/routing/transit', '/v2/routing/walk'])


if __name__ == '__main__':
    unittest.main()


class ServerlessTests(KakaoTests):
    """Vercel 같은 서버리스에서는 ASGI lifespan 이 실행되지 않을 수 있습니다.

    그 상태에서도 모든 엔드포인트가 동작해야 합니다.
    (배포에서 FUNCTION_INVOCATION_FAILED 로 500 이 나던 상황)
    """

    def test_compare_works_without_lifespan(self):
        # with 를 쓰지 않으면 lifespan 이 실행되지 않습니다.
        response = self.client().get('/api/compare', params=PARAMS)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['savings']['amount'], 1400)

    def test_auth_endpoint_works_without_lifespan(self):
        # 로그인 관련 엔드포인트도 같은 app.state 를 씁니다.
        response = self.client().get('/api/auth/me')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('user', response.json())

    def test_health_reports_the_provider(self):
        self.assertEqual(self.client().get('/api/health').json(),
                         {'status': 'ok', 'provider': 'kakao'})

    def test_unexpected_error_returns_our_error_shape(self):
        # 예상 못한 예외도 빈 500 이 아니라 화면이 읽을 수 있는 형식으로 나가야 합니다.
        def explode(request):
            raise RuntimeError('boom kakao-key')
        self.failure = explode
        client = TestClient(create_app(
            Settings(_env_file=None, route_provider='kakao', kakao_rest_api_key='kakao-key'),
            httpx.MockTransport(self.handler)), raise_server_exceptions=False)
        response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()['error']['code'], 'INTERNAL_ERROR')
        self.assertNotIn('kakao-key', response.text)


class PathParameterTests(KakaoTests):
    """좌표를 경로로 받는 방식.

    배포 프록시가 쿼리스트링을 넘기지 않는 경우가 있어 추가한 경로입니다.
    """

    def test_path_form_returns_the_same_result_as_query_form(self):
        with self.client() as client:
            by_query = client.get('/api/compare', params=PARAMS).json()
            by_path = client.get('/api/compare/127.0276,37.4979/127.04,37.51').json()
        self.assertEqual(by_query, by_path)

    def test_same_location_is_rejected(self):
        with self.client() as client:
            body = client.get('/api/compare/127.0,37.5/127.0,37.5').json()
        self.assertEqual(body['error']['code'], 'SAME_LOCATION')

    def test_malformed_and_out_of_range_pairs(self):
        with self.client() as client:
            for path in ('/api/compare/abc/127.0,37.5',
                         '/api/compare/127.0/127.0,37.5',
                         '/api/compare/999,37.5/127.0,37.5',
                         '/api/compare/127.0,99/127.0,37.5'):
                response = client.get(path)
                self.assertEqual(response.status_code, 400, path)
                self.assertEqual(response.json()['error']['code'], 'INVALID_INPUT', path)
        self.assertEqual(self.calls, [])

    def test_validation_error_names_what_arrived(self):
        # 쿼리스트링이 통째로 사라지는 상황을 바로 알아볼 수 있어야 합니다.
        with self.client() as client:
            body = client.get('/api/compare').json()
        self.assertIn('받은 항목: 없음', body['error']['message'])


class BodyParameterTests(KakaoTests):
    """좌표를 요청 본문으로 받는 방식.

    배포 프록시가 쿼리스트링이나 경로 뒷부분을 넘기지 않는 경우가 있어 추가했습니다.
    본문은 그 영향을 받지 않습니다.
    """

    BODY = {'start': {'x': 127.0276, 'y': 37.4979}, 'end': {'x': 127.04, 'y': 37.51}}

    def test_body_form_matches_query_form(self):
        with self.client() as client:
            by_query = client.get('/api/compare', params=PARAMS).json()
            by_body = client.post('/api/compare', json=self.BODY).json()
        self.assertEqual(by_query, by_body)

    def test_same_location_is_rejected(self):
        same = {'start': {'x': 127.0, 'y': 37.5}, 'end': {'x': 127.0, 'y': 37.5}}
        with self.client() as client:
            self.assertEqual(client.post('/api/compare', json=same).json()['error']['code'],
                             'SAME_LOCATION')

    def test_bad_bodies_are_invalid_input(self):
        bad = [
            {},
            {'start': {'x': 127.0, 'y': 37.5}},
            {'start': {'x': 999, 'y': 37.5}, 'end': {'x': 127.0, 'y': 37.5}},
            {'start': {'x': 127.0, 'y': 99}, 'end': {'x': 127.0, 'y': 37.5}},
            {'start': {'x': 'abc', 'y': 37.5}, 'end': {'x': 127.0, 'y': 37.5}},
        ]
        with self.client() as client:
            for body in bad:
                response = client.post('/api/compare', json=body)
                self.assertEqual(response.status_code, 400, body)
                self.assertEqual(response.json()['error']['code'], 'INVALID_INPUT', body)
        self.assertEqual(self.calls, [])

    def test_validation_error_names_the_path_it_received(self):
        # 배포에서 경로가 잘리는지 판단할 수 있도록 받은 경로를 함께 알려 줍니다.
        with self.client() as client:
            message = client.get('/api/compare').json()['error']['message']
        self.assertIn('받은 경로: /api/compare', message)


class EchoTests(KakaoTests):
    """진단용 /api/echo.

    배포 프록시가 경로·쿼리·메서드·본문 중 무엇을 지우는지 확인하는 엔드포인트입니다.
    """

    def test_get_reports_what_arrived(self):
        with self.client() as client:
            body = client.get('/api/echo?a=1&b=2').json()
        self.assertEqual(body['method'], 'GET')
        self.assertEqual(body['path'], '/api/echo')
        self.assertEqual(body['queryKeys'], ['a', 'b'])

    def test_post_reports_the_body(self):
        with self.client() as client:
            body = client.post('/api/echo', json={'hi': 1}).json()
        self.assertEqual(body['method'], 'POST')
        self.assertIn('hi', body['body'])

    def test_header_values_are_not_exposed(self):
        # 헤더에는 키나 쿠키가 섞일 수 있으므로 이름만 담습니다.
        with self.client() as client:
            body = client.get('/api/echo', headers={'Authorization': 'KakaoAK secret-value'}).json()
        self.assertIn('authorization', body['headerNames'])
        self.assertNotIn('secret-value', str(body))


class CorsTests(unittest.TestCase):
    """다른 도메인에 배포한 프론트가 부를 수 있어야 합니다.

    브라우저는 POST 전에 OPTIONS(프리플라이트)를 먼저 보냅니다.
    여기서 Access-Control-Allow-Origin 이 빠지면 요청이 아예 막힙니다.
    """

    ORIGIN = 'https://walkride-fe.vercel.app'

    def app(self, origins):
        return TestClient(create_app(
            Settings(_env_file=None, route_provider='kakao', kakao_rest_api_key='k',
                     cors_origins=origins),
            httpx.MockTransport(lambda request: httpx.Response(200, json={'routes': []}))))

    def test_preflight_is_allowed_for_post(self):
        response = self.app([self.ORIGIN]).options('/api/compare', headers={
            'Origin': self.ORIGIN,
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type',
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['access-control-allow-origin'], self.ORIGIN)
        self.assertIn('POST', response.headers['access-control-allow-methods'])

    def test_unknown_origin_is_not_allowed(self):
        response = self.app([self.ORIGIN]).options('/api/compare', headers={
            'Origin': 'https://somewhere-else.example',
            'Access-Control-Request-Method': 'POST',
        })
        self.assertNotIn('access-control-allow-origin', response.headers)

    def test_comma_separated_origins_are_accepted(self):
        # 배포 환경변수에 쉼표로 적어도 동작해야 합니다.
        settings = Settings(_env_file=None, cors_origins=f'{self.ORIGIN}, http://localhost:5173')
        self.assertEqual(settings.cors_origins, [self.ORIGIN, 'http://localhost:5173'])

import copy
import unittest

import httpx
from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.main import create_app


PARAMS = dict(startX=127.0276, startY=37.4979, endX=127.04, endY=37.51)


def transit_path(minutes, fare):
    return {'info': {'totalTime': minutes, 'payment': fare, 'totalWalk': 320},
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
        self.calls = []
        self.failure = None

    def handler(self, request):
        self.calls.append(request)
        if self.failure:
            return self.failure(request)
        return httpx.Response(200, json=copy.deepcopy(
            self.walk if request.url.path.endswith('searchWalkPathV2') else self.transit))

    def client(self, key='test-key'):
        return TestClient(create_app(Settings(_env_file=None, odsay_api_key=key),
                                     httpx.MockTransport(self.handler)))

    def test_comparison_and_provider_contract(self):
        with self.client() as client:
            response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['walk'], {'distance': 1180, 'duration': 16})
        self.assertEqual(body['transit'], {'duration': 10, 'fare': 1400,
                         'transfers': 1, 'walkDistance': 320, 'walkDuration': 5})
        self.assertEqual(body['savings'], {'amount': 1400, 'extraMinutes': 6})
        self.assertEqual(body['recommendation']['choice'], 'walk')
        for request in self.calls:
            self.assertEqual(request.url.params['apiKey'], 'test-key')
            if request.url.path.endswith('searchWalkPathV2'):
                self.assertEqual(request.url.params['loc'], '127.0276,37.4979,127.04,37.51')
            else:
                self.assertEqual(request.url.params['SX'], '127.0276')

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


if __name__ == '__main__':
    unittest.main()

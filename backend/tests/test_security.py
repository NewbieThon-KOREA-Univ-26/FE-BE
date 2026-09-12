"""보안 점검 — 서명된 절감액, 요청 제한, 보안 헤더, 결과 캐시, 진단 엔드포인트 잠금."""
import time
import unittest

import httpx
from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.main import create_app
from src.services.ratelimit import RateLimiter, client_key
from src.services.savings import SavingsLedger
from tests.test_kakao import PARAMS, transit_route, walk_route


def make_client(calls=None, **overrides):
    def handler(request):
        if calls is not None:
            calls.append(request)
        return httpx.Response(200, json=walk_route() if request.url.path.endswith(('/pedestrian', '/walk')) else transit_route())
    settings = Settings(**{'_env_file': None, 'route_provider': 'kakao', 'kakao_rest_api_key': 'k',
                           'session_secret_key': 'test-secret', **overrides})
    return TestClient(create_app(settings, httpx.MockTransport(handler)))


class SignedSavingsTests(unittest.TestCase):
    def test_claim_flow_and_tamper_resistance(self):
        with make_client() as client:
            voucher = client.get('/api/compare', params=PARAMS).json()['savings']['voucher']
            first = client.post('/api/savings/claim', json={'total': None, 'voucher': voucher}).json()
            self.assertEqual((first['saved'], first['walks'], first['gained']), (1400, 1, 1400))
            # 서버가 준 토큰은 검증을 통과합니다
            check = client.get('/api/savings', params={'total': first['total']}).json()
            self.assertEqual(check, {'saved': 1400, 'walks': 1, 'valid': True})
            # 주소창에서 숫자를 고치면(payload 변조) 서명이 깨져 0 이 됩니다
            body, signature = first['total'].split('.')
            forged = f'{body[:-2]}AA.{signature}'
            self.assertEqual(client.get('/api/savings', params={'total': forged}).json(),
                             {'saved': 0, 'walks': 0, 'valid': False})
            self.assertEqual(client.get('/api/savings', params={'total': 'saved=99999999'}).json()['valid'], False)
            # 같은 적립권은 두 번 쓸 수 없습니다
            again = client.post('/api/savings/claim', json={'total': first['total'], 'voucher': voucher})
            self.assertEqual(again.status_code, 409)
            self.assertEqual(again.json()['error']['code'], 'VOUCHER_USED')
            # 위조 적립권은 거절됩니다
            fake = client.post('/api/savings/claim', json={'total': None, 'voucher': 'eyJhbW91bnQiOjk5OTk5fQ.abc'})
            self.assertEqual(fake.status_code, 400)
            self.assertEqual(fake.json()['error']['code'], 'INVALID_VOUCHER')
            # 변조된 누적액 토큰으로 적립하면 0 에서 다시 시작합니다
            voucher2 = client.get('/api/compare', params=PARAMS).json()['savings']['voucher']
            second = client.post('/api/savings/claim', json={'total': forged, 'voucher': voucher2}).json()
            self.assertEqual((second['saved'], second['walks']), (1400, 1))

    def test_expired_voucher_is_rejected(self):
        ledger = SavingsLedger(Settings(_env_file=None, session_secret_key='s'))
        expired = ledger.sign({'amount': 100, 'exp': int(time.time()) - 1, 'nonce': 'n1'})
        with self.assertRaises(Exception) as caught:
            ledger.claim(None, expired)
        self.assertEqual(caught.exception.code, 'VOUCHER_EXPIRED')

    def test_vouchers_are_fresh_even_when_compare_is_cached(self):
        calls = []
        with make_client(calls) as client:
            a = client.get('/api/compare', params=PARAMS).json()['savings']['voucher']
            b = client.get('/api/compare', params=PARAMS).json()['savings']['voucher']
        self.assertNotEqual(a, b)
        self.assertEqual(len(calls), 2)   # 카카오는 도보·대중교통 한 번씩만 (두 번째는 캐시)

    def test_cache_can_be_disabled(self):
        calls = []
        with make_client(calls, compare_cache_seconds=0) as client:
            client.get('/api/compare', params=PARAMS)
            client.get('/api/compare', params=PARAMS)
        self.assertEqual(len(calls), 4)

    def test_missing_secret_still_works_but_keys_differ_per_process(self):
        a = SavingsLedger(Settings(_env_file=None))
        b = SavingsLedger(Settings(_env_file=None))
        self.assertTrue(a.ephemeral)
        token = a.total_token(500, 1)
        self.assertEqual(a.total_from(token), (500, 1, True))
        self.assertEqual(b.total_from(token), (0, 0, False))

    def test_amount_bounds_are_enforced(self):
        ledger = SavingsLedger(Settings(_env_file=None, session_secret_key='s'))
        self.assertEqual(ledger.total_from(ledger.sign({'saved': -1, 'walks': 0})), (0, 0, False))
        self.assertEqual(ledger.total_from(ledger.sign({'saved': 10 ** 12, 'walks': 0})), (0, 0, False))
        self.assertEqual(ledger.total_from(ledger.sign({'saved': 1.5, 'walks': 0})), (0, 0, False))


class ValidationMessageTests(unittest.TestCase):
    def test_non_compare_endpoints_get_a_generic_validation_message(self):
        with make_client() as client:
            response = client.post('/api/savings/claim', json={})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'INVALID_INPUT')
        self.assertIn('문제 항목: voucher', response.json()['error']['message'])
        self.assertNotIn('경도와 위도', response.json()['error']['message'])


class RateLimitTests(unittest.TestCase):
    def test_bucket_refills_over_time(self):
        limiter = RateLimiter(per_minute=2)
        self.assertTrue(limiter.allow('a', now=0))
        self.assertTrue(limiter.allow('a', now=0))
        self.assertFalse(limiter.allow('a', now=0))
        self.assertTrue(limiter.allow('b', now=0))        # 다른 IP 는 별도
        self.assertTrue(limiter.allow('a', now=31))       # 30초 뒤 토큰 1개 회복
        self.assertTrue(RateLimiter(per_minute=0).allow('a'))

    def test_api_returns_429_and_health_is_exempt(self):
        with make_client(rate_limit_per_minute=2) as client:
            self.assertEqual(client.get('/api/compare', params=PARAMS).status_code, 200)
            self.assertEqual(client.get('/api/compare', params=PARAMS).status_code, 200)
            blocked = client.get('/api/compare', params=PARAMS)
            self.assertEqual(blocked.status_code, 429)
            self.assertEqual(blocked.json()['error']['code'], 'RATE_LIMITED')
            self.assertEqual(blocked.headers['Retry-After'], '60')
            self.assertEqual(client.get('/api/health').status_code, 200)

    def test_forwarded_for_uses_the_proxy_appended_last_value(self):
        self.assertEqual(client_key({'x-forwarded-for': '1.1.1.1, 2.2.2.2'}, '10.0.0.1'), '2.2.2.2')
        self.assertEqual(client_key({}, '10.0.0.1'), '10.0.0.1')
        self.assertEqual(client_key({}, None), 'unknown')


class HeadersAndDiagnosticsTests(unittest.TestCase):
    def test_api_responses_carry_security_headers(self):
        with make_client() as client:
            response = client.get('/api/compare', params=PARAMS)
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')

    def test_diagnostic_endpoints_are_closed_by_default(self):
        with make_client() as client:
            self.assertEqual(client.get('/api/echo').status_code, 404)
            self.assertEqual(client.get('/api/debug/upstream/walk', params=PARAMS).status_code, 404)
        with make_client(debug_raw_upstream=True) as client:
            self.assertEqual(client.get('/api/echo').status_code, 200)


if __name__ == '__main__':
    unittest.main()

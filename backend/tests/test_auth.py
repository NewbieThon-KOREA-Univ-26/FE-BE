import unittest
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.main import create_app


class KakaoLoginTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if request.url == httpx.URL('https://kauth.kakao.com/oauth/token'):
            return httpx.Response(200, json={'access_token': 'provider-access-token'})
        if request.url == httpx.URL('https://kapi.kakao.com/v2/user/me'):
            return httpx.Response(200, json={
                'id': 123456789,
                'properties': {'nickname': '걷는 사람'},
            })
        return httpx.Response(404)

    def client(self, **overrides):
        config = {
            'kakao_rest_api_key': 'rest-api-key',
            'kakao_client_secret': 'client-secret',
            'session_secret_key': 'session-signing-key',
            'frontend_url': 'http://frontend.test',
        }
        config.update(overrides)
        settings = Settings(_env_file=None, **config)
        return TestClient(create_app(settings, httpx.MockTransport(self.handler)))

    def start_login(self, client: TestClient) -> str:
        response = client.get('/api/auth/kakao/login', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlparse(response.headers['location']).query)
        self.assertEqual(query['client_id'], ['rest-api-key'])
        self.assertEqual(query['redirect_uri'], ['http://localhost:8000/api/auth/kakao/callback'])
        self.assertEqual(query['response_type'], ['code'])
        return query['state'][0]

    def test_login_callback_creates_signed_local_session(self):
        with self.client() as client:
            state = self.start_login(client)
            response = client.get(
                '/api/auth/kakao/callback',
                params={'code': 'authorization-code', 'state': state},
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers['location'], 'http://frontend.test')

            me = client.get('/api/auth/me')

        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json(), {'user': {'id': '123456789', 'nickname': '걷는 사람'}})
        self.assertEqual(len(self.calls), 2)
        token_request, user_request = self.calls
        form = parse_qs(token_request.content.decode())
        self.assertEqual(form['grant_type'], ['authorization_code'])
        self.assertEqual(form['client_id'], ['rest-api-key'])
        self.assertEqual(form['client_secret'], ['client-secret'])
        self.assertEqual(form['code'], ['authorization-code'])
        self.assertEqual(user_request.headers['authorization'], 'Bearer provider-access-token')
        self.assertNotIn('provider-access-token', response.headers.get('set-cookie', ''))

    def test_callback_rejects_missing_or_wrong_state_without_calling_kakao(self):
        with self.client() as client:
            response = client.get(
                '/api/auth/kakao/callback',
                params={'code': 'authorization-code', 'state': 'wrong-state'},
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['location'], 'http://frontend.test/?authError=KAKAO_LOGIN_FAILED')
        self.assertEqual(self.calls, [])

    def test_logout_only_removes_our_local_session(self):
        with self.client() as client:
            state = self.start_login(client)
            client.get('/api/auth/kakao/callback', params={'code': 'code', 'state': state},
                       follow_redirects=False)
            response = client.post('/api/auth/logout')
            me = client.get('/api/auth/me')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(me.json(), {'user': None})

    def test_invalid_session_is_anonymous(self):
        with self.client() as client:
            response = client.get('/api/auth/me', headers={'cookie': 'walkable_session=invalid'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'user': None})

    def test_login_requires_kakao_rest_key(self):
        with self.client(kakao_rest_api_key='') as client:
            response = client.get('/api/auth/kakao/login', follow_redirects=False)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'AUTH_NOT_CONFIGURED')


if __name__ == '__main__':
    unittest.main()

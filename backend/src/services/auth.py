import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from pydantic import BaseModel

from src.config.settings import Settings
from src.services.compare import ApiError


AUTHORIZATION_URL = 'https://kauth.kakao.com/oauth/authorize'
TOKEN_URL = 'https://kauth.kakao.com/oauth/token'
USER_URL = 'https://kapi.kakao.com/v2/user/me'
SESSION_COOKIE = 'walkable_session'
STATE_COOKIE = 'kakao_oauth_state'
STATE_TTL_SECONDS = 600
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7


class AuthUser(BaseModel):
    id: str
    nickname: str


class KakaoAuth:
    """Kakao OAuth exchanges a short-lived provider token for our signed session."""

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    def authorization_url(self, state: str) -> str:
        key = self._required_secret(self.settings.kakao_rest_api_key, 'KAKAO_REST_API_KEY')
        self._required_secret(self.settings.session_secret_key, 'SESSION_SECRET_KEY')
        query = urlencode({
            'client_id': key,
            'redirect_uri': self.settings.kakao_redirect_uri,
            'response_type': 'code',
            'state': state,
        })
        return f'{AUTHORIZATION_URL}?{query}'

    async def authenticate(self, code: str) -> AuthUser:
        key = self._required_secret(self.settings.kakao_rest_api_key, 'KAKAO_REST_API_KEY')
        form = {
            'grant_type': 'authorization_code',
            'client_id': key,
            'redirect_uri': self.settings.kakao_redirect_uri,
            'code': code,
        }
        client_secret = self.settings.kakao_client_secret.get_secret_value().strip()
        if client_secret:
            form['client_secret'] = client_secret

        try:
            token_response = await self.client.post(
                TOKEN_URL,
                data=form,
                headers={'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8'},
                timeout=self.settings.upstream_timeout_seconds,
            )
            token_response.raise_for_status()
            access_token = token_response.json().get('access_token')
            if not isinstance(access_token, str) or not access_token:
                raise ValueError('access token missing')

            user_response = await self.client.get(
                USER_URL,
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=self.settings.upstream_timeout_seconds,
            )
            user_response.raise_for_status()
            return self._parse_user(user_response.json())
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
            raise ApiError(502, 'KAKAO_AUTH_FAILED', '카카오 로그인 정보를 확인할 수 없습니다')

    def create_session(self, user: AuthUser) -> str:
        secret = self._required_secret(self.settings.session_secret_key, 'SESSION_SECRET_KEY')
        payload = {
            'sub': user.id,
            'nickname': user.nickname,
            'exp': int(time.time()) + SESSION_TTL_SECONDS,
        }
        encoded = self._encode(payload)
        signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
        return f'{encoded}.{self._encode_bytes(signature)}'

    def read_session(self, token: str | None) -> AuthUser | None:
        if not token:
            return None
        secret = self.settings.session_secret_key.get_secret_value().strip()
        if not secret:
            return None
        try:
            encoded, received_signature = token.split('.', 1)
            expected_signature = self._encode_bytes(
                hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
            )
            if not hmac.compare_digest(received_signature, expected_signature):
                return None
            payload = json.loads(self._decode(encoded))
            if not isinstance(payload, dict) or int(payload['exp']) < time.time():
                return None
            user_id = payload['sub']
            nickname = payload['nickname']
            if not isinstance(user_id, str) or not isinstance(nickname, str):
                return None
            return AuthUser(id=user_id, nickname=nickname)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def failure_url(self, code: str) -> str:
        parts = urlsplit(self.settings.frontend_url)
        query = urlencode({'authError': code})
        return urlunsplit((parts.scheme, parts.netloc, parts.path or '/', query, ''))

    @staticmethod
    def new_state() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def _parse_user(payload: object) -> AuthUser:
        if not isinstance(payload, dict):
            raise ValueError('invalid user payload')
        user_id = payload.get('id')
        if isinstance(user_id, bool) or user_id is None:
            raise ValueError('missing user id')
        properties = payload.get('properties')
        account = payload.get('kakao_account')
        profile = properties if isinstance(properties, dict) else {}
        if not profile and isinstance(account, dict) and isinstance(account.get('profile'), dict):
            profile = account['profile']
        nickname = profile.get('nickname')
        return AuthUser(id=str(user_id), nickname=nickname if isinstance(nickname, str) and nickname else '카카오 사용자')

    @staticmethod
    def _encode(payload: dict) -> str:
        return KakaoAuth._encode_bytes(json.dumps(payload, separators=(',', ':')).encode())

    @staticmethod
    def _encode_bytes(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b'=').decode()

    @staticmethod
    def _decode(value: str) -> str:
        padding = '=' * (-len(value) % 4)
        return base64.urlsafe_b64decode(f'{value}{padding}').decode()

    @staticmethod
    def _required_secret(value, name: str) -> str:
        secret = value.get_secret_value().strip()
        if not secret:
            raise ApiError(503, 'AUTH_NOT_CONFIGURED', f'{name} 환경 변수가 설정되지 않았습니다')
        return secret

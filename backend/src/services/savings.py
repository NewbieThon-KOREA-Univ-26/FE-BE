"""F8·F9 절감액 누적을 서버 서명으로 위조하지 못하게 합니다.

전에는 ?saved=4200&walks=3 처럼 평문이라 주소창에서 숫자만 고치면 그대로 반영됐습니다.
이제 두 가지 토큰을 씁니다. 둘 다 base64url(JSON) + "." + base64url(HMAC-SHA256).

- 누적액 토큰  {"saved": 4200, "walks": 3}
    주소창(?t=…)에 실립니다. 내용은 누구나 읽을 수 있지만, 고치면 서명이 맞지 않아 0 으로 돌아갑니다.
- 적립권(바우처) {"amount": 1750, "exp": 1757670000, "nonce": "…"}
    /api/compare 응답에 실립니다. 적립은 서버가 이 적립권을 검증하고 1회만 소모합니다.
    금액은 서버가 계산한 값이므로 프론트가 임의 금액을 적립할 수 없습니다.

비밀은 SESSION_SECRET_KEY 입니다. 없으면 프로세스 시작 시 임의 키를 만들어 쓰므로
동작은 하지만 서버가 재시작되면 기존 누적액 토큰이 무효가 됩니다.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

from src.config.settings import Settings
from src.services.compare import ApiError

MAX_SAVED = 1_000_000_000
MAX_WALKS = 1_000_000
MAX_USED_NONCES = 20_000


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode()


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


class SavingsLedger:
    def __init__(self, settings: Settings):
        secret = settings.session_secret_key.get_secret_value().strip()
        self.ephemeral = not secret
        self._key = (secret or secrets.token_urlsafe(32)).encode()
        self.voucher_ttl = settings.savings_voucher_ttl_seconds
        self._used: dict[str, float] = {}   # 소모한 적립권 nonce → 만료 시각

    # ── 서명 ────────────────────────────────────────────────────────────
    def sign(self, payload: dict) -> str:
        body = _b64(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode())
        return f'{body}.{_b64(hmac.new(self._key, body.encode(), hashlib.sha256).digest())}'

    def verify(self, token: str | None) -> dict | None:
        """서명이 맞으면 payload, 아니면 None. 형식이 이상해도 예외 대신 None."""
        if not isinstance(token, str) or token.count('.') != 1 or len(token) > 2000:
            return None
        body, signature = token.split('.', 1)
        expected = _b64(hmac.new(self._key, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        try:
            payload = json.loads(_unb64(body))
        except (ValueError, UnicodeDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    # ── 누적액 ──────────────────────────────────────────────────────────
    def total_from(self, token: str | None) -> tuple[int, int, bool]:
        """(saved, walks, valid). 토큰이 없거나 위조·손상이면 (0, 0, False)."""
        payload = self.verify(token)
        if payload is None:
            return 0, 0, False
        saved, walks = payload.get('saved'), payload.get('walks')
        if not (isinstance(saved, int) and isinstance(walks, int)
                and 0 <= saved <= MAX_SAVED and 0 <= walks <= MAX_WALKS):
            return 0, 0, False
        return saved, walks, True

    def total_token(self, saved: int, walks: int) -> str:
        return self.sign({'saved': saved, 'walks': walks})

    # ── 적립권 ──────────────────────────────────────────────────────────
    def issue_voucher(self, amount: int) -> str:
        return self.sign({'amount': int(max(0, amount)), 'exp': int(time.time()) + self.voucher_ttl,
                          'nonce': secrets.token_urlsafe(12)})

    def claim(self, total: str | None, voucher: str | None) -> dict:
        """적립권을 소모하고 새 누적액 토큰을 돌려줍니다."""
        payload = self.verify(voucher)
        if payload is None or not isinstance(payload.get('amount'), int) or not isinstance(payload.get('nonce'), str):
            raise ApiError(400, 'INVALID_VOUCHER', '적립권이 올바르지 않습니다. 경로를 다시 비교해 주세요')
        now = time.time()
        if not isinstance(payload.get('exp'), int) or payload['exp'] < now:
            raise ApiError(400, 'VOUCHER_EXPIRED', '적립권이 만료됐습니다. 경로를 다시 비교해 주세요')
        self._purge(now)
        if payload['nonce'] in self._used:
            raise ApiError(409, 'VOUCHER_USED', '이미 적립한 결과입니다')
        self._used[payload['nonce']] = payload['exp']
        saved, walks, _ = self.total_from(total)
        saved = min(MAX_SAVED, saved + payload['amount'])
        walks = min(MAX_WALKS, walks + 1)
        return {'total': self.total_token(saved, walks), 'saved': saved, 'walks': walks,
                'gained': payload['amount']}

    def _purge(self, now: float) -> None:
        if len(self._used) < MAX_USED_NONCES:
            return
        for nonce in [n for n, exp in self._used.items() if exp < now]:
            del self._used[nonce]
        # 만료된 게 없는데도 꽉 찼으면 오래된 것부터 버립니다 (재사용 위험보다 메모리 상한을 우선).
        while len(self._used) >= MAX_USED_NONCES:
            del self._used[next(iter(self._used))]

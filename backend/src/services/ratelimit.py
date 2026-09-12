"""IP 당 분당 요청 수 제한 (토큰 버킷). 카카오·날씨 무료 할당량을 한 사람이 다 쓰지 못하게 합니다.

단일 인스턴스(Render)를 가정한 메모리 구현입니다. 인스턴스가 여럿이면 각자 따로 셉니다.
"""

import time

MAX_BUCKETS = 10_000


class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._buckets: dict[str, tuple[float, float]] = {}   # key → (남은 토큰, 마지막 갱신)

    def allow(self, key: str, now: float | None = None) -> bool:
        if self.per_minute <= 0:
            return True
        now = time.monotonic() if now is None else now
        tokens, last = self._buckets.get(key, (float(self.per_minute), now))
        tokens = min(float(self.per_minute), tokens + (now - last) * self.per_minute / 60)
        if tokens < 1:
            self._buckets[key] = (tokens, now)
            return False
        if len(self._buckets) >= MAX_BUCKETS and key not in self._buckets:
            self._buckets.clear()
        self._buckets[key] = (tokens - 1, now)
        return True


def client_key(headers, client_host: str | None) -> str:
    """프록시 뒤에서는 X-Forwarded-For 의 마지막 값(프록시가 덧붙인 실제 접속 IP)을 씁니다."""
    forwarded = headers.get('x-forwarded-for', '')
    if forwarded:
        return forwarded.split(',')[-1].strip() or 'unknown'
    return client_host or 'unknown'

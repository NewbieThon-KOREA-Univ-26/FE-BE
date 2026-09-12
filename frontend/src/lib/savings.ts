/**
 * F8 절감액 누적 — 총 절감액을 서버가 서명한 토큰으로 URL 쿼리스트링에 저장합니다.
 *
 *   ?t=<base64url(JSON)>.<서명>
 *
 * 전에는 ?saved=4200&walks=3 평문이라 주소창에서 숫자만 고치면 그대로 반영됐습니다.
 * 이제 내용은 누구나 읽을 수 있지만(화면 표시용), 고치면 서명이 맞지 않아 서버가 0 으로 봅니다.
 * 적립(F9)은 /api/compare 가 준 1회용 적립권을 서버에 내면 서버가 금액을 더해 새 토큰을 줍니다.
 * 링크를 공유하면 받는 사람은 보낸 사람의 누적액을 보게 됩니다 — 자랑 용도라는 성격은 그대로입니다.
 */

export interface SavingsTotal {
  /** 지금까지 걸어서 아낀 돈 합계 (원) */
  amount: number
  /** 걷기를 선택한 횟수 */
  walks: number
  /** 서버가 서명한 누적액 토큰. 없으면 아직 적립한 적이 없는 것입니다. */
  token: string | null
}

export const EMPTY_TOTAL: SavingsTotal = { amount: 0, walks: 0, token: null }

const TOKEN_KEY = 't'
/** 예전 평문 형식의 키. 발견하면 지웁니다. */
const LEGACY_KEYS = ['saved', 'walks']

/** 0 이상의 정수만 통과시킵니다. */
function toCount(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
    ? Math.min(Math.floor(value), Number.MAX_SAFE_INTEGER)
    : 0
}

/**
 * 토큰의 내용(payload)을 읽습니다. 서명은 확인하지 않습니다 — 그건 서버 몫입니다.
 * 화면에 먼저 보여 주고, 서버 검증에서 위조로 판명되면 App 이 0 으로 되돌립니다.
 */
export function decodeTotal(token: string | null): SavingsTotal {
  if (!token || !token.includes('.')) {
    return EMPTY_TOTAL
  }
  try {
    const body = token.split('.')[0].replace(/-/g, '+').replace(/_/g, '/')
    const json = decodeURIComponent(
      Array.from(atob(body), (c) => `%${c.charCodeAt(0).toString(16).padStart(2, '0')}`).join(''),
    )
    const payload = JSON.parse(json) as { saved?: unknown; walks?: unknown }
    return { amount: toCount(payload.saved), walks: toCount(payload.walks), token }
  } catch {
    return EMPTY_TOTAL
  }
}

/** 현재 주소창에서 누적액 토큰을 읽습니다. */
export function readTotal(search: string = window.location.search): SavingsTotal {
  return decodeTotal(new URLSearchParams(search).get(TOKEN_KEY))
}

/** 누적액 토큰을 주소창에 반영합니다. 화면 이동 없이 주소만 바꿉니다. */
export function writeTotal(total: SavingsTotal): void {
  const params = new URLSearchParams(window.location.search)
  for (const key of LEGACY_KEYS) {
    params.delete(key)
  }
  if (total.token && total.amount > 0) {
    params.set(TOKEN_KEY, total.token)
  } else {
    params.delete(TOKEN_KEY)
  }
  const query = params.toString()
  const next = `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`
  window.history.replaceState(null, '', next)
}

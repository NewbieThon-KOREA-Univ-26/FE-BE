/**
 * F8 절감액 누적 — 총 절감액을 URL 쿼리스트링에 저장합니다.
 *
 * 기능 명세서에 "일단 url 쿼리스트링에 총 절감액 저장하는 걸로 러프하게 구현" 이라고
 * 적혀 있어 그대로 따랐습니다. 서버도 로그인도 없이 새로고침과 링크 공유를 견딥니다.
 *
 *   ?saved=4200&walks=3
 *
 * 값이 없거나 망가져 있으면 0으로 시작합니다. 링크를 받은 사람은 보낸 사람의 누적액을
 * 그대로 보게 되므로, 개인 기록이 아니라 "이만큼 아꼈다"를 자랑하는 용도에 가깝습니다.
 */

export interface SavingsTotal {
  /** 지금까지 걸어서 아낀 돈 합계 (원) */
  amount: number
  /** 걷기를 선택한 횟수 */
  walks: number
}

export const EMPTY_TOTAL: SavingsTotal = { amount: 0, walks: 0 }

const AMOUNT_KEY = 'saved'
const WALKS_KEY = 'walks'

/** 음수·소수·NaN·지나치게 큰 값을 걸러 0 이상의 정수로 만듭니다. */
function toCount(raw: string | null): number {
  if (raw === null) {
    return 0
  }
  const value = Number(raw)
  if (!Number.isFinite(value) || value <= 0) {
    return 0
  }
  return Math.min(Math.floor(value), Number.MAX_SAFE_INTEGER)
}

/** 현재 주소창에서 누적액을 읽습니다. */
export function readTotal(search: string = window.location.search): SavingsTotal {
  const params = new URLSearchParams(search)
  return {
    amount: toCount(params.get(AMOUNT_KEY)),
    walks: toCount(params.get(WALKS_KEY)),
  }
}

/** 누적액을 주소창에 반영합니다. 화면 이동 없이 주소만 바꿉니다. */
export function writeTotal(total: SavingsTotal): void {
  const params = new URLSearchParams(window.location.search)
  if (total.amount > 0) {
    params.set(AMOUNT_KEY, String(total.amount))
    params.set(WALKS_KEY, String(total.walks))
  } else {
    params.delete(AMOUNT_KEY)
    params.delete(WALKS_KEY)
  }
  const query = params.toString()
  const next = `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`
  window.history.replaceState(null, '', next)
}

/** 한 번 걸었을 때의 누적 결과를 계산합니다. 저장은 하지 않습니다. */
export function addWalk(total: SavingsTotal, amount: number): SavingsTotal {
  const gain = Number.isFinite(amount) && amount > 0 ? Math.floor(amount) : 0
  return { amount: total.amount + gain, walks: total.walks + 1 }
}

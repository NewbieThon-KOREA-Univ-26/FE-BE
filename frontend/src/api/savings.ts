import { getJson, postJson } from './client'
import { EMPTY_TOTAL, type SavingsTotal } from '../lib/savings'

const IS_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

interface ClaimResponse {
  total: string
  saved: number
  walks: number
  gained: number
}

/** 서버에 누적액 토큰이 진짜인지 묻습니다. 위조·손상이면 valid=false 와 0 이 옵니다. */
export async function verifyTotal(token: string): Promise<SavingsTotal> {
  if (IS_MOCK) {
    return { ...EMPTY_TOTAL, token }
  }
  const body = await getJson<{ saved: number; walks: number; valid: boolean }>('/api/savings', { total: token })
  return body.valid ? { amount: body.saved, walks: body.walks, token } : EMPTY_TOTAL
}

/**
 * F9 — 적립권을 서버에 내고 새 누적액을 받습니다.
 * 금액은 서버가 적립권에 서명해 둔 값이라 프론트가 임의로 정할 수 없습니다.
 */
export async function claimWalk(
  total: SavingsTotal,
  voucher: string | undefined,
  fallbackAmount: number,
): Promise<{ total: SavingsTotal; gained: number }> {
  if (IS_MOCK || !voucher) {
    // 목업 모드에는 서버가 없으므로 화면에서만 더합니다.
    const gained = Math.max(0, Math.floor(fallbackAmount))
    return { total: { amount: total.amount + gained, walks: total.walks + 1, token: 'mock.' + Date.now() }, gained }
  }
  const body = await postJson<ClaimResponse>('/api/savings/claim', { total: total.token, voucher })
  return { total: { amount: body.saved, walks: body.walks, token: body.total }, gained: body.gained }
}

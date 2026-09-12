import { formatWon } from '../utils/format'
import type { SavingsTotal } from '../lib/savings'

interface Props {
  total: SavingsTotal
  onReset: () => void
}

/** F8 절감액 누적 — 지금까지 걸어서 아낀 합계를 헤더에 보여줍니다. */
export function SavingsTotalBadge({ total, onReset }: Props) {
  if (total.amount <= 0) {
    return null
  }
  return (
    <div className="savings-total">
      <div className="savings-total-text">
        <span className="savings-total-label">지금까지 아낀 돈</span>
        <strong className="savings-total-amount">{formatWon(total.amount)}</strong>
        <span className="savings-total-count">{total.walks}번 걸었어요</span>
      </div>
      <button type="button" className="link" onClick={onReset}>
        초기화
      </button>
    </div>
  )
}

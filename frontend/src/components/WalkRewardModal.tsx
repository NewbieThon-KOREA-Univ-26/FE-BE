import { useEffect, useRef } from 'react'
import { formatWon } from '../utils/format'
import type { SavingsTotal } from '../lib/savings'

interface Props {
  /** 이번에 걸어서 아낀 금액 (원) */
  amount: number
  /** 적립 후의 누적 결과 */
  total: SavingsTotal
  onClose: () => void
}

/**
 * F9 절감액 적립 — 걷기를 선택했을 때 뜨는 팝업.
 * 이번에 아낀 금액을 크게 보여주고, 누적 합계를 함께 알려줍니다.
 */
export function WalkRewardModal({ amount, total, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null)

  // 팝업이 열리면 닫기 버튼으로 초점을 옮기고, Esc 로 닫습니다.
  useEffect(() => {
    closeRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="reward-title"
        onClick={(event) => event.stopPropagation()}
      >
        <p className="modal-emoji" aria-hidden="true">🎉</p>
        <h2 id="reward-title" className="modal-title">걸어서 아꼈어요</h2>
        <p className="modal-amount">+{formatWon(amount)}</p>

        <dl className="modal-total">
          <div>
            <dt>지금까지 아낀 돈</dt>
            <dd>{formatWon(total.amount)}</dd>
          </div>
          <div>
            <dt>걸어간 횟수</dt>
            <dd>{total.walks}회</dd>
          </div>
        </dl>

        <p className="modal-note">주소창에 저장돼서 새로고침해도 남아 있습니다.</p>

        <button ref={closeRef} type="button" className="primary" onClick={onClose}>
          좋아요
        </button>
      </div>
    </div>
  )
}

import { useCallback, useEffect, useState } from 'react'
import { ErrorBanner } from './components/ErrorBanner'
import { MapPanel } from './components/MapPanel'
import { ResultPanel } from './components/ResultPanel'
import { RouteForm } from './components/RouteForm'
import { SavingsTotalBadge } from './components/SavingsTotalBadge'
import { WalkRewardModal } from './components/WalkRewardModal'
import { useCompare } from './hooks/useCompare'
import { claimWalk, verifyTotal } from './api/savings'
import { EMPTY_TOTAL, readTotal, writeTotal, type SavingsTotal } from './lib/savings'
import type { Place } from './types/place'

/**
 * 한 페이지 구성: 전체 화면 지도 위에 검색 패널과 결과 시트를 얹습니다.
 * 결과가 나오면 지도에 도보·대중교통 경로 선이 함께 그려집니다.
 *
 * F8 절감액 누적은 주소창 쿼리스트링에, F9 적립 팝업은 걷기를 선택했을 때 뜹니다.
 */
export default function App() {
  const [start, setStart] = useState<Place | null>(null)
  const [end, setEnd] = useState<Place | null>(null)
  const { state, run, reset } = useCompare()

  // F8 — 새로고침해도 남도록 주소창에서 읽어 시작합니다.
  const [total, setTotal] = useState<SavingsTotal>(() => readTotal())
  // 적립 실패 안내 (적립권 만료·중복 등). 성공하면 지웁니다.
  const [claimError, setClaimError] = useState<string | null>(null)

  // 주소창의 누적액 토큰은 서버 서명으로 검증합니다. 위조·손상이면 0 으로 되돌립니다.
  useEffect(() => {
    const token = readTotal().token
    if (!token) {
      return
    }
    let alive = true
    verifyTotal(token)
      .then((verified) => {
        if (!alive) return
        setTotal(verified)
        writeTotal(verified)
      })
      .catch(() => {
        // 서버에 닿지 못하면 화면 값은 두고, 적립 시점에 다시 검증됩니다.
      })
    return () => {
      alive = false
    }
  }, [])
  // F9 — 팝업에 띄울 이번 적립액. null 이면 팝업이 닫힌 상태입니다.
  const [reward, setReward] = useState<number | null>(null)
  // 같은 결과로 두 번 적립하지 않도록 표시합니다.
  const [rewarded, setRewarded] = useState(false)

  const result = state.status === 'success' ? state.data : null

  const compare = () => {
    if (start && end) {
      setRewarded(false)
      void run(start, end)
    }
  }

  const resetSearch = () => {
    setStart(null)
    setEnd(null)
    setRewarded(false)
    reset()
  }

  /** F9 — 걷기를 선택하면 절감액을 누적하고 팝업을 띄웁니다. */
  const chooseWalk = useCallback(async () => {
    if (!result || rewarded) {
      return
    }
    try {
      const { total: next, gained } = await claimWalk(total, result.savings.voucher, result.savings.amount)
      setTotal(next)
      writeTotal(next)
      setClaimError(null)
      setRewarded(true)
      setReward(gained)
    } catch (error) {
      setClaimError(error instanceof Error ? error.message : '적립에 실패했습니다')
    }
  }, [result, rewarded, total])

  const resetTotal = () => {
    setTotal(EMPTY_TOTAL)
    writeTotal(EMPTY_TOTAL)
    setRewarded(false)
  }

  return (
    <div className="app">
      <main className="app-main">
        <section className="panel panel-side">
          <div className="search-panel">
            <header className="app-header">
              <div>
                <a
                  className="brand-link"
                  href={`${window.location.pathname}${window.location.search}`}
                  aria-label="처음 화면으로 (새로고침)"
                >
                  <img className="brand-logo" src="/logo.png" alt="이 정도면… 걸을만한데?" />
                </a>
                <p>애매한 거리, 걸으면 얼마를 아끼는지 바로 알려드립니다.</p>
              </div>
            </header>
            <SavingsTotalBadge total={total} onReset={resetTotal} />
            {claimError && (
              <p className="status status-error" role="alert">적립 실패: {claimError}</p>
            )}
            <RouteForm
              start={start}
              end={end}
              onStartChange={(place) => { setStart(place); reset() }}
              onEndChange={(place) => { setEnd(place); reset() }}
              onSubmit={compare}
              loading={state.status === 'loading'}
            />
          </div>
          {state.status === 'loading' && (
            <p className="status" aria-live="polite">
              도보와 대중교통 경로를 비교하는 중…
            </p>
          )}
          {state.status === 'error' && <ErrorBanner error={state.error} onRetry={compare} />}
          {result && (
            <ResultPanel
              data={result}
              onReset={resetSearch}
              onWalkChosen={chooseWalk}
              rewarded={rewarded}
            />
          )}
        </section>

        <section className="panel panel-map" aria-label="지도">
          <MapPanel start={start} end={end} data={result} />
        </section>
      </main>

      {reward !== null && (
        <WalkRewardModal amount={reward} total={total} onClose={() => setReward(null)} />
      )}
    </div>
  )
}

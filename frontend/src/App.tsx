import { useCallback, useState } from 'react'
import { ErrorBanner } from './components/ErrorBanner'
import { MapPanel } from './components/MapPanel'
import { ResultPanel } from './components/ResultPanel'
import { RouteForm } from './components/RouteForm'
import { SavingsTotalBadge } from './components/SavingsTotalBadge'
import { WalkRewardModal } from './components/WalkRewardModal'
import { useCompare } from './hooks/useCompare'
import { EMPTY_TOTAL, addWalk, readTotal, writeTotal, type SavingsTotal } from './lib/savings'
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
  const chooseWalk = useCallback(() => {
    if (!result || rewarded) {
      return
    }
    const amount = result.savings.amount
    const next = addWalk(total, amount)
    setTotal(next)
    writeTotal(next)
    setRewarded(true)
    setReward(amount)
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
                <h1>걸을만한데?</h1>
                <p>한 정거장 거리, 걸으면 얼마를 아끼는지 바로 알려드립니다.</p>
              </div>
            </header>
            <SavingsTotalBadge total={total} onReset={resetTotal} />
            <RouteForm
              start={start}
              end={end}
              onStartChange={setStart}
              onEndChange={setEnd}
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
          <MapPanel start={start} end={end} result={result} />
        </section>
      </main>

      {reward !== null && (
        <WalkRewardModal amount={reward} total={total} onClose={() => setReward(null)} />
      )}
    </div>
  )
}

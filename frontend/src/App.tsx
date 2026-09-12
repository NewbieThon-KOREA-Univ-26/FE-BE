import { useState } from 'react'
import { IS_MOCK } from './api/compare'
import { ErrorBanner } from './components/ErrorBanner'
import { MapPanel } from './components/MapPanel'
import { ResultPanel } from './components/ResultPanel'
import { RouteForm } from './components/RouteForm'
import { useCompare } from './hooks/useCompare'
import type { Place } from './types/place'

/**
 * 한 페이지 구성: 왼쪽 = 입력 폼 + 비교 결과, 오른쪽 = 지도 (사용자 흐름 문서의 화면 스케치).
 * 상세 화면(3번, 선택)은 아직 없고, 필요해지면 라우터를 붙여 페이지로 나누면 됩니다.
 */
export default function App() {
  const [start, setStart] = useState<Place | null>(null)
  const [end, setEnd] = useState<Place | null>(null)
  const { state, run, reset } = useCompare()

  const compare = () => {
    if (start && end) {
      void run(start, end)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>걸을까 탈까</h1>
          <p>한 정거장 거리, 걸으면 얼마를 아끼는지 바로 알려드립니다.</p>
        </div>
        {IS_MOCK && (
          <span className="badge" title="VITE_USE_MOCK=true 라서 백엔드 대신 예시 응답을 씁니다">
            예시 데이터 모드
          </span>
        )}
      </header>

      <main className="app-main">
        <section className="panel panel-side">
          <RouteForm
            start={start}
            end={end}
            onStartChange={setStart}
            onEndChange={setEnd}
            onSubmit={compare}
            loading={state.status === 'loading'}
          />
          {state.status === 'loading' && (
            <p className="status" aria-live="polite">
              도보와 대중교통 경로를 비교하는 중…
            </p>
          )}
          {state.status === 'error' && <ErrorBanner error={state.error} onRetry={compare} />}
          {state.status === 'success' && <ResultPanel data={state.data} onReset={reset} />}
        </section>

        <section className="panel panel-map" aria-label="지도">
          <MapPanel start={start} end={end} />
        </section>
      </main>
    </div>
  )
}

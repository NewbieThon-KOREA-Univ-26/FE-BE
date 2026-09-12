import type { CompareResponse } from '../types/api'
import { useState } from 'react'
import { formatDistance, formatMinutes, formatWon } from '../utils/format'

interface Props {
  data: CompareResponse
  onReset: () => void
  /** F9 — 걷기를 선택했을 때. 절감액을 누적하고 팝업을 띄웁니다. */
  onWalkChosen: () => void
  /** 이번 결과로 이미 적립했는지 */
  rewarded: boolean
}

/**
 * 2. 비교 결과 화면 (핵심 화면, F5).
 * 가장 크게: 걸으면 아끼는 돈 / 나란히: 걷기 vs 대중교통 / 한 줄 결론: recommendation.reason 그대로.
 */
export function ResultPanel({ data, onReset, onWalkChosen, rewarded }: Props) {
  const [expanded, setExpanded] = useState(false)
  const { walk, transit, savings, recommendation } = data
  const walkRecommended = recommendation.choice === 'walk'

  return (
    <section className={`result ${walkRecommended ? 'result-walk' : 'result-transit'} ${expanded ? 'is-expanded' : ''}`} aria-live="polite">
      <div
        className="result-hero"
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            setExpanded((value) => !value)
          }
        }}
      >
        <p className="result-label">{walkRecommended ? '걸으면 아끼는 돈' : '걸으면 아끼지만'}</p>
        <p className="result-amount">{formatWon(savings.amount)}</p>
        <p className="result-sub">{formatMinutes(savings.extraMinutes)} 더 걸림</p>
        <small className="result-expand-hint">{expanded ? '터치하면 요약으로 돌아가기' : '터치하면 상세 정보 보기'}</small>
      </div>

      <p className="result-conclusion">
        <strong>{walkRecommended ? '걷는 걸 추천합니다' : '타는 게 낫습니다'}</strong>
        <span>{recommendation.reason}</span>
      </p>

      <div className="compare-grid">
        <article className={`compare-card card-walk ${walkRecommended ? 'is-recommended' : ''}`}>
          <h3>🚶 걷기</h3>
          <dl>
            <div>
              <dt>소요시간</dt>
              <dd>{formatMinutes(walk.duration)}</dd>
            </div>
            <div>
              <dt>거리</dt>
              <dd>{formatDistance(walk.distance)}</dd>
            </div>
            <div>
              <dt>요금</dt>
              <dd>0원</dd>
            </div>
            {walk.calories !== undefined && (
              <div>
                <dt>소모 열량</dt>
                <dd>{walk.calories}kcal</dd>
              </div>
            )}
          </dl>
        </article>

        <article className={`compare-card card-transit ${walkRecommended ? '' : 'is-recommended'}`}>
          <h3>🚇 대중교통</h3>
          <dl>
            <div>
              <dt>소요시간</dt>
              <dd>{formatMinutes(transit.duration)}</dd>
            </div>
            <div>
              <dt>요금</dt>
              <dd>{formatWon(transit.fare)}</dd>
            </div>
            <div>
              <dt>환승</dt>
              <dd>{transit.transfers}회</dd>
            </div>
            <div>
              <dt>포함된 도보</dt>
              <dd>
                {formatDistance(transit.walkDistance)} · {formatMinutes(transit.walkDuration)}
              </dd>
            </div>
          </dl>
        </article>
      </div>

      <div className="result-actions">
        {savings.amount > 0 && (
          <button
            type="button"
            className={`primary walk-choice ${rewarded ? 'is-done' : ''}`}
            onClick={onWalkChosen}
            disabled={rewarded}
          >
            {rewarded ? '적립했어요' : `🚶 걸어갈래요 (+${formatWon(savings.amount)})`}
          </button>
        )}
        <button type="button" className="secondary" onClick={onReset}>
          다시 검색
        </button>
      </div>
    </section>
  )
}

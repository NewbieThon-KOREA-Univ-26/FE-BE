import type { CompareResponse } from '../types/api'
import { useLayoutEffect, useRef, useState, type CSSProperties } from 'react'
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
  const [searchHidden, setSearchHidden] = useState(false)
  const [detailTab, setDetailTab] = useState<'comparison' | 'transit'>('comparison')
  const [dragOffset, setDragOffset] = useState(0)
  const dragStart = useRef<{ id: number; y: number } | null>(null)
  const sectionRef = useRef<HTMLElement>(null)
  const previousTop = useRef<number | null>(null)
  const transition = useRef<Animation | null>(null)

  useLayoutEffect(() => {
    const element = sectionRef.current
    const from = previousTop.current
    previousTop.current = null
    if (!element || from === null || !window.matchMedia('(max-width: 860px)').matches ||
      window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    transition.current?.cancel()
    const delta = from - element.getBoundingClientRect().top
    transition.current = element.animate([
      { transform: `translateY(${delta}px)`, opacity: 0.85 },
      { transform: 'translateY(0)', opacity: 1 },
    ], { duration: 320, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' })
    return () => transition.current?.cancel()
  }, [expanded])

  const capturePosition = () => {
    previousTop.current = sectionRef.current?.getBoundingClientRect().top ?? null
  }

  const closeDetails = () => {
    if (expanded) capturePosition()
    dragStart.current = null
    setDragOffset(0)
    setExpanded(false)
    setSearchHidden(false)
  }
  const toggleDetails = () => {
    if (expanded) {
      closeDetails()
    } else {
      capturePosition()
      setSearchHidden(true)
      setDetailTab('comparison')
      setExpanded(true)
    }
  }
  const returnToSearch = () => {
    closeDetails()
    setSearchHidden(false)
  }
  const { walk, transit, savings, recommendation } = data
  const weather = data.weather
  const walkRecommended = recommendation.choice === 'walk'

  return (
    <section
      ref={sectionRef}
      className={`result ${walkRecommended ? 'result-walk' : 'result-transit'} ${expanded ? 'is-expanded' : ''} ${searchHidden ? 'is-search-hidden' : ''} ${dragOffset > 0 ? 'is-dragging' : ''}`}
      style={{ '--result-drag-offset': `${dragOffset}px` } as CSSProperties}
      aria-live="polite"
      onKeyDown={(event) => { if (event.key === 'Escape') returnToSearch() }}
    >
      {expanded && (
        <div className="result-close-bar">
          <button type="button" className="result-close" aria-label="검색창과 요약으로 돌아가기" onClick={returnToSearch}>
            <span aria-hidden="true">×</span>
          </button>
        </div>
      )}
      {expanded && (
        <button
          type="button"
          className="result-drag-handle"
          aria-label="상세보기 접고 지도 보기"
          onPointerDown={(event) => {
            if (!event.isPrimary || event.button !== 0) return
            dragStart.current = { id: event.pointerId, y: event.clientY }
            event.currentTarget.setPointerCapture(event.pointerId)
          }}
          onPointerMove={(event) => {
            if (dragStart.current?.id !== event.pointerId) return
            setDragOffset(Math.max(0, event.clientY - dragStart.current.y))
          }}
          onPointerUp={(event) => {
            if (dragStart.current?.id !== event.pointerId) return
            const distance = event.clientY - dragStart.current.y
            dragStart.current = null
            setDragOffset(0)
            if (distance >= 64) closeDetails()
          }}
          onPointerCancel={() => { dragStart.current = null; setDragOffset(0) }}
          onLostPointerCapture={() => { dragStart.current = null; setDragOffset(0) }}
          onClick={(event) => { if (event.detail === 0) closeDetails() }}
        >
          <span aria-hidden="true" />
        </button>
      )}
      <div
        className="result-hero"
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        onClick={toggleDetails}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            toggleDetails()
          }
        }}
      >
        <p className="result-label">{walkRecommended ? '걸으면 아끼는 돈' : '걸으면 절약'}</p>
        <p className="result-amount">{formatWon(savings.amount)}</p>
        <p className="result-sub">{Math.round(savings.extraMinutes) === 0 ? '소요시간이 같아요'
          : `${formatMinutes(Math.abs(savings.extraMinutes))} ${savings.extraMinutes < 0 ? '더 빠름' : '더 걸립니다'}`}</p>
        <small className="result-expand-hint">{expanded ? '터치하면 요약으로 돌아가기' : '터치하면 상세 정보 보기'}</small>
      </div>

      <p className="result-conclusion">
        <strong>{walkRecommended ? '걷는 걸 추천합니다' : '타는 게 낫습니다'}</strong>
        <span>
          {recommendation.reason}
          {expanded && recommendation.weatherReason && ` · ${recommendation.weatherReason}`}
        </span>
      </p>

      {expanded && weather && (
        <div className="weather-summary">
          {weather.iconUrl ? (
            <img src={weather.iconUrl} alt="" />
          ) : (
            <span className="weather-emoji" aria-hidden="true">
              {weather.condition.includes('비') ? '🌧️' : weather.condition.includes('눈') ? '❄️' : '☀️'}
            </span>
          )}
          <span>현재 날씨: {weather.condition}</span>
          {weather.temperatureC !== undefined && <strong>{weather.temperatureC}°C</strong>}
          {weather.precipitationProbability !== undefined && (
            <small>강수확률 {weather.precipitationProbability}%</small>
          )}
        </div>
      )}

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

        {detailTab === 'comparison' ? (
          <article
            className={`compare-card card-transit ${walkRecommended ? '' : 'is-recommended'} ${expanded ? 'is-clickable' : ''}`}
            role={expanded ? 'button' : undefined}
            tabIndex={expanded ? 0 : undefined}
            onClick={() => { if (expanded) setDetailTab('transit') }}
            onKeyDown={(event) => {
              if (expanded && (event.key === 'Enter' || event.key === ' ')) {
                event.preventDefault()
                setDetailTab('transit')
              }
            }}
          >
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
                <dt>도보 구간</dt>
                <dd>
                  {formatDistance(transit.walkDistance)} · {formatMinutes(transit.walkDuration)}
                </dd>
              </div>
            </dl>
            {expanded && <small className="transit-card-hint">눌러서 경로 보기</small>}
          </article>
        ) : (
          <div
            className="transit-route is-clickable"
            role="button"
            tabIndex={0}
            aria-label="다시 누르면 대중교통 정보 카드로 돌아가기"
            onClick={() => setDetailTab('comparison')}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                setDetailTab('comparison')
              }
            }}
          >
          <div className="transit-route-header">
            <strong>대중교통 경로</strong>
            <span>{formatMinutes(transit.duration)} · 환승 {transit.transfers}회</span>
          </div>
          {transit.routeSteps?.length ? (
            <ol className="route-timeline">
              {transit.routeSteps.map((step, index) => (
                <li
                  key={`${step.mode}-${step.lineName ?? 'route'}-${index}`}
                  className={`route-leg route-leg-${step.mode}`}
                  aria-label={`${step.lineName ?? (step.mode === 'subway' ? '지하철' : '버스')}, ${step.fromName ?? '승차 지점'}에서 타고 ${step.toName ?? '하차 지점'}에서 내림`}
                >
                  <span className="route-badge" title={step.lineName} aria-hidden="true">
                    {shortLine(step.lineName, step.mode)}
                  </span>
                  <div className="route-stops">
                    <div className="route-stop route-stop-board">
                      <strong>{step.fromName ?? '승차 지점'}</strong>
                      {step.direction && <span className="route-dir">{step.direction} 방면</span>}
                    </div>
                    <div className="route-stop route-stop-alight">{step.toName ?? '하차 지점'}</div>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <p className="transit-route-empty">역 이름 정보를 제공하지 않는 경로입니다. 지도에서 대중교통 경로를 확인해 주세요.</p>
          )}
          </div>
        )}
      </div>

      {/* 모바일에서 요약만 보일 때 감추는 일은 CSS 가 합니다.
          여기서 expanded 로 걸러내면 데스크톱에서도 "다시 검색" 이 사라집니다. */}
      <p className="status">지도: 빨간색은 도보 · 파란색은 버스·지하철 탑승 구간입니다.</p>
      {[walk.geometryWarning, transit.geometryWarning].filter(Boolean).map((message) => (
        <p className="status" role="status" key={message}>{message}</p>
      ))}
      {!walk.paths?.length && !transit.paths?.length && !walk.geometryWarning && !transit.geometryWarning && (
        <p className="status">이 결과에는 지도 경로가 없습니다. 거리·시간 비교를 참고해 주세요.</p>
      )}

      <p className="attribution">경로 정보 제공: 카카오맵</p>

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

/**
 * 배지에 넣을 짧은 노선 표기. "6호선" → "6", "공항철도" → "공항", "273" → "273".
 * 길면 앞 세 글자만 씁니다. 전체 이름은 배지의 title 과 aria-label 에 있습니다.
 */
function shortLine(name: string | undefined, mode: 'bus' | 'subway'): string {
  if (!name) {
    return mode === 'subway' ? '지하철' : '버스'
  }
  const trimmed = name.replace(/\s*\(.*\)$/, '').trim()
  const line = trimmed.match(/^(\d+)호선/)
  if (line) {
    return line[1]
  }
  if (trimmed.includes('공항')) {
    return '공항'
  }
  const number = trimmed.match(/[A-Za-z가-힣]?\d+[A-Za-z0-9-]*/)
  if (number && number[0].length <= 5) {
    return number[0]
  }
  return trimmed.slice(0, 3)
}

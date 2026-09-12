import type { CompareResponse } from '../types/api'
import { useLayoutEffect, useRef, useState, type CSSProperties } from 'react'
import { formatDistance, formatMinutes, formatWon } from '../utils/format'

interface Props {
  data: CompareResponse
  onReset: () => void
}

/**
 * 2. 비교 결과 화면 (핵심 화면, F5).
 * 가장 크게: 걸으면 아끼는 돈 / 나란히: 걷기 vs 대중교통 / 한 줄 결론: recommendation.reason 그대로.
 */
export function ResultPanel({ data, onReset }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [searchHidden, setSearchHidden] = useState(false)
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
        <p className="result-label">{walkRecommended ? '걸으면 아끼는 돈' : '걸으면 아끼지만'}</p>
        <p className="result-amount">{formatWon(savings.amount)}</p>
        <p className="result-sub">{formatMinutes(savings.extraMinutes)} 더 걸림</p>
        <small className="result-expand-hint">{expanded ? '터치하면 요약으로 돌아가기' : '터치하면 상세 정보 보기'}</small>
      </div>

      <p className="result-conclusion">
        <strong>{walkRecommended ? '걷는 걸 추천합니다' : '타는 게 낫습니다'}</strong>
        <span>
          {recommendation.reason}
          {recommendation.weatherReason && ` · ${recommendation.weatherReason}`}
        </span>
      </p>

      {weather && (
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

      <button type="button" className="secondary" onClick={onReset}>
        다시 검색
      </button>
    </section>
  )
}

import { useEffect, useRef, useState } from 'react'
import { hasKakaoKey, loadKakaoSdk } from '../lib/kakao'
import type { KakaoMap, KakaoMarker, KakaoPolyline } from '../types/kakao'
import type { CompareResponse } from '../types/api'
import type { Place } from '../types/place'

interface Props {
  start: Place | null
  end: Place | null
  data: CompareResponse | null
}

/** 지도 첫 화면 중심. 서울시청 부근. */
const DEFAULT_CENTER = { x: 126.978, y: 37.5665 }

/** 노션 화면 스케치의 선 색: 도보는 빨강, 대중교통은 파랑. */
const WALK_COLOR = '#e0453b'
const TRANSIT_COLOR = '#2563eb'

/**
 * 오른쪽 지도 영역. 카카오 키가 있으면 지도를 띄우고 출발지·도착지 마커를 찍습니다.
 * 응답의 실제 좌표로 도보 및 대중교통 경로를 구간별로 표시합니다.
 */
export function MapPanel({ start, end, data }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<KakaoMap | null>(null)
  const markersRef = useRef<KakaoMarker[]>([])
  const [status, setStatus] = useState<'idle' | 'ready' | 'error'>('idle')
  const [message, setMessage] = useState<string>('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!hasKakaoKey || !containerRef.current) {
      return
    }
    let cancelled = false
    setStatus('idle')
    setMessage('')
    loadKakaoSdk()
      .then((kakao) => {
        if (cancelled || !containerRef.current) {
          return
        }
        mapRef.current = new kakao.maps.Map(containerRef.current, {
          center: new kakao.maps.LatLng(DEFAULT_CENTER.y, DEFAULT_CENTER.x),
          level: 5,
        })
        setStatus('ready')
      })
      .catch((cause: Error) => {
        if (!cancelled) {
          setStatus('error')
          setMessage(cause.message)
        }
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  useEffect(() => {
    const map = mapRef.current
    const kakao = window.kakao
    if (status !== 'ready' || !map || !kakao) {
      return
    }
    for (const marker of markersRef.current) {
      marker.setMap(null)
    }
    markersRef.current = []

    const points = [start, end].filter((place): place is Place => place !== null)
    if (points.length === 0) {
      return
    }
    for (const point of points) {
      const position = new kakao.maps.LatLng(point.y, point.x)
      markersRef.current.push(new kakao.maps.Marker({ position, map }))
    }
    const fitPoints = points.map((point) => new kakao.maps.LatLng(point.y, point.x))
    const lines: KakaoPolyline[] = []
    for (const [paths, color] of [
      [data?.transit.paths, TRANSIT_COLOR], [data?.walk.paths, WALK_COLOR],
    ] as const) {
      for (const section of paths ?? []) {
        const path = section.filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y)
          && Math.abs(p.x) <= 180 && Math.abs(p.y) <= 90)
          .map((p) => new kakao.maps.LatLng(p.y, p.x))
        if (path.length < 2) continue
        path.forEach((point) => fitPoints.push(point))
        lines.push(new kakao.maps.Polyline({ map, path, strokeWeight: 5,
          strokeColor: color, strokeOpacity: 0.85, strokeStyle: 'solid' }))
      }
    }
    const layout = containerRef.current?.closest('.app-main')
    const panel = layout?.querySelector<HTMLElement>('.panel-side')
    if (!panel) return () => { lines.forEach((line) => line.setMap(null)) }
    let frame = 0
    let lastLayout = ''
    const fitMap = () => {
      const canvas = containerRef.current
      if (!canvas) return
      const rect = canvas.getBoundingClientRect()
      const mobile = window.matchMedia('(max-width: 860px)').matches
      let top = 40
      let bottom = 24
      let left = 24
      const right = 24
      if (mobile) {
        const searchElement = panel.querySelector<HTMLElement>('.search-panel')
        const result = panel.querySelector<HTMLElement>('.result')
        const panelTop = panel.getBoundingClientRect().top
        // transform 애니메이션 중의 위치 대신 전환이 끝날 레이아웃 위치로 한 번만 맞춥니다.
        const searchVisible = !result?.classList.contains('is-search-hidden')
        top = searchElement && searchVisible
          ? Math.max(40, panelTop + searchElement.offsetTop + searchElement.offsetHeight - rect.top + 40)
          : 40
        if (result) {
          const resultTop = result.classList.contains('is-expanded')
            ? result.offsetTop
            : panelTop + result.offsetTop
          bottom = Math.max(24, rect.bottom - resultTop + 24)
        }
        // 작은 화면/키보드에서도 여백이 지도 높이를 모두 차지하지 않도록 제한합니다.
        const availablePadding = Math.max(0, rect.height - 120)
        if (top + bottom > availablePadding) {
          const scale = availablePadding / (top + bottom)
          top *= scale
          bottom *= scale
        }
      } else {
        left = panel.getBoundingClientRect().right - rect.left + 40
      }
      const layoutKey = [rect.width, rect.height, top, right, bottom, left].map(Math.round).join(',')
      if (layoutKey === lastLayout) return
      lastLayout = layoutKey
      // 실제 지도를 이동시키지 않고 현재 투영 좌표에서 목표 배율과 중심을 계산합니다.
      const projection = map.getProjection()
      const pixels = fitPoints.map((point) => projection.containerPointFromCoords(point))
      const minX = Math.min(...pixels.map((point) => point.x))
      const maxX = Math.max(...pixels.map((point) => point.x))
      const minY = Math.min(...pixels.map((point) => point.y))
      const maxY = Math.max(...pixels.map((point) => point.y))
      const currentLevel = map.getLevel()
      const ratio = Math.max((maxX - minX) / Math.max(1, rect.width - left - right),
        (maxY - minY) / Math.max(1, rect.height - top - bottom))
      const nextLevel = fitPoints.length === 1 || ratio === 0 ? 4
        : Math.max(1, Math.min(14, currentLevel + Math.ceil(Math.log2(ratio))))
      const scale = 2 ** (nextLevel - currentLevel)
      const center = projection.coordsFromContainerPoint(new kakao.maps.Point(
        (minX + maxX) / 2 + (right - left) * scale / 2,
        (minY + maxY) / 2 + (bottom - top) * scale / 2,
      ))
      map.jump(center, nextLevel, {
        animate: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? false : { duration: 320 },
      })
    }
    const scheduleFit = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(fitMap)
    }
    const resize = new ResizeObserver(scheduleFit)
    resize.observe(containerRef.current!)
    const observePanels = () => {
      for (const element of panel.querySelectorAll('.search-panel, .result')) resize.observe(element)
      scheduleFit()
    }
    const changes = new MutationObserver(observePanels)
    changes.observe(panel, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] })
    observePanels()
    window.addEventListener('resize', scheduleFit)
    return () => {
      cancelAnimationFrame(frame)
      resize.disconnect()
      changes.disconnect()
      window.removeEventListener('resize', scheduleFit)
      lines.forEach((line) => line.setMap(null))
    }
  }, [start, end, status, data])

  useEffect(() => {
    if (status !== 'ready' || !containerRef.current) return
    const canvas = containerRef.current
    const layout = canvas.closest('.app-main')
    const panel = layout?.querySelector<HTMLElement>('.panel-side')
    let frame = 0
    let trackingUntil = 0

    const positionScale = () => {
      const scale = Array.from(canvas.children).find((element): element is HTMLElement =>
        element instanceof HTMLElement &&
        /^\d+(?:\.\d+)?(?:m|km)$/.test(element.textContent?.trim() ?? '') &&
        element.style.position === 'absolute')
      const canvasRect = canvas.getBoundingClientRect()
      const result = panel?.querySelector<HTMLElement>('.result')
      const legend = layout?.querySelector<HTMLElement>('.map-legend')
      const mobile = window.matchMedia('(max-width: 860px)').matches
      const bottom = mobile && result
        ? Math.max(14, canvasRect.bottom - result.getBoundingClientRect().top + 12)
        : 14
      if (scale) {
        scale.style.setProperty('left', 'auto', 'important')
        scale.style.setProperty('right', '14px', 'important')
        scale.style.setProperty('bottom', `${bottom}px`, 'important')
      }
      if (mobile && legend) {
        legend.style.bottom = `${bottom}px`
      }
    }

    const updatePosition = () => {
      positionScale()
      if (performance.now() < trackingUntil) {
        frame = requestAnimationFrame(updatePosition)
      }
    }
    const schedulePosition = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(updatePosition)
    }
    const trackTransition = () => {
      trackingUntil = performance.now() + 400
      schedulePosition()
    }
    const changes = new MutationObserver(trackTransition)
    changes.observe(canvas, { childList: true, subtree: true, characterData: true })
    if (panel) changes.observe(panel, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] })
    const resize = new ResizeObserver(schedulePosition)
    resize.observe(canvas)
    if (panel) resize.observe(panel)
    window.addEventListener('resize', trackTransition)
    trackTransition()
    return () => {
      cancelAnimationFrame(frame)
      changes.disconnect()
      resize.disconnect()
      window.removeEventListener('resize', trackTransition)
    }
  }, [status, data])

  if (!hasKakaoKey) {
    return (
      <div className="map map-placeholder">
        <p>지도 영역</p>
        <small>.env 에 VITE_KAKAO_MAP_KEY 를 넣으면 카카오 지도가 표시됩니다.</small>
      </div>
    )
  }

  return (
    <div className="map">
      <div ref={containerRef} className="map-canvas" />
      {status === 'ready' && data && (
        <div className="map-legend">
          <span className="legend-item">
            <i className="legend-line legend-walk" aria-hidden="true" />
            도보
          </span>
          <span className="legend-item">
            <i className="legend-line legend-transit" aria-hidden="true" />
            대중교통
          </span>
        </div>
      )}
      {status === 'idle' && <p className="map-overlay">지도를 불러오는 중…</p>}
      {status === 'error' && (
        <div className="map-overlay map-error" role="alert">
          <p>{message}</p>
          <button type="button" onClick={() => setAttempt((value) => value + 1)}>지도 다시 불러오기</button>
        </div>
      )}
    </div>
  )
}

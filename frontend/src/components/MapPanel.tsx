import { useEffect, useRef, useState } from 'react'
import { hasKakaoKey, loadKakaoSdk } from '../lib/kakao'
import type { KakaoMap, KakaoMarker, KakaoPolyline } from '../types/kakao'
import type { CompareResponse, Coordinate } from '../types/api'
import type { Place } from '../types/place'

interface Props {
  start: Place | null
  end: Place | null
  /** 비교 결과. 있으면 도보·대중교통 경로 선을 그립니다. */
  result?: CompareResponse | null
}

/** 지도 첫 화면 중심. 서울시청 부근. */
const DEFAULT_CENTER = { x: 126.978, y: 37.5665 }

/** 노션 화면 스케치의 선 색: 도보는 빨강, 대중교통은 파랑. */
const WALK_COLOR = '#e0453b'
const TRANSIT_COLOR = '#2563eb'

/**
 * 오른쪽 지도 영역. 카카오 키가 있으면 지도를 띄우고 출발지·도착지 마커를 찍습니다.
 * 비교 결과가 오면 도보(빨강)와 대중교통(파랑) 경로 선을 함께 그립니다.
 *
 * 백엔드가 좌표를 주면 그 좌표를 잇고, 좌표가 없으면 출발지-도착지 직선을 점선으로
 * 그린 뒤 "직선 표시" 라고 알립니다. 실제 경로인 척하지 않기 위해서입니다.
 */
export function MapPanel({ start, end, result }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<KakaoMap | null>(null)
  const markersRef = useRef<KakaoMarker[]>([])
  const linesRef = useRef<KakaoPolyline[]>([])
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
    for (const line of linesRef.current) {
      line.setMap(null)
    }
    markersRef.current = []
    linesRef.current = []

    const points = [start, end].filter((place): place is Place => place !== null)
    if (points.length === 0) {
      return
    }
    for (const point of points) {
      const position = new kakao.maps.LatLng(point.y, point.x)
      markersRef.current.push(new kakao.maps.Marker({ position, map }))
    }

    // 경로 선. 백엔드 좌표가 없으면 출발지-도착지 직선을 점선으로 대신 그립니다.
    if (result && start && end) {
      const straight: Coordinate[] = [
        { x: start.x, y: start.y },
        { x: end.x, y: end.y },
      ]
      const lines = [
        { coords: result.transit.path, color: TRANSIT_COLOR, weight: 6 },
        { coords: result.walk.path, color: WALK_COLOR, weight: 4 },
      ]
      for (const { coords, color, weight } of lines) {
        const exact = !!coords && coords.length >= 2
        const source = exact ? coords! : straight
        linesRef.current.push(
          new kakao.maps.Polyline({
            path: source.map((point) => new kakao.maps.LatLng(point.y, point.x)),
            strokeWeight: weight,
            strokeColor: color,
            strokeOpacity: exact ? 0.85 : 0.55,
            strokeStyle: exact ? 'solid' : 'shortdash',
          }),
        )
      }
      for (const line of linesRef.current) {
        line.setMap(map)
      }
    }

    const layout = containerRef.current?.closest('.app-main')
    const panel = layout?.querySelector<HTMLElement>('.panel-side')
    if (!panel) return
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
      const pixels = points.map((point) => projection.containerPointFromCoords(new kakao.maps.LatLng(point.y, point.x)))
      const minX = Math.min(...pixels.map((point) => point.x))
      const maxX = Math.max(...pixels.map((point) => point.x))
      const minY = Math.min(...pixels.map((point) => point.y))
      const maxY = Math.max(...pixels.map((point) => point.y))
      const currentLevel = map.getLevel()
      const ratio = Math.max((maxX - minX) / Math.max(1, rect.width - left - right),
        (maxY - minY) / Math.max(1, rect.height - top - bottom))
      const nextLevel = points.length === 1 || ratio === 0 ? 4
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

    }
  }, [start, end, result, status])

  const approximate =
    !!result && (!result.walk.path || !result.transit.path)

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
      {status === 'ready' && result && (
        <div className="map-legend">
          <span className="legend-item">
            <i className="legend-line legend-walk" aria-hidden="true" />
            도보
          </span>
          <span className="legend-item">
            <i className="legend-line legend-transit" aria-hidden="true" />
            대중교통
          </span>
          {approximate && <span className="legend-note">점선은 직선 표시</span>}
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

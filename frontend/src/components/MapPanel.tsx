import { useEffect, useRef, useState } from 'react'
import { hasKakaoKey, loadKakaoSdk } from '../lib/kakao'
import type { KakaoMap, KakaoMarker } from '../types/kakao'
import type { Place } from '../types/place'

interface Props {
  start: Place | null
  end: Place | null
}

/** 지도 첫 화면 중심. 서울시청 부근. */
const DEFAULT_CENTER = { x: 126.978, y: 37.5665 }

/**
 * 오른쪽 지도 영역. 카카오 키가 있으면 지도를 띄우고 출발지·도착지 마커를 찍습니다.
 * 경로 선(스케치의 빨간 도보 / 파란 대중교통)은 백엔드 응답에 경로 좌표가 없어서 아직 그리지 않습니다.
 */
export function MapPanel({ start, end }: Props) {
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
    const bounds = new kakao.maps.LatLngBounds()
    for (const point of points) {
      const position = new kakao.maps.LatLng(point.y, point.x)
      markersRef.current.push(new kakao.maps.Marker({ position, map }))
      bounds.extend(position)
    }
    if (points.length === 1) {
      map.setCenter(new kakao.maps.LatLng(points[0]!.y, points[0]!.x))
      map.setLevel(4)
    } else {
      // 왼쪽 검색 패널 아래로 마커가 숨지 않도록 지도 범위에 패널 너비만큼 여백을 둡니다.
      map.setBounds(bounds, 40, 40, 40, 460)
    }
  }, [start, end, status])

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

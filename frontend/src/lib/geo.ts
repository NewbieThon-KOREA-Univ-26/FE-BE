import type { Coordinate } from '../types/api'

/** 백엔드 MAX_DISTANCE_KM 과 같은 값. 카카오 도보 경로가 약 30km 를 넘으면 결과를 주지 않습니다. */
export const MAX_COMPARE_KM = 30

/** 두 좌표(경도 x, 위도 y) 사이의 직선 거리(km). 하버사인 공식. */
export function distanceKm(a: Coordinate, b: Coordinate): number {
  const rad = (deg: number) => (deg * Math.PI) / 180
  const dLat = rad(b.y - a.y)
  const dLng = rad(b.x - a.x)
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.y)) * Math.cos(rad(b.y)) * Math.sin(dLng / 2) ** 2
  return 2 * 6371 * Math.asin(Math.sqrt(h))
}

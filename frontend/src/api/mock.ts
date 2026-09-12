import type { Coordinate, CompareResponse } from '../types/api'
import { ApiError } from './client'

/**
 * 백엔드 없이 화면을 개발하기 위한 예시 응답입니다.
 * API 명세서의 예시 JSON(도보 1180m / 16분 / 52kcal, 요금 1400원)을 기준으로
 * 두 좌표 사이 거리에 따라 값을 대략 바꿔서 돌려줍니다.
 * 아래 숫자는 전부 화면 개발용 임시값이며 실제 요금·시간이 아닙니다.
 */

/** 기준 보행속도 (m/s). 기능 명세서 "정해야 할 것"의 예시값. */
const WALK_SPEED_MPS = 1.2
/** 직선거리 → 도보거리 보정계수. API 명세서 "최후의 수단" 방식. */
const DETOUR_FACTOR = 1.3
/** 명세서 예시 응답의 요금. 실제 기준(기본요금·환승·거리비례)은 미정. */
const EXAMPLE_FARE_WON = 1400
/** 명세서 예시 응답 비율(52kcal / 1180m)로 맞춘 도보 열량. */
const KCAL_PER_METER = 52 / 1180
/** "걸을 만하다"의 경계 (분). 팀에서 아직 정하지 않은 값이라 임시로 둡니다. */
const WALKABLE_EXTRA_MINUTES = 15

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** 두 좌표 사이 직선거리 (m). */
function haversineMeters(a: Coordinate, b: Coordinate): number {
  const R = 6_371_000
  const toRad = (deg: number) => (deg * Math.PI) / 180
  const dLat = toRad(b.y - a.y)
  const dLng = toRad(b.x - a.x)
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.y)) * Math.cos(toRad(b.y)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

/**
 * 예시용 경로 좌표. 출발지에서 도착지까지 살짝 꺾어 실제 경로처럼 보이게 만듭니다.
 * 실제 경로가 아니라 지도 표시를 확인하기 위한 값입니다.
 */
function fakePath(start: Coordinate, end: Coordinate, bend: number): Coordinate[] {
  const midX = (start.x + end.x) / 2
  const midY = (start.y + end.y) / 2
  const dx = end.x - start.x
  const dy = end.y - start.y
  return [
    start,
    { x: midX - dy * bend, y: midY + dx * bend },
    end,
  ]
}

export async function mockCompare(start: Coordinate, end: Coordinate): Promise<CompareResponse> {
  await delay(600)

  if (start.x === end.x && start.y === end.y) {
    throw new ApiError('SAME_LOCATION', '출발지와 도착지가 같습니다', 400)
  }

  const walkDistance = Math.round(haversineMeters(start, end) * DETOUR_FACTOR)
  const walkDuration = Math.max(1, Math.round(walkDistance / WALK_SPEED_MPS / 60))
  const transitDuration = Math.max(3, Math.round(walkDuration * 0.4))
  const extraMinutes = Math.max(0, walkDuration - transitDuration)
  const choice = extraMinutes <= WALKABLE_EXTRA_MINUTES ? 'walk' : 'transit'
  const fareText = EXAMPLE_FARE_WON.toLocaleString('ko-KR')

  return {
    walk: {
      distance: walkDistance,
      duration: walkDuration,
      calories: Math.round(walkDistance * KCAL_PER_METER),
      paths: [fakePath(start, end, 0.08)],
      geometryWarning: '예시 데이터의 경로 선은 실제 경로가 아닙니다.',
    },
    transit: {
      duration: transitDuration,
      fare: EXAMPLE_FARE_WON,
      transfers: 1,
      walkDistance: Math.min(320, walkDistance),
      walkDuration: Math.min(5, walkDuration),
      paths: [fakePath(start, end, -0.14)],
      routeSteps: [
        {
          mode: 'subway',
          lineName: '2호선',
          fromName: '강남역',
          toName: '잠실역',
        },
        {
          mode: 'bus',
          lineName: '간선 3412번',
          fromName: '잠실역 버스정류장',
          toName: '도착지 인근 정류장',
        },
      ],
    },
    savings: {
      amount: EXAMPLE_FARE_WON,
      extraMinutes,
    },
    recommendation: {
      choice,
      reason:
        choice === 'walk'
          ? `${extraMinutes}분 더 걷고 ${fareText}원을 아낍니다`
          : `걸으면 ${extraMinutes}분이나 더 걸려서 타는 게 낫습니다`,
    },
    weather: {
      condition: '맑음',
      temperatureC: 23,
      precipitationProbability: 10,
    },
  }
}

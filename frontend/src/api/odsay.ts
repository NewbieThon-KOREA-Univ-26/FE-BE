import type { Coordinate, CompareResponse, TransitInfo, WalkInfo } from '../types/api'
import { ApiError } from './client'

const API_URL = 'https://api.odsay.com/v1/api'
const API_KEY = (import.meta.env.VITE_ODSAY_API_KEY ?? '').trim()
const WALK_MAX_MINUTES = readPositiveNumber(import.meta.env.VITE_WALK_MAX_MINUTES, 30)
const WALK_MAX_METERS = readPositiveNumber(import.meta.env.VITE_WALK_MAX_METERS, 2000)

type JsonObject = Record<string, unknown>

function readPositiveNumber(value: string | undefined, fallback: number): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

function asObject(value: unknown): JsonObject {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ApiError('UPSTREAM_ERROR', 'ODsay 응답 형식을 확인할 수 없습니다', 0)
  }
  return value as JsonObject
}

function asArray(value: unknown): unknown[] {
  if (!Array.isArray(value)) {
    throw new ApiError('UPSTREAM_ERROR', 'ODsay 응답 형식을 확인할 수 없습니다', 0)
  }
  return value
}

function asNumber(value: unknown): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed < 0) {
    throw new ApiError('UPSTREAM_ERROR', 'ODsay 응답에 올바른 숫자가 없습니다', 0)
  }
  return parsed
}

function parsePoint(value: unknown): Coordinate | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const point = value as JsonObject
  const x = Number(point.x)
  const y = Number(point.y)
  if (!Number.isFinite(x) || !Number.isFinite(y) || Math.abs(x) > 180 || Math.abs(y) > 90) {
    return null
  }
  return { x, y }
}

function parsePointList(value: unknown): Coordinate[] {
  if (!Array.isArray(value)) {
    const point = parsePoint(value)
    return point ? [point] : []
  }
  return value.flatMap((item) => {
    if (Array.isArray(item)) return parsePointList(item)
    const point = parsePoint(item)
    return point ? [point] : []
  })
}

function loadLaneMapObject(value: string): string {
  const firstSegment = value.split('@', 1)[0] ?? ''
  const coordinateBaseEnd = value.indexOf('@')
  const hasCoordinateBase = coordinateBaseEnd >= 0 && firstSegment.split(':').length === 2
  return hasCoordinateBase ? `0:0${value.slice(coordinateBaseEnd)}` : `0:0@${value}`
}

function providerError(data: JsonObject): ApiError | null {
  if (!('error' in data)) return null
  const errorValue = Array.isArray(data.error) ? data.error[0] : data.error
  const error = errorValue && typeof errorValue === 'object' ? errorValue as JsonObject : {}
  const code = String(error.code ?? '')
  const message = String(error.message ?? '')

  if (message.includes('ApiKeyAuthFailed')) {
    return new ApiError(
      'CONFIGURATION_ERROR',
      'ODsay Web 키 인증에 실패했습니다. Vercel 키와 ODsay에 등록한 서비스 URI를 확인해 주세요',
      0,
    )
  }
  if (code === '429' || message.toLowerCase().includes('limit')) {
    return new ApiError('RATE_LIMITED', 'ODsay 호출 한도를 초과했습니다. 잠시 후 다시 시도해 주세요', 429)
  }
  if (['3', '4', '5', '6', '-98', '-99'].includes(code)) {
    return new ApiError('NO_ROUTE', '비교할 대중교통 경로를 찾을 수 없습니다', 404)
  }
  return new ApiError('UPSTREAM_ERROR', 'ODsay가 경로 요청을 처리하지 못했습니다', 0)
}

async function requestOdsay(endpoint: string, params: Record<string, string | number>): Promise<JsonObject> {
  if (!API_KEY) {
    throw new ApiError(
      'SERVICE_NOT_CONFIGURED',
      'VITE_ODSAY_API_KEY가 설정되지 않았습니다',
      0,
    )
  }

  const query = new URLSearchParams({ apiKey: API_KEY, output: 'json' })
  for (const [key, value] of Object.entries(params)) query.set(key, String(value))

  let response: Response
  try {
    response = await fetch(`${API_URL}/${endpoint}?${query.toString()}`, {
      headers: { Accept: 'application/json' },
    })
  } catch {
    throw new ApiError('NETWORK_ERROR', 'ODsay 경로 서비스에 연결할 수 없습니다', 0)
  }

  if (response.status === 429) {
    throw new ApiError('RATE_LIMITED', 'ODsay 호출 한도를 초과했습니다. 잠시 후 다시 시도해 주세요', 429)
  }

  let data: JsonObject
  try {
    data = asObject(await response.json())
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError('UPSTREAM_ERROR', 'ODsay 응답을 읽지 못했습니다', response.status)
  }

  const error = providerError(data)
  if (error) throw error
  if (!response.ok) {
    throw new ApiError('UPSTREAM_ERROR', `ODsay 요청에 실패했습니다 (HTTP ${response.status})`, response.status)
  }
  return data
}

async function fetchWalk(start: Coordinate, end: Coordinate): Promise<WalkInfo> {
  const data = await requestOdsay('searchWalkPathV2', {
    loc: `${start.x},${start.y},${end.x},${end.y}`,
    opt: 'reco',
  })
  const result = asObject(data.result)
  const paths = asArray(result.path)
  if (paths.length === 0) throw new ApiError('NO_ROUTE', '도보 경로를 찾을 수 없습니다', 404)
  const path = asObject(paths[0])
  if (path.hasPathResult !== true) {
    const code = String(path.errorCode ?? '')
    if (code === '403') throw new ApiError('SAME_LOCATION', '출발지와 도착지가 같습니다', 400)
    throw new ApiError('NO_ROUTE', '도보 경로를 찾을 수 없습니다', 404)
  }

  const recommend = asObject(path.recommend)
  const summary = asObject(recommend.summary)
  let points: Coordinate[] = []
  try {
    points = asArray(recommend.routes).flatMap((route) => {
      const coordinate = asObject(route).coordinate
      return parsePointList(coordinate)
    })
  } catch {
    // Geometry is optional. Keep the route summary even when coordinates are absent.
  }

  return {
    distance: asNumber(summary.distance),
    duration: Math.ceil(asNumber(summary.duration) / 60),
    paths: points.length >= 2 ? [points] : [],
    geometryWarning: points.length >= 2 ? null : '도보 경로 선을 불러오지 못했습니다. 거리·시간은 확인할 수 있습니다.',
  }
}

interface TransitCandidate {
  info: TransitInfo
  mapObject: string | null
}

async function fetchTransit(start: Coordinate, end: Coordinate): Promise<TransitInfo> {
  const data = await requestOdsay('searchPubTransPathT', {
    SX: start.x, SY: start.y, EX: end.x, EY: end.y, SearchType: 0,
  })
  const result = asObject(data.result)
  if (Number(result.searchType) !== 0) {
    throw new ApiError('NO_ROUTE', '현재는 도시 내 대중교통 경로만 비교할 수 있습니다', 404)
  }

  const candidates: TransitCandidate[] = asArray(result.path).map((item) => {
    const path = asObject(item)
    const info = asObject(path.info)
    const sections = asArray(path.subPath).map(asObject)
    const boardings = sections.filter((section) => [1, 2].includes(Number(section.trafficType))).length
    if (boardings === 0) {
      throw new ApiError('UPSTREAM_ERROR', 'ODsay 대중교통 경로에 탑승 구간이 없습니다', 0)
    }
    const walking = sections.filter((section) => Number(section.trafficType) === 3)
    return {
      info: {
        duration: asNumber(info.totalTime),
        fare: Math.round(asNumber(info.payment)),
        transfers: boardings - 1,
        walkDistance: asNumber(info.totalWalk),
        walkDuration: walking.reduce((sum, section) => sum + asNumber(section.sectionTime), 0),
        paths: [],
      },
      mapObject: typeof info.mapObj === 'string' ? info.mapObj : null,
    }
  })

  if (candidates.length === 0) throw new ApiError('NO_ROUTE', '대중교통 경로를 찾을 수 없습니다', 404)
  const selected = candidates.sort((a, b) =>
    a.info.duration - b.info.duration || a.info.fare - b.info.fare || a.info.transfers - b.info.transfers,
  )[0]!

  try {
    if (!selected.mapObject) throw new Error('missing map object')
    const geometry = await requestOdsay('loadLane', {
      mapObject: loadLaneMapObject(selected.mapObject),
    })
    const lanes = asArray(asObject(geometry.result).lane)
    selected.info.paths = lanes.flatMap((lane) =>
      asArray(asObject(lane).section).map((section) => parsePointList(asObject(section).graphPos)),
    ).filter((points) => points.length >= 2)
    if (selected.info.paths.length === 0) throw new Error('empty geometry')
  } catch {
    selected.info.paths = []
    selected.info.geometryWarning = '대중교통 경로 선을 불러오지 못했습니다. 시간·요금은 확인할 수 있습니다.'
  }
  return selected.info
}

function validateCoordinate(point: Coordinate): void {
  if (!Number.isFinite(point.x) || !Number.isFinite(point.y)
      || Math.abs(point.x) > 180 || Math.abs(point.y) > 90) {
    throw new ApiError('INVALID_INPUT', '유효한 출발지·도착지 좌표를 선택해 주세요', 400)
  }
}

export async function compareWithOdsay(start: Coordinate, end: Coordinate): Promise<CompareResponse> {
  validateCoordinate(start)
  validateCoordinate(end)
  if (start.x === end.x && start.y === end.y) {
    throw new ApiError('SAME_LOCATION', '출발지와 도착지가 같습니다', 400)
  }

  const [walk, transit] = await Promise.all([fetchWalk(start, end), fetchTransit(start, end)])
  const extraMinutes = walk.duration - transit.duration
  const choice = walk.duration <= WALK_MAX_MINUTES && walk.distance <= WALK_MAX_METERS
    ? 'walk' as const : 'transit' as const
  const time = extraMinutes > 0
    ? `${extraMinutes}분 더 걸리지만`
    : extraMinutes < 0 ? `${Math.abs(extraMinutes)}분 더 빠르고` : '같은 시간이 걸리고'

  return {
    walk,
    transit,
    savings: { amount: transit.fare, extraMinutes },
    recommendation: {
      choice,
      reason: choice === 'walk'
        ? `걸으면 ${time} ${transit.fare.toLocaleString('ko-KR')}원을 아낍니다`
        : `도보 ${walk.duration}분·${Math.round(walk.distance)}m로 걷기 추천 기준을 초과합니다`,
    },
  }
}

import type { ApiErrorBody } from '../types/api'

/**
 * 백엔드가 돌려주는 에러 형식 { error: { code, message } } 를 그대로 담는 예외.
 * 네트워크 자체가 안 되면 code = 'NETWORK_ERROR', status = 0 입니다.
 */
export class ApiError extends Error {
  readonly code: string
  readonly status: number

  constructor(code: string, message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')

/** GET 요청을 보내고 JSON 을 돌려줍니다. 실패하면 ApiError 를 던집니다. */
export async function getJson<T>(
  path: string,
  params: Record<string, string | number>,
): Promise<T> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    query.set(key, String(value))
  }

  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}?${query.toString()}`, {
      headers: { Accept: 'application/json' },
    })
  } catch {
    throw new ApiError('NETWORK_ERROR', '서버에 연결할 수 없습니다', 0)
  }

  if (!response.ok) {
    let body: Partial<ApiErrorBody> | undefined
    try {
      body = (await response.json()) as Partial<ApiErrorBody>
    } catch {
      // 본문이 JSON 이 아니면 백엔드가 아니라 중간 프록시(개발 서버, Vercel 등)가 낸 응답입니다.
      // 502/503/504 는 백엔드에 닿지 못한 경우라 네트워크 오류로 취급합니다.
      if (response.status === 502 || response.status === 503 || response.status === 504) {
        throw new ApiError('NETWORK_ERROR', '백엔드에 연결할 수 없습니다', response.status)
      }
    }
    throw new ApiError(
      body?.error?.code ?? 'UNKNOWN',
      body?.error?.message ?? `요청에 실패했습니다 (HTTP ${response.status})`,
      response.status,
    )
  }

  return (await response.json()) as T
}

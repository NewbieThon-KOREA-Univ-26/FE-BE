import type { ApiErrorCode } from '../types/api'

/**
 * 백엔드 호출과 입력 검증 오류를 화면까지 전달하는 예외입니다.
 * code 는 ErrorBanner 가 안내 문구를 고르는 데 씁니다.
 */
export class ApiError extends Error {
  readonly code: string
  readonly status: number

  constructor(code: ApiErrorCode | string, message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

/**
 * 백엔드에 GET 요청을 보내고 JSON 을 돌려줍니다.
 *
 * 경로 조회는 서버가 대신합니다. 카카오 REST API 키는 비밀이라 브라우저에 둘 수 없고,
 * 카카오 REST 엔드포인트는 브라우저에서 부르면 CORS 사전 요청이 막히기 때문입니다.
 */
export async function getJson<T>(
  path: string,
  params: Record<string, string | number>,
): Promise<T> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    query.set(key, String(value))
  }
  const url = query.size > 0 ? `${path}?${query}` : path

  let response: Response
  try {
    response = await fetch(url, {
      headers: { Accept: 'application/json' },
    })
  } catch {
    throw new ApiError('NETWORK_ERROR', '서버에 연결할 수 없습니다', 0)
  }

  return readJsonOrThrow<T>(response)
}

/** 응답을 JSON 으로 읽고, 실패 응답이면 ApiError 로 바꿉니다. */
async function readJsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let body: { error?: { code?: string; message?: string } } | undefined
    try {
      body = await response.json()
    } catch {
      // 본문이 JSON 이 아니면 백엔드가 아니라 중간 프록시가 낸 응답입니다.
      if ([502, 503, 504].includes(response.status)) {
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

/**
 * 백엔드에 POST 요청을 보내고 JSON 을 돌려줍니다.
 *
 * 좌표를 본문에 싣는 이유는, 배포 프록시가 쿼리스트링이나 경로 뒷부분을
 * 백엔드까지 넘기지 않는 경우가 있기 때문입니다. 본문은 그 영향을 받지 않습니다.
 */
export async function postJson<T>(path: string, body: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new ApiError('NETWORK_ERROR', '서버에 연결할 수 없습니다', 0)
  }
  return readJsonOrThrow<T>(response)
}

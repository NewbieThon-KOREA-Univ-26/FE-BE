import type { ApiError } from '../api/client'

interface Props {
  error: ApiError
  onRetry: () => void
}

interface Guide {
  title: string
  hint?: string
  retry: boolean
}

/** API 명세서 "에러 코드" 표의 화면 동작을 코드별로 옮겼습니다. 입력값은 폼이 그대로 들고 있습니다. */
const GUIDES: Record<string, Guide> = {
  INVALID_INPUT: { title: '입력값을 확인해 주세요', retry: false },
  SAME_LOCATION: { title: '출발지와 도착지가 같습니다', hint: '다른 도착지를 입력해 주세요', retry: false },
  TOO_FAR: { title: '너무 먼 거리예요', hint: '30km 이내 구간만 비교할 수 있어요. 도착지를 가까운 곳으로 바꿔 주세요', retry: false },
  NO_ROUTE: { title: '경로를 찾을 수 없습니다', hint: '출발지나 도착지를 바꿔서 다시 시도해 보세요', retry: true },
  UPSTREAM_ERROR: { title: '경로 정보를 가져오지 못했습니다', retry: true },
  RATE_LIMITED: { title: '요청이 너무 많습니다', hint: '잠시 후 다시 시도해 주세요', retry: true },
  CONFIGURATION_ERROR: { title: 'ODsay 인증 설정을 확인해 주세요', retry: false },
  INTERNAL_ERROR: {
    title: '서버에서 문제가 생겼습니다',
    hint: '잠시 후 다시 시도해 주세요. 계속되면 서버 로그를 확인해야 합니다',
    retry: true,
  },
  SERVICE_NOT_CONFIGURED: {
    title: '서버에 경로 API 키가 없습니다',
    hint: '백엔드 .env 의 KAKAO_REST_API_KEY 를 채우고, 카카오디벨로퍼스에서 카카오맵 사용 설정을 켰는지 확인하세요',
    retry: false,
  },
  NETWORK_ERROR: {
    title: '경로 서비스에 연결할 수 없습니다',
    hint: '네트워크 상태를 확인한 뒤 다시 시도해 주세요',
    retry: true,
  },
}

const FALLBACK: Guide = { title: '문제가 생겼습니다', retry: true }

export function ErrorBanner({ error, onRetry }: Props) {
  const guide = GUIDES[error.code] ?? FALLBACK
  const showServerMessage = error.message && error.message !== guide.title

  return (
    <div className="error" role="alert">
      <p className="error-title">{guide.title}</p>
      {showServerMessage && <p className="error-detail">{error.message}</p>}
      {guide.hint && <p className="error-hint">{guide.hint}</p>}
      <p className="error-code">
        {error.code}
        {error.status > 0 ? ` · HTTP ${error.status}` : ''}
      </p>
      {guide.retry && (
        <button type="button" className="secondary" onClick={onRetry}>
          다시 시도
        </button>
      )}
    </div>
  )
}

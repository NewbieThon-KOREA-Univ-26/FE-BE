/**
 * ODsay 호출과 입력 검증 오류를 화면까지 전달하는 예외입니다.
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

import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/**
 * 화면을 그리다 예외가 나면 React 는 트리 전체를 지워 빈 화면이 됩니다.
 * 대신 무슨 일이 났는지와 새로고침 버튼을 보여 줍니다. 누적 절감액은 주소에 있어 사라지지 않습니다.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('화면 렌더링 오류', error, info.componentStack)
  }

  render() {
    if (!this.state.error) {
      return this.props.children
    }
    return (
      <div className="app-crash" role="alert">
        <h1>화면을 그리는 중 문제가 생겼습니다</h1>
        <p>새로고침하면 대부분 해결됩니다. 누적 절감액은 주소에 저장돼 있어 사라지지 않습니다.</p>
        <p className="error-code">
          {this.state.error.name}: {this.state.error.message}
        </p>
        <button type="button" className="primary" onClick={() => window.location.reload()}>
          새로고침
        </button>
      </div>
    )
  }
}

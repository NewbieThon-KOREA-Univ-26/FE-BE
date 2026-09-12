# Backend

Python 3.13 + FastAPI 기반 도보 길찾기 서비스 백엔드입니다.

## 설치 (PowerShell)

프로젝트 루트에서 실행합니다.

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

- `fastapi[standard]`: API 프레임워크와 Uvicorn 서버 등 표준 의존성
- `httpx`: 외부 도보 길찾기 API의 비동기 HTTP 호출
- `pydantic-settings`: 환경변수 및 `.env` 설정 읽기

가상환경을 활성화하지 않아도 위처럼 실행 파일 경로를 지정하면 됩니다.
`py -3.13`이 Python을 찾지 못하면 `& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m venv .venv`로 생성할 수 있습니다.
API 키를 담은 `.env`와 `.venv`는 Git에서 제외합니다.
아직 서버 애플리케이션과 길찾기 API 연동은 구현하지 않았습니다.

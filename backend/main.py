"""배포용 진입점.

Vercel 은 `vercel.json` 의 entrypoint 를 파일 하나로 읽어 들입니다.
`src/main.py` 를 직접 가리키면 그 파일이 단독 모듈로 import 되어
안쪽의 `from src.config...` 가 `ModuleNotFoundError: No module named 'src'` 로 깨집니다.

이 파일은 서비스 루트(backend/)에 있으므로, 로드될 때 backend/ 가 모듈 경로에 들어갑니다.
그래서 `src` 패키지가 정상적으로 보이고 앱을 그대로 넘겨줄 수 있습니다.

로컬 실행은 둘 다 됩니다.
    uvicorn main:app --reload --port 8000        (배포와 같은 경로)
    uvicorn src.main:app --reload --port 8000    (기존 방식)
"""

from src.main import app

__all__ = ['app']

# SUNO Manager

SUNO AI를 활용한 모던한 음악 생성 및 관리 웹 애플리케이션입니다.

## 기능

- **대시보드**: 생성된 음악 통계 및 최근 곡 목록 확인
- **음악 생성**: AI 프롬프트를 통한 음악 생성
- **라이브러리**: 생성된 음악 관리, 재생, 다운로드, 삭제

## 기술 스택

- **Backend**: Flask 3.0
- **Frontend**: Tailwind CSS (다크 모드)
- **API**: SUNO API

## 프로젝트 구조

```
suno-manager/
├── main.py                 # Flask 애플리케이션 메인 파일
├── suno_api.py            # SUNO API 클라이언트
├── templates/             # HTML 템플릿
│   ├── base.html         # 기본 레이아웃
│   ├── dashboard.html    # 대시보드 페이지
│   ├── generate.html     # 음악 생성 페이지
│   └── library.html      # 라이브러리 페이지
├── static/               # 정적 파일
│   ├── css/
│   ├── js/
│   └── audio/           # 다운로드된 음악 파일
└── .env                 # 환경 변수 (생성 필요)
```

## 설치 및 실행

### 1. 패키지 설치

필요한 Python 패키지를 설치합니다:

```bash
pip install Flask requests python-dotenv
```

또는 requirements.txt를 사용:

```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정

`.env.example` 파일을 `.env`로 복사하고 실제 값으로 수정:

```bash
cp .env.example .env
```

`.env` 파일에서 다음 값을 설정:

```
SUNO_API_KEY=your_actual_api_key
SUNO_API_URL=https://api.suno.ai/v1
SECRET_KEY=your_random_secret_key
```

### 3. 애플리케이션 실행

```bash
python main.py
```

브라우저에서 `http://localhost:5000` 접속

## 사용 방법

### 음악 생성

1. 왼쪽 메뉴에서 "음악 생성" 클릭
2. 프롬프트 입력 (예: "밝고 경쾌한 팝 음악, 어쿠스틱 기타")
3. 음악 길이, 장르, 분위기 등 옵션 설정
4. "음악 생성하기" 버튼 클릭

### 음악 관리

1. 왼쪽 메뉴에서 "음악 라이브러리" 클릭
2. 생성된 음악 목록 확인
3. 각 곡에서 재생, 다운로드, 삭제 가능

## API 엔드포인트

### 음악 생성
```http
POST /api/generate
Content-Type: application/json

{
  "prompt": "밝고 경쾌한 팝 음악",
  "duration": 30,
  "genre": "pop",
  "mood": "happy"
}
```

### 곡 목록 조회
```http
GET /api/songs?limit=50&offset=0
```

### 곡 삭제
```http
DELETE /api/songs/{song_id}
```

### 곡 다운로드
```http
GET /api/songs/{song_id}/download
```

## 개발 환경

- Python 3.8+
- Flask 3.0
- Modern browsers (Chrome, Firefox, Safari, Edge)

## 라이선스

MIT License

## 기여

이슈 및 풀 리퀘스트는 언제나 환영합니다!

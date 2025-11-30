# SUNO Manager

SUNO AI를 활용한 모던한 음악 생성 및 관리 웹 애플리케이션입니다.

## 기능

- **로그인**: SUNO 세션 토큰을 사용한 인증
- **대시보드**: 생성된 음악 통계 및 최근 곡 목록 확인
- **음악 생성**: AI 프롬프트를 통한 음악 생성 (준비 중)
- **라이브러리**: 생성된 음악 관리, 재생, 다운로드, 삭제

## 기술 스택

- **Backend**: Flask 3.0
- **Frontend**: Tailwind CSS (다크 모드)
- **API**: SUNO Studio API (실제 API 연동)

## 프로젝트 구조

```
suno-manager/
├── main.py                 # Flask 애플리케이션 메인 파일
├── suno_api.py            # SUNO API 클라이언트
├── templates/             # HTML 템플릿
│   ├── base.html         # 기본 레이아웃
│   ├── login.html        # 로그인 페이지
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

### 2. 환경 변수 설정

`.env.example` 파일을 `.env`로 복사하고 실제 값으로 수정:

```bash
cp .env.example .env
```

`.env` 파일에서 다음 값을 설정:

```
SUNO_SESSION_TOKEN=your_actual_session_token
SECRET_KEY=your_random_secret_key
```

### 3. SUNO 세션 토큰 가져오기

1. [SUNO 웹사이트](https://suno.com)에 로그인
2. 브라우저 개발자 도구 열기 (F12)
3. Application/Storage → Cookies → https://suno.com
4. `token` 쿠키 값 복사
5. `.env` 파일의 `SUNO_SESSION_TOKEN`에 붙여넣기

또는 애플리케이션 실행 후 로그인 페이지에서 직접 입력할 수도 있습니다.

### 4. 애플리케이션 실행

```bash
python main.py
```

브라우저에서 `http://localhost:5000` 접속

## 사용 방법

### 로그인

1. 브라우저에서 `http://localhost:5000` 접속
2. SUNO 세션 토큰 입력
3. 로그인 버튼 클릭

### 대시보드

- 전체 곡 수, 생성 중인 곡, 오늘 생성된 곡 통계 확인
- 최근 생성된 곡 5개 미리보기

### 음악 라이브러리

- 생성된 모든 음악 목록 확인
- 검색 및 정렬 기능 (제목, 날짜)
- 각 곡에서 다음 작업 가능:
  - **재생**: 새 탭에서 음악 재생
  - **다운로드**: MP3 파일 다운로드
  - **삭제**: 음악 삭제

### 음악 생성 (준비 중)

- 프롬프트 입력하여 음악 생성
- 장르, 분위기, 템포 등 설정

## API 엔드포인트

### 인증

```http
POST /login
Content-Type: application/json

{
  "token": "your_suno_session_token"
}
```

### 곡 목록 조회

```http
GET /api/songs?page=0
```

응답:
```json
{
  "status": "success",
  "clips": [...],
  "num_total_results": 16,
  "current_page": 0,
  "has_more": false
}
```

### 곡 삭제

```http
DELETE /api/songs/{song_id}
```

### 곡 다운로드

```http
GET /api/songs/{song_id}/download
```

## 실제 SUNO API 연동

이 프로젝트는 실제 SUNO Studio API를 사용합니다:

- **API Endpoint**: `https://studio-api.prod.suno.com/api`
- **인증 방식**: Session Token (쿠키)
- **응답 구조**: 실제 SUNO 응답 구조 사용 (`clips` 배열)

### API 응답 예시

```json
{
  "clips": [
    {
      "id": "...",
      "title": "곡 제목",
      "audio_url": "https://cdn1.suno.ai/...",
      "image_url": "https://cdn2.suno.ai/...",
      "created_at": "2025-10-10T12:40:28.107Z",
      "status": "complete",
      "play_count": 12,
      "metadata": {
        "tags": "krnb, neo-soul",
        "prompt": "가사 내용...",
        "duration": 316.96
      },
      "display_tags": "krnb, neo-soul"
    }
  ],
  "num_total_results": 16,
  "has_more": false
}
```

## 특징

- **실시간 데이터**: 실제 SUNO 계정의 음악 목록을 실시간으로 확인
- **앨범 커버**: SUNO에서 생성한 이미지 표시
- **재생 수 표시**: 각 곡의 재생 수 확인
- **태그 표시**: 장르/스타일 태그 표시
- **세션 관리**: Flask 세션을 통한 토큰 관리

## 개발 환경

- Python 3.8+
- Flask 3.0
- Modern browsers (Chrome, Firefox, Safari, Edge)

## 보안 주의사항

- `.env` 파일을 절대 Git에 커밋하지 마세요
- 세션 토큰은 민감한 정보이므로 안전하게 관리하세요
- 프로덕션 환경에서는 `SECRET_KEY`를 반드시 변경하세요

## 라이선스

MIT License

## 기여

이슈 및 풀 리퀘스트는 언제나 환영합니다!

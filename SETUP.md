# Beauty Trend Dashboard — 세팅 가이드

## 전체 구조

```
beauty-trend-dashboard/
├── config/
│   ├── ingredients.yaml      ← 성분 마스터 (여기만 수정하면 전체 반영)
│   ├── sheets_client.py      ← Google Sheets 연동
├── collect/
│   ├── google_trends.py      ← V-Index 자동 수집
│   ├── reddit_score.py       ← R-Score 자동 수집
│   └── run_collector.py      ← 수집 오케스트레이터
├── dashboard.py              ← Streamlit 대시보드
├── .github/workflows/
│   └── weekly_collect.yml    ← 매주 월요일 자동 실행
├── .env.example              ← 환경변수 템플릿
└── requirements.txt
```

---

## 1단계: Python 환경 세팅

```bash
cd beauty-trend-dashboard
pip install -r requirements.txt
```

---

## 2단계: Google Sheets 서비스 계정 만들기

1. [Google Cloud Console](https://console.cloud.google.com) → 새 프로젝트 생성
2. **API 및 서비스 → 라이브러리** → `Google Sheets API` + `Google Drive API` 활성화
3. **API 및 서비스 → 사용자 인증 정보 → 서비스 계정 만들기**
   - 이름: `beauty-trend-bot`
   - 역할: 편집자
4. 서비스 계정 클릭 → **키 → JSON 키 추가** → 파일 다운로드
5. 다운로드한 파일을 `service_account.json`으로 이름 변경 후 프로젝트 루트에 저장
6. **Google Sheets** 에서 새 스프레드시트 생성
   - URL에서 ID 복사: `https://docs.google.com/spreadsheets/d/[이 부분]/edit`
   - 서비스 계정 이메일(`~@~.iam.gserviceaccount.com`)을 스프레드시트 **공유 편집자**로 추가

---

## 3단계: Reddit API 계정 만들기

1. [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) → 앱 만들기
2. 유형: `script`
3. redirect uri: `http://localhost:8080`
4. Client ID (앱 이름 아래 짧은 문자열) + Client Secret 복사

---

## 4단계: .env 파일 설정

```bash
cp .env.example .env
```

`.env` 파일을 열고 값 입력:
```
GOOGLE_SHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json
REDDIT_CLIENT_ID=abc123xyz
REDDIT_CLIENT_SECRET=secretkey456
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 5단계: 시트 초기화 + 첫 수집 실행

```bash
# 탭 생성 + 성분 마스터 동기화
python collect/run_collector.py --init

# 전체 수집 (Google Trends + Reddit)
python collect/run_collector.py

# 개별 실행
python collect/run_collector.py --trends
python collect/run_collector.py --reddit
```

---

## 6단계: 대시보드 실행

```bash
streamlit run dashboard.py
```

브라우저에서 `http://localhost:8501` 접속

---

## 7단계: Streamlit Cloud 배포 (선택)

1. GitHub 레포 생성 후 코드 push
   - ⚠️ `.env`와 `service_account.json`은 절대 push 금지 (`.gitignore`에 추가)
2. [share.streamlit.io](https://share.streamlit.io) → 레포 연결
3. **Advanced settings → Secrets**에 `.env` 내용 붙여넣기
4. 자동 배포 완료

---

## 8단계: 주간 자동 수집 (GitHub Actions)

GitHub 레포 → **Settings → Secrets and variables → Actions**에 추가:

| Secret 이름 | 값 |
|---|---|
| `GOOGLE_SHEET_ID` | 스프레드시트 ID |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | service_account.json 파일 전체 내용 |
| `REDDIT_CLIENT_ID` | Reddit Client ID |
| `REDDIT_CLIENT_SECRET` | Reddit Client Secret |
| `ANTHROPIC_API_KEY` | Claude API 키 |

설정 후 매주 월요일 오전 9시 KST 자동 실행됩니다.
Actions 탭 → `Weekly Trend Collection` → `Run workflow`로 수동 실행도 가능.

---

## 성분 추가/수정 방법

`config/ingredients.yaml` 파일만 수정하면 됩니다. 수집기 실행 시 자동으로 Sheets에 동기화됩니다.

```yaml
- id: new_ingredient          # 고유 ID (영문, 언더스코어)
  name_kr: 새 성분
  name_en: New Ingredient
  status: watching             # rising / falling / watching
  category: barrier            # 카테고리
  google_keywords:
    - "new ingredient skincare"
  reddit_terms:
    - "new ingredient"
  notes: "설명"
```

---

## 수동 입력 (TikTok / Amazon)

대시보드 → **수동 입력 탭**에서 직접 입력하거나,
Google Sheets `manual_input` 탭에 직접 행 추가해도 됩니다.

| 컬럼 | 내용 |
|---|---|
| date | YYYY-MM-DD |
| ingredient_id | ingredients.yaml의 id |
| tiktok_hashtag_views_M | 조회수 (만 단위) |
| amazon_bsr_top_count | BSR 진입 제품 수 |
| c_ratio_note | 높음/중간/낮음 |
| manual_note | 메모 |

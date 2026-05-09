# 🌐 GitHub Actions 셋업 — Mac 무관 일일 자동 실행

외출 잦거나 Mac 며칠씩 안 켜도 GitHub 클라우드에서 매일 자동 실행. 무료.

---

## 📋 단계별 셋업 (총 30~45분)

### Step 1. GitHub 계정 + Repo (5분)

1. **github.com 가입/로그인** — Katie의 개인 계정 또는 본업 계정 (private repo 가능)
2. 우상단 **+ → New repository**
   - Name: `aplb-beauty-os` (또는 원하는 이름)
   - **Private** 선택 ★ (코드/데이터 외부 노출 방지)
   - Initialize 옵션 모두 **체크 해제** (이미 로컬에 git이 있음)
   - **Create repository** 클릭

3. 표시되는 화면에서 **HTTPS URL 복사** (예: `https://github.com/katie-bom/aplb-beauty-os.git`)

---

### Step 2. 로컬 → GitHub Push (10분)

**터미널에서 실행** (Mac):

```bash
cd "/Users/user/Downloads/00. 클로드/beauty-trend-dashboard"

# 기존 git 상태 확인
git status

# 원격 저장소 연결 (URL은 위에서 복사한 것)
git remote add origin https://github.com/{Katie-ID}/aplb-beauty-os.git

# 또는 이미 origin 있으면:
# git remote set-url origin https://github.com/{Katie-ID}/aplb-beauty-os.git

# 변경사항 staging
git add .
git commit -m "Initial Beauty OS commit — APLB ingredient intelligence"

# 첫 push
git branch -M main
git push -u origin main
```

**인증 요청 시**:
- Username: GitHub 아이디
- Password: GitHub 비밀번호 ❌ — **Personal Access Token** 사용
  - GitHub → **Settings → Developer settings → Personal access tokens → Tokens (classic)**
  - **Generate new token (classic)**
  - Scopes: `repo` 체크
  - 생성 후 토큰 복사 → Password 자리에 붙여넣기

---

### Step 3. GitHub Secrets 등록 (10분) ★ 가장 중요

GitHub repo 페이지 → **Settings → Secrets and variables → Actions → New repository secret**

다음 4개 등록 (Name 정확히 일치):

| Name | Value (어디서 가져오나) |
|---|---|
| `GEMINI_API_KEY` | 로컬 `.env` 파일의 `GEMINI_API_KEY=...` 값 |
| `GOOGLE_CREDENTIALS` | 로컬 `.env` 파일의 `GOOGLE_CREDENTIALS=...` 의 JSON 전체 |
| `GOOGLE_SHEET_ID` | 로컬 `.env` 파일의 `GOOGLE_SHEET_ID=...` 값 |
| `NCBI_API_KEY` | 로컬 `.env` 파일의 `NCBI_API_KEY=...` 값 |

**`.env` 값 확인**:
```bash
cd "/Users/user/Downloads/00. 클로드/beauty-trend-dashboard"
grep "GEMINI_API_KEY\|GOOGLE_SHEET_ID\|NCBI_API_KEY" .env
```

`GOOGLE_CREDENTIALS`는 multi-line JSON이라 복사 까다로움 — `.env`에서 `GOOGLE_CREDENTIALS=` 다음 모든 줄 (다음 변수 시작 전까지)을 통째로 복사.

---

### Step 4. Workflow 활성화 + 첫 실행 (5분)

GitHub repo 페이지 → **Actions** 탭

처음 들어가면 "Workflows are disabled" 경고 → **Enable workflows** 클릭

좌측에 **Daily R&D Pipeline** 보임 → 클릭 → 우측 **Run workflow** 버튼 → **Run workflow**

5~10분 후 실행 완료. 초록 ✅면 성공, 빨간 ❌면 로그 확인 (Secrets 누락이 99% 원인).

---

### Step 5. 매일 자동 실행 확인 (자동, 0분)

이미 workflow는 매일 한국 시간 새벽 6시 자동 실행되도록 설정됨:
```yaml
schedule:
  - cron: "0 21 * * *"   # UTC 21:00 = KST 06:00
```

GitHub Actions가 시간 됐을 때 자동 실행 → 결과 commit → 다음 날 Mac 켜면 `git pull`로 최신 데이터 받음.

---

## 🔄 Mac에서 최신 데이터 받기

Mac 켰을 때 한 번:
```bash
cd "/Users/user/Downloads/00. 클로드/beauty-trend-dashboard"
git pull
```

이걸 자동화하려면 `start_dashboard.sh`에 추가:
```bash
# 대시보드 시작 전에 git pull
git pull --quiet 2>/dev/null
```

---

## 🧹 Mac LaunchAgent 비활성화 (선택)

GitHub Actions로 이전했으니 Mac 자동 실행은 불필요. 중복 방지:

```bash
launchctl unload ~/Library/LaunchAgents/com.aplb.research.plist
mv ~/Library/LaunchAgents/com.aplb.research.plist ~/Library/LaunchAgents/com.aplb.research.plist.disabled
```

(나중에 되살리려면 `.disabled` 빼고 다시 load)

---

## ✅ 셋업 완료 체크리스트

- [ ] GitHub 계정 + private repo 생성
- [ ] `git push origin main` 성공
- [ ] Secrets 4개 등록 (GEMINI/GOOGLE_CREDENTIALS/GOOGLE_SHEET_ID/NCBI)
- [ ] Actions 탭에서 수동 실행 → ✅ 성공 확인
- [ ] data/ 변경 사항이 자동 commit 됨 확인 (Actions 끝난 후 repo에 새 commit 보임)
- [ ] Mac에서 `git pull` 했을 때 새 데이터 들어옴 확인

---

## 🔧 트러블슈팅

### "Permission denied" on git push
→ Personal Access Token 사용. Step 2 참조.

### Actions 실행 시 "GOOGLE_CREDENTIALS not found"
→ Secrets 이름 정확히 확인. 대소문자 구분.

### Actions가 5분 후 timeout
→ workflow의 `timeout-minutes: 30` 늘려도 OK. PubMed가 느린 날 발생.

### data/ commit이 push 안 됨
→ workflow에서 `permissions.contents: write` 확인 (이미 설정됨).

### Gemini quota 초과
→ research_analyzer가 자동 skip (cache hash). 다음날 재시도 자동.

---

## 💰 비용

| 항목 | 사용량 | 무료 한도 | 여유 |
|---|---|---|---|
| GitHub Actions (private repo) | 약 10분/일 × 30일 = 300분/월 | 2,000분/월 | 85% |
| Gemini 무료 tier | 약 15 calls/일 | 1,500/일 | 99% |
| Google Sheets API | 약 100 ops/일 | 무제한 | — |
| ClinicalTrials.gov API | 약 50 calls/일 | 무제한 | — |

**모든 운영 비용 무료**. 나중에 사용량 늘면 GitHub Pro ($4/월) 또는 Gemini API 유료 tier로 확장.

---

## 🎯 다음 단계 (선택)

이미 GitHub repo가 있으니 다음도 쉽게 추가 가능:

### A. Streamlit Cloud로 대시보드 호스팅 (10분)
- share.streamlit.io 가입
- "New app" → repo 선택 → `dashboard.py` 지정
- Secrets 동일하게 등록
- 본인 휴대폰/외부 PC 어디서나 `https://aplb.streamlit.app` 접속

### B. 협업자 초대 (5분)
- repo Settings → Collaborators → 팀원 GitHub ID 초대

# 🌐 Tailscale 셋업 가이드 — Mac에서 외부/팀 공유

## 왜 Tailscale인가?

- **초대받은 사람만** 접근 (공개 URL 아님)
- **데이터 외부 노출 0** — Mac 안에만 있고 Tailscale은 단지 네트워크 터널
- **5명까지 무료**
- 모바일/외부 PC/태블릿 어디서든 접근

## 1단계: Mac에 Tailscale 설치 (5분)

```bash
# Homebrew로 설치
brew install --cask tailscale

# 또는 https://tailscale.com/download 에서 다운로드
```

설치 후 **Tailscale.app 실행** → "Sign in" → Google/Microsoft 계정으로 로그인.

## 2단계: Mac의 Tailscale IP 확인

```bash
tailscale ip
# 예: 100.64.123.45
```

이 IP를 메모해 두세요. **이게 외부 접근용 주소**입니다.

## 3단계: Streamlit을 모든 인터페이스에서 받도록 실행

```bash
cd "/Users/user/Downloads/00. 클로드/beauty-trend-dashboard"

# 외부 접근 허용 (--server.address 0.0.0.0)
streamlit run dashboard.py \
  --server.port 8501 \
  --server.address 0.0.0.0 \
  --server.headless true
```

또는 자동 시작 스크립트:
```bash
bash scripts/start_dashboard.sh
```

## 4단계: 본인 휴대폰/외부 PC 셋업

1. 휴대폰/PC에 Tailscale 앱 설치
2. **같은 Google/Microsoft 계정으로 로그인**
3. 브라우저에서: `http://100.64.123.45:8501` (위에서 확인한 Mac IP)

→ 첫 화면: 로그인 (이메일/비번 입력)
→ 30일간 자동 로그인 유지

## 5단계: 팀원 (2-5명) 초대

### 방식 A: 같은 Tailnet에 초대 (가장 안전)

1. Tailscale 관리 페이지: https://login.tailscale.com/admin/users
2. "Invite users" → 팀원 이메일 입력
3. 팀원이 초대 수락 + Tailscale 설치
4. 본인 Mac IP로 접근 가능

### 방식 B: Tailscale Funnel (선택 — 더 광범위 공유 시)

Funnel은 Tailnet 외부에서도 공개 URL 접근 가능 (HTTPS 자동):

```bash
tailscale funnel --bg 8501
# 출력: https://your-mac.tailnet.ts.net/
```

⚠️ Funnel은 **인터넷 공개**이므로 streamlit-authenticator 비번 인증이 핵심 방어선.

## 6단계: 팀원별 로그인 계정 추가

본인 (Katie) Mac 터미널에서:
```bash
cd "/Users/user/Downloads/00. 클로드/beauty-trend-dashboard"
python3 scripts/manage_users.py add jane jane@team.com "Jane Doe" viewer
# 비밀번호 입력 + 확인
```

기본 비밀번호 변경 (첫 로그인 후 권장):
```bash
python3 scripts/manage_users.py change_password katie
```

사용자 목록:
```bash
python3 scripts/manage_users.py list
```

## 7단계: Mac sleep 방지

외출 시 Mac이 sleep 되면 외부 접근 끊김:

```bash
# 디스플레이 sleep 방지 (백그라운드)
caffeinate -dimsu &

# 또는 시스템 환경설정 > 배터리 > "Mac이 자동으로 sleep 모드로 전환되지 않게 함"
```

## 8단계: 시작 시 자동 실행 (선택)

`~/Library/LaunchAgents/com.aplb.dashboard.plist` 생성하면
Mac 부팅 시 streamlit + caffeinate 자동 시작 가능. (요청 시 별도 셋업)

---

## 🔍 체크리스트

- [ ] Mac에 Tailscale 설치 + 로그인
- [ ] Streamlit이 `0.0.0.0:8501`에서 실행 중
- [ ] 본인 휴대폰/외부 PC에 Tailscale 설치
- [ ] `http://<mac-ip>:8501` 접근 성공
- [ ] `katie` 계정으로 로그인 (기본 `beauty2025!`)
- [ ] **첫 로그인 후 비밀번호 변경**
- [ ] 팀원 추가 (필요 시): `manage_users.py add ...`

## ❓ 자주 묻는 질문

**Q. Mac IP가 변하나요?**
A. Tailscale IP는 영구 고정 (100.x.x.x). 일반 Wi-Fi IP와 무관.

**Q. VPN처럼 느려지나요?**
A. Tailscale은 P2P로 연결되므로 거의 직접 연결과 동일 속도.

**Q. 무료 5명 초과 시?**
A. Personal Plus (월 $5/사용자) 또는 별도 Tailnet 분리.

**Q. 본인 Tailnet 외 사람도 접근하려면?**
A. Funnel 사용 (위 5-B 참조) — 비번 인증이 진입 차단막.

#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# 대시보드 시작 스크립트 — Tailscale 외부 접근 + 멀티 사용자 인증
# ─────────────────────────────────────────────────────────────────
# 사용:
#   bash scripts/start_dashboard.sh         # 포그라운드
#   bash scripts/start_dashboard.sh --bg    # 백그라운드
# ─────────────────────────────────────────────────────────────────

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="$PROJECT_DIR/data/dashboard.log"
PORT=8501

cd "$PROJECT_DIR"

# 기존 streamlit 프로세스 종료
pkill -f "streamlit run dashboard.py" 2>/dev/null
sleep 1

# Tailscale IP 확인 (있으면 표시)
if command -v tailscale &> /dev/null; then
    TAILSCALE_IP=$(tailscale ip -4 2>/dev/null | head -1)
    if [ -n "$TAILSCALE_IP" ]; then
        echo "🌐 Tailscale IP: $TAILSCALE_IP"
        echo "   외부 접근 URL: http://$TAILSCALE_IP:$PORT"
    fi
fi

# 로컬 IP
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)
echo "💻 로컬 URL: http://localhost:$PORT  |  http://$LOCAL_IP:$PORT"
echo ""

# Mac sleep 방지 (백그라운드)
caffeinate -dimsu -t 86400 &
CAFFEINATE_PID=$!
echo "☕ Sleep 방지 활성 (PID $CAFFEINATE_PID, 24h)"

# Streamlit 실행
if [ "$1" == "--bg" ]; then
    echo "🚀 백그라운드 시작 → 로그: $LOG_FILE"
    nohup streamlit run dashboard.py \
        --server.port $PORT \
        --server.address 0.0.0.0 \
        --server.headless true \
        > "$LOG_FILE" 2>&1 &
    STREAMLIT_PID=$!
    echo "✅ Streamlit PID $STREAMLIT_PID"
    echo ""
    echo "🛑 종료 명령:"
    echo "   pkill -f 'streamlit run dashboard.py'"
    echo "   kill $CAFFEINATE_PID  # caffeinate 종료"
else
    echo "🚀 포그라운드 시작 (Ctrl+C로 종료)"
    streamlit run dashboard.py \
        --server.port $PORT \
        --server.address 0.0.0.0 \
        --server.headless true
fi

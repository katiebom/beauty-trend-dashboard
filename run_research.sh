#!/bin/bash
# R&D 파이프라인 자동 수집 스크립트
# LaunchAgent: ~/Library/LaunchAgents/com.aplb.research.plist (매일 6 AM)
# 수동 실행: bash run_research.sh

PROJECT="/Users/user/Downloads/00. 클로드/beauty-trend-dashboard"
LOG="$PROJECT/data/research_pipeline.log"
PYTHON="/usr/local/bin/python3"

cd "$PROJECT"

echo "" >> "$LOG"
echo "=== $(date '+%Y-%m-%d %H:%M:%S') 수집 시작 ===" >> "$LOG"

# .env는 python-dotenv가 자동 로드 (shell source는 JSON 줄바꿈으로 깨짐)
# 전체 R&D 파이프라인 실행 (PubMed → CIR → Gemini 분석 → Sheets → Brief)
$PYTHON collect/run_collector.py --research >> "$LOG" 2>&1

echo "=== $(date '+%Y-%m-%d %H:%M:%S') 수집 완료 ===" >> "$LOG"

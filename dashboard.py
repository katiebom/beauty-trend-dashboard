"""
뷰티 성분 트렌드 대시보드
streamlit run dashboard.py
"""

import os
import hashlib
import io
import json
import yaml
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import date, datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


# ── 비밀번호 인증 (로컬 토큰 파일로 30일 유지) ───────────────────────
_AUTH_TOKEN_FILE = Path.home() / ".beauty_dashboard_auth"
_AUTH_TOKEN_DAYS = 30


def _make_token(password: str) -> str:
    return hashlib.sha256(f"{password}:beauty_dashboard_v1".encode()).hexdigest()


def _save_auth_token(password: str):
    data = {
        "token": _make_token(password),
        "expires": (datetime.now() + timedelta(days=_AUTH_TOKEN_DAYS)).isoformat(),
    }
    _AUTH_TOKEN_FILE.write_text(json.dumps(data))


def _load_auth_token(password: str) -> bool:
    """로컬 토큰 파일이 유효하면 True."""
    if not _AUTH_TOKEN_FILE.exists():
        return False
    try:
        data = json.loads(_AUTH_TOKEN_FILE.read_text())
        if data.get("token") != _make_token(password):
            return False
        if datetime.fromisoformat(data["expires"]) < datetime.now():
            _AUTH_TOKEN_FILE.unlink(missing_ok=True)
            return False
        return True
    except Exception:
        return False


def check_password():
    """환경변수 DASHBOARD_PASSWORD로 접근 제한. 미설정 시 공개."""
    password = os.getenv("DASHBOARD_PASSWORD", "")
    if not password:
        return True

    # 1. 로컬 토큰 파일로 자동 인증 (새로고침해도 유지)
    if _load_auth_token(password):
        st.session_state.authenticated = True
        return True

    # 2. 세션 내 인증 상태
    if st.session_state.get("authenticated"):
        return True

    st.set_page_config(page_title="Beauty Trends — Login", page_icon="🔒", layout="centered")
    st.markdown("## 🔒 Beauty Ingredient Trends")
    pwd = st.text_input("비밀번호", type="password", placeholder="Enter password")
    if st.button("로그인"):
        if pwd == password:
            st.session_state.authenticated = True
            _save_auth_token(password)   # 로컬에 토큰 저장 → 30일 유지
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    st.stop()


if not check_password():
    st.stop()


# ── 페이지 설정 ────────────────────────────────────────────────────
st.set_page_config(
    page_title="Beauty Ingredient Trends",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 전역 스타일 (모던 디자인) ──────────────────────────────────────
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://cdn.jsdelivr.net">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css">
<style>
    /* ── 전역 폰트 ─────────────────────────────────────────── */
    html, body, [class*="css"], .stMarkdown, .stText, .stDataFrame {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, "SF Pro KR",
                     "Apple SD Gothic Neo", "Noto Sans KR", system-ui, sans-serif !important;
        -webkit-font-smoothing: antialiased;
    }

    /* ── 메인 영역 ─────────────────────────────────────────── */
    .stApp {
        background: linear-gradient(180deg, #fafafa 0%, #f5f5f7 100%);
    }
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 4rem;
        max-width: 1400px;
    }
    h1 {
        font-weight: 800 !important;
        letter-spacing: -0.02em !important;
        color: #0f0f12 !important;
        margin-bottom: 0.4rem !important;
    }
    h2 {
        font-weight: 700 !important;
        letter-spacing: -0.015em !important;
        color: #1a1a1f !important;
    }
    h3 {
        font-weight: 700 !important;
        letter-spacing: -0.01em !important;
        color: #1a1a1f !important;
        margin-top: 1.2rem !important;
        margin-bottom: 0.6rem !important;
    }

    /* ── 사이드바 ───────────────────────────────────────────── */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #ffffff 0%, #fbfbfd 100%);
        border-right: 1px solid #ececef;
        box-shadow: 1px 0 0 rgba(0,0,0,0.02);
    }
    section[data-testid="stSidebar"] > div {
        padding-top: 1.6rem;
    }
    /* 사이드바 타이틀 */
    section[data-testid="stSidebar"] h1 {
        font-size: 1.2rem !important;
        font-weight: 800 !important;
        letter-spacing: -0.02em !important;
        background: linear-gradient(135deg, #ec4899 0%, #8b5cf6 60%, #06b6d4 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem !important;
    }

    /* ── 사이드바 라디오 → 모던 메뉴 카드 ────────────────────── */
    section[data-testid="stSidebar"] .stRadio > label {
        display: none;  /* "뷰 선택" 라벨 숨김 */
    }
    section[data-testid="stSidebar"] [role="radiogroup"] {
        gap: 2px !important;
    }
    section[data-testid="stSidebar"] [role="radiogroup"] > label {
        background: transparent;
        padding: 9px 12px !important;
        border-radius: 9px;
        cursor: pointer;
        transition: all 0.15s ease;
        margin-bottom: 1px !important;
        border: 1px solid transparent;
    }
    section[data-testid="stSidebar"] [role="radiogroup"] > label:hover {
        background: #f3f4f7;
    }
    /* 라디오 동그라미 숨김 */
    section[data-testid="stSidebar"] [role="radiogroup"] > label > div:first-child {
        display: none !important;
    }
    /* 텍스트 폰트 */
    section[data-testid="stSidebar"] [role="radiogroup"] > label p {
        font-size: 0.88rem !important;
        font-weight: 500 !important;
        color: #3a3a44 !important;
        margin: 0 !important;
        letter-spacing: -0.01em;
    }
    /* 선택된 항목 — 그라데이션 배경 */
    section[data-testid="stSidebar"] [role="radiogroup"] > label:has(input:checked) {
        background: linear-gradient(135deg, #fdf2f8 0%, #f3e8ff 100%);
        border: 1px solid #f0d8ec;
        box-shadow: 0 1px 3px rgba(236, 72, 153, 0.08);
    }
    section[data-testid="stSidebar"] [role="radiogroup"] > label:has(input:checked) p {
        color: #7c2d6a !important;
        font-weight: 700 !important;
    }

    /* ── 사이드바 캡션/구분선 ─────────────────────────────────── */
    section[data-testid="stSidebar"] hr {
        margin: 0.9rem 0 !important;
        border-color: #ececef !important;
    }
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
        font-size: 0.72rem !important;
        color: #9ca3af !important;
        letter-spacing: 0.02em;
    }

    /* ── 사이드바 버튼 (새로고침 등) ─────────────────────────── */
    section[data-testid="stSidebar"] .stButton > button {
        width: 100%;
        border-radius: 9px;
        border: 1px solid #ececef;
        background: #ffffff;
        color: #4b5563;
        font-weight: 500;
        font-size: 0.84rem;
        padding: 7px 12px;
        transition: all 0.15s ease;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background: #f9fafb;
        border-color: #d8d8de;
        color: #1f2937;
    }

    /* ── 메인 버튼 ─────────────────────────────────────────── */
    .main .stButton > button {
        border-radius: 10px;
        font-weight: 600;
        letter-spacing: -0.005em;
        transition: all 0.15s ease;
        border: 1px solid #e5e7eb;
    }
    .main .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%);
        border: none;
        color: #fff;
        box-shadow: 0 1px 4px rgba(236, 72, 153, 0.25);
    }
    .main .stButton > button[kind="primary"]:hover {
        transform: translateY(-1px);
        box-shadow: 0 3px 10px rgba(236, 72, 153, 0.35);
    }

    /* ── 메트릭 카드 (KPI) ──────────────────────────────────── */
    [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #ececef;
        border-radius: 12px;
        padding: 14px 18px;
        transition: all 0.15s ease;
    }
    [data-testid="stMetric"]:hover {
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.78rem !important;
        color: #6b7280 !important;
        font-weight: 600 !important;
        letter-spacing: 0.01em;
        text-transform: uppercase;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.6rem !important;
        font-weight: 800 !important;
        color: #0f0f12 !important;
        letter-spacing: -0.02em;
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.78rem !important;
    }

    /* ── 탭 ─────────────────────────────────────────────────── */
    .stTabs [role="tablist"] {
        gap: 4px;
        border-bottom: 1px solid #ececef;
    }
    .stTabs [role="tab"] {
        font-weight: 600;
        font-size: 0.9rem;
        color: #6b7280;
        padding: 8px 16px;
        border-radius: 8px 8px 0 0;
        letter-spacing: -0.005em;
    }
    .stTabs [role="tab"][aria-selected="true"] {
        color: #ec4899;
        background: linear-gradient(180deg, #fdf2f8 0%, #ffffff 100%);
        border-bottom: 2px solid #ec4899 !important;
    }

    /* ── alert/info/warning/success 더 부드럽게 ────────────── */
    .stAlert > div {
        font-size: 0.85rem;
        padding: 10px 14px;
        border-radius: 10px;
        border: none !important;
    }

    /* ── 데이터프레임 ────────────────────────────────────────── */
    [data-testid="stDataFrame"] {
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid #ececef;
    }
    .dataframe thead th {
        background: #f9fafb !important;
        color: #1f2937 !important;
        font-weight: 700;
        font-size: 0.82rem !important;
        letter-spacing: 0.01em;
    }

    /* ── expander ────────────────────────────────────────────── */
    .streamlit-expanderHeader {
        font-weight: 600 !important;
        background: #ffffff !important;
        border-radius: 9px !important;
        border: 1px solid #ececef !important;
    }

    /* ── 입력 필드 ───────────────────────────────────────────── */
    .stTextInput > div > div > input,
    .stSelectbox > div > div,
    .stTextArea > div > div > textarea {
        border-radius: 9px;
        border: 1px solid #d1d5db;
        font-family: inherit;
    }

    /* ── divider 더 얇게 ────────────────────────────────────── */
    hr {
        border-color: #ececef;
        margin: 1.2rem 0;
    }

    /* ── 코드 블록 ───────────────────────────────────────────── */
    code {
        background: #f3f4f7 !important;
        color: #6b21a8 !important;
        padding: 2px 6px !important;
        border-radius: 4px !important;
        font-size: 0.85em !important;
        font-family: "SF Mono", "JetBrains Mono", monospace !important;
    }
    /* 메인 영역 줄간격 */
    .stMarkdown p { line-height: 1.65; }
</style>
""", unsafe_allow_html=True)

YAML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "ingredients.yaml")

STATUS_EMOJI = {"rising": "🟢", "falling": "🔴", "watching": "🟡"}
STATUS_COLOR = {"rising": "#00C48C", "falling": "#FF6B6B", "watching": "#FFB800"}

# ── 데이터 로딩 ────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_ingredients_config() -> list[dict]:
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["ingredients"]


@st.cache_data(ttl=3600)
def load_sheets_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Google Sheets에서 raw_trends + manual_input 로드"""
    try:
        import sys
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from config.sheets_client import read_all, ensure_tabs_exist, TAB_RAW_TRENDS, TAB_MANUAL_INPUT

        ensure_tabs_exist()
        raw = read_all(TAB_RAW_TRENDS)
        manual = read_all(TAB_MANUAL_INPUT)

        df_raw = pd.DataFrame(raw) if raw else pd.DataFrame()
        df_manual = pd.DataFrame(manual) if manual else pd.DataFrame()

        # Sheets는 연결됐지만 아직 데이터 없으면 샘플 데이터 사용
        if df_raw.empty:
            return _sample_data()

        if not df_raw.empty:
            df_raw["date"] = pd.to_datetime(df_raw["date"])
            df_raw["value"] = pd.to_numeric(df_raw["value"], errors="coerce")

        if not df_manual.empty:
            df_manual["date"] = pd.to_datetime(df_manual["date"])

        return df_raw, df_manual

    except Exception as e:
        # GOOGLE_SHEET_ID 미설정 시엔 조용히 샘플 데이터 사용 (설정 후엔 실제 연결)
        sheet_id = os.getenv("GOOGLE_SHEET_ID")
        if sheet_id:
            st.warning(f"Google Sheets 연결 실패: [{type(e).__name__}] {e}")
        return _sample_data()


def _sample_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sheets 연결 전 UI 미리보기용 샘플 데이터"""
    dates = pd.date_range(end=date.today(), periods=12, freq="W")
    ingredients = ["ectoin", "retinal", "beef_tallow", "pdrn_exosome",
                   "retinol", "vitamin_c_laa", "ceramide", "bakuchiol"]
    base_v  = {"ectoin": 62, "retinal": 71, "beef_tallow": 54, "pdrn_exosome": 48,
               "retinol": -18, "vitamin_c_laa": -32, "ceramide": 8, "bakuchiol": 22}
    base_r  = {"ectoin": 78, "retinal": 82, "beef_tallow": 65, "pdrn_exosome": 72,
               "retinol": 58, "vitamin_c_laa": 52, "ceramide": 74, "bakuchiol": 69}
    base_et_kr = {"ectoin": 68, "retinal": 76, "beef_tallow": 38, "pdrn_exosome": 71,
                  "retinol": 55, "vitamin_c_laa": 49, "ceramide": 72, "bakuchiol": 60}
    base_et_us = {"ectoin": 55, "retinal": 70, "beef_tallow": 28, "pdrn_exosome": 52,
                  "retinol": 72, "vitamin_c_laa": 65, "ceramide": 80, "bakuchiol": 68}
    pain_pts = {
        "ectoin": "刺激없음 | 가격 비쌈 | 향 불호",
        "retinal": "초기 각질 | 눈가 자극 | 농도 조절 어려움",
        "beef_tallow": "냄새 | 모공막힘 우려 | 위생 우려",
        "pdrn_exosome": "가격 매우 비쌈 | 효과 체감 느림 | 정품 구별 어려움",
        "retinol": "각질·건조 | 광과민성 | 임산부 불가",
        "vitamin_c_laa": "산화 빠름 | 따가움 | 변색",
        "ceramide": "무겁고 끈적 | 효과 체감 낮음 | 성분 함량 낮은 제품 많음",
        "bakuchiol": "효과 레티놀 대비 약함 | 향 강함 | 가격 대비 효과",
    }

    rows = []
    for d in dates:
        for ing_id in ingredients:
            dv = np.random.normal(0, 4)
            dr = np.random.normal(0, 2)
            det = np.random.normal(0, 3)
            for metric, base, drift, lo, hi in [
                ("v_index",     base_v[ing_id],      dv,  -100, 100),
                ("n_score",     base_r[ing_id],      dr,     0, 100),
                ("et_score_kr", base_et_kr[ing_id],  det,    0, 100),
                ("et_score_us", base_et_us[ing_id],  det,    0, 100),
            ]:
                rows.append({"date": d, "ingredient_id": ing_id,
                              "metric_name": metric,
                              "value": max(lo, min(hi, base + drift)),
                              "source": "sample"})
            # Pain points (최신 날짜에만)
            if d == dates[-1]:
                rows.append({"date": d, "ingredient_id": ing_id,
                              "metric_name": "pain_points",
                              "value": pain_pts.get(ing_id, ""),
                              "source": "sample"})

    df_raw = pd.DataFrame(rows)
    df_manual = pd.DataFrame()
    return df_raw, df_manual


@st.cache_data(ttl=3600)
def get_latest_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """성분별 최신 지표 추출. collected_at 기준 가장 최근 수집값 사용 (평균 X)."""
    if df.empty:
        return pd.DataFrame()
    latest_date = df["date"].max()
    recent = df[df["date"] >= latest_date - timedelta(days=8)].copy()

    # collected_at 컬럼이 있으면 정렬에 활용, 없으면 date만 사용
    sort_cols = ["ingredient_id", "metric_name", "date"]
    if "collected_at" in recent.columns:
        recent["collected_at"] = pd.to_datetime(recent["collected_at"], errors="coerce")
        sort_cols.append("collected_at")

    # 정렬 후 (ingredient_id, metric_name) 그룹에서 마지막 행 = 가장 최신 수집값
    recent_sorted = recent.sort_values(sort_cols, na_position="first")
    latest_rows = recent_sorted.groupby(["ingredient_id", "metric_name"]).last().reset_index()

    pivot = (
        latest_rows
        .pivot(index="ingredient_id", columns="metric_name", values="value")
        .reset_index()
    )
    pivot.columns.name = None
    return pivot


# ── 사이드바 ────────────────────────────────────────────────────────
def sidebar():
    # ── 헤더 (브랜드 마크) ────────────────────────────────────
    st.sidebar.markdown("""
    <div style="padding: 4px 0 18px 0;">
      <div style="font-size: 1.45rem; font-weight: 800; letter-spacing: -0.025em;
           background: linear-gradient(135deg, #ec4899 0%, #8b5cf6 60%, #06b6d4 100%);
           -webkit-background-clip: text; -webkit-text-fill-color: transparent;
           line-height: 1.15;">
        Beauty OS
      </div>
      <div style="font-size: 0.72rem; color: #9ca3af; font-weight: 500;
           letter-spacing: 0.04em; margin-top: 2px;">
        APLB · INGREDIENT INTELLIGENCE
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 섹션 그룹 + 메뉴 (라디오는 단일이지만 캡션으로 그루핑 시각화) ──
    # 각 항목 아이콘 + 한국어 더 간결하게
    view_groups = [
        ("📊  현황 모니터링", [
            "📊 As-Is 매트릭스",
            "📅 주간 트래킹",
            "📈 시계열 분석",
            "📋 판매 검증 입력",
        ]),
        ("🔬  R&D · 신성분", [
            "🔬 성분 연구 인사이트",
            "🔭 신성분 발굴 (3-Tier)",
            "🏪 시장 경쟁 진단",
            "🔬 왜 안 뜨는가 진단",
        ]),
        ("✨  APLB 전략", [
            "✨ APLB 마케팅 클레임",
            "⚫ APLB Black 후보",
        ]),
        ("⚙️  시스템", [
            "⚙️ 지표 방법론",
            "📺 채널 관리",
            "🛠️ 관리자 가이드",
        ]),
    ]
    all_options = []
    for _, items in view_groups:
        all_options.extend(items)

    # 그룹별 헤더 + 라디오 한 번에
    # streamlit-radio는 단일이라 그룹 헤더는 별도 markdown으로
    # → 메뉴 전체는 하나의 라디오, 헤더는 그룹 캡션을 본문에 끼워넣음
    # → 정렬 위해 옵션 리스트에 헤더 자체를 끼워넣지는 않고
    #   대신 사이드바 위에 그룹 컬러 띠만 표시
    st.sidebar.markdown("""
    <div style="display:flex; gap:6px; margin-bottom:14px;">
      <div style="flex:1; height:3px; background:linear-gradient(90deg,#ec4899,#f472b6); border-radius:2px;"></div>
      <div style="flex:1; height:3px; background:linear-gradient(90deg,#8b5cf6,#a78bfa); border-radius:2px;"></div>
      <div style="flex:1; height:3px; background:linear-gradient(90deg,#06b6d4,#22d3ee); border-radius:2px;"></div>
      <div style="flex:1; height:3px; background:linear-gradient(90deg,#9ca3af,#d1d5db); border-radius:2px;"></div>
    </div>
    """, unsafe_allow_html=True)

    # 그룹별로 캡션 + 라디오 — Streamlit radio는 한 그룹 내에서만 단일 선택 가능하므로
    # 모든 옵션을 단일 radio로 두고, 그룹 헤더는 markdown으로 표시
    # 그룹별로 분리해서 보여주려면 각 그룹마다 selectbox/button을 써야 하는데
    # → 가장 간단한 깔끔한 방식: 그룹별 캡션 + 단일 라디오 (각 그룹마다 옵션 추출)
    # 여기서는 시각적 구분을 위해 각 그룹 옵션 목록을 별도 라디오로 분리하면
    # session_state로 마지막 선택 추적 필요 → 단순화 위해 단일 라디오 유지하되
    # 옵션 구분선은 첫 항목들에서 보이도록 그룹 헤더만 markdown으로 렌더

    # 단일 라디오 유지 (가장 안정적)
    # Executive Brief를 가장 위에 추가
    all_options_with_brief = ["🎯 Executive Brief"] + all_options
    view = st.sidebar.radio(
        "메뉴",
        all_options_with_brief,
        label_visibility="collapsed",
        key="main_nav",
    )

    # 그룹 라벨을 라디오 위에 시각적으로 보이게 캡션 형태로 출력
    # → CSS로 라디오 라벨 사이에 임의 캡션 삽입은 어려움.
    # 대신 사이드바 하단에 그룹별 빠른 점프 칩 제공
    st.sidebar.markdown("""
    <div style="margin-top: 16px; padding: 10px 0; border-top: 1px solid #ececef;">
      <div style="font-size: 0.65rem; color: #9ca3af; font-weight: 700;
           letter-spacing: 0.06em; margin-bottom: 8px;">CATEGORIES</div>
      <div style="display:flex; flex-wrap:wrap; gap:4px;">
        <span style="font-size:0.7rem; padding:2px 8px; background:#fdf2f8;
              color:#be185d; border-radius:6px; font-weight:600;">📊 현황</span>
        <span style="font-size:0.7rem; padding:2px 8px; background:#f3e8ff;
              color:#6b21a8; border-radius:6px; font-weight:600;">🔬 R&D</span>
        <span style="font-size:0.7rem; padding:2px 8px; background:#cffafe;
              color:#0e7490; border-radius:6px; font-weight:600;">✨ 전략</span>
        <span style="font-size:0.7rem; padding:2px 8px; background:#f3f4f6;
              color:#4b5563; border-radius:6px; font-weight:600;">⚙️ 시스템</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 데이터 신선도 인디케이터 ────────────────────────────
    brief_path = Path(__file__).parent / "data" / "executive_brief" / "latest.json"
    freshness_emoji = "🟢"
    freshness_text = "Live"
    days_ago = "?"
    if brief_path.exists():
        try:
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
            kpi = brief.get("kpi", {})
            d = kpi.get("days_since_data", 999)
            days_ago = f"{d}d ago" if d >= 0 else "?"
            if d <= 1:
                freshness_emoji, freshness_text = "🟢", "Fresh"
            elif d <= 7:
                freshness_emoji, freshness_text = "🟡", "Stale"
            else:
                freshness_emoji, freshness_text = "🔴", "Very stale"
        except Exception:
            pass

    # ── 푸터 ───────────────────────────────────────────────────
    st.sidebar.markdown(f"""
    <div style="margin-top: 14px; padding: 12px 0; border-top: 1px solid #ececef;
         font-size: 0.7rem; color: #9ca3af;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
        <span style="font-weight:600;">{freshness_emoji} {freshness_text}</span>
        <span style="font-family:'SF Mono',monospace; font-size:0.66rem;">
          {days_ago}
        </span>
      </div>
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <span style="font-size:0.66rem;">UTC</span>
        <span style="font-family:'SF Mono',monospace; font-size:0.66rem;">
          {date.today().isoformat()}
        </span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if st.sidebar.button("🔄 데이터 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    return view


def compute_final_score(v: str, r: str, et: str) -> str:
    """V×0.3 + R×0.3 + ET×0.4. V는 -100~+100 → 0~100 정규화 후 합산"""
    try:
        v_norm = (float(v) + 100) / 2 if v != "—" else None
        r_val  = float(r) if r != "—" else None
        et_val = float(et) if et != "—" else None

        if v_norm is None and r_val is None:
            return "—"
        # ET 없을 때 V:R = 0.5:0.5
        if et_val is None:
            score = (v_norm or 50) * 0.5 + (r_val or 50) * 0.5
        else:
            score = (v_norm or 50) * 0.3 + (r_val or 50) * 0.3 + et_val * 0.4
        return f"{score:.0f}"
    except Exception:
        return "—"


def build_export_df(ingredients: list[dict], df: pd.DataFrame) -> pd.DataFrame:
    """성분별 최신 지표를 모아 내보내기용 DataFrame 생성"""
    latest = get_latest_metrics(df)

    def _val(ing_id, metric):
        if latest.empty or metric not in latest.columns:
            return None
        row = latest[latest["ingredient_id"] == ing_id]
        if row.empty:
            return None
        v = row.iloc[0].get(metric)
        if v is None or (not isinstance(v, str) and pd.isna(v)):
            return None
        return v

    rows = []
    for ing in ingredients:
        iid = ing["id"]
        v      = _val(iid, "v_index")
        r      = _val(iid, "n_score")
        et_kr  = _val(iid, "et_score_kr")
        et_us  = _val(iid, "et_score_us")
        fs_str = compute_final_score(
            f"{v:.0f}" if v is not None else "—",
            f"{r:.0f}" if r is not None else "—",
            f"{et_kr:.0f}" if et_kr is not None else "—",
        )

        rows.append({
            "순위":         None,
            "성분 ID":      iid,
            "성분명 (KR)":  ing["name_kr"],
            "성분명 (EN)":  ing["name_en"],
            "카테고리":     ing.get("category", ""),
            "상태":         ing.get("status", ""),
            "V-Index":      round(v, 1) if v is not None else None,
            "N-Score":      round(r, 1) if r is not None else None,
            "ET-KR":        round(et_kr, 1) if et_kr is not None else None,
            "ET-US":        round(et_us, 1) if et_us is not None else None,
            "FinalScore":   float(fs_str) if fs_str != "—" else None,
            "Pain Points":  _val(iid, "pain_points") or "",
            "비고":         ing.get("notes", ""),
        })

    df_out = pd.DataFrame(rows)
    # FinalScore 기준 내림차순 정렬 + 순위 부여
    df_out = df_out.sort_values("FinalScore", ascending=False, na_position="last").reset_index(drop=True)
    df_out["순위"] = df_out["FinalScore"].notna().cumsum().where(df_out["FinalScore"].notna())
    df_out["순위"] = df_out["순위"].astype("Int64")
    return df_out


# ── View 1: As-Is 매트릭스 ──────────────────────────────────────────
def view_matrix(ingredients: list[dict], df: pd.DataFrame, df_manual: pd.DataFrame):
    st.title("📊 K-Beauty 글로벌 성분 트렌드")
    st.caption(f"기준일: {date.today().isoformat()} | 전략: 미국에서 뜨는 성분을 K-Beauty로 선점 → 글로벌 출시")

    # ── 📖 매트릭스 사용 가이드 ───────────────────────────────
    st.markdown("""
    <div style="background:#fafafa;border:1px solid #ececef;border-radius:10px;
         padding:14px 18px;margin-bottom:14px">
      <div style="font-size:0.78rem;color:#6b7280;font-weight:700;
           letter-spacing:0.05em;margin-bottom:10px">📖 점수 해석 가이드</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;font-size:0.82rem">
        <div style="border-left:3px solid #4fc3f7;padding:6px 10px">
          <b>V-Index</b> (검색 가속도, -100~+100)<br>
          <span style="color:#666">+50 이상: 폭발 / 0 이하: 식는 중</span>
        </div>
        <div style="border-left:3px solid #ff7043;padding:6px 10px">
          <b>N-Score</b> (네이버 트렌드)<br>
          <span style="color:#666">한국 시장 검색 강도 (0~100)</span>
        </div>
        <div style="border-left:3px solid #66bb6a;padding:6px 10px">
          <b>ET-Index</b> (YouTube 콘텐츠량)<br>
          <span style="color:#666">소비자 노출도 (KR/US 별도)</span>
        </div>
        <div style="border-left:3px solid #ec4899;padding:6px 10px">
          <b>FinalScore</b> = V·30% + N·30% + ET·40%<br>
          <span style="color:#666">62점 이상 = 출시 검토 기준선</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # APLB 보유 매핑
    aplb_owned_set = set()
    try:
        aplb_yaml = Path(__file__).parent / "config" / "aplb_products.yaml"
        if aplb_yaml.exists():
            aplb = yaml.safe_load(aplb_yaml.read_text(encoding="utf-8"))
            for cx in aplb.get("complexes", []) + aplb.get("single_actives", []):
                for ing in cx.get("primary_ingredients", []):
                    aplb_owned_set.add(ing.lower())
    except Exception:
        pass

    latest = get_latest_metrics(df)

    # ── 헬퍼 함수 ────────────────────────────────────────────────
    def get_val(ing_id: str, metric: str) -> str:
        if latest.empty or metric not in latest.columns:
            return "—"
        row = latest[latest["ingredient_id"] == ing_id]
        if row.empty:
            return "—"
        val = row.iloc[0].get(metric)
        if val is None or (not isinstance(val, str) and pd.isna(val)):
            return "—"
        if isinstance(val, str):
            return val
        return f"{val:.0f}"

    def get_c_ratio(ing_id: str) -> str:
        if df_manual.empty or "ingredient_id" not in df_manual.columns:
            return "—"
        row = df_manual[df_manual["ingredient_id"] == ing_id].sort_values("date", ascending=False)
        if row.empty:
            return "—"
        return str(row.iloc[0].get("c_ratio_note", "—"))

    def score_color(val_str, lo=-100, hi=100):
        if val_str == "—": return "#aaa"
        pct = (float(val_str) - lo) / (hi - lo)
        if pct >= 0.7: return "#111"
        if pct >= 0.5: return "#444"
        if pct >= 0.3: return "#888"
        return "#cc3333"

    def v_display(val_str):
        if val_str == "—": return "—", "#aaa"
        val = float(val_str)
        display = f"+{val:.0f}" if val > 0 else f"{val:.0f}"
        color = "#111" if val >= 50 else ("#444" if val >= 0 else "#cc3333")
        return display, color

    def final_score_color(val_str):
        if val_str == "—": return "#aaa", "#f5f5f5"
        val = float(val_str)
        if val >= 70: return "#fff", "#1b5e20"
        if val >= 50: return "#fff", "#388e3c"
        if val >= 30: return "#111", "#fdd835"
        return "#fff", "#c62828"

    def build_relation_badges(ing_data):
        badges, id_to_name = [], {i["id"]: i["name_kr"] for i in ingredients}
        for tid in ing_data.get("replaces", []):
            badges.append(f'<span style="background:#e8f5e9;color:#2e7d32;border:1px solid #a5d6a7;border-radius:4px;padding:2px 7px;font-size:0.67rem;font-weight:600;margin-right:4px;">▲ {id_to_name.get(tid,tid)} 대체</span>')
        for tid in ing_data.get("replaced_by", []):
            badges.append(f'<span style="background:#fce4ec;color:#c62828;border:1px solid #ef9a9a;border-radius:4px;padding:2px 7px;font-size:0.67rem;font-weight:600;margin-right:4px;">▼ {id_to_name.get(tid,tid)}에 이전</span>')
        return "".join(badges)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SECTION 1 — 이번 주 요약 배너
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    _weekly_summary_banner(ingredients, latest)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SECTION 2 — 기회 맵 + Top 10 + 시사점
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    st.subheader("🌏 K-Beauty 글로벌 기회 맵")
    st.caption("💡 **우상단 = 퍼스트무버 찬스** (미국 수요 ↑ + 한국서도 아직 초기 → K-Beauty 글로벌 미진입 가능) | **우하단** = 한국 이미 인기 → K-Beauty 브랜드 글로벌 런치 중일 가능성 높음 (PDRN/Medicube 사례) | **좌상단** = 글로벌 수요 형성 전 선점 모니터링")
    chart_data, has_us_data = _scatter_map(ingredients, latest)
    _launch_top_picks(chart_data, has_us_data, ingredients, latest)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SECTION 3 — 성분별 상세 카드
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    st.divider()
    st.subheader("🧪 성분별 상세 지표")

    # ★ FinalScore 범례
    st.markdown("""
<div style="background:#f8f9fa;border:1px solid #e0e0e0;border-radius:8px;padding:10px 16px;
            margin-bottom:16px;font-size:0.78rem;line-height:1.9;">
  <b>★ FinalScore</b> — 카드 우상단 숫자. 각 성분의 <b>종합 트렌드 강도</b>를 0~100으로 표현
  &nbsp;|&nbsp; 공식: <b>글로벌 V-Index 30%</b> (Google 검색 가속도) + <b>N-Score 30%</b> (K-Beauty 시장 침투도) + <b>ET-Index 40%</b> (전문의 YouTube 언급)
  &nbsp;|&nbsp; ET 없을 때는 V:N = 50:50
  &nbsp;&nbsp;
  <span style="background:#1b5e20;color:#fff;border-radius:4px;padding:1px 7px;font-weight:700;">★70+</span> 즉시 검토&nbsp;
  <span style="background:#388e3c;color:#fff;border-radius:4px;padding:1px 7px;font-weight:700;">★50+</span> 유망&nbsp;
  <span style="background:#fdd835;color:#111;border-radius:4px;padding:1px 7px;font-weight:700;">★30+</span> 관망&nbsp;
  <span style="background:#c62828;color:#fff;border-radius:4px;padding:1px 7px;font-weight:700;">★30미만</span> 하락
</div>
""", unsafe_allow_html=True)

    for status in ["rising", "falling", "watching"]:
        group = [i for i in ingredients if i["status"] == status]
        if not group:
            continue

        emoji = STATUS_EMOJI[status]
        color = STATUS_COLOR[status]
        label = {"rising": "RISING ▲", "falling": "FALLING ▼", "watching": "WATCHING ~"}[status]
        bg = {"rising": "#f0faf5", "falling": "#fff5f5", "watching": "#fffbf0"}[status]

        st.markdown(f"""
<div style="background:{bg}; border-radius:8px; padding:8px 16px; margin-bottom:12px; display:inline-block;">
<span style="font-size:1.1rem; font-weight:700; color:#111;">{emoji} {label}</span>
</div>
""", unsafe_allow_html=True)
        cols = st.columns(min(len(group), 4))

        for idx, ing in enumerate(group):
            with cols[idx % 4]:
                v     = get_val(ing["id"], "v_index")
                v_us  = get_val(ing["id"], "v_index_us")
                r     = get_val(ing["id"], "n_score")
                et_kr = get_val(ing["id"], "et_score_kr")
                et_us = get_val(ing["id"], "et_score_us")
                c     = get_c_ratio(ing["id"])
                fs    = compute_final_score(v, r, et_kr)
                gs    = get_val(ing["id"], "gs_index")        # Google Shopping
                amz_reviews  = get_val(ing["id"], "amazon_top_reviews")
                amz_badges   = get_val(ing["id"], "amazon_bestseller_count")
                is_seasonal = get_val(ing["id"], "is_seasonal") == "1"
                pain_raw  = get_val(ing["id"], "pain_points")
                pain_pts  = [p.strip() for p in pain_raw.split("|") if p.strip()] if pain_raw != "—" else []
                note      = ing.get("notes", "")[:65] + ("…" if len(ing.get("notes", "")) > 65 else "")

                badges_html = build_relation_badges(ing)
                relation_note = ing.get("relation_note", "")
                relation_section = ""
                if badges_html:
                    rel_tooltip = f'<div style="font-size:0.67rem;color:#888;margin-top:3px;">{relation_note}</div>' if relation_note else ""
                    relation_section = f'<div style="margin-bottom:8px;">{badges_html}{rel_tooltip}</div>'

                seasonal_flag = '<span style="background:#fff3e0;color:#e65100;border:1px solid #ffcc80;border-radius:4px;padding:1px 6px;font-size:0.65rem;font-weight:600;margin-left:4px;">⚠️ 계절성</span>' if is_seasonal else ""
                v_str, v_col = v_display(v)
                fs_text_col, fs_bg_col = final_score_color(fs)
                et_kr_col = score_color(et_kr, 0, 100) if et_kr != "—" else "#aaa"
                et_us_col = score_color(et_us, 0, 100) if et_us != "—" else "#aaa"
                gs_col    = score_color(gs, -100, 100) if gs != "—" else "#aaa"

                # Amazon + GS 하단 보조 행
                extra_html = ""
                extra_parts = []
                if gs != "—":
                    try:
                        gs_f = float(gs)
                        gs_label = "🛍 GS"
                        extra_parts.append(
                            f'<span style="background:#f3e5f5;color:#6a1b9a;border-radius:4px;padding:1px 6px;font-size:0.65rem;font-weight:700;">'
                            f'{gs_label} {gs_f:+.0f}</span>'
                        )
                    except (ValueError, TypeError):
                        pass
                if amz_reviews != "—":
                    try:
                        amz_r = int(float(amz_reviews))
                        badge_str = f" 🏅{int(float(amz_badges))}개" if amz_badges != "—" else ""
                        extra_parts.append(
                            f'<span style="background:#fff8e1;color:#f57f17;border-radius:4px;padding:1px 6px;font-size:0.65rem;font-weight:700;">'
                            f'🛒 {amz_r:,}리뷰{badge_str}</span>'
                        )
                    except (ValueError, TypeError):
                        pass
                if extra_parts:
                    extra_html = '<div style="margin-top:5px;display:flex;flex-wrap:wrap;gap:4px;">' + "".join(extra_parts) + '</div>'

                pain_html = ""
                if pain_pts:
                    tags = "".join([f'<span style="background:#fff3f3;color:#c62828;border:1px solid #ffcdd2;border-radius:3px;padding:1px 5px;font-size:0.65rem;margin-right:3px;">{p}</span>' for p in pain_pts])
                    pain_html = f'<div style="margin-top:6px;"><span style="font-size:0.65rem;color:#999;font-weight:600;">⚠ PAIN</span> {tags}</div>'

                st.markdown(f"""
<div style="border-left:5px solid {color};border-radius:8px;padding:14px 16px;margin-bottom:12px;background:#ffffff;box-shadow:0 1px 4px rgba(0,0,0,0.08);">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:2px;">
    <div style="font-size:1.05rem;font-weight:700;color:#111;">{ing['name_kr']}{seasonal_flag}</div>
    <div style="background:{fs_bg_col};color:{fs_text_col};border-radius:6px;padding:3px 9px;font-size:0.8rem;font-weight:800;min-width:36px;text-align:center;">★ {fs}</div>
  </div>
  <div style="font-size:0.72rem;color:#777;margin-bottom:8px;">{ing['name_en']} · {ing.get('category','')}</div>
  {relation_section}
  <div style="display:flex;justify-content:space-between;text-align:center;gap:4px;margin-bottom:6px;align-items:stretch;">
    <div style="flex:1.6;background:#f5f5f5;border-radius:6px;padding:6px 4px;display:flex;flex-direction:column;justify-content:center;min-width:0;">
      <div style="font-size:0.5rem;color:#777;font-weight:700;letter-spacing:0.03em;margin-bottom:3px;white-space:nowrap;">V-INDEX</div>
      <div style="display:flex;justify-content:space-around;align-items:center;">
        <div style="flex:1;min-width:0;">
          <div style="font-size:0.5rem;color:#888;font-weight:600;">🌐GL</div>
          <div style="font-size:0.95rem;font-weight:800;color:{v_col};line-height:1.3;">{v_str}</div>
        </div>
        <div style="width:1px;background:#ddd;align-self:stretch;margin:0 3px;"></div>
        <div style="flex:1;min-width:0;">
          <div style="font-size:0.5rem;color:#888;font-weight:600;">🇺🇸US</div>
          <div style="font-size:0.95rem;font-weight:800;color:{v_display(v_us)[1]};line-height:1.3;">{v_display(v_us)[0]}</div>
        </div>
      </div>
    </div>
    <div style="flex:1;background:#f5f5f5;border-radius:6px;padding:8px 3px;display:flex;flex-direction:column;justify-content:center;min-width:0;">
      <div style="font-size:0.58rem;color:#777;font-weight:600;letter-spacing:0.04em;white-space:nowrap;">N-SCORE</div>
      <div style="font-size:1.2rem;font-weight:800;color:{score_color(r,0,100)};line-height:1.3;margin-top:3px;">{r}</div>
    </div>
    <div style="flex:1.8;background:#f0f4ff;border-radius:6px;padding:6px 4px;display:flex;flex-direction:column;justify-content:center;min-width:0;">
      <div style="font-size:0.55rem;color:#5c6bc0;font-weight:700;letter-spacing:0.03em;margin-bottom:3px;white-space:nowrap;">ET-INDEX</div>
      <div style="display:flex;justify-content:space-around;align-items:center;">
        <div style="flex:1;min-width:0;">
          <div style="font-size:0.5rem;color:#888;font-weight:600;">🇰🇷KR</div>
          <div style="font-size:0.95rem;font-weight:800;color:{et_kr_col};line-height:1.3;word-break:keep-all;">{et_kr}</div>
        </div>
        <div style="width:1px;background:#dde;align-self:stretch;margin:0 3px;"></div>
        <div style="flex:1;min-width:0;">
          <div style="font-size:0.5rem;color:#888;font-weight:600;">🇺🇸US</div>
          <div style="font-size:0.95rem;font-weight:800;color:{et_us_col};line-height:1.3;word-break:keep-all;">{et_us}</div>
        </div>
      </div>
    </div>
    <div style="flex:1;background:#f5f5f5;border-radius:6px;padding:8px 3px;display:flex;flex-direction:column;justify-content:center;min-width:0;">
      <div style="font-size:0.58rem;color:#777;font-weight:600;letter-spacing:0.04em;white-space:nowrap;">C-RATIO</div>
      <div style="font-size:1.2rem;font-weight:800;color:#555;line-height:1.3;margin-top:3px;">{c}</div>
    </div>
  </div>
  {extra_html}
  {pain_html}
  <div style="font-size:0.72rem;color:#555;margin-top:8px;line-height:1.5;border-top:1px solid #eee;padding-top:8px;">{note}</div>
</div>
""", unsafe_allow_html=True)

        st.divider()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SECTION 4 — 내보내기 (하단)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with st.expander("📥 데이터 내보내기 (Excel / JSON)", expanded=False):
        export_df = build_export_df(ingredients, df)
        st.dataframe(export_df, use_container_width=True, hide_index=True)
        col_xl, col_js, col_note = st.columns([1, 1, 3])
        with col_xl:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                export_df.to_excel(writer, index=False, sheet_name="출시유망순위")
            st.download_button("⬇️ Excel 다운로드", buf.getvalue(),
                               f"beauty_trends_{date.today().isoformat()}.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with col_js:
            st.download_button("⬇️ JSON 다운로드",
                               export_df.to_json(orient="records", force_ascii=False, indent=2),
                               f"beauty_trends_{date.today().isoformat()}.json", "application/json")
        with col_note:
            st.caption("FinalScore 기준 내림차순 정렬.")


def _weekly_summary_banner(ingredients: list[dict], latest):
    """페이지 최상단: 이번 주 핵심 시사점 3줄 배너"""
    if latest.empty:
        return

    # 데이터 집계
    rising = [i for i in ingredients if i["status"] == "rising"]
    top_rising_names = [i["name_kr"] for i in rising[:3]]

    # US V-Index 기준 상위 성분
    us_scores = []
    for ing in ingredients:
        row = latest[latest["ingredient_id"] == ing["id"]]
        if row.empty:
            continue
        v_us = row.iloc[0].get("v_index_us")
        n = row.iloc[0].get("n_score")
        t = row.iloc[0].get("t_score")
        if v_us is not None and not pd.isna(v_us) and float(v_us) > 0:
            us_scores.append({
                "name": ing["name_kr"],
                "v_us": float(v_us),
                "n": float(n) if (n is not None and not pd.isna(n)) else 50,
                "t": float(t) if (t is not None and not pd.isna(t)) else None,
                "gap": 100 - (float(n) if (n is not None and not pd.isna(n)) else 50),
            })

    us_scores.sort(key=lambda x: x["v_us"], reverse=True)
    tiktok_signals = [s for s in us_scores if s["t"] is not None and s["t"] >= 65]
    prime_opps = [s for s in us_scores if s["gap"] > 50]

    # 배너 문구 조합
    bullets = []
    if us_scores:
        top1 = us_scores[0]
        bullets.append(
            f"🔥 <b>{top1['name']}</b>이 미국 검색 가속도 1위 (V-Index US: +{top1['v_us']:.0f}) "
            f"— {'K-Beauty 아직 미개척, 퍼스트무버 가능' if top1['gap'] > 50 else 'K-Beauty 이미 진입 중, 차별화 필요'}"
        )
    if tiktok_signals:
        names = ", ".join([s["name"] for s in tiktok_signals[:2]])
        bullets.append(
            f"🎵 <b>{names}</b> TikTok 선행 신호 포착 — 구글 검색보다 앞선 얼리 시그널, 소싱 타이밍 검토 권장"
        )
    if prime_opps:
        cnt = len(prime_opps)
        bullets.append(
            f"🌱 미국 수요 있고 K-Beauty 미개척 성분 <b>{cnt}개</b> — "
            f"우상단 기회 맵에서 상세 확인"
        )
    if not bullets:
        bullets.append("📊 데이터 수집 후 이번 주 시사점이 자동 생성됩니다.")

    bullets_html = "".join(
        f'<div style="padding:5px 0;border-bottom:1px solid #e8f4fd;font-size:0.85rem;color:#1a1a2e;line-height:1.6;">{b}</div>'
        for b in bullets
    )
    st.markdown(f"""
<div style="background:linear-gradient(135deg,#e8f4fd 0%,#f0faf5 100%);
            border:1px solid #b3d9f7;border-radius:10px;padding:14px 20px;margin-bottom:20px;">
  <div style="font-size:0.72rem;font-weight:700;color:#1565c0;letter-spacing:0.08em;margin-bottom:8px;">
    📌 이번 주 K-Beauty 기회 시사점 · {date.today().isoformat()}
  </div>
  {bullets_html}
</div>
""", unsafe_allow_html=True)


def _scatter_map(ingredients, latest):
    if latest.empty:
        st.info("데이터 수집 후 차트가 표시됩니다.")
        return [], False

    chart_data = []
    has_us_data = False
    for ing in ingredients:
        row = latest[latest["ingredient_id"] == ing["id"]]
        if row.empty:
            continue
        v_us = row.iloc[0].get("v_index_us", None)
        v_global = row.iloc[0].get("v_index", None)
        n = row.iloc[0].get("n_score", None)
        t = row.iloc[0].get("t_score", None)

        # US V-Index 없으면 Global V-Index 폴백
        if v_us is not None and not pd.isna(v_us):
            v = float(v_us)
            has_us_data = True
        elif v_global is not None and not pd.isna(v_global):
            v = float(v_global)
        else:
            continue

        n_val = float(n) if (n is not None and not pd.isna(n)) else 50.0
        t_val = float(t) if (t is not None and not pd.isna(t)) else None
        # K-Beauty 미개척도: N-Score 낮을수록 K-Beauty 브랜드가 아직 이 성분을 안 씀
        # → 높을수록 퍼스트무버로 K-Beauty 글로벌 런치 가능
        kbeauty_gap = round(100 - n_val, 1)

        chart_data.append({
            "ingredient_id": ing["id"],
            "name_kr": ing["name_kr"],
            "name_en": ing.get("name_en", ""),
            "v_us": v,
            "v_global": float(v_global) if (v_global is not None and not pd.isna(v_global)) else None,
            "kr_gap": kbeauty_gap,   # 변수명 유지 (내부 계산 호환)
            "kbeauty_gap": kbeauty_gap,
            "n_score": n_val,
            "t_score": t_val,
            "status": ing["status"],
            "category": ing.get("category", ""),
            "notes": ing.get("notes", ""),
        })

    if not chart_data:
        st.info("데이터 수집 후 차트가 표시됩니다.")
        return [], False

    x_label = "US V-Index (미국 검색 가속도)" if has_us_data else "Global V-Index (검색 가속도)"
    df_chart = pd.DataFrame(chart_data)

    fig = px.scatter(
        df_chart,
        x="v_us", y="kbeauty_gap",
        color="status",
        color_discrete_map=STATUS_COLOR,
        size=[20] * len(df_chart),
        hover_name="name_kr",
        hover_data={
            "category": True, "status": True, "v_us": True,
            "n_score": True, "kbeauty_gap": True, "t_score": True,
        },
        labels={
            "v_us": x_label,
            "kbeauty_gap": "K-Beauty 미개척도 (100 - N-Score)",
            "n_score": "N-Score (K-Beauty 시장 침투도)",
            "t_score": "T-Score (TikTok 버즈)",
        },
    )

    # 사분면 기준선
    fig.add_hline(y=45, line_dash="dot", line_color="gray", opacity=0.4)
    fig.add_vline(x=20, line_dash="dot", line_color="gray", opacity=0.4)
    fig.add_vline(x=0, line_dash="solid", line_color="#ccc", opacity=0.5)

    # 사분면 레이블 (개선: N-Score의 실제 의미 반영)
    # Y축 해석:
    #   높음(100-N_low) = "한국서도 아직 초기" → 글로벌 K-Beauty 브랜드도 미진입 가능성
    #   낮음(100-N_high) = "한국서 이미 인기" → K-Beauty 브랜드가 이미 글로벌 런치 중일 수 있음
    fig.add_annotation(xref="paper", yref="paper", x=0.99, y=0.99,
                       text="🎯 퍼스트무버 찬스 — 미국 뜨는데 K-Beauty도 아직 초기",
                       showarrow=False, xanchor="right", yanchor="top",
                       font=dict(color="#1b5e20", size=11, family="Arial Black"),
                       bgcolor="rgba(232,245,233,0.95)")
    fig.add_annotation(xref="paper", yref="paper", x=0.99, y=0.02,
                       text="⚡ K-Beauty 이미 글로벌 진출 중 — 차별화 없으면 후발주자",
                       showarrow=False, xanchor="right", yanchor="bottom",
                       font=dict(color="#b71c1c", size=10),
                       bgcolor="rgba(255,235,238,0.9)")
    fig.add_annotation(xref="paper", yref="paper", x=0.01, y=0.99,
                       text="👀 글로벌 조기 신호 — 미국 수요 형성 전 (선점 모니터링)",
                       showarrow=False, xanchor="left", yanchor="top",
                       font=dict(color="#e65100", size=10),
                       bgcolor="rgba(255,243,224,0.9)")
    fig.add_annotation(xref="paper", yref="paper", x=0.01, y=0.02,
                       text="📉 기회 없음 — 미국 수요도 없고 K-Beauty도 포화",
                       showarrow=False, xanchor="left", yanchor="bottom",
                       font=dict(color="#9e9e9e", size=10),
                       bgcolor="rgba(255,255,255,0.8)")

    # ── 겹침 방지 레이블: 반발력(repulsion) 기반 오프셋 계산 ──────────
    # 차트 범위: x(-105~105)=210units, y(0~105)=105units
    # 차트 픽셀: width≈900px, height≈560px → 약 4.3px/unit(x), 5.3px/unit(y)
    _X_SCALE = 4.3
    _Y_SCALE = 5.3
    _REPULSE_R = 55   # px 이내 이웃에 반발
    _LABEL_DIST = 28  # 최소 레이블 거리(px)

    pts = [(float(r["v_us"]), float(r["kbeauty_gap"])) for _, r in df_chart.iterrows()]

    def _label_offset(i):
        xi, yi = pts[i]
        rdx, rdy = 0.0, 0.0
        for j, (xj, yj) in enumerate(pts):
            if i == j:
                continue
            dx_px = (xi - xj) * _X_SCALE
            dy_px = (yi - yj) * _Y_SCALE
            dist  = max(1.0, (dx_px ** 2 + dy_px ** 2) ** 0.5)
            if dist < _REPULSE_R:
                force = (_REPULSE_R - dist) / _REPULSE_R
                rdx += (dx_px / dist) * force
                rdy += (dy_px / dist) * force
        length = (rdx ** 2 + rdy ** 2) ** 0.5
        if length > 0.5:
            ax = (rdx / length) * _LABEL_DIST
            ay = (rdy / length) * _LABEL_DIST
        else:
            ax, ay = 0.0, _LABEL_DIST   # 기본: 위쪽
        # 차트 경계 근처 포인트는 안쪽으로 보정
        if xi > 85:   ax = min(ax, -8)
        if xi < -80:  ax = max(ax, 8)
        if yi > 75:   ay = min(ay, -8)
        if yi < 15:   ay = max(ay, 8)
        return round(ax, 1), round(-ay, 1)  # Plotly ay: 음수=위쪽

    for i, (_, r) in enumerate(df_chart.iterrows()):
        ax_off, ay_off = _label_offset(i)
        fig.add_annotation(
            x=r["v_us"], y=r["kbeauty_gap"],
            text=r["name_kr"],
            showarrow=True,
            arrowhead=0,
            arrowwidth=0.8,
            arrowcolor="rgba(160,160,160,0.55)",
            ax=ax_off,
            ay=ay_off,
            font=dict(size=8, color="#222"),
            bgcolor="rgba(255,255,255,0.82)",
            borderpad=2,
        )

    fig.update_layout(
        height=580,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f8f9fa",
        font_color="#111",
        legend_title="Status",
        xaxis=dict(range=[-105, 105], gridcolor="#e0e0e0", zerolinecolor="#aaa",
                   title=f"← 미국 수요 감소   {x_label}   미국 수요 성장 →"),
        yaxis=dict(range=[0, 105], gridcolor="#e0e0e0",
                   title="K-Beauty 글로벌 선점 가능성 ↑   (높음=한국서도 아직 초기→글로벌 미진입 가능 / 낮음=한국 이미 인기→K-Beauty 글로벌 런치 중)"),
        legend=dict(bgcolor="#ffffff", bordercolor="#ddd", borderwidth=1),
    )
    st.plotly_chart(fig, use_container_width=True)
    return chart_data, has_us_data


def _launch_top_picks(chart_data: list, has_us_data: bool, ingredients: list[dict], latest):
    """기회 맵 하단: K-Beauty 글로벌 런치 Top 10 + 시사점"""
    if not chart_data:
        return

    df_opp = pd.DataFrame(chart_data)

    # ── K-Beauty 글로벌 기회점수 계산 ────────────────────────────────
    # 전략: 미국 소비자가 원하는 성분을 K-Beauty 브랜드가 아직 안 씀 → 퍼스트무버
    # v_us(-100~100) → 0~100 정규화
    df_opp["v_norm"] = (df_opp["v_us"].clip(-100, 100) + 100) / 2
    # T-Score 있으면 보너스 반영 (없으면 중간값 50 가정)
    t_fill = df_opp["t_score"].fillna(50)
    # 기회점수 = 미국수요 50% + K-Beauty미개척도 35% + TikTok버즈 15%
    df_opp["opp_score"] = (
        df_opp["v_norm"] * 0.50
        + df_opp["kbeauty_gap"] * 0.35
        + t_fill * 0.15
    ).round(1)

    # 미국에서 성장 중인 것들만 (v_us > 0)
    positive_df = df_opp[df_opp["v_us"] > 0].sort_values("opp_score", ascending=False)
    top_df = positive_df.head(10)

    if top_df.empty:
        return

    st.divider()

    # ── 태그 범례 ──────────────────────────────────────────────────
    st.markdown("""
<div style="background:#f8f9fa;border-radius:10px;padding:14px 18px;margin-bottom:16px;
            border:1px solid #e8e8e8;font-size:0.78rem;line-height:2;">
<div style="font-weight:700;color:#333;margin-bottom:8px;">🏷️ 카드 태그 읽는 법</div>
<div style="display:flex;flex-wrap:wrap;gap:6px 0;">
  <div style="width:50%;min-width:280px;">
    <b>미국 수요 신호 (X축)</b><br>
    <span style="background:#fff3e0;color:#e65100;border-radius:4px;padding:1px 7px;font-weight:600;">🔥 US 검색 폭발</span> V-Index +60 이상 — 미국 메인스트림 진입 중<br>
    <span style="background:#e8f5e9;color:#2e7d32;border-radius:4px;padding:1px 7px;font-weight:600;">📈 US 급성장</span> V-Index +30~60 — 얼리어답터 단계<br>
    <span style="background:#e3f2fd;color:#1565c0;border-radius:4px;padding:1px 7px;font-weight:600;">➕ US 성장 중</span> V-Index 0~30 — 관심 시작
  </div>
  <div style="width:50%;min-width:280px;">
    <b>K-Beauty 미개척도 (Y축)</b><br>
    <span style="background:#f3e5f5;color:#6a1b9a;border-radius:4px;padding:1px 7px;font-weight:600;">🌱 K-Beauty 퍼스트무버</span> 미개척 70+ — K-Beauty 아무도 안 씀<br>
    <span style="background:#e8eaf6;color:#283593;border-radius:4px;padding:1px 7px;font-weight:600;">✨ 진입 여지 충분</span> 미개척 50~70 — 아직 경쟁 적음<br>
    <span style="background:#fce4ec;color:#880e4f;border-radius:4px;padding:1px 7px;font-weight:600;">⚡ 경쟁 시작</span> 미개척 30~50 — 빠르게 움직여야<br>
    <span style="background:#ffebee;color:#b71c1c;border-radius:4px;padding:1px 7px;font-weight:600;">⏰ K-Beauty 포화</span> 미개척 30 미만 — 차별화 없인 힘듦
  </div>
  <div style="width:100%;margin-top:4px;">
    <b>TikTok 신호</b><br>
    <span style="background:#fce4ec;color:#880e4f;border-radius:4px;padding:1px 7px;font-weight:600;">🎵 TikTok 선행 신호</span> T-Score 65+ & V-Index 낮음 — <b>구글 검색보다 앞선 가장 빠른 신호</b>. 지금 소싱 시작하면 미국 수요 피크 전에 출시 가능<br>
    <span style="background:#fff3e0;color:#bf360c;border-radius:4px;padding:1px 7px;font-weight:600;">🔥 소셜+검색 동시 폭발</span> T-Score 65+ & V-Index 30+ — TikTok 바이럴이 구글 검색까지 전이됨. <b>이미 메인스트림, 지금이 막차</b>
  </div>
</div>
</div>
""", unsafe_allow_html=True)

    st.subheader("🚀 K-Beauty 글로벌 런치 검토 Top 10")
    v_label = "US V-Index" if has_us_data else "Global V-Index"
    st.caption(
        f"**전략**: 미국 소비자가 원하는 성분을 K-Beauty 브랜드로 선점 → US·EU·아시아 글로벌 출시 | "
        f"**기회점수** = 미국수요 50% + K-Beauty 미개척도 35% + TikTok 버즈 15%"
    )

    ing_map = {i["id"]: i for i in ingredients}

    # ── Top 10 카드 그리드 ──────────────────────────────────────────
    rows_of_2 = [top_df.iloc[i:i+2] for i in range(0, len(top_df), 2)]
    for chunk in rows_of_2:
        cols = st.columns(2)
        for col, (_, row) in zip(cols, chunk.iterrows()):
            rank = list(top_df.index).index(row.name) + 1
            opp = row["opp_score"]
            v = row["v_us"]
            kbeauty_gap = row["kbeauty_gap"]
            n_score = row["n_score"]
            t_score = row.get("t_score")
            status = row.get("status", "watching")
            category = row.get("category", "")
            ing_data = ing_map.get(row["ingredient_id"], {})

            # ── 근거 태그 자동 생성 ──
            tags = []
            # 미국 수요 태그
            if v >= 60:
                tags.append(("🔥", f"US 검색 폭발 (+{v:.0f})", "#fff3e0", "#e65100"))
            elif v >= 30:
                tags.append(("📈", f"US 급성장 (+{v:.0f})", "#e8f5e9", "#2e7d32"))
            else:
                tags.append(("➕", f"US 성장 중 (+{v:.0f})", "#e3f2fd", "#1565c0"))

            # K-Beauty 미개척도 태그
            if kbeauty_gap >= 70:
                tags.append(("🌱", f"K-Beauty 퍼스트무버 가능 (미개척 {kbeauty_gap:.0f})", "#f3e5f5", "#6a1b9a"))
            elif kbeauty_gap >= 50:
                tags.append(("✨", f"K-Beauty 진입 여지 충분 (미개척 {kbeauty_gap:.0f})", "#e8eaf6", "#283593"))
            elif kbeauty_gap >= 30:
                tags.append(("⚡", f"K-Beauty 경쟁 시작 (미개척 {kbeauty_gap:.0f})", "#fce4ec", "#880e4f"))
            else:
                tags.append(("⏰", f"K-Beauty 이미 포화 — 차별화 필수 (미개척 {kbeauty_gap:.0f})", "#ffebee", "#b71c1c"))

            # TikTok 태그: 구글 검색보다 앞선 선행 신호 vs 이미 검색까지 폭발
            if t_score is not None and t_score >= 65:
                if v >= 30:
                    tags.append(("🔥", f"소셜+검색 동시 폭발 (T:{t_score:.0f})", "#fff3e0", "#bf360c"))
                else:
                    tags.append(("🎵", f"TikTok 선행 신호 — 검색보다 앞섬 (T:{t_score:.0f})", "#fce4ec", "#880e4f"))

            status_colors = {"rising": "#00C48C", "falling": "#FF6B6B", "watching": "#FFB800"}
            sc = status_colors.get(status, "#aaa")
            tags_html = " ".join(
                f'<span style="background:{bg};color:{tc};border-radius:4px;padding:2px 8px;'
                f'font-size:0.7rem;font-weight:600;margin-right:3px;margin-bottom:3px;display:inline-block;">'
                f'{emoji} {label}</span>'
                for emoji, label, bg, tc in tags
            )

            notes = ing_data.get("notes", "")
            notes_html = (
                f'<div style="font-size:0.75rem;color:#555;margin-top:6px;line-height:1.4;">'
                f'{notes[:110]}{"…" if len(notes) > 110 else ""}</div>'
            ) if notes else ""

            if opp >= 75:
                opp_bg, opp_tc = "#1b5e20", "#fff"
            elif opp >= 62:
                opp_bg, opp_tc = "#388e3c", "#fff"
            elif opp >= 50:
                opp_bg, opp_tc = "#f9a825", "#111"
            else:
                opp_bg, opp_tc = "#e0e0e0", "#333"

            with col:
                st.markdown(f"""
<div style="border:1px solid #e0e0e0;border-radius:10px;padding:14px 16px;margin-bottom:10px;
            background:#fff;border-left:4px solid {sc};">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
    <div>
      <span style="font-size:0.75rem;color:#999;font-weight:600;">#{rank}</span>
      <span style="font-size:1.05rem;font-weight:700;color:#111;margin-left:6px;">{row['name_kr']}</span>
      <span style="font-size:0.7rem;color:#888;margin-left:6px;">{row.get('name_en','')}</span>
      <span style="font-size:0.68rem;color:#aaa;margin-left:6px;">{category}</span>
    </div>
    <div style="background:{opp_bg};color:{opp_tc};border-radius:6px;padding:3px 10px;
                font-size:0.8rem;font-weight:700;white-space:nowrap;">
      기회 {opp:.0f}
    </div>
  </div>
  <div style="margin-bottom:6px;line-height:1.8;">{tags_html}</div>
  {notes_html}
</div>
""", unsafe_allow_html=True)

    # ── 전략적 시사점 ────────────────────────────────────────────────
    st.divider()
    st.subheader("💡 글로벌 K-Beauty 전략 시사점")

    top3 = top_df.head(3)["name_kr"].tolist()
    prime_zone = df_opp[(df_opp["v_us"] > 20) & (df_opp["kbeauty_gap"] > 50)]
    competition_zone = df_opp[(df_opp["v_us"] > 0) & (df_opp["kbeauty_gap"] < 30)]
    tiktok_hot = df_opp[df_opp["t_score"].notna() & (df_opp["t_score"] >= 65)]
    avg_gap_top5 = top_df.head(5)["kbeauty_gap"].mean()
    cat_counts = top_df["category"].value_counts()
    top_cat = cat_counts.index[0] if len(cat_counts) > 0 else ""
    top_cat_n = int(cat_counts.iloc[0]) if len(cat_counts) > 0 else 0

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**📌 지금 움직여야 하는 이유**")
        insights_now = []
        if len(prime_zone) >= 2:
            insights_now.append(
                f"미국 소비자가 원하는데 K-Beauty가 아직 안 잡은 성분 **{len(prime_zone)}개** — "
                f"글로벌 뷰티 시장에서 K-Beauty 퍼스트무버 포지셔닝 가능한 윈도우"
            )
        if avg_gap_top5 > 50:
            insights_now.append(
                f"Top 5 K-Beauty 미개척도 평균 **{avg_gap_top5:.0f}점** — "
                f"아직 Sephora·Ulta·아마존에서 K-Beauty 제품으로 포화 안 됨"
            )
        if len(tiktok_hot) >= 2:
            insights_now.append(
                f"TikTok 화제 성분 **{len(tiktok_hot)}개** 포착 — "
                f"TikTok 바이럴이 Sephora·아마존 수요로 전환되는 리드타임 통상 3~9개월"
            )
        if top3:
            insights_now.append(
                f"**{', '.join(top3)}** 기회점수 최상위 — "
                f"K-Beauty 스토리텔링 + 성분 차별화로 글로벌 론칭 시 카테고리 선점 가능"
            )
        for txt in insights_now:
            st.markdown(f"- {txt}")

    with col_b:
        st.markdown("**⚠️ 리스크 & 주의사항**")
        insights_risk = []
        if len(competition_zone) > 0:
            names = ", ".join(competition_zone["name_kr"].tolist()[:3])
            insights_risk.append(
                f"**{names}** 등 {len(competition_zone)}개는 미국 수요는 있지만 K-Beauty도 이미 포화 — "
                f"포뮬러·패키징·채널 차별화 없이는 단가 경쟁 빠짐"
            )
        watching_cnt = int((df_opp["status"] == "watching").sum())
        if watching_cnt >= 2:
            insights_risk.append(
                f"상위권 중 **{watching_cnt}개**가 'watching' 상태 — "
                f"신호는 있지만 임상 데이터·소비자 교육 아직 부족, 마케팅 비용 높을 수 있음"
            )
        if top_cat and top_cat_n >= 2:
            insights_risk.append(
                f"기회 성분의 **{top_cat_n}개**가 {top_cat} 카테고리 집중 — "
                f"같은 카테고리 여러 SKU 동시 출시 시 소비자 혼란 및 자기잠식 주의"
            )
        insights_risk.append(
            f"모든 점수는 검색·소셜 트렌드 기반 — 실제 글로벌 수요는 Sephora 리뷰·Amazon BSR 크로스체크 권장. "
            f"⚠️ 계절성 뱃지 성분은 일시적 급등일 수 있음"
        )
        for txt in insights_risk:
            st.markdown(f"- {txt}")

    # ── 글로벌 런치 리드타임 가이드 ──────────────────────────────────
    st.markdown("---")
    st.markdown(f"""**📅 신호 단계별 K-Beauty 글로벌 런치 리드타임** (`{date.today().isoformat()}` 기준)

| 신호 | 의미 | 지금 시작하면 런치 시점 | 액션 |
|---|---|---|---|
| 🎵 TikTok 폭발 (T≥70) | US 소셜 바이럴 초기 | **12~18개월 후** | 소싱·R&D 킥오프 |
| 🔥 US V-Index ≥60 | 미국 메인스트림 진입 | **9~12개월 후** | 포뮬러 확정·OEM 계약 |
| 📈 US V-Index 30~60 | 미국 얼리어답터 단계 | **6~9개월 후** | 이미 소싱 중이어야 함 |
| ➕ US V-Index 0~30 | 미국 관심 시작 | **3~6개월 후** | 출시 준비 완료 상태여야 |
| 📊 N-Score 상승 시작 | K-Beauty 브랜드 진입 시작 | **지금이 막차** | 채널·가격 차별화로 속도전 |
""")


# ── View 2: 시계열 분석 ────────────────────────────────────────────
def view_timeseries(ingredients: list[dict], df: pd.DataFrame):
    st.title("📈 성분별 시계열 분석")

    if df.empty:
        st.info("Google Sheets에 데이터가 없습니다. 수집기를 먼저 실행하세요.")
        return

    # ── 📖 시계열 분석 사용 가이드 ────────────────────────────
    st.markdown("""
    <div style="background:#fafafa;border:1px solid #ececef;border-radius:10px;
         padding:14px 18px;margin-bottom:14px">
      <div style="font-size:0.78rem;color:#6b7280;font-weight:700;
           letter-spacing:0.05em;margin-bottom:10px">📖 시계열 분석 — 결정 직전 deep-dive 가이드</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;font-size:0.82rem">
        <div style="border-left:3px solid #ec4899;padding:6px 10px">
          <b style="color:#be185d">🔥 75 이상 (폭발)</b><br>
          <span style="color:#666">검색 가속도 폭발 — 즉시 R&D 검토 또는 마케팅 강화</span>
        </div>
        <div style="border-left:3px solid #f59e0b;padding:6px 10px">
          <b style="color:#b45309">📈 50~75 (성장)</b><br>
          <span style="color:#666">건강한 상승 — 시장 진입 시점 잡기</span>
        </div>
        <div style="border-left:3px solid #6b7280;padding:6px 10px">
          <b style="color:#374151">📊 25~50 (보통)</b><br>
          <span style="color:#666">평이 — 차별화 없으면 진입 어려움</span>
        </div>
        <div style="border-left:3px solid #ef4444;padding:6px 10px">
          <b style="color:#b91c1c">📉 25 미만 (약세)</b><br>
          <span style="color:#666">관심 식는 중 — 라인 정리 또는 회피</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # 필터
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        selected_ids = st.multiselect(
            "성분 선택",
            options=[i["id"] for i in ingredients],
            format_func=lambda x: next((i["name_kr"] for i in ingredients if i["id"] == x), x),
            default=[i["id"] for i in ingredients[:4]],
        )
    with col2:
        metric = st.selectbox("지표", ["v_index", "n_score"], format_func=lambda x: {
            "v_index": "V-Index (검색 가속도)", "n_score": "N-Score (네이버 트렌드)"
        }[x])
    with col3:
        # 실제 데이터 범위 자동 감지 → 동적 옵션
        if not df.empty:
            data_days = (df["date"].max() - df["date"].min()).days
            available = []
            if data_days >= 7:   available.append("최근 7일")
            if data_days >= 14:  available.append("최근 14일")
            if data_days >= 30:  available.append("1M")
            if data_days >= 90:  available.append("3M")
            if data_days >= 180: available.append("6M")
            if data_days >= 365: available.append("12M")
            available.append("전체")
            default_idx = len(available) - 1  # 데이터 적으면 "전체" 기본
            period = st.selectbox("기간", available, index=default_idx,
                                  help=f"수집 데이터: 총 {data_days}일")
        else:
            period = "전체"

    period_map = {"최근 7일":7, "최근 14일":14, "1M":30, "3M":90, "6M":180, "12M":365, "전체":99999}
    days = period_map.get(period, 99999)
    cutoff = pd.Timestamp(date.today()) - timedelta(days=days)

    # 데이터 부족 알림
    if not df.empty:
        actual_days = (df["date"].max() - df["date"].min()).days
        days_since_latest = (pd.Timestamp(date.today()) - df["date"].max()).days
        if actual_days < 14:
            st.info(f"⏳ 데이터 누적 {actual_days}일 — 신뢰성 높은 패턴 분석은 4주 이상 누적 후 가능합니다.")
        if days_since_latest > 7:
            st.warning(f"🟡 마지막 수집: {df['date'].max().date()} ({days_since_latest}일 전) — cron 점검 필요")

    filtered = df[
        (df["ingredient_id"].isin(selected_ids)) &
        (df["metric_name"] == metric) &
        (df["date"] >= cutoff)
    ]

    if filtered.empty:
        st.info("선택한 조건에 해당하는 데이터가 없습니다.")
        return

    PALETTE = ["#4fc3f7","#ff7043","#66bb6a","#ab47bc",
               "#ffd54f","#26c6da","#ef5350","#ec407a","#42a5f5","#8d6e63"]
    metric_label = {"v_index":"V-Index (검색 가속도)","n_score":"N-Score (네이버)",
                    "t_score":"T-Score (TikTok)","et_index":"ET-Index (YouTube)"}.get(metric, metric)

    # ── 데이터 전처리: 이상값 제거 ───────────────────────────────────
    # 1) 0 또는 결측 제거
    # 2) 성분별로 첫날 값이 이후 평균의 3배 이상이면 이상값으로 제거 (첫 수집 스파이크)
    clean = {}
    for ing_id in selected_ids:
        d = filtered[filtered["ingredient_id"] == ing_id].sort_values("date").copy()
        d = d[d["value"] > 0].copy()
        if d.empty:
            continue
        if len(d) >= 3:
            rest_mean = d.iloc[1:]["value"].mean()
            if rest_mean > 0 and d.iloc[0]["value"] > rest_mean * 2.5:
                d = d.iloc[1:]   # 첫날 스파이크 제거
        clean[ing_id] = d

    if not clean:
        st.info("유효한 데이터가 없습니다.")
        return

    # ── 데이터 기간 안내 ────────────────────────────────────────────
    all_dates = pd.concat([d["date"] for d in clean.values()])
    data_start = all_dates.min().strftime("%Y-%m-%d")
    data_end   = all_dates.max().strftime("%Y-%m-%d")
    data_days  = (all_dates.max() - all_dates.min()).days + 1
    st.caption(
        f"📅 데이터 기간: {data_start} ~ {data_end} ({data_days}일) · "
        f"50 기준선 = 보통 수준 · 수집 누락일은 차트에서 끊어짐"
    )

    # ── 차트 ────────────────────────────────────────────────────────
    fig = go.Figure()

    # 기준선 50 (배경)
    fig.add_hline(y=50, line_dash="dot", line_color="rgba(150,150,150,0.4)",
                  annotation_text="기준(50)", annotation_position="left",
                  annotation_font_color="rgba(150,150,150,0.7)")

    for idx, ing_id in enumerate(selected_ids):
        d = clean.get(ing_id)
        if d is None or d.empty:
            continue
        ing_info = next((i for i in ingredients if i["id"] == ing_id), {})
        color = PALETTE[idx % len(PALETTE)]
        name_kr = ing_info.get("name_kr", ing_id)
        last_val = d.iloc[-1]["value"]

        # 면적 채우기 (투명도 낮게)
        fig.add_trace(go.Scatter(
            x=d["date"], y=d["value"],
            name=name_kr,
            mode="lines+markers",
            line=dict(color=color, width=2.5),
            marker=dict(size=7, color=color,
                        line=dict(width=2, color="white")),
            fill="tozeroy",
            fillcolor=f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.08)",
            opacity=1.0,
            connectgaps=False,
            hovertemplate=(
                f"<b>{name_kr}</b><br>%{{x|%m/%d(%a)}}<br>"
                f"{metric_label.split('(')[0].strip()}: <b>%{{y:.1f}}</b>"
                f"{'  🔥' if last_val >= 70 else '  📈' if last_val >= 50 else ''}"
                "<extra></extra>"
            ),
        ))

        # 마지막 값 라벨
        fig.add_annotation(
            x=d.iloc[-1]["date"], y=last_val,
            text=f"<b>{last_val:.0f}</b>",
            showarrow=False,
            xanchor="left", xshift=8,
            font=dict(color=color, size=12),
        )

    fig.update_layout(
        height=460,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#fafafa",
        font=dict(color="#333", size=12),
        xaxis=dict(
            gridcolor="#eeeeee", zerolinecolor="#ddd",
            tickformat="%m/%d", tickangle=-30,
            title=None,
        ),
        yaxis=dict(
            gridcolor="#eeeeee", zerolinecolor="#ddd",
            range=[0, 105], title=metric_label,
            tickvals=[0, 25, 50, 75, 100],
        ),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="left", x=0,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#ddd", borderwidth=1,
        ),
        hovermode="x unified",
        margin=dict(l=10, r=60, t=40, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── 해석 가이드 ──────────────────────────────────────────────────
    with st.expander("📖 수치 읽는 법", expanded=False):
        st.markdown(f"""
| 범위 | 의미 |
|---|---|
| **75 이상** 🔥 | 폭발적 성장 — 즉시 주목 |
| **50–75** 📈 | 성장 중 — 트렌드 형성 |
| **25–50** | 보통 수준 |
| **25 미만** | 약세 또는 데이터 부족 |

- **{metric_label}**: 절댓값이 아닌 *상대 가속도* (Google 기준 0–100 정규화)
- 첫 수집일 이상값(스파이크)은 자동 제거됩니다
- 차트가 끊기는 구간 = 해당일 수집 실패 (데이터 없음)
""")

    # ── 성분별 현황 카드 ─────────────────────────────────────────────
    st.subheader("성분별 현황")
    cols = st.columns(min(len(clean), 4))
    for idx, (ing_id, d) in enumerate(clean.items()):
        ing_info = next((i for i in ingredients if i["id"] == ing_id), {})
        color = PALETTE[idx % len(PALETTE)]
        last_val  = d.iloc[-1]["value"]
        first_val = d.iloc[0]["value"]
        change_pct = ((last_val - first_val) / first_val * 100) if first_val > 0 else 0
        arrow = "▲" if change_pct > 0 else ("▼" if change_pct < 0 else "─")
        signal = "🔥 급등" if last_val >= 75 else ("📈 상승" if last_val >= 50 else ("📉 약세" if last_val < 25 else "➡ 보통"))
        with cols[idx % 4]:
            st.markdown(f"""
<div style="border-left:4px solid {color};padding:10px 14px;background:#f9f9f9;border-radius:0 8px 8px 0;margin-bottom:8px">
  <div style="font-weight:700;font-size:0.95rem;color:#222">{ing_info.get('name_kr', ing_id)}</div>
  <div style="font-size:1.6rem;font-weight:800;color:{color};line-height:1.2">{last_val:.0f}</div>
  <div style="font-size:0.8rem;color:#666">{arrow} {abs(change_pct):.0f}%&nbsp;&nbsp;{signal}</div>
  <div style="font-size:0.75rem;color:#999">기준: {d.iloc[-1]['date'].strftime('%m/%d')}</div>
</div>""", unsafe_allow_html=True)

    # ── 🎯 자동 한 줄 요약 (선택 변경 시 즉시 갱신) ────────────────
    summary_data = []
    for ing_id, d in clean.items():
        ing_info = next((i for i in ingredients if i["id"] == ing_id), {})
        last_val = d.iloc[-1]["value"]
        first_val = d.iloc[0]["value"]
        change_pct = ((last_val - first_val) / first_val * 100) if first_val > 0 else 0
        summary_data.append({
            "name_kr": ing_info.get("name_kr", ing_id),
            "last_val": last_val,
            "change_pct": change_pct,
        })
    summary_data.sort(key=lambda x: -x["last_val"])

    explosive = [s for s in summary_data if s["last_val"] >= 75]
    growing = [s for s in summary_data if 50 <= s["last_val"] < 75]
    weak = [s for s in summary_data if s["last_val"] < 25]
    biggest_gain = max(summary_data, key=lambda x: x["change_pct"]) if summary_data else None
    biggest_drop = min(summary_data, key=lambda x: x["change_pct"]) if summary_data else None

    explosive_str = ", ".join([f"<b style='color:#be185d'>{s['name_kr']}</b>({s['last_val']:.0f})" for s in explosive[:3]])
    growing_str = ", ".join([f"{s['name_kr']}({s['last_val']:.0f})" for s in growing[:3]])
    weak_str = ", ".join([f"{s['name_kr']}({s['last_val']:.0f})" for s in weak[:3]])

    summary_lines_html = []
    if explosive:
        summary_lines_html.append(f"🔥 <b>폭발(75+)</b>: {explosive_str} → 즉시 R&D 또는 마케팅 강화")
    if growing:
        summary_lines_html.append(f"📈 <b>성장(50~75)</b>: {growing_str} → 진입 시점 잡기")
    if weak:
        summary_lines_html.append(f"📉 <b>약세(&lt;25)</b>: {weak_str} → 라인 정리 검토")
    if biggest_gain and biggest_gain["change_pct"] > 5:
        summary_lines_html.append(
            f"🚀 <b>가장 많이 오른 성분</b>: <b style='color:#047857'>{biggest_gain['name_kr']}</b> (+{biggest_gain['change_pct']:.0f}%)"
        )
    if biggest_drop and biggest_drop["change_pct"] < -5:
        summary_lines_html.append(
            f"⚠️ <b>가장 많이 떨어진 성분</b>: <b style='color:#b91c1c'>{biggest_drop['name_kr']}</b> ({biggest_drop['change_pct']:.0f}%)"
        )

    if summary_lines_html:
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#fdf2f8 0%,#f3e8ff 100%);
             border-left:4px solid #ec4899;padding:14px 18px;border-radius:0 10px 10px 0;
             margin-top:14px;margin-bottom:14px">
          <div style="font-size:0.85rem;color:#374151;line-height:1.8">
            <b style="color:#be185d">🎯 선택 성분 한 줄 요약 (자동)</b><br/>
            {' <br/> '.join(['• ' + line for line in summary_lines_html])}
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── AI 시사점 (클릭 시 생성) ────────────────────────────────────
    st.divider()
    st.subheader("🤖 AI 트렌드 시사점 (Gemini)")

    # 데이터 요약 (Gemini에 넘길 compact 텍스트)
    summary_lines = [f"지표: {metric_label}, 기간: {data_start}~{data_end}"]
    for ing_id, d in clean.items():
        ing_info = next((i for i in ingredients if i["id"] == ing_id), {})
        last_val  = d.iloc[-1]["value"]
        first_val = d.iloc[0]["value"]
        chg = ((last_val - first_val) / first_val * 100) if first_val > 0 else 0
        status = ing_info.get("status", "watching")
        summary_lines.append(
            f"- {ing_info.get('name_kr', ing_id)}({ing_info.get('name_en','')}): "
            f"현재 {last_val:.0f}/100, 변화 {chg:+.0f}%, 상태={status}"
        )
    data_summary = "\n".join(summary_lines)

    if st.button("✨ AI 시사점 생성 (Gemini)", type="primary", key="ai_insight_btn"):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            st.error("GEMINI_API_KEY가 .env에 없습니다.")
        else:
            with st.spinner("Gemini 분석 중..."):
                try:
                    from google import genai
                    from google.genai import types as genai_types
                    client = genai.Client(api_key=api_key)
                    prompt = f"""당신은 뷰티 화장품 트렌드 전략 애널리스트입니다.
아래는 최근 성분별 검색 트렌드 지표입니다. 이 데이터를 보고 화장품 브랜드 CEO와 제품기획자에게 유용한 시사점을 한국어로 작성하세요.

{data_summary}

지표 설명:
- V-Index 0~100: 구글 검색 가속도. 75+ = 폭발적 성장, 50~75 = 성장 중, 25 미만 = 약세
- 상태(rising/watching/falling): 중장기 추세 판단

요청사항:
1. 지금 당장 주목해야 할 성분과 이유 (1~2개)
2. 예상치 못한 이상 신호가 있다면 (있으면만)
3. 다음 2주 내 제품기획 액션 포인트 1개

형식: 불릿 3~4개, 각 1~2문장, 명확하고 실행 가능하게. 총 200자 이내."""

                    response = client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=prompt,
                        config=genai_types.GenerateContentConfig(
                            temperature=0.4,
                            max_output_tokens=400,
                        ),
                    )
                    insight_text = response.text
                    st.session_state["ts_insight"] = insight_text
                    st.session_state["ts_insight_date"] = data_end
                except Exception as e:
                    err = str(e)
                    if "429" in err or "RESOURCE_EXHAUSTED" in err:
                        st.warning("⏳ Gemini 무료 한도 초과 — 내일 다시 시도하세요 (매일 1,500회 무료)")
                    else:
                        st.error(f"오류: {e}")

    # 저장된 시사점 표시
    if "ts_insight" in st.session_state:
        st.markdown(
            f"""<div style="background:#f0f7ff;border-left:4px solid #4fc3f7;
            padding:16px 20px;border-radius:0 8px 8px 0;margin-top:8px">
            <div style="font-size:0.75rem;color:#888;margin-bottom:8px">
            🤖 Gemini 분석 · 기준: {st.session_state.get('ts_insight_date','')}</div>
            <div style="color:#222;line-height:1.7;white-space:pre-wrap">{st.session_state['ts_insight']}</div>
            </div>""",
            unsafe_allow_html=True,
        )


# ── View 3: 수동 입력 ──────────────────────────────────────────────
def view_manual_input(ingredients: list[dict], df_manual: pd.DataFrame):
    st.title("📋 판매 검증 데이터 입력")
    st.caption("자동 수집 지표(검색·소셜)가 실제 구매로 이어지는지 검증하기 위한 실판매 데이터. 주 1회 15~20분 체크.")

    # 입력 가이드
    with st.expander("📖 무엇을 입력하나요? (초보자 가이드)", expanded=False):
        st.markdown("""
**각 필드 입력 방법:**

| 필드 | 어디서 확인 | 입력 예시 |
|---|---|---|
| **Amazon BSR 순위** | amazon.com → "[성분명] serum" 검색 → 1위 제품 클릭 → 우측 상세정보의 "Best Sellers Rank" | `1,234` (낮을수록 잘 팔림) |
| **Amazon 리뷰 수** | 동일 제품의 리뷰 개수 | `8,521` |
| **Sephora 신제품 수** | sephora.com → New Arrivals 필터 → [성분명]으로 검색 → 지난 30일 | `3` |
| **Sephora 베스트셀러** | sephora.com → Bestsellers → 해당 성분 포함 제품 있으면 Yes | Yes/No |
| **Amazon 1위 제품 가격** | 위에서 찾은 1위 제품 가격 | `28.99` |
| **TikTok 조회수** | TikTok 앱 → 해시태그 검색 → 상단 조회수 (억 단위) | `2.3` (억) |

**왜 이 데이터가 중요한가요?**
- 대시보드의 V-Index/N-Score는 *검색 관심도* — 실제로 사는지는 별개
- Amazon BSR이 빠르게 올라가면 = 검색 관심 → 실구매 전환 확인
- Sephora 신제품 출시 수 증가 = 경쟁사들이 이미 진입 시작했다는 신호
- 이 두 개를 같이 보면: **"아직 Sephora에 신제품 없는데 Amazon BSR은 오름"** = 골든 타이밍
""")

    with st.form("manual_form"):
        selected_id = st.selectbox(
            "성분 선택",
            options=[i["id"] for i in ingredients],
            format_func=lambda x: next((f"{i['name_kr']} — {i['name_en']}" for i in ingredients if i["id"] == x), x),
        )

        st.markdown("**🛒 Amazon 데이터** (amazon.com → `[성분명] serum` 검색 → 1위 제품)")
        col1, col2, col3 = st.columns(3)
        with col1:
            amazon_bsr = st.number_input("BSR 순위 (낮을수록 잘 팔림)", min_value=0, step=100,
                                          help="Amazon Best Sellers Rank. 1,000 이하면 매우 잘 팔리는 것")
        with col2:
            amazon_reviews = st.number_input("리뷰 수", min_value=0, step=100,
                                              help="리뷰 수 증가 속도가 수요 신호")
        with col3:
            price_usd = st.number_input("1위 제품 가격 ($)", min_value=0.0, step=0.5,
                                         help="가격대로 시장 포지셔닝 파악 — 프리미엄인지 매스인지")

        st.markdown("**💄 Sephora 데이터** (sephora.com)")
        col4, col5 = st.columns(2)
        with col4:
            sephora_new = st.number_input("신제품 수 (최근 30일)", min_value=0, step=1,
                                           help="New Arrivals에서 이 성분 포함 제품 수")
        with col5:
            sephora_bs = st.selectbox("베스트셀러 등재", ["미확인", "있음", "없음"],
                                       help="Sephora Bestsellers 목록에 이 성분 포함 제품 있으면 '있음'")

        st.markdown("**📱 TikTok / 기타**")
        col6, col7 = st.columns(2)
        with col6:
            tiktok_views = st.number_input("TikTok 조회수 (억)", min_value=0.0, step=0.1,
                                            help="TikTok 앱에서 해시태그 검색 → 상단 조회수")
        with col7:
            c_ratio = st.selectbox("C-Ratio (원가율)", ["데이터 없음", "높음(>60%)", "중간(30~60%)", "낮음(<30%)"])

        manual_note = st.text_area("메모 — 특이사항, 경쟁사 동향, 채널 관찰 등", height=70,
                                    placeholder="예: Drunk Elephant 신제품에 포함됨. The Ordinary에서 단독 세럼 출시.")
        submitted = st.form_submit_button("💾 저장", type="primary")

    if submitted:
        try:
            from config.sheets_client import append_rows, TAB_MANUAL_INPUT
            ing_info = next(i for i in ingredients if i["id"] == selected_id)
            row = [
                date.today().isoformat(),
                selected_id,
                ing_info["name_kr"],
                amazon_bsr or "",
                amazon_reviews or "",
                sephora_new or "",
                sephora_bs,
                price_usd or "",
                tiktok_views or "",
                c_ratio,
                manual_note,
            ]
            append_rows(TAB_MANUAL_INPUT, [row])
            st.success(f"✅ {ing_info['name_kr']} 저장 완료 — {date.today().isoformat()}")
            st.cache_data.clear()
        except Exception as e:
            st.error(f"저장 실패: {e}")

    st.divider()
    st.subheader("📊 누적 판매 검증 데이터")
    if df_manual.empty:
        st.info("아직 입력된 데이터가 없습니다. 위 폼으로 첫 번째 데이터를 입력해보세요.")
    else:
        st.dataframe(df_manual.sort_values("date", ascending=False), use_container_width=True, hide_index=True)


# ── View 4: 지표 방법론 ────────────────────────────────────────────
SCORING_YAML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "scoring_config.yaml")

@st.cache_data(ttl=60)
def load_scoring_config() -> dict:
    with open(SCORING_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _score_bar(score_ranges: list[dict]) -> str:
    """점수 범위 시각화 HTML 바"""
    segments = []
    for r in score_ranges:
        width = r["max"] - r["min"]
        segments.append(
            f'<div style="flex:{width}; background:{r["color"]}; height:20px; '
            f'display:flex; align-items:center; justify-content:center; '
            f'font-size:0.6rem; color:white; font-weight:700;">'
            f'{r["min"]}~{r["max"]}</div>'
        )
    return f'<div style="display:flex; border-radius:6px; overflow:hidden; margin:8px 0 16px;">{"".join(segments)}</div>'


def _range_table(score_ranges: list[dict]) -> None:
    rows = []
    for r in score_ranges:
        dot = f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{r["color"]};margin-right:6px;"></span>'
        rows.append({
            "점수": f'{r["min"]} ~ {r["max"]}',
            "등급": f'{dot}{r["label"]}',
            "의미": r["meaning"],
            "액션": r["action"],
        })
    df = pd.DataFrame(rows)
    st.markdown(
        df.to_html(escape=False, index=False, classes="score-table"),
        unsafe_allow_html=True,
    )
    st.markdown("""
<style>
.score-table { width:100%; border-collapse:collapse; font-size:0.82rem; }
.score-table th { background:#f0f0f0; padding:8px 10px; text-align:left; border-bottom:2px solid #ddd; }
.score-table td { padding:7px 10px; border-bottom:1px solid #eee; vertical-align:top; }
</style>
""", unsafe_allow_html=True)


def view_methodology():
    cfg = load_scoring_config()

    st.title("⚙️ 지표 방법론")
    st.caption("scoring_config.yaml을 직접 수정하면 이 페이지에 즉시 반영됩니다.")

    st.info(
        "💡 **점수 기준(score_ranges)과 가중치(weights)는 "
        "`config/scoring_config.yaml`에서 수정 가능합니다.** "
        "수정 후 브라우저에서 R키를 누르면 즉시 반영됩니다.",
        icon=None,
    )

    # ── V-Index ──────────────────────────────────────────────────
    st.divider()
    v = cfg["v_index"]
    st.subheader(f"① {v['name']}")
    st.markdown(f"**{v['description']}**")

    col1, col2, col3 = st.columns(3)
    col1.metric("데이터 소스", v["data_source"])
    col2.metric("업데이트 주기", v["update_frequency"])
    col3.metric("룩백 윈도우", v["lookback_window"])

    st.markdown("**계산 로직**")
    steps = v["calculation"]
    for key in sorted(steps):
        st.markdown(f"- `{key}` {steps[key]}")

    weights = v["weights"]
    st.markdown(
        f"**현재 가중치:** 가속도 `{int(weights['velocity']*100)}%` + "
        f"절대 관심도 `{int(weights['log_absolute']*100)}%`"
        f" &nbsp;←&nbsp; *scoring_config.yaml에서 수정 가능*"
    )

    st.markdown("**점수 구간 해석**")
    st.markdown(_score_bar(v["score_ranges"]), unsafe_allow_html=True)
    _range_table(v["score_ranges"])

    st.markdown("**알려진 한계**")
    for lim in v["known_limitations"]:
        st.markdown(f"- ⚠️ {lim}")

    # ── N-Score ──────────────────────────────────────────────────
    st.divider()
    r = cfg["n_score"]
    st.subheader(f"② {r['name']}")
    st.markdown(f"**{r['description']}**")

    col1, col2, col3 = st.columns(3)
    col1.metric("데이터 소스", r["data_source"])
    col2.metric("업데이트 주기", r["update_frequency"])
    col3.metric("룩백 윈도우", r["lookback_window"])
    st.caption(f"분석 엔진: {r['analyzer']}")

    st.markdown("**계산 로직**")
    steps = r["calculation"]
    for key in sorted(steps):
        st.markdown(f"- `{key}` {steps[key]}")

    st.markdown("**점수 구간 해석**")
    st.markdown(_score_bar(r["score_ranges"]), unsafe_allow_html=True)
    _range_table(r["score_ranges"])

    st.markdown("**알려진 한계**")
    for lim in r["known_limitations"]:
        st.markdown(f"- ⚠️ {lim}")

    # ── ET-Index ─────────────────────────────────────────────────
    st.divider()
    et = cfg["et_index"]
    st.subheader(f"③ {et['name']}")
    st.markdown(f"**{et['description']}**")

    col1, col2, col3 = st.columns(3)
    col1.metric("데이터 소스", et["data_source"])
    col2.metric("업데이트 주기", et["update_frequency"])
    col3.metric("룩백 윈도우", et["lookback_window"])
    st.caption(f"분석 엔진: {et['analyzer']}")

    st.markdown("**계산 로직**")
    steps = et["calculation"]
    for key in sorted(steps):
        st.markdown(f"- `{key}` {steps[key]}")

    st.markdown("**권장 강도 분류**")
    rsm = et["recommendation_strength_map"]
    strength_html = "<div style='display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;'>"
    strength_colors = {
        "strong_recommend": "#00c853", "moderate_recommend": "#66bb6a",
        "neutral": "#ff9800", "caution": "#ef5350", "against": "#b71c1c",
        "not_mentioned": "#aaa",
    }
    for k, v_txt in rsm.items():
        color = strength_colors.get(k, "#aaa")
        strength_html += f"<span style='background:{color}22; border:1px solid {color}; border-radius:12px; padding:3px 10px; font-size:0.75rem; color:{color}; font-weight:600;'>{k}</span>"
    strength_html += "</div>"
    st.markdown(strength_html, unsafe_allow_html=True)
    for k, v_txt in rsm.items():
        st.markdown(f"- **`{k}`** {v_txt}")

    st.markdown("**점수 구간 해석**")
    st.markdown(_score_bar(et["score_ranges"]), unsafe_allow_html=True)
    _range_table(et["score_ranges"])

    st.markdown("**알려진 한계**")
    for lim in et["known_limitations"]:
        st.markdown(f"- ⚠️ {lim}")

    # ── FinalScore ───────────────────────────────────────────────
    st.divider()
    fs = cfg["final_score"]
    st.subheader(f"④ {fs['name']}")
    st.markdown(f"**{fs['description']}**")

    fw = fs["weights"]
    st.markdown(
        f"**가중치:** V-Index `{int(fw['v_index']*100)}%` + "
        f"N-Score `{int(fw['n_score']*100)}%` + "
        f"ET-Index `{int(fw['et_index']*100)}%`"
    )
    st.caption(f"수식: `{fs['formula']}`")
    st.caption(f"ET 없을 시: {fs['et_fallback']}")

    thr = fs["thresholds"]
    col1, col2, col3 = st.columns(3)
    col1.metric("출시 착수 권장", f"≥ {thr['launch_ready']}점", delta="Launch Ready")
    col2.metric("모니터링 구간", f"{thr['watch']}~{thr['launch_ready']}점", delta="Watch")
    col3.metric("우선순위 낮춤", f"< {thr['deprioritize']}점", delta="Deprioritize")

    # ── 2×2 매트릭스 ─────────────────────────────────────────────
    st.divider()
    ci = cfg["combined_interpretation"]
    st.subheader(f"⑤ {ci['description']}")

    quad_cols = st.columns(2)
    for i, q in enumerate(ci["quadrants"]):
        with quad_cols[i % 2]:
            v_lo, v_hi = map(int, q["v_range"].split("~"))
            r_lo, r_hi = map(int, q["r_range"].split("~"))
            v_color = "#00c853" if v_lo >= 70 else "#ff9800"
            r_color = "#00c853" if r_lo >= 70 else "#ff9800"
            st.markdown(f"""
<div style="border:1px solid #ddd; border-radius:8px; padding:14px; margin-bottom:12px; background:#fafafa;">
  <div style="font-size:1rem; font-weight:700; margin-bottom:6px;">{q['label']}</div>
  <div style="font-size:0.78rem; color:#555; margin-bottom:8px;">
    V-Index <b style="color:{v_color}">{q['v_range']}</b> &nbsp;×&nbsp;
    R-Score <b style="color:{r_color}">{q['r_range']}</b>
  </div>
  <div style="font-size:0.78rem; color:#333;">→ {q['action']}</div>
</div>
""", unsafe_allow_html=True)

    # ── 파일 경로 안내 ────────────────────────────────────────────
    st.divider()
    st.caption(f"📁 설정 파일: `{SCORING_YAML}`")
    st.caption("점수 범위·가중치·설명 수정 → 파일 저장 → 브라우저 R키")


# ── View 5: 채널 관리 ───────────────────────────────────────────────
CHANNELS_YAML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "youtube_channels.yaml")

@st.cache_data(ttl=60)
def load_channels_config() -> dict:
    with open(CHANNELS_YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def view_admin_guide():
    st.title("🛠️ 관리자 가이드 — 지표 해석 & 점수 기준")
    st.caption("이 대시보드의 전략적 목적, 각 점수 계산 방식, 차트 해석 방법을 설명합니다.")

    # ── 전략 개요 ────────────────────────────────────────────────────
    st.subheader("🎯 전략 개요")
    st.markdown("""
**핵심 질문**: *미국·글로벌 소비자가 원하는 성분인데 아직 K-Beauty 브랜드가 선점하지 않은 것은 무엇인가?*

**비즈니스 로직**:
1. 미국 소비자 수요 신호를 최대한 빠르게 포착 (Google Trends US, TikTok)
2. 그 성분을 K-Beauty 브랜드로 포뮬러·패키징해서 글로벌 선점
3. 타겟 시장: **US → EU → 동남아·일본** (K-Beauty 브랜드 신뢰도가 높은 순서)

**2nd Mover 전략**: 완전히 새로운 성분이 아니라, *미국에서 막 뜨기 시작한* 성분을 K-Beauty로 먼저 포장·출시
- 성분 자체는 이미 검증됨 → R&D 리스크 낮음
- 미국 소비자 수요 이미 형성됨 → 마케팅 비용 절감
- K-Beauty 미개척 → 카테고리 선점 가능
""")

    st.divider()

    # ── 지표별 계산 방법 ─────────────────────────────────────────────
    st.subheader("📐 지표별 계산 방법")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["V-Index (Google)", "N-Score (Naver)", "T-Score (TikTok)", "ET-Index (YouTube)", "기회점수", "★ FinalScore", "📊 신호 한계 & 해석"])

    with tab1:
        st.markdown("""
### V-Index — Google Trends 검색 가속도
**범위**: -100 ~ +100 (0 = 변화 없음, 양수 = 성장, 음수 = 하락)

**데이터 소스**: Google Trends (pytrends) — 5년 주간 검색 관심도 (0~100 상대값)

**수집 지역**:
- `v_index` = Global (전 세계)
- `v_index_us` = US only → 차트에서 X축으로 사용

**계산 공식**:
```
recent_avg  = 최근 12주 평균
prev_avg    = 그 이전 12주 평균

velocity    = (recent_avg / prev_avg - 1.0) × 100  → clip(-100, +100)
log_abs     = log(recent_avg+1) / log(101) × 100   → 절대 규모 (0~100)

V-Index = velocity × 0.6 + log_abs × 0.4
```

**계절성 보정**:
- 단기(3개월) 급등인데 YoY(전년 동기 대비)로는 안 올랐으면 → ×0.65 페널티
- 봄 자외선차단제, 겨울 보습 성분 등 계절적 착시 방지

**해석**:
| V-Index | 의미 |
|---|---|
| +60 이상 | 폭발적 성장 — 메인스트림 진입 중 |
| +30 ~ +60 | 빠른 성장 — 얼리어답터 단계 |
| 0 ~ +30 | 완만한 성장 — 관심 시작 |
| -30 ~ 0 | 정체 혹은 소폭 하락 |
| -30 이하 | 명확한 하락 추세 |
""")

    with tab2:
        st.markdown("""
### N-Score — Naver DataLab 검색 트렌드 (K-Beauty 시장 침투도)
**범위**: 0 ~ 100 (높을수록 K-Beauty 시장에서 이미 인식됨)

**데이터 소스**: Naver DataLab 검색트렌드 API (무료, 공식) — 최근 1년 월별 검색량 지수

**전략적 의미**:
- N-Score **높음** → K-Beauty 브랜드들이 이미 이 성분을 쓰고 있음 → **경쟁 심화**
- N-Score **낮음** → K-Beauty 브랜드가 아직 이 성분을 안 씀 → **퍼스트무버 기회**
- Y축 = `100 - N-Score` = **K-Beauty 미개척도** (높을수록 기회)

**계산 공식**:
```
monthly_values = 최근 12개월 월별 검색 지수 (0~100)

velocity    = (최근 3개월 평균 / 이전 3개월 평균 - 1) × 100
log_abs     = log(avg+1) / log(101) × 100

N-Score = velocity × 0.6 + log_abs × 0.4
```

**주의**: Naver는 한국 시장 신호. K-Beauty 브랜드가 글로벌로 이 성분을 쓰기 시작하면
N-Score가 올라가기 시작 → 기회 윈도우 닫히는 신호로 해석

**해석**:
| N-Score | K-Beauty 미개척도 | 의미 |
|---|---|---|
| 0~20 | 80~100 | K-Beauty 완전 블루오션 — 퍼스트무버 가능 |
| 20~40 | 60~80 | K-Beauty 진입 초기 — 아직 기회 있음 |
| 40~60 | 40~60 | K-Beauty 진입 중 — 속도가 관건 |
| 60~80 | 20~40 | K-Beauty 경쟁 심화 — 차별화 전략 필요 |
| 80~100 | 0~20 | K-Beauty 포화 — 신규 진입 어려움 |
""")

    with tab3:
        st.markdown("""
### T-Score — TikTok 해시태그 버즈 모멘텀
**범위**: 0 ~ 100 (높을수록 TikTok에서 빠르게 성장 중)

**데이터 소스**: TikTok 공개 해시태그 API (`tiktok.com/api/challenge/detail/`) — 누적 조회수

**전략적 의미**:
- TikTok은 미국 뷰티 트렌드의 **가장 빠른 선행 지표**
- TikTok 화제 → 3~9개월 내 Sephora/Ulta 수요 → 미국 구글 검색 상승 → K-Beauty 브랜드 진입
- T-Score가 높으면서 V-Index가 아직 낮으면 = **가장 빠른 기회 신호**

**계산 공식**:
```
# 매주 스냅샷 저장
weekly_delta = 이번 주 조회수 - 저번 주 조회수
growth_rate  = weekly_delta / prev_views

# 성장 점수 (주간 +6% = 98점, +1% = 58점, 0% = 50점)
growth_score = clip(50 + growth_rate × 800, 0, 100)

# 절대 규모 (1억 조회 ≈ 75점)
size_score = log(조회수+1) / log(5×10^10+1) × 100

T-Score = growth_score × 0.7 + size_score × 0.3
```

**첫 실행**: 베이스라인만 저장, T-Score 의미 없음 → 다음 주 실행부터 계산

**해석**:
| T-Score | 의미 |
|---|---|
| 70 이상 | TikTok 폭발 성장 — 바이럴 진행 중 |
| 55~70 | TikTok 성장 중 — 모멘텀 있음 |
| 45~55 | 정체 또는 완만한 성장 |
| 45 미만 | 관심 낮거나 감소 중 |
""")

    with tab4:
        st.markdown("""
### ET-Index — YouTube 전문의 영상 버즈
**범위**: 0 ~ 100

**데이터 소스**: 한국 피부과 전문의 + 미국 Dermatologist YouTube 채널 영상 제목/설명 분석

**두 가지 버전**:
- `et_score_kr` = 한국 피부과 채널 (성분 임상 검증 신호)
- `et_score_us` = 미국 Derm 채널 (영어권 전문가 신뢰도 신호)

**전략적 의미**:
- ET-KR이 높으면 → 한국 의사들이 검증한 성분 → K-Beauty 브랜드 신뢰도 마케팅 가능
- ET-US가 높으면 → 미국 전문가 신뢰 → 미국 소비자 설득 용이

**⚠️ 현재 상태**: 한국 YouTube 채널은 한국어 제목 사용으로 키워드 매칭 개선 중
""")

    with tab5:
        st.markdown("""
### 기회점수 (Opportunity Score) — K-Beauty 글로벌 런치 우선순위
**범위**: 0 ~ 100 (높을수록 지금 당장 출시 검토 필요)

**공식**:
```
v_norm      = (US V-Index + 100) / 2          # -100~+100 → 0~100 정규화
t_fill      = T-Score (없으면 50으로 가정)

기회점수    = v_norm × 0.50
            + K-Beauty미개척도(100-N-Score) × 0.35
            + T-Score × 0.15
```

**가중치 근거**:
| 지표 | 가중치 | 이유 |
|---|---|---|
| US V-Index | 50% | 타겟 시장(미국) 실수요 신호 — 가장 중요 |
| K-Beauty 미개척도 | 35% | K-Beauty 브랜드 선점 여지 — 핵심 전략 변수 |
| TikTok T-Score | 15% | 선행 바이럴 신호 — 없는 경우 많아 보수적 반영 |

**해석**:
| 기회점수 | 액션 |
|---|---|
| 75+ | 🟢 즉시 R&D 킥오프 권장 |
| 62~75 | 🟡 소싱·포뮬러 리서치 시작 |
| 50~62 | 🟠 모니터링 강화, 분기 내 결정 |
| 50 미만 | ⚪ 관망 (미국 수요 더 확인 필요) |
""")

    st.divider()

    # ── 차트 해석 가이드 ─────────────────────────────────────────────
    st.subheader("📊 기회 맵 차트 완전 해석 가이드")
    st.markdown("""
**축 의미**:
- **X축 (→ 오른쪽)**: US V-Index — 미국 소비자 검색 가속도. 오른쪽일수록 미국에서 빠르게 뜨는 중
- **Y축 (↑ 위쪽)**: K-Beauty 미개척도 = 100 - N-Score. 위쪽일수록 K-Beauty 브랜드가 아직 이 성분을 안 씀

**4사분면 해석**:

| 위치 | 의미 | 전략 |
|---|---|---|
| 🎯 **우상단** (X+, Y+) | 미국 수요 있음 + K-Beauty 아직 미개척 | **지금 당장 글로벌 K-Beauty 출시** |
| ⚡ **우하단** (X+, Y-) | 미국 수요 있음 + K-Beauty 이미 포화 | 차별화(포뮬러·가격·채널)로만 진입 가능 |
| 👀 **좌상단** (X-, Y+) | 미국 수요 아직 초기 + K-Beauty 미개척 | TikTok·소셜 모니터링 강화, 6개월 후 재평가 |
| 📉 **좌하단** (X-, Y-) | 미국 수요 감소 + K-Beauty도 포화 | 신규 진입 불필요 |

**색상 (Status)**:
- 🟢 **Rising**: 데이터 신호 + 수동 판단으로 상승 추세 확인됨
- 🟡 **Watching**: 신호 있음, 아직 확신 부족 — 추가 데이터 필요
- 🔴 **Falling**: 하락 추세 또는 기회 소멸

⚠️ **주의**: 색상은 `ingredients.yaml`의 `status` 필드를 수동으로 설정한 것.
차트 위치(X/Y)는 실제 데이터 신호. 색상과 위치가 불일치하면 **데이터를 우선 신뢰**하고 status 업데이트 검토.
""")

    with tab6:
        st.markdown("""
### ★ FinalScore — 카드 우상단 종합 점수

**범위**: 0 ~ 100

**공식**:
```
# ET-Index 있을 때
FinalScore = V_norm × 0.3 + N-Score × 0.3 + ET-KR × 0.4

# ET-Index 없을 때 (YouTube 수집 전)
FinalScore = V_norm × 0.5 + N-Score × 0.5

단, V_norm = (V-Index + 100) / 2  → -100~+100을 0~100으로 변환
```

**각 지표의 역할**:
| 지표 | 가중치 | 의미 |
|---|---|---|
| V-Index (Global) | 30% | 전 세계 검색 가속도 — 성분이 얼마나 빠르게 뜨는지 |
| N-Score | 30% | K-Beauty 시장 침투도 — 이미 K-Beauty 브랜드가 쓰고 있는지 |
| ET-Index KR | 40% | 한국 전문의 언급 — 성분의 과학적 신뢰도 |

**해석**:
| ★ 점수 | 색상 | 의미 | 액션 |
|---|---|---|---|
| 70 이상 | 🟢 진한 초록 | 전 지표 고르게 강함 — 즉시 출시 검토 | R&D 킥오프 |
| 50~70 | 🟢 초록 | 유망 — 한두 지표 더 상승 기다릴 수 있음 | 소싱 시작 |
| 30~50 | 🟡 노랑 | 관망 — 신호 있지만 아직 약함 | 모니터링 |
| 30 미만 | 🔴 빨강 | 하락 혹은 신호 없음 | 보류 |

**⚠️ FinalScore vs 기회점수 차이**:
- **★ FinalScore**: 성분 자체의 종합 트렌드 강도 (글로벌 포함)
- **기회점수**: K-Beauty 글로벌 런치 타이밍 점수 (미국 수요 + K-Beauty 미개척도 위주)

FinalScore가 높아도 K-Beauty 이미 포화면 기회점수는 낮을 수 있음 — **차트의 위치가 더 중요**
""")

    with tab7:
        st.markdown("""
### 📊 신호 한계 & 올바른 해석 가이드

#### ① V-Index (검색 관심도) vs 실제 판매의 차이

| 상황 | V-Index | 실제 Amazon 판매 | 해석 |
|---|---|---|---|
| 성분이 막 뜨기 시작 | 급등 | 아직 낮음 | **V-Index가 선행 — 3~6개월 내 판매 급증 예상** |
| 성분이 성숙 단계 | 낮음/0 | 높고 안정적 | 검색 plateau지만 충성 구매층 형성 (레티놀, 세라마이드 유형) |
| TikTok 바이럴 성분 | 낮음 | 갑자기 급증 | **T-Score가 V-Index보다 앞서는 신호** — 검색 전에 구매부터 |

> 💡 **엑소좀 패러독스**: US V-Index 음수지만 Amazon 3위. 이유: 의료 시술 검색과 홈케어 제품 검색이 섞여 V-Index가 희석됨. 실제 제품 구매는 Amazon 내부 추천·브랜드 충성도로 이루어짐.

---

#### ② N-Score Y축 — "K-Beauty 글로벌 선점 가능성"의 올바른 해석

```
Y축 = 100 - N-Score (Naver 한국 검색 인기도)
```

| Y축 위치 | N-Score | 실제 의미 | 전략 해석 |
|---|---|---|---|
| **높음** (Y > 60) | 낮음 | 한국서도 아직 모름 | → 글로벌 K-Beauty 브랜드도 미진입 가능성 높음 ✅ |
| **중간** (Y 40~60) | 중간 | 한국 얼리어답터가 알기 시작 | → K-Beauty 브랜드 글로벌 런치 준비 중일 수 있음 ⚠️ |
| **낮음** (Y < 40) | 높음 | 한국서 이미 대중화 | → K-Beauty 브랜드 이미 Amazon 등 글로벌 진출 중 (PDRN/Medicube 사례) ❗ |

> ⚠️ **우하단(높은 US 수요 + 낮은 Y) 성분이 "기회 없음"이 아닐 수 있음**: PDRN처럼 한국 브랜드가 이미 글로벌 성공을 거두고 있는 경우. 이 경우 전략은 "K-Beauty 기반 차별화 포뮬라"로 진입 가능.

---

#### ③ GS-Index (Google Shopping) 추가 해석

카드의 **🛍 GS** 값: Google Shopping(froogle) 기반 구매 의도 지표

| GS vs V 비교 | 해석 |
|---|---|
| V 높음 + GS 높음 | 검색도 늘고 사려는 사람도 늘어남 → **가장 강한 런치 신호** |
| V 높음 + GS 낮음 | 관심은 있는데 아직 살 마음은 없음 → 인지 단계, 조금 더 대기 |
| V 낮음 + GS 높음 | 검색은 줄어도 구매는 유지 → 성숙 성분, 충성 수요 |

---

#### ④ Amazon 리뷰 수 해석

카드의 **🛒 리뷰** 수: 상위 노출 제품의 리뷰 합계 (현재 Amazon 봇 방어로 배지 수는 제한적)

- **리뷰 1,000+**: 이미 검증된 시장 — 경쟁 심화 가능성
- **리뷰 100~500**: 성장 초기 — K-Beauty 퀄리티로 점유율 빼앗기 좋은 타이밍
- **리뷰 없음/낮음**: 아직 아마존 시장 미형성 — 퍼스트무버 가능
""")

    st.divider()

    # ── 데이터 수집 주기 ─────────────────────────────────────────────
    st.subheader("⏱️ 데이터 수집 주기 & 실행 명령어")
    st.markdown("""
| 수집기 | 주기 | 소요시간 | 명령어 |
|---|---|---|---|
| Google Trends (Global + US) | 주 1회 | ~10분 | `python collect/run_collector.py --trends` |
| Naver DataLab (N-Score) | 주 1회 | ~3분 | `python collect/run_collector.py --naver` |
| TikTok T-Score | 주 1회 | ~5분 | `python collect/run_collector.py --tiktok` |
| ET-Index (YouTube) | 월 2회 | ~20분 | `python collect/run_collector.py --et` |
| **Google Shopping (GS-Index)** | 주 1회 | ~15분 | `python collect/run_collector.py --shopping` |
| **Amazon 검색 (리뷰·배지)** | 주 1회 | ~10분 | `python collect/run_collector.py --amazon` |
| 전체 실행 | 주 1회 권장 | ~60분 | `python collect/run_collector.py` |

**권장 수집 일정**: 매주 월요일 오전 (주말 소셜 버즈 반영됨)

**첫 실행 시**:
```bash
# 1. Sheets 탭 초기화
python collect/run_collector.py --init

# 2. 전체 수집 (첫 T-Score는 베이스라인만, 다음 주부터 의미 있음)
python collect/run_collector.py
```
""")
    st.code("""# .env 필요 키
GOOGLE_SHEET_ID=...         # Google Sheets 시트 ID
GOOGLE_CREDENTIALS=...      # 서비스 계정 JSON (Base64 인코딩)
NAVER_CLIENT_ID=...         # Naver Developers 앱 Client ID
NAVER_CLIENT_SECRET=...     # Naver Developers 앱 Secret
DASHBOARD_PASSWORD=...      # 대시보드 접근 비밀번호 (선택)
""", language="bash")

    st.divider()

    # ── ingredients.yaml 관리 ────────────────────────────────────────
    st.subheader("📝 성분 추가/수정 방법 (`config/ingredients.yaml`)")
    st.markdown("""
새 성분 추가 시 아래 필드 구조를 따라 `ingredients.yaml`에 추가:
""")
    st.code("""- id: ingredient_id           # 영문 소문자, 언더스코어 (고유값)
  name_kr: 성분명              # 한국어 이름
  name_en: Ingredient Name     # 영어 이름
  category: 보습/항노화/미백/진정/각질제거/항균/기타
  status: watching             # rising / watching / falling (수동 설정)
  notes: "성분 특징 및 시장 맥락 설명"
  google_keywords:             # Google Trends 검색어 (최대 5개)
    - "keyword 1"
    - "keyword 2"
  naver_keywords:              # Naver DataLab 검색어 (없으면 name_kr 자동 사용)
    - "성분명 세럼"
    - "성분명 화장품"
  tiktok_hashtags:             # TikTok 해시태그 (없으면 name_en 자동 사용)
    - hashtag1
    - hashtag2skincare
""", language="yaml")


# ── View: 주간 트래킹 ──────────────────────────────────────────────
def view_weekly_tracking(ingredients: list[dict], df: pd.DataFrame, df_manual: pd.DataFrame):
    st.title("📅 주간 기회 트래킹")
    st.caption("매주 수집된 데이터로 성분별 기회점수 변화 추이를 추적합니다. 신호가 실제 판매로 이어지는지 교차 검증합니다.")

    if df.empty:
        st.info("데이터 수집 후 이용 가능합니다.")
        return

    # ── 📖 주간 트래킹 사용 가이드 (정적, 즉시 보임) ──────────
    st.markdown("""
    <div style="background:#fafafa;border:1px solid #ececef;border-radius:10px;
         padding:14px 18px;margin-bottom:14px">
      <div style="font-size:0.78rem;color:#6b7280;font-weight:700;
           letter-spacing:0.05em;margin-bottom:10px">📖 주간 트래킹 — 매주 5분 리뷰 가이드</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;font-size:0.82rem">
        <div style="border-left:3px solid #10b981;padding:6px 10px">
          <b style="color:#047857">▲ 가장 많이 오른 성분</b><br>
          <span style="color:#666">신호 강해진 후보 — 시계열 분석 → R&D 검토</span>
        </div>
        <div style="border-left:3px solid #ef4444;padding:6px 10px">
          <b style="color:#b91c1c">▼ 가장 많이 떨어진 성분</b><br>
          <span style="color:#666">관심 식는 성분 — 마케팅 축소 또는 라인 정리</span>
        </div>
        <div style="border-left:3px solid #06b6d4;padding:6px 10px">
          <b style="color:#0e7490">기회점수 62 이상 (점선)</b><br>
          <span style="color:#666">출시 검토 기준선 — 통과 시 실판매 검증 필수</span>
        </div>
        <div style="border-left:3px solid #ec4899;padding:6px 10px">
          <b style="color:#be185d">신호 ↔ 판매 교차 검증</b><br>
          <span style="color:#666">신호만 강해도 안 됨 — Amazon BSR 낮으면 진짜</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    ing_map = {i["id"]: i for i in ingredients}

    # ── 주차별 기회점수 계산 ────────────────────────────────────────
    df2 = df.copy()
    df2["week"] = pd.to_datetime(df2["date"]).dt.to_period("W").dt.start_time

    # 메트릭 피벗: (week, ingredient_id) × metric_name
    numeric = df2[pd.to_numeric(df2["value"], errors="coerce").notna()].copy()
    numeric["value"] = pd.to_numeric(numeric["value"])

    # collected_at 기준 최신값 선택
    sort_cols = ["ingredient_id", "metric_name", "week"]
    if "collected_at" in numeric.columns:
        numeric["collected_at"] = pd.to_datetime(numeric["collected_at"], errors="coerce")
        sort_cols.append("collected_at")
    numeric_sorted = numeric.sort_values(sort_cols, na_position="first")
    weekly_latest = (
        numeric_sorted
        .groupby(["week", "ingredient_id", "metric_name"])["value"]
        .last()
        .reset_index()
    )

    pivoted = weekly_latest.pivot_table(
        index=["week", "ingredient_id"], columns="metric_name", values="value"
    ).reset_index()

    # 기회점수 계산
    def opp(row):
        v = row.get("v_index_us") or row.get("v_index")
        n = row.get("n_score")
        t = row.get("t_score")
        if v is None or pd.isna(v):
            return None
        v_norm = (float(v) + 100) / 2
        n_val = float(n) if (n is not None and not pd.isna(n)) else 50
        t_val = float(t) if (t is not None and not pd.isna(t)) else 50
        return round(v_norm * 0.50 + (100 - n_val) * 0.35 + t_val * 0.15, 1)

    pivoted["opp_score"] = pivoted.apply(opp, axis=1)
    pivoted["name_kr"] = pivoted["ingredient_id"].map(lambda x: ing_map.get(x, {}).get("name_kr", x))
    pivoted["status"] = pivoted["ingredient_id"].map(lambda x: ing_map.get(x, {}).get("status", "watching"))
    pivoted = pivoted.dropna(subset=["opp_score"])

    weeks = sorted(pivoted["week"].unique())
    if len(weeks) < 2:
        st.info("최소 2주 이상의 데이터가 필요합니다. 다음 주 수집 후 이용 가능합니다.")
        st.caption(f"현재 수집된 주차: {len(weeks)}주")
        return

    # ── 섹션 1: 이번 주 vs 지난 주 등락 ──────────────────────────
    st.subheader("🏆 이번 주 기회점수 등락 (vs 지난 주)")

    last_week = pivoted[pivoted["week"] == weeks[-1]][["ingredient_id", "name_kr", "status", "opp_score"]].rename(columns={"opp_score": "이번주"})
    prev_week = pivoted[pivoted["week"] == weeks[-2]][["ingredient_id", "opp_score"]].rename(columns={"opp_score": "지난주"})
    delta_df = last_week.merge(prev_week, on="ingredient_id", how="left")
    delta_df["변화"] = (delta_df["이번주"] - delta_df["지난주"]).round(1)
    delta_df = delta_df.sort_values("변화", ascending=False)

    col_up, col_down = st.columns(2)
    with col_up:
        st.markdown("**📈 가장 많이 오른 성분 Top 5**")
        up5 = delta_df[delta_df["변화"] > 0].head(5)
        for _, row in up5.iterrows():
            st.markdown(f"""
<div style="background:#f0faf5;border-left:4px solid #00C48C;border-radius:6px;
            padding:8px 12px;margin-bottom:6px;display:flex;justify-content:space-between;">
  <span style="font-weight:700;color:#111;">{row['name_kr']}</span>
  <span style="color:#00C48C;font-weight:800;">▲ +{row['변화']:.1f} &nbsp; ({row['이번주']:.0f}점)</span>
</div>""", unsafe_allow_html=True)

    with col_down:
        st.markdown("**📉 가장 많이 떨어진 성분 Top 5**")
        dn5 = delta_df[delta_df["변화"] < 0].tail(5).sort_values("변화")
        for _, row in dn5.iterrows():
            st.markdown(f"""
<div style="background:#fff5f5;border-left:4px solid #FF6B6B;border-radius:6px;
            padding:8px 12px;margin-bottom:6px;display:flex;justify-content:space-between;">
  <span style="font-weight:700;color:#111;">{row['name_kr']}</span>
  <span style="color:#FF6B6B;font-weight:800;">▼ {row['변화']:.1f} &nbsp; ({row['이번주']:.0f}점)</span>
</div>""", unsafe_allow_html=True)

    # ── 섹션 2: 주차별 기회점수 라인 차트 ──────────────────────────
    st.divider()
    st.subheader("📈 성분별 기회점수 주간 추이")

    # 표시할 성분 선택 (기본: 이번 주 상위 10개)
    top10_ids = delta_df.head(10)["ingredient_id"].tolist()
    all_ids = sorted(pivoted["ingredient_id"].unique().tolist())
    selected_ids = st.multiselect(
        "성분 선택 (기본: 이번 주 기회점수 상위 10개)",
        options=all_ids,
        default=top10_ids,
        format_func=lambda x: ing_map.get(x, {}).get("name_kr", x),
    )

    if selected_ids:
        chart_df = pivoted[pivoted["ingredient_id"].isin(selected_ids)].copy()
        chart_df["week_str"] = chart_df["week"].dt.strftime("%m/%d")
        fig = px.line(
            chart_df, x="week_str", y="opp_score", color="name_kr",
            markers=True,
            labels={"week_str": "주차", "opp_score": "기회점수", "name_kr": "성분"},
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig.update_layout(
            height=420, paper_bgcolor="#fff", plot_bgcolor="#f8f9fa",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis=dict(range=[0, 100], gridcolor="#e0e0e0"),
            xaxis=dict(gridcolor="#e0e0e0"),
        )
        fig.add_hline(y=62, line_dash="dot", line_color="#388e3c", opacity=0.5,
                      annotation_text="출시 검토 기준선 (62)", annotation_position="right")
        st.plotly_chart(fig, use_container_width=True)

    # ── 섹션 3: 전체 주차별 스냅샷 테이블 ─────────────────────────
    st.divider()
    st.subheader("📋 전체 성분 기회점수 히스토리")

    pivot_wide = pivoted.pivot_table(
        index="name_kr", columns="week", values="opp_score"
    ).round(1)
    pivot_wide.columns = [f"{w.strftime('%m/%d')}" for w in pivot_wide.columns]
    pivot_wide = pivot_wide.sort_values(by=pivot_wide.columns[-1], ascending=False, na_position="last")
    st.dataframe(pivot_wide, use_container_width=True)

    # ── 🎯 한 줄 요약 (자동) ──────────────────────────────────────
    n_up = (delta_df["변화"] > 0).sum()
    n_down = (delta_df["변화"] < 0).sum()
    n_pass_threshold = (delta_df["이번주"] >= 62).sum()
    top_up_name = up5.iloc[0]["name_kr"] if not up5.empty else "—"
    top_up_delta = up5.iloc[0]["변화"] if not up5.empty else 0
    top_down_name = dn5.iloc[0]["name_kr"] if not dn5.empty else "—"
    top_down_delta = dn5.iloc[0]["변화"] if not dn5.empty else 0
    top_score_name = delta_df.sort_values("이번주", ascending=False).iloc[0]["name_kr"]
    top_score_val = delta_df.sort_values("이번주", ascending=False).iloc[0]["이번주"]

    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#fdf2f8 0%,#f3e8ff 100%);
         border-left:4px solid #ec4899;padding:14px 18px;border-radius:0 10px 10px 0;margin-top:14px">
      <div style="font-size:0.85rem;color:#374151;line-height:1.7">
        <b style="color:#be185d">🎯 이번 주 한 줄 요약 (팀 미팅/슬랙 복붙용)</b><br/>
        • 상승 <b>{n_up}개</b> · 하락 <b>{n_down}개</b> · 출시 검토 기준선(62점) 통과 <b>{n_pass_threshold}개</b><br/>
        • 🥇 이번 주 1위: <b style="color:#be185d">{top_score_name}</b> ({top_score_val:.0f}점)<br/>
        • 📈 가장 많이 오른: <b style="color:#047857">{top_up_name}</b> (+{top_up_delta:.1f})
        &nbsp;|&nbsp; 📉 가장 많이 떨어진: <b style="color:#b91c1c">{top_down_name}</b> ({top_down_delta:.1f})<br/>
        • 다음 액션: 상승 Top 3 → 시계열 분석 page에서 deep-dive → R&D/마케팅 결정
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 섹션 4: 신호 vs 판매 교차 검증 ────────────────────────────
    if not df_manual.empty:
        st.divider()
        st.subheader("🔗 신호 ↔ 판매 교차 검증")
        st.caption("대시보드 신호(기회점수)와 실제 Amazon/Sephora 데이터를 같이 보여줍니다.")

        manual_clean = df_manual.copy()
        manual_clean["date"] = pd.to_datetime(manual_clean["date"])

        for ing_id in (df_manual.get("ingredient_id", pd.Series()).unique() if "ingredient_id" in df_manual.columns else []):
            m_rows = manual_clean[manual_clean["ingredient_id"] == ing_id].sort_values("date")
            o_rows = pivoted[pivoted["ingredient_id"] == ing_id].sort_values("week")
            if m_rows.empty or o_rows.empty:
                continue
            name = ing_map.get(ing_id, {}).get("name_kr", ing_id)
            latest_opp = o_rows.iloc[-1]["opp_score"]
            latest_m = m_rows.iloc[-1]

            amz = latest_m.get("amazon_bsr_rank", "")
            seph = latest_m.get("sephora_new_launches", "")
            seph_bs = latest_m.get("sephora_bestseller", "")
            validation = "✅ 신호 일치" if (amz and int(float(str(amz).replace(",","") or 0)) < 5000 and latest_opp > 55) else "⚠️ 검증 미완"

            st.markdown(f"""
<div style="background:#f8f9fa;border-radius:8px;padding:10px 16px;margin-bottom:8px;
            display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
  <span style="font-weight:700;font-size:0.95rem;">{name}</span>
  <span style="font-size:0.8rem;color:#555;">기회점수 <b>{latest_opp:.0f}</b></span>
  <span style="font-size:0.8rem;color:#555;">Amazon BSR <b>{amz or '미입력'}</b></span>
  <span style="font-size:0.8rem;color:#555;">Sephora 신제품 <b>{seph or '미입력'}개</b></span>
  <span style="font-size:0.8rem;color:#555;">베스트셀러 <b>{seph_bs or '미확인'}</b></span>
  <span style="font-weight:700;font-size:0.82rem;">{validation}</span>
</div>""", unsafe_allow_html=True)
    else:
        st.info("💡 '판매 검증 입력' 탭에서 Amazon/Sephora 데이터를 입력하면 여기서 신호와 교차 검증됩니다.")


def view_channel_admin():
    st.title("📺 YouTube 채널 관리")
    st.caption("ET-Index 수집 대상 채널 목록. 설정 변경은 `config/youtube_channels.yaml`에서.")

    cfg = load_channels_config()
    channels = cfg.get("channels", [])
    collection = cfg.get("collection", {})

    # 수집 설정 요약
    col1, col2, col3 = st.columns(3)
    col1.metric("룩백 기간", f"{collection.get('lookback_days', 90)}일")
    col2.metric("채널당 최대 영상", f"{collection.get('max_videos_per_channel', 10)}개")
    col3.metric("자막 분석", "사용" if collection.get("use_transcript", True) else "미사용")

    st.divider()

    # 마켓 탭으로 분리
    tab_kr, tab_us = st.tabs(["🇰🇷 K-Expert (한국 전문의)", "🇺🇸 US-Expert (미국 전문의)"])

    def render_channel_table(market: str):
        market_channels = [c for c in channels if c.get("market", "kr") == market]
        active_count = sum(1 for c in market_channels if c.get("active", False))

        col1, col2, col3 = st.columns(3)
        col1.metric("전체 채널", len(market_channels))
        col2.metric("활성", active_count)
        col3.metric("비활성", len(market_channels) - active_count)

        st.markdown("")

        # 필터
        filter_col1, filter_col2 = st.columns([2, 1])
        with filter_col1:
            search = st.text_input("채널 검색", placeholder="채널명 또는 specialty", key=f"search_{market}")
        with filter_col2:
            show_inactive = st.checkbox("비활성 포함", value=True, key=f"inactive_{market}")

        rows = []
        for c in market_channels:
            if not show_inactive and not c.get("active", False):
                continue
            if search and search.lower() not in c["name"].lower() and search.lower() not in c.get("specialty", "").lower():
                continue

            ch_id = c.get("channel_id", "")
            id_status = "✅" if ch_id else "⚠️ handle로 자동조회"
            active_badge = "🟢 활성" if c.get("active", False) else "⭕ 비활성"

            rows.append({
                "상태": active_badge,
                "채널명": c["name"],
                "handle": c.get("handle", ""),
                "specialty": c.get("specialty", ""),
                "authority": c.get("authority_weight", 1.0),
                "focus": c.get("focus", ""),
                "channel_id": id_status,
            })

        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "authority": st.column_config.NumberColumn("authority_weight", format="%.1f"),
                    "focus": st.column_config.TextColumn("주요 분석 분야", width="large"),
                },
            )
        else:
            st.info("해당 조건의 채널이 없습니다.")

        # authority_weight 분포 차트
        if market_channels:
            active_chs = [c for c in market_channels if c.get("active", False)]
            if active_chs:
                st.markdown("**Authority Weight 분포 (활성 채널)**")
                aw_data = pd.DataFrame([
                    {"채널명": c["name"], "authority_weight": c.get("authority_weight", 1.0),
                     "specialty": c.get("specialty", "")}
                    for c in sorted(active_chs, key=lambda x: x.get("authority_weight", 1.0), reverse=True)
                ])
                fig = px.bar(
                    aw_data, x="채널명", y="authority_weight",
                    color="specialty", text="authority_weight",
                    height=320,
                    color_discrete_sequence=px.colors.qualitative.Set2,
                )
                fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
                fig.update_layout(
                    paper_bgcolor="#ffffff", plot_bgcolor="#f8f9fa",
                    font_color="#111", showlegend=True,
                    xaxis_tickangle=-35,
                    yaxis=dict(range=[0, 2.2], title="authority_weight"),
                    margin=dict(b=100),
                )
                st.plotly_chart(fig, use_container_width=True)

        st.info(
            f"채널 활성/비활성 변경: `config/youtube_channels.yaml`에서 `active: true/false` 수정 후 수집 실행\n"
            f"channel_id 검증 방법: 해당 채널 유튜브 페이지 → 우클릭 → 소스 보기 → 'channelId' 검색",
            icon="💡"
        )

    with tab_kr:
        render_channel_table("kr")
        st.markdown("**K-Expert Index 역할**")
        st.markdown("""
- **선행 지표 (Leading Indicator)**: K-뷰티 전문의가 주목하는 성분은 6~12개월 후 글로벌 트렌드로 전환되는 경향
- **FinalScore 계산**: K-ET × 0.4 가중치 (가장 높음) — 안전·효능 근거로 활용
- **언제 높은 K-ET가 의미 있는가**: 피부왕 정우열(1.8), 닥터임이석(1.8) 등 논문 인용 채널에서 강추 시 임상 근거 확보로 판단
        """)

    with tab_us:
        render_channel_table("us")
        st.markdown("**US-Expert Index 역할**")
        st.markdown("""
- **현지화 지표**: 서구권 피부 특성(얇은 피부층, 주름·홍조 중심), 소구점(Glass Skin vs Skin Barrier) 차이 반영
- **FinalScore 미포함**: US-ET는 별도 참고 지표 — 글로벌 출시 전략 수립 시 활용
- **핵심 활용 케이스**: K-ET 높은 성분이 US-ET도 높으면 글로벌 출시 확신 / US-ET 낮으면 제형 현지화 필요 신호
- **Dr. Dray(1.8), Lab Muffin(1.6)**: 성분 안전성 글로벌 권위자 — 이들의 언급 여부가 핵심
        """)


# ── 로그인 ─────────────────────────────────────────────────────────
AUTH_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "auth_config.yaml")

def run_with_auth():
    """로그인 래퍼 — 멀티 사용자 + 30일 쿠키.
    auth_config.yaml이 없거나 placeholder면 로그인 없이 실행 (개발 모드).
    """
    try:
        import streamlit_authenticator as stauth

        with open(AUTH_CONFIG_PATH, "r", encoding="utf-8") as f:
            auth_cfg = yaml.safe_load(f)

        # placeholder 해시면 로그인 건너뜀 (초기 셋업 전)
        first_pw = list(auth_cfg["credentials"]["usernames"].values())[0].get("password", "")
        if "placeholder" in first_pw:
            main()
            return

        authenticator = stauth.Authenticate(
            auth_cfg["credentials"],
            auth_cfg["cookie"]["name"],
            auth_cfg["cookie"]["key"],
            auth_cfg["cookie"]["expiry_days"],
        )

        # streamlit-authenticator 0.3+ 호환: kwargs 방식
        try:
            authenticator.login(location="main", fields={"Form name": "🌿 Beauty OS — 로그인"})
            name = st.session_state.get("name")
            auth_status = st.session_state.get("authentication_status")
            username = st.session_state.get("username")
        except TypeError:
            # 구 버전 호환
            name, auth_status, username = authenticator.login("Beauty OS — 로그인", "main")

        if auth_status is False:
            st.error("❌ 아이디 또는 비밀번호가 틀렸습니다.")
            available = list(auth_cfg["credentials"]["usernames"].keys())
            st.info(f"💡 등록된 ID: `{'`, `'.join(available)}`  \n"
                    f"💡 비밀번호 분실 시: `python3 scripts/manage_users.py change_password <ID>`")
        elif auth_status is None:
            st.info("🔐 아이디와 비밀번호를 입력하세요. 30일간 자동 로그인 유지됩니다.")
            available = list(auth_cfg["credentials"]["usernames"].keys())
            st.caption(f"등록된 ID: `{'`, `'.join(available)}` | 기본 비번: `beauty2025!`")
            with st.expander("ℹ️ 외부 접근 방법 (Tailscale + 모바일/외부 PC)"):
                st.markdown("""
                **이 대시보드는 Mac에서 호스팅됩니다.** 외부에서 접근하려면:

                1. **Tailscale 가입**: https://login.tailscale.com/start
                2. Mac과 본인 기기 모두에 Tailscale 설치
                3. 같은 네트워크에 들어오면 `http://<mac-tailscale-ip>:8501` 접근 가능
                4. 자세한 셋업: `docs/TAILSCALE_SETUP.md` 참조
                """)
        else:
            # 사이드바 사용자 정보 + 로그아웃
            users = auth_cfg["credentials"]["usernames"]
            user_info = users.get(username, {})
            role = user_info.get("role", "viewer")
            role_emoji = "👑" if role == "admin" else "👤"
            st.sidebar.markdown(f"### {role_emoji} {name}")
            st.sidebar.caption(f"권한: {role} · 30일 자동 로그인")
            try:
                authenticator.logout(location="sidebar", button_name="🚪 로그아웃")
            except TypeError:
                authenticator.logout("로그아웃", "sidebar")
            main()

    except FileNotFoundError:
        st.warning("⚠️ auth_config.yaml 없음 — 로그인 없이 실행 중")
        main()
    except ImportError:
        st.warning("⚠️ streamlit-authenticator 미설치 — `pip install streamlit-authenticator bcrypt`")
        main()
    except (yaml.YAMLError, KeyError, AttributeError) as e:
        # 진짜 인증 설정 오류만 fallback (view 내부 에러는 그대로 노출)
        if "yaml" in str(type(e)).lower() or "auth" in str(e).lower() or "credentials" in str(e).lower():
            st.error(f"인증 설정 오류: {e}")
            st.caption("로그인 없이 실행됩니다.")
            main()
        else:
            raise  # view 에러는 정상적으로 표시


# ── View: 성분 연구 인사이트 ────────────────────────────────────────
def view_ingredient_research():
    st.title("🔬 성분 연구 인사이트")
    st.caption(
        "최신 화장품·의약품 성분 논문 및 임상시험 데이터를 기반으로 R&D 방향을 도출합니다. "
        "| 데이터 기준: 2022–2025 주요 피어리뷰 논문 및 임상 데이터베이스 (PubMed, ClinicalTrials.gov, CIR)"
    )

    # ─── 데이터 정의 ───────────────────────────────────────────────
    INGREDIENTS = [
        {
            "id": "pdrn_pn",
            "name_kr": "PDRN / PN",
            "name_en": "Polydeoxyribonucleotide",
            "category": "생체고분자 / 재생",
            "stage": "더마코스메틱 전환",
            "stage_code": 3,
            "paper_count": 312,
            "trend": "급성장",
            "mechanism": (
                "연어 정자 유래 DNA 단편. A2A 아데노신 수용체 활성화 → "
                "세포 증식·조직 재생 촉진. 항염(NF-κB 억제) + VEGF 발현 증가로 "
                "혈관 신생 및 진피 리모델링 가속."
            ),
            "efficacy": (
                "8주 임상(n=42): 피부 탄력 28% 개선, 수분량 34% 증가 (vs 위약). "
                "주름 깊이 15% 감소. 아토피 피부 TEWL 개선 유의미(p<0.05)."
            ),
            "concentration": "1–5% (코스메틱 기준) | 주사 제형: 0.4–3.0%",
            "synergy": "히알루론산(HA) — 수분 보유력 상승 / 나이아신아마이드 — 미백+재생 복합 타겟",
            "conflict": "강산성(pH<4) 환경에서 DNA 단편 분해 가속. 고농도 알코올(>15%)과 혼합 시 안정성 저하.",
            "rnd_insight": (
                "스킨부스터 시장(2025 글로벌 $1.8B) 직접 겨냥 가능. "
                "주사 제형의 PDRN 효능을 표방한 '토피컬 PDRN 앰플' 포지셔닝이 유효하며, "
                "HA 복합 패치 또는 마이크로니들 포맷으로 전달 효율 개선 시 차별화 가능."
            ),
        },
        {
            "id": "exosome",
            "name_kr": "엑소좀",
            "name_en": "Exosomes / EVs",
            "category": "세포외소포체",
            "stage": "임상연구 단계",
            "stage_code": 2,
            "paper_count": 487,
            "trend": "급성장",
            "mechanism": (
                "줄기세포(MSC, 지방세포 등) 유래 나노소포체(30–150nm). "
                "성장인자·miRNA·단백질 복합 전달 → 섬유아세포 활성화, 콜라겐I/III 합성 증가, "
                "염증 억제(IL-6·TNF-α 감소)."
            ),
            "efficacy": (
                "탈모 임상(n=30, 두피 주사): 16주 후 모발 밀도 28.3% 증가. "
                "피부 재생(n=20, 레이저 후 국소도포): 홍반 회복 속도 40% 단축. "
                "단, 토피컬 단독 흡수 효율 데이터는 제한적."
            ),
            "concentration": "N/A (농도 표준화 미확립) | 입자 수 기준: 1×10⁹–10¹⁰ particles/mL",
            "synergy": "마이크로니들 / 이온토포레시스와 결합 시 경피 흡수율 대폭 향상",
            "conflict": "열·동결건조 반복 시 구조 손상. pH 7.4 외 환경에서 안정성 급락. 방부제(paraben류) 막 파괴 우려.",
            "rnd_insight": (
                "현재 토피컬 제형의 가장 큰 허들은 경피 흡수율 — 기기(LED, RF, 마이크로니들) 연계 홈케어 키트로 "
                "포지셔닝하면 토피컬 한계를 우회 가능. "
                "2025년 식약처 가이드라인 정비 예정이므로 규제 선점 전략이 중요."
            ),
        },
        {
            "id": "retinal",
            "name_kr": "레티날 (레티날데하이드)",
            "name_en": "Retinaldehyde",
            "category": "비타민A 유도체",
            "stage": "코스메슈티컬",
            "stage_code": 4,
            "paper_count": 198,
            "trend": "상승",
            "mechanism": (
                "레티놀 → 레티날 → 레티노산의 산화 단계에서 레티노산 직전 전구체. "
                "레티놀 대비 레티노산 전환 효율 11배 높음 → 동일 효능에 낮은 농도 사용 가능. "
                "RAR(핵수용체) 직접 활성화, 콜라겐 합성 및 세포 교체 촉진."
            ),
            "efficacy": (
                "12주 임상: 주름 깊이 44% 감소 (레티놀 0.1% 대비 동등 효능, 자극은 47% 적음). "
                "색소침착 개선 MASI 스코어 32% 감소(n=55)."
            ),
            "concentration": "0.05–0.1% (유효) | 0.025% (민감성 입문)",
            "synergy": "바쿠치올(자극 완화 + 항산화 시너지) / 펩타이드(매트리실+레티날 복합 제형으로 리프팅 강화)",
            "conflict": "산화에 극히 불안정 → 불투명·질소 충진 포장 필수. pH>7에서 분해 가속. AHA/BHA와 동시 사용 시 자극 급증.",
            "rnd_insight": (
                "레티놀의 '부작용 없는 업그레이드'로 포지셔닝 가능한 황금 성분. "
                "국내 더마 브랜드의 레티날 0.05~0.1% 앰플·크림 포맷이 현 시장에서 가장 빠른 진입 경로. "
                "캡슐화(마이크로스피어, 리포좀) 기술 결합 시 안정성 문제를 해결하며 프리미엄 포지셔닝 가능."
            ),
        },
        {
            "id": "bakuchiol",
            "name_kr": "바쿠치올",
            "name_en": "Bakuchiol",
            "category": "식물 유래 레티놀 대안",
            "stage": "코스메슈티컬",
            "stage_code": 4,
            "paper_count": 89,
            "trend": "안정 성장",
            "mechanism": (
                "Psoralea corylifolia 씨앗 추출 메로터페노이드. "
                "레티노산 수용체(RAR/RXR) 부분 활성화 + 항산화·항염 작용. "
                "레티놀과 유사한 유전자 발현 프로파일을 보이나 구조적으로 완전히 다름."
            ),
            "efficacy": (
                "12주 RCT: 레티놀 0.5%와 동등한 주름 감소 및 색소침착 개선. "
                "임산부·민감성 피부에서 자극 지수 현저히 낮음. 광안정성 우수(UV 조사 후 85% 잔존)."
            ),
            "concentration": "0.5–2.0%",
            "synergy": "레티놀(저농도 복합으로 시너지, 자극 상쇄) / 나이아신아마이드 / 비타민C 유도체",
            "conflict": "강한 향(쌉쌀한 허브향) → 향료와 조합 시 관능 밸런스 주의. 고농도(>3%)에서 일부 피부 자극 보고.",
            "rnd_insight": (
                "임산부·수유부 세분화 시장에서 '레티놀 대안' 포지셔닝이 명확. "
                "국내 시장에서 인지도가 아직 낮으므로 선점 기회 존재. "
                "레티날(0.05%) + 바쿠치올(1%) 복합 제형은 효능과 순함을 동시에 소구할 수 있는 포뮬라."
            ),
        },
        {
            "id": "ectoin",
            "name_kr": "엑토인",
            "name_en": "Ectoin",
            "category": "아미노산 유도체 / 장벽 강화",
            "stage": "코스메슈티컬",
            "stage_code": 4,
            "paper_count": 143,
            "trend": "상승",
            "mechanism": (
                "극한 미생물 유래 compatible solute. 물 분자 클러스터 형성 → "
                "단백질·세포막 구조 안정화. HSP(열충격단백질) 발현 억제로 항염 + "
                "청색광·UV 스트레스로부터 피부세포 보호."
            ),
            "efficacy": (
                "아토피 피부(n=52): 4주 후 가려움 지수 46% 개선. "
                "환경 민감성 피부 장벽 회복 속도 타크롤리무스 1% 대비 동등 수준(독일 임상). "
                "청색광 차단 효능: 세포 생존율 67%→89% (in vitro)."
            ),
            "concentration": "0.5–2.0%",
            "synergy": "판테놀(장벽 복구 시너지) / 세라마이드(조합 시 TEWL 추가 감소) / 알란토인",
            "conflict": "특별한 길항 성분 없음. 고온(>50°C) 제조 공정에서 구조 변형 가능 → 후처리 투입 권장.",
            "rnd_insight": (
                "도심 환경 민감성·쿠퍼로제 피부 타겟 '어반 실드' 콘셉트에 최적. "
                "청색광 차단을 전면에 내세운 디지털 디톡스 세럼 포지셔닝이 2025 트렌드와 부합. "
                "마스크 착용 트러블 피부 라인에서 판테놀과 복합 처방 시 즉각 순함 소구 가능."
            ),
        },
        {
            "id": "ghk_cu",
            "name_kr": "GHK-Cu (구리 트리펩타이드)",
            "name_en": "Copper Peptide GHK-Cu",
            "category": "펩타이드 / 재생",
            "stage": "더마코스메틱 전환",
            "stage_code": 3,
            "paper_count": 267,
            "trend": "안정 성장",
            "mechanism": (
                "글리실-L-히스티딜-L-라이신-구리(II) 복합체. "
                "구리 이온 매개 → 콜라겐/엘라스틴 합성 효소(리실 옥시다제) 활성화. "
                "MMPs(기질금속단백분해효소) 억제 + 항산화 + 모낭 성장인자 자극."
            ),
            "efficacy": (
                "12주 사용 후 피부 밀도 17% 증가, 잔주름 감소율 30%. "
                "탈모 임상(국소 도포): 미녹시딜 5%와 유사한 모발 성장 효과(소규모 n=40). "
                "상처 치유 촉진 — 피부 재생 속도 35% 단축(in vivo)."
            ),
            "concentration": "0.1–5.0% | 일반 제품: 0.5–2%",
            "synergy": "펩타이드(마트릭실, 아르지렐린)와 복합 시 다중 타겟 항노화 시너지 / 비오틴(탈모 케어)",
            "conflict": "고농도 비타민C(L-AA)와 혼합 시 킬레이션으로 구리 이온 불활성화 → 효능 상실. 강산성 환경(pH<4) 분해.",
            "rnd_insight": (
                "탈모+피부 노화 동시 타겟 '두피-얼굴 경계' 케어 제품군(헤어라인 세럼)으로 차별화 가능. "
                "재생 클리닉 PMR(Post Medical Recovery) 라인에서 엑소좀과 복합 처방 시 "
                "병원 채널 진입 전략으로 활용 가능."
            ),
        },
        {
            "id": "niacinamide",
            "name_kr": "나이아신아마이드",
            "name_en": "Niacinamide (Vit B3)",
            "category": "비타민 / 미백·장벽",
            "stage": "메인스트림",
            "stage_code": 5,
            "paper_count": 892,
            "trend": "성숙기",
            "mechanism": (
                "비타민 B3 유도체. 멜라노솜 이동 억제(keratinocyte-melanocyte junction 차단) → 미백. "
                "세라마이드·지방산 합성 촉진 → 장벽 강화. PARP-1 활성화로 DNA 수복 지원."
            ),
            "efficacy": (
                "5% 농도 8주: 기미 L값 개선 12%, 피부 홍조 감소 34%(n=50). "
                "10% 농도: 여드름 병변 감소 효과 BPO 4%와 유사(무자극). "
                "모공 개선 메타분석 효과 크기 d=0.62."
            ),
            "concentration": "2–10% (미백·장벽) | >10% 에서 홍조 역반응 주의",
            "synergy": "레티놀(자극 완화 + 상보 작용) / 아젤라익산(미백 강화) / 아연(여드름 복합 타겟)",
            "conflict": "고농도 L-아스코르브산(순수 비타민C)과 혼합 시 니아신으로 전환 → 홍조 유발 가능 (단, pH 조절로 대부분 방지 가능). 고온 저장 시 황변.",
            "rnd_insight": (
                "성숙 성분이나 고농도(15%+)·특수 제형(나노캡슐) 차별화 여지 존재. "
                "아젤라익산 + 나이아신아마이드 + 트라넥사믹애씨드 3중 미백 복합 처방이 "
                "메디컬 에스테틱 채널에서 주목받는 트렌드."
            ),
        },
        {
            "id": "polyglutamic_acid",
            "name_kr": "폴리글루타믹애씨드",
            "name_en": "Polyglutamic Acid (PGA)",
            "category": "생체고분자 / 수분",
            "stage": "코스메슈티컬",
            "stage_code": 4,
            "paper_count": 76,
            "trend": "상승",
            "mechanism": (
                "낫토균(Bacillus subtilis) 발효 유래 폴리아미노산. "
                "분자량 100–1000 kDa → HA 대비 4배 높은 수분 보유 능력. "
                "피부 표면 필름 형성 + 천연 보습인자(NMF) 생성 촉진."
            ),
            "efficacy": (
                "4주 임상: 피부 수분량 HA 2% 대비 38% 추가 증가. "
                "TEWL 개선 효과 지속 시간 HA 2배. "
                "필러 시술 후 보조 보습제로 처방 시 결과 만족도 향상(n=28, 의사 평가)."
            ),
            "concentration": "0.1–1.0%",
            "synergy": "히알루론산 다분자량 복합(저·중·고 HA + PGA 레이어링)으로 수분 전달 최적화",
            "conflict": "양이온 계면활성제와 복합체 형성 → 침전. 강산성 환경에서 가수분해.",
            "rnd_insight": (
                "HA 시장의 직접 대체제로 포지셔닝하기보다 'HA 다음 단계' 포스트HA 내러티브 활용 권장. "
                "스킨부스터 시술 직후 사용하는 '회복 세럼' 포맷에서 PDRN + PGA 복합 처방이 "
                "클리닉 채널 침투에 유효."
            ),
        },
        {
            "id": "spermidine",
            "name_kr": "스퍼미딘",
            "name_en": "Spermidine",
            "category": "폴리아민 / 세포 재생",
            "stage": "기초·임상연구",
            "stage_code": 1,
            "paper_count": 54,
            "trend": "신흥 주목",
            "mechanism": (
                "천연 폴리아민. 오토파지(세포 자가청소) 활성화 → 손상 단백질·소기관 제거. "
                "히스톤 아세틸화 억제로 항노화 유전자 발현 조절. "
                "체내에서 소맥배아·콩 등 식품에 풍부, 최근 외용 연구 시작."
            ),
            "efficacy": (
                "경구 복용 RCT(n=100): 모발 직경 35% 증가, 모발 성장기 연장. "
                "토피컬 연구: 소규모 파일럿(n=15)에서 피부 탄력 개선 초기 신호. "
                "단, 외용 임상 데이터 매우 제한적 — 추가 검증 필요."
            ),
            "concentration": "N/A (외용 표준 농도 미확립) | 경구: 1–3mg/일",
            "synergy": "N/A (외용 복합 처방 연구 데이터 없음)",
            "conflict": "N/A (외용 안전성 장기 데이터 부족)",
            "rnd_insight": (
                "현 단계에서는 경구 보충제(이너뷰티) 라인 또는 '세포 재생' 마케팅 클레임 재료로 활용 적합. "
                "외용 임상이 본격화되는 2026–2027년이 코스메슈티컬 진입 타이밍. "
                "선행 특허 확보 및 파일럿 임상 투자가 지금의 전략적 포인트."
            ),
        },
        {
            "id": "ceramide",
            "name_kr": "세라마이드",
            "name_en": "Ceramide (NP/AP/EOP)",
            "category": "지질 / 장벽",
            "stage": "메인스트림",
            "stage_code": 5,
            "paper_count": 634,
            "trend": "성숙기",
            "mechanism": (
                "각질층 지질 이중층의 핵심 구성 성분(50%). "
                "수분 증발 차단(TEWL 억제) + 외부 자극원 침투 방어. "
                "세라마이드:콜레스테롤:지방산 = 3:1:1 이상적 비율로 장벽 회복 최대화."
            ),
            "efficacy": (
                "아토피 피부(n=62): 세라마이드 복합 제형 4주 SCORAD 38% 개선. "
                "건성 피부: 8주 후 각질층 수분량 43% 증가, TEWL 29% 감소. "
                "신생아 예방적 사용: 아토피 발생 위험 50% 감소(대규모 코호트, n=124)."
            ),
            "concentration": "0.5–5.0% | 복합 제형(+콜레스테롤+지방산) 권장",
            "synergy": "콜레스테롤 + 지방산(팔미틱/리놀레익) 3중 조합 / 판테놀·엑토인과 민감성 라인 조합",
            "conflict": "일부 계면활성제(SLS)가 세라마이드 장벽 손상. 과도한 AHA 사용과 병행 시 박리 후 장벽 노출 → 자극 증폭.",
            "rnd_insight": (
                "성숙 카테고리이나 '세라마이드 함량 높은 처방'이 소비자 인지 포인트로 부상. "
                "단순 세라마이드 제품보다 세라마이드+엑토인+판테놀 '트리플 장벽 포뮬라' 포지셔닝이 "
                "더마 채널에서 차별화 가능."
            ),
        },
    ]

    STAGE_META = {
        1: {"label": "🧪 기초·임상 연구", "color": "#9B59B6", "desc": "전임상/소규모 임상 — 코스메틱 진입 전"},
        2: {"label": "🏥 의학 채널 활성", "color": "#E74C3C", "desc": "병원·클리닉 중심 사용, 코스메틱 규제 준비 중"},
        3: {"label": "💉 더마코스메틱 전환", "color": "#E67E22", "desc": "메디컬→코스메틱 교차 단계, 스킨부스터·앰플"},
        4: {"label": "✨ 코스메슈티컬", "color": "#27AE60", "desc": "기능성 코스메틱 정착, 더마 브랜드 주력"},
        5: {"label": "🛒 메인스트림", "color": "#2980B9", "desc": "일반 코스메틱 대중화, 차별화 어려움"},
    }

    # ─── 상단 KPI 카드 ──────────────────────────────────────────────
    total_papers = sum(i["paper_count"] for i in INGREDIENTS)
    rising = [i for i in INGREDIENTS if i["trend"] in ("급성장", "상승", "신흥 주목")]
    transitioning = [i for i in INGREDIENTS if i["stage_code"] == 3]
    medical_active = [i for i in INGREDIENTS if i["stage_code"] <= 2]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div style="background:#1a1a2e;border-radius:10px;padding:16px 20px;text-align:center">
            <div style="font-size:2rem;font-weight:700;color:#4fc3f7">{total_papers:,}</div>
            <div style="font-size:0.78rem;color:#aaa;margin-top:4px">분석 논문 수 (추정)</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div style="background:#1a2e1a;border-radius:10px;padding:16px 20px;text-align:center">
            <div style="font-size:2rem;font-weight:700;color:#66bb6a">{len(rising)}</div>
            <div style="font-size:0.78rem;color:#aaa;margin-top:4px">연구 급성장 성분</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div style="background:#2e1a0e;border-radius:10px;padding:16px 20px;text-align:center">
            <div style="font-size:2rem;font-weight:700;color:#ffa726">{len(transitioning)}</div>
            <div style="font-size:0.78rem;color:#aaa;margin-top:4px">더마코스메틱 전환 중</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
        <div style="background:#2e0e0e;border-radius:10px;padding:16px 20px;text-align:center">
            <div style="font-size:2rem;font-weight:700;color:#ef5350">{len(medical_active)}</div>
            <div style="font-size:0.78rem;color:#aaa;margin-top:4px">의학 연구 단계</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ─── 탭 구성 ────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs(["🗺️ 성숙도 맵", "📋 성분 상세 카드", "⚗️ 시너지 & 충돌 매트릭스", "🔍 TikTok 신규 발굴"])

    # ── 탭 1: 성숙도 맵 ─────────────────────────────────────────────
    with tab1:
        st.markdown("### 성분 R&D 성숙도 현황")
        st.caption("X축: 논문 수(연구 볼륨) | Y축: 성숙도 단계(1=기초연구 → 5=메인스트림) | 원 크기: 트렌드 모멘텀")

        trend_score = {"급성장": 40, "신흥 주목": 35, "상승": 28, "안정 성장": 20, "성숙기": 14}

        map_df = pd.DataFrame([{
            "성분명": f"{i['name_kr']}\n({i['name_en']})",
            "name_kr": i["name_kr"],
            "name_en": i["name_en"],   # ★ APLB 보유 매칭용
            "논문 수": i["paper_count"],
            "성숙도": i["stage_code"],
            "단계": STAGE_META[i["stage_code"]]["label"],
            "트렌드": i["trend"],
            "버블크기": trend_score.get(i["trend"], 15),
            "색상코드": STAGE_META[i["stage_code"]]["color"],
        } for i in INGREDIENTS])

        fig = px.scatter(
            map_df,
            x="논문 수",
            y="성숙도",
            size="버블크기",
            color="단계",
            text="name_kr",
            hover_data={"트렌드": True, "논문 수": True, "버블크기": False, "성숙도": False},
            color_discrete_map={v["label"]: v["color"] for v in STAGE_META.values()},
            size_max=55,
            height=480,
        )
        fig.update_traces(textposition="top center", textfont_size=11)
        fig.update_layout(
            yaxis=dict(
                tickvals=[1, 2, 3, 4, 5],
                ticktext=[STAGE_META[i]["label"] for i in range(1, 6)],
                gridcolor="#333",
            ),
            xaxis=dict(gridcolor="#333"),
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            font_color="#ddd",
            legend=dict(orientation="h", yanchor="bottom", y=-0.3),
            margin=dict(l=20, r=20, t=20, b=60),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### 단계별 정의")
        cols = st.columns(5)
        for idx, (code, meta) in enumerate(STAGE_META.items()):
            with cols[idx]:
                st.markdown(f"""
                <div style="border-left:3px solid {meta['color']};padding:8px 10px;background:#111;border-radius:4px;height:80px">
                    <div style="font-size:0.8rem;font-weight:600;color:{meta['color']}">{meta['label']}</div>
                    <div style="font-size:0.72rem;color:#bbb;margin-top:4px">{meta['desc']}</div>
                </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 트렌드 모멘텀 순위")

        # ── 단계별 액션 가이드 (정적, 즉시 보임) ────────────────────
        st.markdown("""
        <div style="background:#fafafa;border:1px solid #ececef;border-radius:10px;
             padding:14px 18px;margin-bottom:14px">
          <div style="font-size:0.78rem;color:#6b7280;font-weight:700;
               letter-spacing:0.05em;margin-bottom:10px">📖 단계별 APLB 액션 가이드</div>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;font-size:0.82rem">
            <div style="border-left:3px solid #10b981;padding:6px 10px">
              <b style="color:#047857">🌱 기초·임상 연구</b><br>
              <span style="color:#666">관망. 24개월 후 진입 후보로 모니터링</span>
            </div>
            <div style="border-left:3px solid #06b6d4;padding:6px 10px">
              <b style="color:#0e7490">🏥 의학 채널 활성</b><br>
              <span style="color:#666">시술/derma 영역에서 활성 — 12~18mo 후 cosmetic 진입</span>
            </div>
            <div style="border-left:3px solid #8b5cf6;padding:6px 10px">
              <b style="color:#6b21a8">💉 더마코스메틱 전환</b><br>
              <span style="color:#666"><b>지금 컴플렉스 개발 시작</b>. 6~12mo 후 매스 진입</span>
            </div>
            <div style="border-left:3px solid #ec4899;padding:6px 10px">
              <b style="color:#be185d">✨ 코스메슈티컬</b><br>
              <span style="color:#666"><b>1순위 신제품 후보</b>. 차별화(농도/페어/기술) 필수</span>
            </div>
            <div style="border-left:3px solid #6b7280;padding:6px 10px">
              <b style="color:#374151">🛒 메인스트림</b><br>
              <span style="color:#666">포화. APLB 보유면 강화, 미보유면 회피 또는 프리미엄만</span>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # ── APLB 보유 매핑 + 액션 컬럼 ────────────────────────────
        try:
            aplb_yaml = Path(__file__).parent / "config" / "aplb_products.yaml"
            aplb_owned_set = set()
            if aplb_yaml.exists():
                aplb = yaml.safe_load(aplb_yaml.read_text(encoding="utf-8"))
                for cx in aplb.get("complexes", []) + aplb.get("single_actives", []):
                    for ing in cx.get("primary_ingredients", []):
                        aplb_owned_set.add(ing.lower())
        except Exception:
            aplb_owned_set = set()

        # 단계별 액션 라벨
        STAGE_ACTION = {
            "기초·임상 연구":   "👀 관망 — 24mo 모니터링",
            "의학 채널 활성":   "🔭 12~18mo 후 진입 — 미리 컴플렉스 설계",
            "더마코스메틱 전환": "🚀 즉시 R&D 시작 — 6~12mo 진입",
            "코스메슈티컬":     "⚡ 1순위 신제품 — 차별화 필수",
            "메인스트림":       "🛒 포화 — 보유 시 프리미엄/Black",
        }

        rank_df = map_df[["name_kr", "name_en", "트렌드", "논문 수", "단계"]].copy()
        rank_df["APLB"] = rank_df["name_en"].apply(
            lambda x: "✅ 보유" if any(o in (x or "").lower() for o in aplb_owned_set) else "🆕 미보유"
        )
        rank_df["권장 액션"] = rank_df["단계"].map(lambda s: STAGE_ACTION.get(s, "—"))
        rank_df = rank_df[["name_kr", "트렌드", "논문 수", "단계", "APLB", "권장 액션"]]
        rank_df.columns = ["성분명", "트렌드", "논문 수", "R&D 단계", "APLB 보유", "권장 액션"]
        rank_df = rank_df.sort_values("논문 수", ascending=False).reset_index(drop=True)
        rank_df.index += 1
        st.dataframe(rank_df, use_container_width=True, hide_index=False)

        # ── 한 줄 요약 (자동) ──────────────────────────────────────
        owned_in_top = rank_df[(rank_df["APLB 보유"] == "✅ 보유")].shape[0]
        not_owned_premium = rank_df[
            (rank_df["APLB 보유"] == "🆕 미보유") &
            (rank_df["R&D 단계"].isin(["코스메슈티컬", "더마코스메틱 전환"]))
        ]
        gap_list = ", ".join(not_owned_premium["성분명"].head(3).tolist())

        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#fdf2f8 0%,#f3e8ff 100%);
             border-left:4px solid #ec4899;padding:14px 18px;border-radius:0 10px 10px 0;margin-top:14px">
          <div style="font-size:0.85rem;color:#374151;line-height:1.7">
            <b style="color:#be185d">🎯 한 줄 요약 ({len(rank_df)}개 추적 中)</b><br/>
            • APLB 보유 성분 <b>{owned_in_top}개</b>가 상위 모멘텀에 포함 → 마케팅 강화 대상<br/>
            • 미보유 + 코스메슈티컬/더마전환 단계 = <b>신제품 후보</b>: <span style="color:#be185d;font-weight:700">{gap_list or '없음'}</span><br/>
            • 메인스트림(포화) 진입은 프리미엄/Black 라인만 검토
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── 탭 2: 성분 상세 카드 ────────────────────────────────────────
    with tab2:
        st.markdown("### 성분별 처방 과학 상세")

        filter_stage = st.multiselect(
            "단계 필터",
            options=[m["label"] for m in STAGE_META.values()],
            default=[m["label"] for m in STAGE_META.values()],
            label_visibility="collapsed",
        )
        active_codes = [c for c, m in STAGE_META.items() if m["label"] in filter_stage]
        filtered = [i for i in INGREDIENTS if i["stage_code"] in active_codes]

        if not filtered:
            st.info("선택된 단계에 해당하는 성분이 없습니다.")
        else:
            for ing in filtered:
                stage = STAGE_META[ing["stage_code"]]
                with st.expander(
                    f"{stage['label']} | **{ing['name_kr']}** ({ing['name_en']}) — {ing['trend']} | 논문 {ing['paper_count']}건",
                    expanded=False,
                ):
                    col_l, col_r = st.columns([3, 1])
                    with col_l:
                        fields = [
                            ("🔬 작용 기전", ing["mechanism"]),
                            ("📊 효능 & 결과", ing["efficacy"]),
                            ("💊 유효 농도", ing["concentration"]),
                            ("🤝 시너지 성분", ing["synergy"]),
                            ("⚠️ 충돌 / 불안정", ing["conflict"]),
                            ("💡 R&D 인사이트", ing["rnd_insight"]),
                        ]
                        for label, value in fields:
                            st.markdown(f"**{label}**")
                            st.markdown(
                                f'<div style="background:#111;border-radius:6px;padding:10px 14px;'
                                f'font-size:0.85rem;color:#ddd;margin-bottom:10px;'
                                f'border-left:3px solid {stage["color"]}">{value}</div>',
                                unsafe_allow_html=True,
                            )
                    with col_r:
                        st.markdown(f"""
                        <div style="background:#111;border-radius:8px;padding:14px;text-align:center">
                            <div style="font-size:0.72rem;color:#888">카테고리</div>
                            <div style="font-size:0.82rem;color:#ddd;margin:4px 0">{ing['category']}</div>
                            <hr style="border-color:#333;margin:8px 0">
                            <div style="font-size:0.72rem;color:#888">R&D 단계</div>
                            <div style="font-size:0.8rem;font-weight:600;color:{stage['color']};margin:4px 0">{stage['label']}</div>
                            <hr style="border-color:#333;margin:8px 0">
                            <div style="font-size:0.72rem;color:#888">트렌드</div>
                            <div style="font-size:0.85rem;color:#ffd54f;margin:4px 0">{ing['trend']}</div>
                            <hr style="border-color:#333;margin:8px 0">
                            <div style="font-size:0.72rem;color:#888">분석 논문</div>
                            <div style="font-size:1.4rem;font-weight:700;color:#4fc3f7">{ing['paper_count']}</div>
                        </div>""", unsafe_allow_html=True)

    # ── 탭 3: 시너지 & 충돌 매트릭스 ────────────────────────────────
    with tab3:
        st.markdown("### 성분 간 시너지 & 충돌 요약")
        st.caption("제형 설계 시 참고용 — 원칙은 개별 임상 검증 우선")

        synergy_data = [
            {"성분 A": "레티날", "성분 B": "바쿠치올", "관계": "✅ 시너지", "근거": "레티날 자극 완화 + 광안정성 보완. 저농도 복합에서 항노화 시너지"},
            {"성분 A": "레티날", "성분 B": "AHA/BHA", "관계": "⚠️ 주의", "근거": "동시 사용 시 자극 급증. 사용 시간대 분리(레티날 야간, AHA 격일) 권장"},
            {"성분 A": "나이아신아마이드", "성분 B": "레티놀", "관계": "✅ 시너지", "근거": "나이아신아마이드가 레티놀 자극 완화 + 미백·항노화 복합 타겟"},
            {"성분 A": "나이아신아마이드", "성분 B": "순수 비타민C(L-AA)", "관계": "🔴 충돌 주의", "근거": "고온·고농도에서 니아신 전환 → 홍조. pH 3.5 이하 유지 또는 유도체(APS, VC-IP)로 대체"},
            {"성분 A": "GHK-Cu", "성분 B": "비타민C(L-AA)", "관계": "🔴 충돌", "근거": "킬레이션으로 구리 이온 불활성화 → GHK-Cu 효능 소실. 절대 혼합 금지"},
            {"성분 A": "PDRN", "성분 B": "히알루론산", "관계": "✅ 시너지", "근거": "재생+수분 이중 타겟. HA가 PDRN의 경피 흡수 환경 개선"},
            {"성분 A": "세라마이드", "성분 B": "콜레스테롤+지방산", "관계": "✅ 시너지", "근거": "3:1:1 비율 복합이 각질층 지질 이중층 가장 가깝게 복원"},
            {"성분 A": "엑토인", "성분 B": "판테놀", "관계": "✅ 시너지", "근거": "항염(엑토인)+피부 재생(판테놀) 조합. 민감성·쿠퍼로제 처방 표준"},
            {"성분 A": "레티날", "성분 B": "GHK-Cu", "관계": "✅ 시너지", "근거": "콜라겐 합성 경로 다중 타겟(레티날:RAR 경로 / GHK-Cu:리실옥시다제 경로)"},
            {"성분 A": "폴리글루타믹애씨드", "성분 B": "히알루론산", "관계": "✅ 시너지", "근거": "분자량 보완으로 진피~표피 전층 수분 레이어링 가능"},
            {"성분 A": "엑소좀", "성분 B": "마이크로니들", "관계": "✅ 시너지", "근거": "마이크로니들로 각질층 채널 형성 → 엑소좀 경피 흡수율 극대화"},
        ]

        synergy_df = pd.DataFrame(synergy_data)

        def highlight_relation(val):
            if "시너지" in val:
                return "background-color: #1a3a1a; color: #66bb6a"
            elif "충돌" in val:
                return "background-color: #3a1a1a; color: #ef5350"
            elif "주의" in val:
                return "background-color: #3a2a0a; color: #ffa726"
            return ""

        st.dataframe(
            synergy_df.style.map(highlight_relation, subset=["관계"]),
            use_container_width=True,
            height=420,
        )

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 신제품 기획 가이드 — 복합 처방 추천")
        recs = [
            ("항노화 프리미엄 세럼", "레티날 0.05–0.1% + 바쿠치올 1% + GHK-Cu 1% + 폴리글루타믹애씨드 0.3%", "콜라겐 합성 3중 경로 + 광안정성 확보"),
            ("더마 재생 앰플 (클리닉 채널)", "PDRN 2% + 엑소좀 (1×10¹⁰/mL) + 히알루론산 복합 + 판테놀 5%", "스킨부스터 시술 후 PMR 케어, 병원 채널 진입"),
            ("민감성 장벽 크림", "엑토인 1.5% + 세라마이드 NP/AP 복합 2% + 판테놀 3% + 폴리글루타믹애씨드 0.5%", "청색광 차단 + 장벽 복구 + 수분 삼중 소구"),
            ("멀티태스킹 미백·안티에이징", "나이아신아마이드 5% + 아젤라익산 5% + 바쿠치올 1% + GHK-Cu 0.5%", "미백·재생·순함 동시 소구, 모든 피부 타입 적합"),
        ]
        for name, formula, point in recs:
            st.markdown(f"""
            <div style="background:#111;border-radius:8px;padding:14px 18px;margin-bottom:10px;border-left:4px solid #4fc3f7">
                <div style="font-weight:600;color:#4fc3f7;font-size:0.9rem">{name}</div>
                <div style="font-size:0.82rem;color:#ccc;margin:6px 0"><b>처방:</b> {formula}</div>
                <div style="font-size:0.8rem;color:#aaa"><b>포인트:</b> {point}</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.caption("⚠️ 본 인사이트는 공개 논문·임상 데이터 기반이며, 실제 제품화 전 사내 안정성 테스트 및 임상 검증이 반드시 필요합니다.")

    # ── 탭 4: TikTok 신규 발굴 ──────────────────────────────────────
    with tab4:
        st.markdown("### 🔍 TikTok에서 새로 뜨는 성분")
        st.caption("200+ 뷰티 해시태그를 추적해 아직 YAML에 등록되지 않은 신규 버즈 성분을 자동 발굴합니다. | 매일 새벽 6시 자동 업데이트")

        # 최신 발굴 데이터 로드
        try:
            from collect.tiktok_discovery import load_latest
            discovery = load_latest()
        except Exception:
            discovery = None

        if not discovery:
            st.info("📭 아직 발굴 데이터가 없습니다. 터미널에서 먼저 실행하세요:")
            st.code("python3 collect/run_collector.py --discovery", language="bash")
            st.stop()
            return

        disc_date = discovery.get("date", "")
        flagged   = discovery.get("flagged", [])
        top_all   = discovery.get("top_overall", [])

        # 메타 KPI
        col1, col2, col3 = st.columns(3)
        col1.metric("분석 해시태그", f"{discovery.get('total_hashtags_checked', 0):,}개")
        col2.metric("조회수 수집 성공", f"{discovery.get('views_collected', 0):,}개")
        col3.metric("신규 성분 후보", f"{discovery.get('new_candidates', 0)}개", help="YAML 미등록 + 100만 뷰 이상 + Gemini 성분 확인")
        st.caption(f"데이터 기준: {disc_date}")

        st.divider()

        # ── 신규 발굴 성분 카드 ──────────────────────────────────────
        if flagged:
            st.markdown("#### 🚨 신규 발굴 성분 (YAML 미등록)")
            st.caption("growth_rate = 직전 스냅샷 대비 주간 조회수 증가율")

            for item in flagged[:10]:
                growth_pct  = item.get("growth_rate", 0) * 100
                views_m     = item.get("views", 0) / 1_000_000
                confidence  = item.get("confidence", "low")
                conf_color  = {"high": "#4fc3f7", "medium": "#ffb74d", "low": "#888"}.get(confidence, "#888")
                conf_label  = {"high": "높음", "medium": "보통", "low": "낮음"}.get(confidence, "낮음")

                with st.expander(
                    f"#{item['hashtag']}  ·  {item.get('ingredient_name_kr') or item.get('ingredient_name_en', '')}  "
                    f"·  {views_m:.1f}M views  ·  주간 +{growth_pct:.1f}%",
                    expanded=False,
                ):
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.markdown(f"**성분명 (EN):** {item.get('ingredient_name_en', 'N/A')}")
                        st.markdown(f"**카테고리:** {item.get('category', 'N/A')}")
                        st.markdown(f"**누적 조회수:** {item['views']:,} views ({views_m:.1f}M)")
                        st.markdown(f"**주간 증가:** +{growth_pct:.1f}%  ·  +{item.get('weekly_delta', 0):,} views")
                    with c2:
                        st.markdown(
                            f"<div style='text-align:center;padding:12px;background:#1a1a1a;"
                            f"border-radius:8px;border:1px solid {conf_color}'>"
                            f"<div style='font-size:0.75rem;color:#888'>Gemini 신뢰도</div>"
                            f"<div style='font-size:1.3rem;font-weight:700;color:{conf_color}'>{conf_label}</div>"
                            f"</div>", unsafe_allow_html=True
                        )
                    st.markdown("---")
                    st.markdown("**YAML 추가 코드 (복사 후 ingredients.yaml에 붙여넣기)**")
                    yaml_snippet = (
                        f"  - id: {item['hashtag'].lower().replace(' ', '_')}\n"
                        f"    name_kr: {item.get('ingredient_name_kr') or item.get('ingredient_name_en', '')}\n"
                        f"    name_en: {item.get('ingredient_name_en', item['hashtag'])}\n"
                        f"    status: watching\n"
                        f"    category: {item.get('category', '기타')}\n"
                        f"    tiktok_hashtags: [\"{item['hashtag']}\"]\n"
                        f"    added_date: \"{disc_date}\"\n"
                        f"    notes: \"TikTok 자동 발굴. {views_m:.1f}M views, 주간 +{growth_pct:.1f}%\""
                    )
                    st.code(yaml_snippet, language="yaml")
        else:
            st.success("✅ 이번 주는 새로 발굴된 성분 없음 (기존 YAML 성분이 상위를 차지 중)")

        st.divider()

        # ── 전체 Top 10 (YAML 포함) ──────────────────────────────────
        if top_all:
            st.markdown("#### 📊 이번 주 TikTok 뷰티 해시태그 Top 10 (전체)")
            st.caption("기존 등록 성분 포함 — 조회수 성장률 기준 정렬")
            rows = []
            for i, item in enumerate(top_all[:10], 1):
                rows.append({
                    "순위": i,
                    "해시태그": f"#{item['hashtag']}",
                    "조회수": f"{item['views']/1_000_000:.1f}M",
                    "주간 증가율": f"+{item['growth_rate']*100:.1f}%",
                    "주간 증가 조회수": f"+{item['weekly_delta']:,}",
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.caption(
            "💡 **활용법:** 신규 발굴 성분 중 confidence=높음인 항목을 우선 검토 → "
            "YAML에 추가 → 다음 R&D 파이프라인 실행 시 자동으로 PubMed 논문 수집 시작"
        )


# ─────────────────────────────────────────────────────────────────
# 섹션 A: APLB 마케팅 클레임 빌더
# ─────────────────────────────────────────────────────────────────
def view_aplb_marketing_claims():
    st.title("✨ APLB 마케팅 클레임 빌더")
    st.caption(
        "보유 성분/컴플렉스 → PubMed 임상 근거 → 마케팅팀 사용 가능한 클레임 카드. "
        "한국 광고법 + FDA cosmetic claim 가이드 위반 위험 표현 회피."
    )

    APLB_YAML = Path(__file__).parent / "config" / "aplb_products.yaml"
    CLAIMS_DIR = Path(__file__).parent / "data" / "aplb_claims"
    RESEARCH_DIR = Path(__file__).parent / "data" / "aplb_research"

    if not APLB_YAML.exists():
        st.error("config/aplb_products.yaml 파일이 없습니다.")
        return

    aplb = yaml.safe_load(APLB_YAML.read_text(encoding="utf-8"))
    all_complexes = aplb.get("complexes", []) + aplb.get("single_actives", [])

    # ── 상단 KPI ──────────────────────────────────────────────────
    n_complexes = len(all_complexes)
    n_with_research = sum(1 for c in all_complexes if (RESEARCH_DIR / c["id"]).exists())
    n_with_claims = sum(1 for c in all_complexes if (CLAIMS_DIR / f"{c['id']}_claims.json").exists())

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("등록 컴플렉스", n_complexes)
    k2.metric("논문 검색 완료", n_with_research, f"{n_with_research}/{n_complexes}")
    k3.metric("클레임 생성", n_with_claims, f"{n_with_claims}/{n_complexes}")
    k4.metric("APLB 제품 SKU", len(aplb.get("products", [])))

    st.divider()

    # ── 컴플렉스 선택 (Executive Brief에서 jump 시 자동 선택) ────
    cx_options = {f"{c.get('trade_mark') or c.get('name_kr')} ({c['id']})": c for c in all_complexes}
    cx_keys = list(cx_options.keys())

    # PASS 받은 컴플렉스 우선 정렬 + Executive Brief 점프 처리
    pass_complexes = []
    try:
        qc_files = sorted(CLAIMS_DIR.glob("_qc_report_*.json"), reverse=True)
        if qc_files:
            qc = json.loads(qc_files[0].read_text(encoding="utf-8"))
            pass_complexes = [r["complex_id"] for r in qc if "PASS" in r.get("grade", "")]
    except Exception:
        pass

    # 정렬: PASS 우선 → 나머지
    sorted_keys = sorted(cx_keys, key=lambda k: (
        0 if cx_options[k]["id"] in pass_complexes else 1
    ))

    # Deep-link: Executive Brief에서 점프해 온 경우 해당 컴플렉스 자동 선택
    default_idx = 0
    jump_target = st.session_state.pop("jump_to_complex", None)
    if jump_target:
        for idx, k in enumerate(sorted_keys):
            if cx_options[k]["id"] == jump_target:
                default_idx = idx
                break

    # PASS 받은 항목에 ✅ 배지 표시
    def _label(k):
        cid = cx_options[k]["id"]
        return f"✅ {k}" if cid in pass_complexes else k
    display_keys = [_label(k) for k in sorted_keys]

    if pass_complexes:
        st.success(f"🎯 글로벌 출시 검토 가능한 PASS 컴플렉스 **{len(pass_complexes)}개** — 아래 ✅ 표시 항목")

    selected_display = st.selectbox("컴플렉스 선택", display_keys, index=default_idx)
    # 표시용 라벨에서 원본 키 복원
    cx_label = sorted_keys[display_keys.index(selected_display)]
    cx = cx_options[cx_label]
    cx_id = cx["id"]

    # ── Tab 구성 ──────────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["📝 클레임 카드", "📚 임상 근거 (PubMed)", "🔧 데이터 갱신"])

    # ── Tab 1: 클레임 카드 ────────────────────────────────────────
    with tab1:
        claim_file = CLAIMS_DIR / f"{cx_id}_claims.json"
        if not claim_file.exists():
            st.warning(
                f"이 컴플렉스의 클레임 카드가 아직 없습니다.\n\n"
                f"`python collect/aplb_claim_builder.py --complex {cx_id}` 실행 필요."
            )
        else:
            data = json.loads(claim_file.read_text(encoding="utf-8"))
            c = data["claims"]

            # QC 등급 배지 (실시간 검증)
            try:
                import sys as _sys
                _sys.path.append(os.path.dirname(os.path.abspath(__file__)))
                from collect.aplb_claim_qc import qc_one
                qc = qc_one(claim_file)
                qc_color = {"🟢": "#10b981", "🟡": "#f59e0b", "🟠": "#fb923c", "🔴": "#ef4444"}
                emoji = qc["grade"][0] if qc["grade"] else "🔵"
                qc_box_color = qc_color.get(emoji, "#666")
                st.markdown(f"""
                <div style="background:#fff;padding:10px 14px;border-radius:8px;
                     border-left:4px solid {qc_box_color};margin-bottom:14px;
                     display:flex;justify-content:space-between;align-items:center">
                  <div>
                    <span style="font-weight:700">QC: {qc['grade']}</span>
                    <span style="color:#666;margin-left:14px;font-size:0.85rem">
                      PMID 유효성 <b>{qc['pmid_validity_pct']}%</b> ·
                      완성도 <b>{qc['completeness_pct']}%</b> ·
                      위반 <b>{len(qc['violations'])}</b>건
                    </span>
                  </div>
                </div>
                """, unsafe_allow_html=True)
                if qc["violations"]:
                    with st.expander(f"⚠️ 위반 표현 {len(qc['violations'])}건 — 수정 필요"):
                        for v in qc["violations"]:
                            st.warning(v)
                if qc["hallucinated_pmids"]:
                    st.error(f"🔴 환각 PMID 검출: {', '.join(qc['hallucinated_pmids'])} — 재생성 필요")
            except Exception as e:
                st.caption(f"(QC 모듈 로드 실패: {e})")

            # Hero (영/한 병기)
            h = c.get("hero_claim", {})
            tier = h.get("tier", "")
            tier_badge = {"strong":"🟢", "moderate":"🟡", "weak":"🔴"}.get(tier, "")
            # 신/구 스키마 호환
            head_en = h.get("headline_en") or h.get("headline", "")
            head_kr = h.get("headline_kr", "")
            sub_en  = h.get("subheadline_en") or h.get("subheadline", "")
            sub_kr  = h.get("subheadline_kr", "")
            sci_en  = h.get("scientific_basis_en") or h.get("scientific_basis", "")
            sci_kr  = h.get("scientific_basis_kr", "")

            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#fff8e1 0%,#fff3cd 100%);
                 padding:24px;border-radius:14px;border-left:6px solid #f59e0b;margin-bottom:16px">
              <div style="font-size:0.8rem;color:#888;letter-spacing:0.05em;
                   text-transform:uppercase">HERO CLAIM {tier_badge} {tier.upper()}</div>
              <div style="font-size:1.4rem;font-weight:700;color:#222;line-height:1.4;margin-top:8px">
                🇺🇸 {head_en}
              </div>
              {f'<div style="font-size:1.2rem;font-weight:700;color:#444;line-height:1.4;margin-top:6px">🇰🇷 {head_kr}</div>' if head_kr else ''}
              <div style="font-size:0.95rem;color:#555;margin-top:10px">
                {sub_en}{f'<br/><span style="color:#666">{sub_kr}</span>' if sub_kr else ''}
              </div>
              <div style="font-size:0.85rem;color:#666;margin-top:12px;font-style:italic;line-height:1.5">
                💡 {sci_en}
                {f'<br/>💡 {sci_kr}' if sci_kr else ''}
              </div>
            </div>
            """, unsafe_allow_html=True)

            # 세계 최초 기회 (병기)
            wf_en = c.get("world_first_opportunity_en") or c.get("world_first_opportunity")
            wf_kr = c.get("world_first_opportunity_kr")
            if wf_en or wf_kr:
                msg = ""
                if wf_en: msg += f"🇺🇸 {wf_en}"
                if wf_kr: msg += (f"  \n🇰🇷 {wf_kr}" if msg else f"🇰🇷 {wf_kr}")
                if msg: st.success(f"🏆 **세계 최초 기회**\n\n{msg}")

            col1, col2 = st.columns([3, 2])

            # RTB (영/한 병기)
            with col1:
                st.markdown("### 🎯 Reason-to-Believe")
                for rtb in c.get("rtb_points", []):
                    pt_en = rtb.get("point_en") or rtb.get("point", "")
                    pt_kr = rtb.get("point_kr", "")
                    st.markdown(f"""
                    <div style="background:#f8f9fa;padding:12px 16px;border-left:3px solid #4fc3f7;
                         margin-bottom:8px;border-radius:0 8px 8px 0">
                      <div style="color:#222;font-weight:500;line-height:1.5">
                        🇺🇸 {pt_en}
                        {f'<br/>🇰🇷 <span style="color:#444">{pt_kr}</span>' if pt_kr else ''}
                      </div>
                      <div style="color:#777;font-size:0.78rem;margin-top:6px">
                        근거: {rtb.get('evidence','')}
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

                # Tech story (병기)
                t = c.get("tech_story", {})
                t_head_en = t.get("headline_en") or t.get("headline", "")
                t_head_kr = t.get("headline_kr", "")
                if t_head_en or t_head_kr:
                    st.markdown("### ⚙️ Tech Story")
                    if t_head_en: st.markdown(f"**🇺🇸 {t_head_en}**")
                    if t_head_kr: st.markdown(f"**🇰🇷 {t_head_kr}**")
                    facts_en = t.get("supporting_facts_en") or t.get("supporting_facts", [])
                    facts_kr = t.get("supporting_facts_kr", [])
                    for i, s in enumerate(facts_en):
                        kr = facts_kr[i] if i < len(facts_kr) else ""
                        st.markdown(f"- 🇺🇸 {s}" + (f"  \n  🇰🇷 {kr}" if kr else ""))

            # 회피 클레임 + 북미 어필 (병기)
            with col2:
                st.markdown("### ⚠️ 회피 클레임")
                risky_en = c.get("risky_claims_to_avoid_en") or c.get("risky_claims_to_avoid", [])
                risky_kr = c.get("risky_claims_to_avoid_kr", [])
                for i, r in enumerate(risky_en):
                    kr = risky_kr[i] if i < len(risky_kr) else ""
                    st.markdown(
                        f"<div style='color:#c00;font-size:0.85rem;line-height:1.5'>✗ 🇺🇸 {r}"
                        + (f"<br/>✗ 🇰🇷 {kr}" if kr else "")
                        + "</div>",
                        unsafe_allow_html=True,
                    )
                # 국문만 있는 추가 항목
                for kr in risky_kr[len(risky_en):]:
                    st.markdown(f"<div style='color:#c00;font-size:0.85rem'>✗ 🇰🇷 {kr}</div>",
                                unsafe_allow_html=True)

                na_en = c.get("north_america_angle_en") or c.get("north_america_angle")
                na_kr = c.get("north_america_angle_kr")
                if na_en or na_kr:
                    st.markdown("### 🇺🇸 북미 시장 어필")
                    if na_en: st.info(f"🇺🇸 {na_en}")
                    if na_kr: st.info(f"🇰🇷 {na_kr}")

            # 인용 가능 논문 (활용 영/한 병기)
            st.markdown("### 📄 인용 가능 논문 (마케팅 자료에 출처 표기)")
            papers = c.get("citation_ready_papers", [])
            if papers:
                df_papers = pd.DataFrame([
                    {
                        "PMID": p.get("pmid", ""),
                        "연도": p.get("year", ""),
                        "제목": (p.get("title") or "")[:90],
                        "🇺🇸 활용": p.get("use_case_en") or p.get("use_case", ""),
                        "🇰🇷 활용": p.get("use_case_kr", ""),
                        "링크": f"https://pubmed.ncbi.nlm.nih.gov/{p.get('pmid','')}/" if p.get("pmid") else "",
                    } for p in papers
                ])
                st.dataframe(df_papers, use_container_width=True, hide_index=True,
                             column_config={"링크": st.column_config.LinkColumn("PubMed")})
            else:
                st.caption("(인용 논문 없음)")

            # JSON 다운로드
            st.download_button(
                "📥 클레임 JSON 다운로드 (마케팅팀 전달용)",
                data=json.dumps(data, ensure_ascii=False, indent=2),
                file_name=f"{cx_id}_claims_{date.today().isoformat()}.json",
                mime="application/json",
            )
            st.caption(f"생성 시각: {data.get('generated_at','')}")

    # ── Tab 2: 임상 근거 ──────────────────────────────────────────
    with tab2:
        cx_dir = RESEARCH_DIR / cx_id
        if not cx_dir.exists():
            st.warning(f"이 컴플렉스의 PubMed 검색 결과가 없습니다.\n\n"
                       f"`python collect/aplb_pair_search.py --complex {cx_id}` 실행 필요.")
        else:
            files = sorted(cx_dir.glob("*.json"))
            pair_results, trio_results = [], []
            for f in files:
                d = json.loads(f.read_text(encoding="utf-8"))
                if f.name.startswith("TRIO_"):
                    trio_results.append(d)
                else:
                    pair_results.append(d)

            # 페어 시너지 표
            st.markdown("### 🔗 페어 시너지 (논문수 정렬)")
            pair_results.sort(key=lambda x: -x["paper_count"])
            df_pairs = pd.DataFrame([
                {
                    "성분 A": p["ingredient_a"],
                    "성분 B": p["ingredient_b"],
                    "논문수": p["paper_count"],
                    "신호": "🟢 강함" if p["paper_count"] >= 5
                            else ("🟡 약간" if p["paper_count"] >= 1 else "🔴 없음"),
                } for p in pair_results
            ])
            st.dataframe(df_pairs, use_container_width=True, hide_index=True)

            # 트리오
            if trio_results:
                st.markdown("### 🔺 트리오 시너지")
                df_trios = pd.DataFrame([
                    {
                        "성분": " × ".join(t["ingredients"]),
                        "논문수": t["paper_count"],
                        "기회": "🏆 세계 최초 가능" if t["paper_count"] == 0 else "📚 기존 근거 있음",
                    } for t in trio_results
                ])
                st.dataframe(df_trios, use_container_width=True, hide_index=True)

            # 페어 상세 보기
            st.markdown("### 📚 논문 초록 보기")
            pair_label = st.selectbox(
                "페어 선택",
                [f"{p['ingredient_a']} × {p['ingredient_b']} ({p['paper_count']}건)"
                 for p in pair_results if p["paper_count"] > 0],
                key="pair_select",
            )
            if pair_label:
                idx = [f"{p['ingredient_a']} × {p['ingredient_b']} ({p['paper_count']}건)"
                       for p in pair_results].index(pair_label)
                selected = pair_results[idx]
                for art in selected["articles"][:5]:
                    title = art.get("title") or "(제목 없음)"
                    pmid = art.get("pmid", "")
                    year = art.get("year", "")
                    journal = art.get("journal", "")
                    abstract = (art.get("abstract") or "")[:1000]
                    with st.expander(f"[{year}] {title[:90]}"):
                        st.caption(f"📓 {journal} | PMID: {pmid} | "
                                   f"[PubMed 링크](https://pubmed.ncbi.nlm.nih.gov/{pmid}/)")
                        st.write(abstract or "(초록 없음)")

    # ── Tab 3: 데이터 갱신 ────────────────────────────────────────
    with tab3:
        st.markdown("### 🔄 데이터 갱신 명령어")
        st.code(f"""# 1. PubMed 논문 재검색 (페어 + 트리오)
python collect/aplb_pair_search.py --complex {cx_id}

# 2. Gemini 클레임 카드 재생성
python collect/aplb_claim_builder.py --complex {cx_id}

# 전체 컴플렉스 일괄 처리
python collect/aplb_pair_search.py
python collect/aplb_claim_builder.py
""", language="bash")
        st.info("💡 Gemini 무료 한도(1,500/일) 초과 시 다음 날 자동 재시도. "
                "트리오 0건은 '세계 최초' 마케팅 신호로 자동 검출됩니다.")


# ─────────────────────────────────────────────────────────────────
# 섹션 B: 신성분 발굴 (3-Tier Funnel)
# ─────────────────────────────────────────────────────────────────
def view_emerging_ingredients():
    st.title("🔭 신성분 발굴 (3-Tier Funnel)")
    st.caption(
        "Medical/Aesthetic → Skinceutical/Dermocosmetic → Mass Cosmetic 흐름 추적. "
        "T1·T2 출판 시그널 + V-Index 가속도로 6~24개월 후 뜰 성분 예측."
    )

    EMERGING_DIR = Path(__file__).parent / "data" / "emerging_signals"
    APLB_YAML = Path(__file__).parent / "config" / "aplb_products.yaml"
    latest_file = EMERGING_DIR / "latest.json"

    if not latest_file.exists():
        st.warning(
            "아직 시그널 데이터가 없습니다.\n\n"
            "터미널에서 실행: `python collect/emerging_ingredients.py --pubmed`"
        )
        return

    data = json.loads(latest_file.read_text(encoding="utf-8"))
    signals = [s for s in data["signals"] if s["total_papers"] > 0]

    # ── 가이드 expander ────────────────────────────────────────────
    with st.expander("📖 이 페이지를 어떻게 읽나요?", expanded=False):
        st.markdown("""
        **3-Tier Funnel 가설**: 신성분은 Medical → Skinceutical → Mass 순으로 흐릅니다.

        | Tier | 무엇 | 예시 저널 | 성분 진입 시그널 |
        |---|---|---|---|
        | **T1 Medical/Aesthetic** | 시술·외과·처방 의약 | JAAD, Aesthet Surg J, Lasers Surg Med | 가장 빠른 진입 (T+12~24mo 후 매스) |
        | **T2 Skinceutical/Dermocosmetic** | 더마코스메틱 (Skinceuticals/La Roche-Posay 류) | J Cosmet Dermatol, Skin Pharmacol Physiol | 매스 진입 직전 (T+6~12mo) |
        | **T3 Mass Cosmetic** | 일반 매스 화장품 | Cosmetics journal, J Cosmet Sci | 이미 시장에 있음 |

        **시그널 점수 = T1 + T2×1.5 - T3×0.5 + 최근논문 가중 + 임상시험 가중**

        | 라벨 | 의미 |
        |---|---|
        | 🔥 임박 (T+6mo) | T2 강하게 등장 + 매스 미진입 — 신제품 컨셉 즉시 검토 |
        | 🟡 등장 중 (T+12mo) | T1→T2 전환 중 — 12개월 내 진입 |
        | 🟢 잠재 (T+24mo) | T1 임상시험 활성 — 모니터링 |

        **데이터 갱신**: `python collect/emerging_ingredients.py --pubmed`
        """)

    # ── KPI 상단 ───────────────────────────────────────────────────
    n_imminent = sum(1 for s in signals if "임박" in s["signal_label"])
    n_emerging = sum(1 for s in signals if "등장" in s["signal_label"])
    n_nascent  = sum(1 for s in signals if "잠재" in s["signal_label"])

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🔥 임박 (T+6mo)", n_imminent)
    k2.metric("🟡 등장 중 (T+12mo)", n_emerging)
    k3.metric("🟢 잠재 (T+24mo)", n_nascent)
    k4.metric("총 추적 성분", len(signals))

    st.caption(f"📅 마지막 분석: {data.get('generated_at','')[:19]}")
    st.divider()

    # ── 탭 구성 ────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🔥 임박 신호 TOP",
        "📊 3-Tier Funnel 매트릭스",
        "🆕 APLB 신복합 아이디어",
        "🤖 Gemini 신제품 컨셉",
        "🧬 ClinicalTrials.gov",
        "🔍 성분별 상세"
    ])

    # ── Tab 1: 임박 신호 ─────────────────────────────────────────
    with tab1:
        st.markdown("### 🔥 우선순위 — 신제품 검토 후보")
        top = signals[:20]
        df_top = pd.DataFrame([
            {
                "순위": i + 1,
                "성분": s["name_kr"],
                "영문명": s["name_en"],
                "시그널": s["signal_label"],
                "T1": s["tier_dist"]["T1"],
                "T2": s["tier_dist"]["T2"],
                "T3": s["tier_dist"]["T3"],
                "임상": s["clinical_trials"],
                "최근(2024+)": s["recent_papers"],
                "점수": s["signal_score"],
                "카테고리": s.get("category", ""),
            } for i, s in enumerate(top)
        ])
        st.dataframe(df_top, use_container_width=True, hide_index=True,
                     column_config={
                         "점수": st.column_config.ProgressColumn(
                             "점수", min_value=0, max_value=40, format="%.1f"
                         ),
                     })

        st.markdown("### 🥇 TOP 5 상세 (인용 가능 논문)")
        for s in top[:5]:
            with st.expander(f"{s['signal_label']}  **{s['name_kr']}** ({s['name_en']}) — score {s['signal_score']}"):
                c1, c2 = st.columns(2)
                c1.metric("T1 의료·시술", s["tier_dist"]["T1"])
                c2.metric("T2 더마코스메틱", s["tier_dist"]["T2"])
                if s["top_t1_papers"]:
                    st.markdown("**🏥 T1 (Medical/Aesthetic)**")
                    for p in s["top_t1_papers"]:
                        st.markdown(
                            f"- [{p['year']}] {p['title']} "
                            f"_{p['journal']}_ [PMID:{p['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{p['pmid']}/)"
                        )
                if s["top_t2_papers"]:
                    st.markdown("**🧪 T2 (Skinceutical/Dermocosmetic)**")
                    for p in s["top_t2_papers"]:
                        st.markdown(
                            f"- [{p['year']}] {p['title']} "
                            f"_{p['journal']}_ [PMID:{p['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{p['pmid']}/)"
                        )

    # ── Tab 2: 3-Tier Funnel 매트릭스 (Plotly scatter) ────────────
    with tab2:
        st.markdown("### 📊 3-Tier Funnel — T1 vs T2 분포")
        st.caption("우상단 = T1·T2 모두 강함 (가장 임박). 좌하단 = 아직 약함.")

        df_scatter = pd.DataFrame([
            {
                "이름": s["name_kr"],
                "T1": s["tier_dist"]["T1"],
                "T2": s["tier_dist"]["T2"],
                "T3": s["tier_dist"]["T3"],
                "점수": s["signal_score"],
                "라벨": s["signal_label"],
                "총논문": s["total_papers"],
            } for s in signals if s["total_papers"] >= 3
        ])
        if not df_scatter.empty:
            fig = px.scatter(
                df_scatter, x="T1", y="T2", size="총논문", color="점수",
                hover_data=["이름", "라벨", "T3"], text="이름",
                color_continuous_scale="RdYlGn_r",
                size_max=40,
                labels={"T1": "T1 Medical/Aesthetic 논문", "T2": "T2 Dermocosmetic 논문"},
            )
            fig.update_traces(textposition="top center", textfont_size=10)
            fig.add_shape(type="line", x0=0, y0=0, x1=10, y1=10,
                          line=dict(color="gray", dash="dash"), opacity=0.5)
            fig.update_layout(height=550, plot_bgcolor="#fafafa")
            st.plotly_chart(fig, use_container_width=True)

        # 카테고리별 분포
        st.markdown("### 📈 카테고리별 시그널 분포")
        cat_df = pd.DataFrame([
            {"카테고리": s.get("category", "기타") or "기타",
             "라벨": s["signal_label"][:6], "점수": s["signal_score"]}
            for s in signals
        ])
        if not cat_df.empty:
            fig2 = px.box(cat_df, x="카테고리", y="점수", color="라벨",
                          height=380)
            st.plotly_chart(fig2, use_container_width=True)

    # ── Tab 3: APLB 신복합 아이디어 ────────────────────────────────
    with tab3:
        st.markdown("### 🆕 APLB 신복합 컨셉 후보")
        st.caption(
            "임박 신호 신성분 × APLB 보유 성분 = 신제품 페어. "
            "같은 데이터로 **APLB 마케팅 클레임** 페이지의 candidate_ingredients 결과 활용."
        )

        # APLB 보유 성분 추출
        aplb = yaml.safe_load(APLB_YAML.read_text(encoding="utf-8")) if APLB_YAML.exists() else {}
        aplb_owned = set()
        for cx in aplb.get("complexes", []) + aplb.get("single_actives", []):
            for ing in cx.get("primary_ingredients", []):
                aplb_owned.add(ing)

        st.markdown(f"**APLB 보유 핵심 성분**: `{', '.join(sorted(aplb_owned))}`")

        # 임박 신호 + APLB 미보유 성분 = 신복합 후보
        new_candidates = []
        for s in signals[:20]:
            ing_en_lower = s["name_en"].lower()
            ing_id_lower = (s["ingredient_id"] or "").lower()
            if "임박" not in s["signal_label"]:
                continue
            owned_match = any(
                o.lower() in ing_en_lower or o.lower() == ing_id_lower
                for o in aplb_owned
            )
            if not owned_match:
                new_candidates.append(s)

        st.markdown(f"#### 🎯 APLB 미보유 임박 신호 — **{len(new_candidates)}개**")
        for s in new_candidates[:10]:
            color = "#fef3c7" if "🔥" in s["signal_label"] else "#fef9c3"
            border = "#f59e0b" if "🔥" in s["signal_label"] else "#facc15"
            st.markdown(f"""
            <div style="background:{color};padding:14px 18px;border-radius:10px;
                 border-left:5px solid {border};margin-bottom:10px">
              <div style="font-size:1.1rem;font-weight:700;color:#222">
                {s['signal_label']} {s['name_kr']} ({s['name_en']})
              </div>
              <div style="font-size:0.85rem;color:#555;margin-top:6px">
                T1 의료: <b>{s['tier_dist']['T1']}</b>건 ·
                T2 더마: <b>{s['tier_dist']['T2']}</b>건 ·
                최근(2024+) <b>{s['recent_papers']}</b>건 ·
                점수 <b>{s['signal_score']}</b>
              </div>
              <div style="font-size:0.8rem;color:#666;margin-top:6px">
                💡 신제품 페어 후보: APLB 보유 성분과 시너지 검증 필요
                ({', '.join(sorted(aplb_owned)[:5])} 등)
              </div>
            </div>
            """, unsafe_allow_html=True)

        st.divider()
        st.info(
            "💡 **다음 액션**: 위 성분 중 우선순위가 높은 1~2개를 `aplb_products.yaml`의 "
            "`candidate_ingredients`에 추가하고 `python collect/aplb_pair_search.py --complex <id>` 실행 → "
            "**APLB 마케팅 클레임** 페이지에 시너지 분석 + 클레임 카드 자동 생성."
        )

    # ── Tab 4: Gemini 신제품 컨셉 ────────────────────────────────
    with tab4:
        CONCEPTS_LATEST = Path(__file__).parent / "data" / "aplb_concepts" / "latest.json"
        if not CONCEPTS_LATEST.exists():
            st.warning(
                "신제품 컨셉이 아직 없습니다.\n\n"
                "터미널에서: `python collect/aplb_concept_generator.py`"
            )
        else:
            cd = json.loads(CONCEPTS_LATEST.read_text(encoding="utf-8"))
            concepts = cd.get("concepts", [])
            st.caption(f"📅 생성: {cd.get('generated_at','')[:19]} · 총 {len(concepts)}개 컨셉")

            for c in concepts:
                wf = c.get("world_first_aspect")
                wf_badge = "<span style='background:#dc2626;color:#fff;padding:2px 10px;border-radius:10px;font-size:0.7rem'>🏆 세계 최초</span>" if wf else ""
                rr = c.get("regulatory_risk", "low")
                rr_color = {"low": "#10b981", "medium": "#f59e0b", "high": "#dc2626"}.get(rr, "#666")

                st.markdown(f"""
                <div style="background:#fff;border:2px solid #e5e7eb;border-radius:12px;
                     padding:18px 22px;margin-bottom:14px">
                  <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:8px">
                    <div>
                      <div style="font-size:0.7rem;color:#888;text-transform:uppercase">#{c.get('rank','?')} {c.get('category','')}</div>
                      <div style="font-size:1.3rem;font-weight:800;color:#111">
                        {c.get('product_name_kr', '')}
                      </div>
                      <div style="font-size:0.85rem;color:#666;margin-top:2px">
                        {c.get('product_name_en','')} · 상표: <b>{c.get('complex_trademark','')}</b>
                      </div>
                    </div>
                    <div style="display:flex;gap:6px">{wf_badge}
                      <span style="background:{rr_color};color:#fff;padding:2px 10px;border-radius:10px;font-size:0.7rem">
                        규제 {rr}
                      </span>
                    </div>
                  </div>
                  <div style="background:#f0f9ff;border-left:3px solid #4fc3f7;padding:10px 14px;
                       border-radius:0 8px 8px 0;margin:10px 0">
                    <div style="font-size:0.75rem;color:#666">CORE CLAIM</div>
                    <div style="font-size:1rem;color:#222;font-weight:600">{c.get('core_claim','')}</div>
                  </div>
                  <div style="font-size:0.85rem;color:#444;line-height:1.6">
                    🎯 <b>타겟</b>: {c.get('target_audience','')}<br/>
                    💰 <b>가격대</b>: {c.get('price_band_kr','')} · <b>채널</b>: {c.get('channel_strategy','')}<br/>
                    🆚 <b>차별화</b>: {c.get('differentiation_vs_competitors','')}<br/>
                    {f'🏆 <b>세계 최초</b>: {wf}<br/>' if wf else ''}
                    💡 <b>예상 후기</b>: {c.get('expected_voc_appeal','')}
                  </div>
                </div>
                """, unsafe_allow_html=True)

                # 핵심 성분 표
                key_ings = c.get("key_ingredients", [])
                if key_ings:
                    df_ki = pd.DataFrame(key_ings)
                    st.dataframe(df_ki, use_container_width=True, hide_index=True)

                # 시너지 근거
                if c.get("synergy_rationale"):
                    with st.expander(f"📖 시너지 근거"):
                        st.write(c["synergy_rationale"])

                st.divider()

            st.info("💡 갱신: `python collect/aplb_concept_generator.py` (Gemini 1회 호출, 1500/일 무료 한도)")

    # ── Tab 5: ClinicalTrials.gov ─────────────────────────────────
    with tab5:
        CT_LATEST = Path(__file__).parent / "data" / "clinical_trials" / "latest.json"
        if not CT_LATEST.exists():
            st.warning(
                "ClinicalTrials.gov 데이터 없음.\n\n"
                "터미널에서: `python collect/clinical_trials.py`"
            )
        else:
            ct = json.loads(CT_LATEST.read_text(encoding="utf-8"))
            ct_summary = ct.get("summary", [])

            n_active = sum(s["active_count"] for s in ct_summary)
            n_recent = sum(s["recent_complete_count"] for s in ct_summary)
            n_with = sum(1 for s in ct_summary if s["active_count"] > 0)

            k1, k2, k3 = st.columns(3)
            k1.metric("활성 임상시험 총합", n_active)
            k2.metric("2025-2028 완료예정", n_recent, "T1 미래 시그널")
            k3.metric("임상 활동 성분 수", n_with)
            st.caption(f"📅 갱신: {ct.get('generated_at','')[:19]}")

            st.markdown("### 🔥 활성 임상 TOP — T1 미래 시그널")
            df_ct = pd.DataFrame([
                {
                    "성분": s["name_kr"],
                    "영문": s["name_en"],
                    "활성 임상": s["active_count"],
                    "2025-28 완료": s["recent_complete_count"],
                    "시그널 점수": s["future_signal_score"],
                } for s in ct_summary[:25] if s["active_count"] > 0
            ])
            if not df_ct.empty:
                st.dataframe(df_ct, use_container_width=True, hide_index=True,
                             column_config={
                                 "시그널 점수": st.column_config.ProgressColumn(
                                     "시그널", min_value=0, max_value=80, format="%d"
                                 ),
                             })

            # 상위 5개 상세
            st.markdown("### 🥇 TOP 5 임상시험 상세")
            for s in ct_summary[:5]:
                if s["active_count"] == 0:
                    continue
                with st.expander(
                    f"{s['name_kr']} ({s['name_en']}) — 활성 {s['active_count']}건, "
                    f"미래 시그널 {s['future_signal_score']}"
                ):
                    for t in s["top_trials"]:
                        phase = " / ".join(t.get("phases") or []) or "—"
                        st.markdown(f"""
                        - **[{phase}]** {t['title']}
                          📍 {t.get('sponsor','')} · 상태: {t.get('status','')} · 완료예정: {t.get('completion','')}
                          🔗 [{t.get('nct_id','')}]({t.get('url','')})
                        """)

    # ── Tab 6: 성분별 상세 ────────────────────────────────────────
    with tab6:
        st.markdown("### 🔍 성분별 상세 시그널")
        ing_options = {f"{s['name_kr']} ({s['name_en']})": s for s in signals}
        ing_label = st.selectbox("성분 선택", list(ing_options.keys()))
        s = ing_options[ing_label]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("시그널", s["signal_label"])
        c2.metric("점수", s["signal_score"])
        c3.metric("총 논문", s["total_papers"])
        c4.metric("임상시험", s["clinical_trials"])

        # Tier 분포 차트
        d = s["tier_dist"]
        df_tier = pd.DataFrame([
            {"Tier": "T1 Medical/Aesthetic", "논문": d["T1"]},
            {"Tier": "T2 Dermocosmetic", "논문": d["T2"]},
            {"Tier": "T3 Mass Cosmetic", "논문": d["T3"]},
            {"Tier": "Unknown", "논문": d["unknown"]},
        ])
        fig = px.bar(df_tier, x="Tier", y="논문", color="논문",
                     color_continuous_scale="Blues", height=280)
        st.plotly_chart(fig, use_container_width=True)

        # 논문 리스트
        if s["top_t1_papers"]:
            st.markdown("#### 🏥 T1 논문")
            for p in s["top_t1_papers"]:
                st.markdown(
                    f"- **[{p['year']}]** {p['title']} _{p['journal']}_ "
                    f"[PMID:{p['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{p['pmid']}/)"
                )
        if s["top_t2_papers"]:
            st.markdown("#### 🧪 T2 논문")
            for p in s["top_t2_papers"]:
                st.markdown(
                    f"- **[{p['year']}]** {p['title']} _{p['journal']}_ "
                    f"[PMID:{p['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{p['pmid']}/)"
                )


# ─────────────────────────────────────────────────────────────────
# 🏪 시장 경쟁 진단 (Commercial Landscape) — 학술 × 상업 매트릭스
# ─────────────────────────────────────────────────────────────────
def view_commercial_landscape():
    st.title("🏪 시장 경쟁 진단 — Commercial Tier")
    st.caption(
        "학술 시그널과 별개로 '이미 브랜드가 점유했는가' 추적. "
        "학술×상업 6-구역 매트릭스로 APLB 전략 포지션 자동 분류."
    )

    LANDSCAPE_LATEST = Path(__file__).parent / "data" / "commercial_landscape" / "latest.json"
    if not LANDSCAPE_LATEST.exists():
        st.warning(
            "상업 분석 데이터 없음.\n\n"
            "터미널에서: `python collect/commercial_landscape.py --top 25`"
        )
        return

    data = json.loads(LANDSCAPE_LATEST.read_text(encoding="utf-8"))
    results = list(data.get("results", {}).values())

    with st.expander("📖 상업 티어(C0~C3) + APLB 전략 포지션", expanded=False):
        st.markdown("""
        ### 상업 티어
        | 티어 | 의미 | APLB 의미 |
        |---|---|---|
        | **C0** 무주공산 | 매스 시장 부재, 시술/derma만 | 선점 가장 좋음 |
        | **C1** 진입기 | 소수 브랜드, 점유 미정 | 차별화 진입 |
        | **C2** 성장기 | 3~5개 강자 형성 중 | 농도/페어/기술 차별화 필수 |
        | **C3** 포화기 | Top 1~3이 70%+ 점유 | 신규 진입 어려움 — 프리미엄/Black만 |

        ### APLB 전략 포지션 (학술 × 상업 매트릭스)
        | 포지션 | 학술 | 상업 | APLB 액션 |
        |---|---|---|---|
        | 🚀 **Pioneer** | 강 | 약 (C0/C1) | 시장 선점 — 최우선 |
        | ⚡ **Differentiator** | 강 | 중 (C2) | 차별화 (농도·페어·기술) |
        | 💎 **Late Entry Premium** | 강 | 강 (C3) | 프리미엄/Black 라인만 |
        | 👀 **Watch** | 약 | 약 | 모니터링 |
        | ⛔ **Skip** | 약 | 강 | 회피 |
        """)

    # ── KPI 상단 ───────────────────────────────────────────────
    by_tier = {"C0": 0, "C1": 0, "C2": 0, "C3": 0}
    by_posture = {}
    for r in results:
        tier = r.get("commercial_tier", "?")
        if tier in by_tier:
            by_tier[tier] += 1
        p = r.get("aplb_strategic_posture", "?")
        by_posture[p] = by_posture.get(p, 0) + 1

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🚀 Pioneer 후보", by_posture.get("Pioneer", 0))
    k2.metric("⚡ Differentiator", by_posture.get("Differentiator", 0))
    k3.metric("💎 Late Premium", by_posture.get("Late_Entry_Premium", 0))
    k4.metric("👀 Watch + ⛔ Skip", by_posture.get("Watch", 0) + by_posture.get("Skip", 0))
    st.caption(f"📅 분석: {data.get('generated_at','')[:19]} · 총 {len(results)}개")

    st.divider()

    # ── 탭 ────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "🚀 Pioneer (선점 후보)",
        "⚡ Differentiator (차별화)",
        "💎 Late Premium",
        "🗂 전체 분석"
    ])

    def _render_card(r):
        tier = r.get("commercial_tier", "?")
        posture = r.get("aplb_strategic_posture", "?")
        tier_color = {"C0":"#10b981", "C1":"#3b82f6", "C2":"#f59e0b", "C3":"#dc2626"}.get(tier, "#888")
        posture_emoji = {"Pioneer":"🚀", "Differentiator":"⚡",
                         "Late_Entry_Premium":"💎", "Watch":"👀", "Skip":"⛔"}.get(posture, "")

        st.markdown(f"""
        <div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;
             padding:14px 18px;margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div style="font-size:1.1rem;font-weight:700;color:#111">
              {posture_emoji} {r.get('id','')}
            </div>
            <div>
              <span style="background:{tier_color};color:#fff;padding:3px 10px;
                   border-radius:10px;font-size:0.75rem;font-weight:700">{tier}</span>
              <span style="color:#666;font-size:0.8rem;margin-left:8px">
                마케팅 {r.get('marketing_intensity','-')}
              </span>
            </div>
          </div>
          <div style="font-size:0.82rem;color:#666;margin-top:4px;font-style:italic">
            {r.get('tier_rationale','')}
          </div>
        </div>
        """, unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**🇰🇷 한국 Top 브랜드**")
            kr_brands = r.get("top_brands_kr", [])
            if kr_brands:
                for b in kr_brands[:5]:
                    s_emoji = {"high":"🔥", "medium":"🟡", "low":"⚪"}.get(b.get("strength","low"), "")
                    st.caption(f"{s_emoji} **{b.get('brand','?')}** — {b.get('product_example','')}")
            else:
                st.caption("(데이터 없음)")
        with c2:
            st.markdown("**🇺🇸 북미 Top 브랜드**")
            us_brands = r.get("top_brands_us", [])
            if us_brands:
                for b in us_brands[:5]:
                    s_emoji = {"high":"🔥", "medium":"🟡", "low":"⚪"}.get(b.get("strength","low"), "")
                    st.caption(f"{s_emoji} **{b.get('brand','?')}** — {b.get('product_example','')}")
            else:
                st.caption("(데이터 없음)")

        st.markdown(
            f"**🎯 시장 갭**: {r.get('market_gap','')}  \n"
            f"**🛡 가장 위협**: {r.get('key_competitor_to_beat','')}  \n"
            f"**💡 APLB 액션**: {r.get('aplb_action_kr','')}"
        )
        st.divider()

    # Pioneer
    with tab1:
        st.caption("🚀 학술 시그널 강 + 상업 시장 약 → 선점 진입 최우선")
        items = [r for r in results if r.get("aplb_strategic_posture") == "Pioneer"]
        items.sort(key=lambda r: r.get("commercial_tier", "C9"))  # C0 먼저
        for r in items:
            _render_card(r)

    # Differentiator
    with tab2:
        st.caption("⚡ 학술 강 + 상업 성장기 → 농도/페어/기술 차별화로 진입")
        items = [r for r in results if r.get("aplb_strategic_posture") == "Differentiator"]
        for r in items:
            _render_card(r)

    # Late Premium
    with tab3:
        st.caption("💎 포화 시장 — 프리미엄/Black 라인 또는 자체 기술 차별화만")
        items = [r for r in results if r.get("aplb_strategic_posture") == "Late_Entry_Premium"]
        for r in items:
            _render_card(r)

    # 전체
    with tab4:
        df = pd.DataFrame([
            {
                "성분": r.get("id"),
                "상업티어": r.get("commercial_tier"),
                "전략": r.get("aplb_strategic_posture"),
                "마케팅 강도": r.get("marketing_intensity"),
                "한국 Top1": r.get("top_brands_kr", [{}])[0].get("brand", "—") if r.get("top_brands_kr") else "—",
                "북미 Top1": r.get("top_brands_us", [{}])[0].get("brand", "—") if r.get("top_brands_us") else "—",
                "최대 위협": r.get("key_competitor_to_beat", ""),
            } for r in results
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.info(
        "💡 갱신: `python collect/commercial_landscape.py --top 30` "
        "(Gemini 1회 호출/배치 8성분, 토큰 효율적)"
    )


# ─────────────────────────────────────────────────────────────────
# X1: "왜 안 뜨는가" 진단 — 4-사분면 분석
# ─────────────────────────────────────────────────────────────────
def view_why_not_trending(ingredients: list[dict], df_raw: pd.DataFrame):
    st.title("🔬 왜 안 뜨는가? — 진단 매트릭스")
    st.caption(
        "성분 안 뜨는 이유 자동 분류 → APLB 차별 대응 전략. "
        "마케팅/키워드/경쟁/매력 4가지 가설을 데이터로 진단."
    )

    with st.expander("📖 4-사분면 진단 방법", expanded=False):
        st.markdown("""
        **2축 진단**:
        - **X축 = 학술 수요 (PubMed T1+T2 논문수)** — 의료/derma 영역에서 주목받는가
        - **Y축 = 시장 노출 (V-Index)** — 소비자 검색 가속도가 있는가

        **4-사분면 → APLB 대응 전략**:

        | 사분면 | 진단 | APLB 액션 |
        |---|---|---|
        | 🟢 **고학술 + 고시장** | 트렌드 폭발 중 | 즉시 신제품 / 신라인 |
        | 🟡 **고학술 + 저시장** | "숨은 보석" — 마케팅·교육 부재 | **콘텐츠 마케팅 선점**, 아카이빙 자산화 |
        | 🟠 **저학술 + 고시장** | 인플루언서 거품 (위험) | 관망, 자체 임상 후 진입 |
        | 🔴 **저학술 + 저시장** | 매력 부족 / 죽은 키워드 | 회피 |

        **추가 진단 시그널**:
        - **키워드 미스매치**: 동의어/의학용어 검색량 ≫ 일반어 → 검색 키워드 잘못 잡음
        - **경쟁자 강함**: 단일 브랜드 점유 70%+ → APLB 진입 어려움 (별도 포지셔닝 필요)
        """)

    EMERGING_DIR = Path(__file__).parent / "data" / "emerging_signals"
    LANDSCAPE_LATEST = Path(__file__).parent / "data" / "commercial_landscape" / "latest.json"
    latest_file = EMERGING_DIR / "latest.json"
    if not latest_file.exists():
        st.warning("emerging_signals 데이터 없음 — `python collect/emerging_ingredients.py --pubmed` 실행 필요")
        return
    sig_data = json.loads(latest_file.read_text(encoding="utf-8"))

    # 상업 분석 데이터 로드 (있으면 통합)
    commercial_map = {}
    if LANDSCAPE_LATEST.exists():
        cd = json.loads(LANDSCAPE_LATEST.read_text(encoding="utf-8"))
        commercial_map = cd.get("results", {})

    # V-Index 추출 (raw_trends에서 v_index 메트릭)
    v_index_map = {}
    if not df_raw.empty:
        v_df = df_raw[df_raw["metric"] == "v_index"] if "metric" in df_raw.columns else pd.DataFrame()
        if not v_df.empty:
            latest_v = v_df.sort_values("date").groupby("ingredient_id").tail(1)
            v_index_map = dict(zip(latest_v["ingredient_id"], latest_v["value"]))

    # 4-사분면 데이터 구성 (상업 차원 통합)
    rows = []
    for s in sig_data["signals"]:
        if s["total_papers"] < 1:
            continue
        ing_id = s["ingredient_id"]
        academic = s["tier_dist"]["T1"] + s["tier_dist"]["T2"]
        v_idx = v_index_map.get(ing_id)
        v_proxy = v_idx if v_idx is not None else max(0, s["signal_score"] - 15)

        # 상업 정보 통합
        comm = commercial_map.get(ing_id, {})
        c_tier = comm.get("commercial_tier", "?")  # C0/C1/C2/C3/?
        posture = comm.get("aplb_strategic_posture", "")
        top_brand_kr = (comm.get("top_brands_kr", [{}])[0] if comm.get("top_brands_kr") else {}).get("brand", "")
        top_brand_us = (comm.get("top_brands_us", [{}])[0] if comm.get("top_brands_us") else {}).get("brand", "")
        market_gap = comm.get("market_gap", "")

        # 사분면 판정 (학술×시장 V-Index)
        academic_high = academic >= 3
        market_high = v_proxy >= 50
        if academic_high and market_high:
            quadrant = "🟢 트렌드 폭발 (즉시 진입)"
            base_action = "신제품 즉시 검토."
        elif academic_high and not market_high:
            quadrant = "🟡 숨은 보석 (마케팅 선점)"
            base_action = "콘텐츠 마케팅 선점. SEO·과학 스토리텔링·임상 인용."
        elif not academic_high and market_high:
            quadrant = "🟠 인플루언서 거품 (위험)"
            base_action = "1~2분기 관망. 자체 RCT 진행."
        else:
            quadrant = "🔴 매력 부족"
            base_action = "회피 또는 키워드 동의어 재검색."

        # 상업 티어로 액션 미세조정
        if c_tier == "C3":
            adjusted = f"{base_action} ⚠️ 상업 포화 — 프리미엄/Black 라인만 검토 ({top_brand_kr or top_brand_us} 강자)."
        elif c_tier == "C2":
            adjusted = f"{base_action} ⚡ 차별화 필수 (농도/페어/기술). 위협: {top_brand_kr or top_brand_us}."
        elif c_tier in ("C0", "C1"):
            adjusted = f"{base_action} 🚀 선점 가능 — 시장 갭: {market_gap[:60]}"
        else:
            adjusted = base_action

        rows.append({
            "성분": s["name_kr"],
            "영문": s["name_en"],
            "학술 수요": academic,
            "시장 노출": v_proxy,
            "V-Index 실측": v_idx if v_idx is not None else None,
            "총 논문": s["total_papers"],
            "상업 티어": c_tier,
            "전략": posture,
            "한국 Top1": top_brand_kr or "—",
            "북미 Top1": top_brand_us or "—",
            "사분면": quadrant,
            "APLB 액션": adjusted,
            "신호": s["signal_label"],
        })

    df_q = pd.DataFrame(rows)

    if df_q.empty:
        st.info("진단할 성분 없음")
        return

    # ── 4-사분면 산점도 ────────────────────────────────────────
    st.markdown("### 📊 4-사분면 매트릭스")
    fig = px.scatter(
        df_q, x="학술 수요", y="시장 노출",
        size="총 논문", color="사분면", hover_data=["성분", "영문", "신호"],
        text="성분",
        color_discrete_map={
            "🟢 트렌드 폭발 (즉시 진입)": "#10b981",
            "🟡 숨은 보석 (마케팅 선점)": "#f59e0b",
            "🟠 인플루언서 거품 (위험)": "#fb923c",
            "🔴 매력 부족": "#9ca3af",
        },
        size_max=40, height=560,
    )
    fig.update_traces(textposition="top center", textfont_size=10)
    # 사분면 구분선
    fig.add_hline(y=50, line_dash="dash", line_color="gray", opacity=0.4)
    fig.add_vline(x=3,  line_dash="dash", line_color="gray", opacity=0.4)
    fig.update_layout(
        plot_bgcolor="#fafafa",
        xaxis_title="학술 수요 (T1+T2 논문수)",
        yaxis_title="시장 노출 (V-Index 또는 proxy)",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── 사분면별 상세 (상업 티어 컬럼 추가) ────────────────────
    st.markdown("### 📋 사분면별 진단 결과 (학술 × 시장 노출 × 상업 티어 통합)")
    for q_label in ["🟡 숨은 보석 (마케팅 선점)", "🟢 트렌드 폭발 (즉시 진입)",
                    "🟠 인플루언서 거품 (위험)", "🔴 매력 부족"]:
        sub = df_q[df_q["사분면"] == q_label]
        if sub.empty:
            continue
        with st.expander(f"{q_label} — {len(sub)}개 성분", expanded=("숨은 보석" in q_label)):
            st.dataframe(
                sub[["성분", "영문", "학술 수요", "시장 노출", "총 논문",
                     "상업 티어", "전략", "한국 Top1", "북미 Top1", "APLB 액션"]],
                use_container_width=True, hide_index=True,
            )

    # ── 키워드 미스매치 진단 (V-Index가 있는 경우만) ──────────────
    st.divider()
    st.markdown("### 🔍 키워드 미스매치 진단")
    st.caption("학술 검색은 활발한데 일반 V-Index가 낮으면 → 검색 키워드 잘못 잡고 있을 가능성.")
    mismatched = df_q[(df_q["학술 수요"] >= 3) & (df_q["시장 노출"] < 30)]
    if mismatched.empty:
        st.caption("(미스매치 의심 성분 없음)")
    else:
        for _, r in mismatched.iterrows():
            st.markdown(f"""
            <div style="background:#fffbeb;border-left:4px solid #f59e0b;padding:10px 14px;
                 border-radius:0 8px 8px 0;margin-bottom:8px">
              <b>{r['성분']} ({r['영문']})</b> — 학술 {r['학술 수요']}건, 시장 노출 {r['시장 노출']:.0f}<br/>
              <span style="font-size:0.85rem;color:#666">
                💡 진단: 의학용어/동의어 검색은 활발할 가능성. 일반 키워드 변형 추가 검색 권장.
              </span>
            </div>
            """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────
# X2: APLB Black — 프리미엄 라인 후보 (고농도 + VOC + 복합)
# ─────────────────────────────────────────────────────────────────
def view_aplb_black():
    st.title("⚫ APLB Black — 프리미엄 라인 후보")
    st.caption(
        "VOC 기반 고농도 요구 + PubMed 임상 권장 농도 + APLB 보유/미보유 매핑 → "
        "프리미엄 라인 신성분/복합 후보."
    )

    with st.expander("📖 이 페이지 컨셉", expanded=False):
        st.markdown("""
        **APLB 일반 라인 vs APLB Black**:
        - 일반: 안전 농도, 매스 진입, 글로벌 컴플라이언스
        - **Black: 임상 max 농도, 복합 시너지 강화, 시술 후/전문 케어 채널 (clinic, premium)**

        **수집·검증 4단계**:
        1. **VOC 시그널** (Reddit/Naver/리뷰): "트라넥삼산 3% 이상이어야 효과" 같은 농도 요구
        2. **임상 권장 농도** (PubMed efficacy paper): 학술 권장 농도 vs APLB 현재 농도 비교
        3. **복합 페어** (이미 검증된 시너지): aplb_pair_search 결과 활용
        4. **안전성 한계** (CIR): 외용 최대 안전 농도

        **출력**: 성분별 "현재 농도 → Black 권장 농도 → 임상 근거 PMID → 페어 후보"
        """)

    APLB_YAML = Path(__file__).parent / "config" / "aplb_products.yaml"
    BLACK_VOC_YAML = Path(__file__).parent / "config" / "aplb_black_voc.yaml"
    RESEARCH_DIR = Path(__file__).parent / "data" / "aplb_research"

    if not APLB_YAML.exists():
        st.error("aplb_products.yaml 없음")
        return
    aplb = yaml.safe_load(APLB_YAML.read_text(encoding="utf-8"))

    # ── VOC 후보 (없으면 sample 표시 + 입력 가이드) ──────────────
    voc_candidates = []
    if BLACK_VOC_YAML.exists():
        try:
            voc_candidates = yaml.safe_load(BLACK_VOC_YAML.read_text(encoding="utf-8")).get("candidates", [])
        except Exception as e:
            st.warning(f"VOC YAML 로드 실패: {e}")

    # 부트스트랩 — 파일이 없으면 기본 후보 제공
    if not voc_candidates:
        st.info(
            "🚧 **VOC 데이터 부트스트랩 필요**\n\n"
            "`config/aplb_black_voc.yaml` 파일이 없거나 비었습니다. "
            "샘플 후보를 자동 생성합니다 (Katie의 트라넥삼산 3% 인사이트 포함)."
        )
        voc_candidates = _bootstrap_black_candidates()

    # ── KPI ───────────────────────────────────────────────────
    n_total = len(voc_candidates)
    n_high_demand = sum(1 for c in voc_candidates if c.get("voc_intensity", 0) >= 4)
    n_aplb_owned = sum(1 for c in voc_candidates if c.get("aplb_currently_owns"))
    n_priority = sum(1 for c in voc_candidates if c.get("priority", "low") == "high")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("총 Black 후보", n_total)
    k2.metric("고강도 VOC", n_high_demand)
    k3.metric("APLB 보유", n_aplb_owned)
    k4.metric("최우선 후보", n_priority)

    st.divider()

    # ── 후보 카드 ──────────────────────────────────────────────
    st.markdown("### 🎯 Black 라인 후보 (우선순위 정렬)")
    voc_candidates.sort(key=lambda c: (
        0 if c.get("priority") == "high" else 1,
        -c.get("voc_intensity", 0),
    ))

    for cand in voc_candidates:
        prio = cand.get("priority", "low")
        prio_color = {"high": "#dc2626", "medium": "#f59e0b", "low": "#9ca3af"}[prio]
        owned_badge = "✅ APLB 보유 (농도 강화)" if cand.get("aplb_currently_owns") else "🆕 APLB 미보유 (신규 도입)"
        clinical_max = cand.get("clinical_max_concentration", "조사 필요")
        current_aplb = cand.get("aplb_current_concentration", "—")
        proposed = cand.get("proposed_black_concentration", "—")
        voc_quotes = cand.get("voc_quotes", [])
        pair_partners = cand.get("synergy_pairs", [])
        evidence_pmids = cand.get("evidence_pmids", [])
        rationale = cand.get("rationale", "")

        with st.container():
            st.markdown(f"""
            <div style="background:#fff;border:2px solid {prio_color};border-radius:12px;
                 padding:18px 22px;margin-bottom:14px">
              <div style="display:flex;justify-content:space-between;align-items:start">
                <div>
                  <div style="font-size:1.3rem;font-weight:800;color:#111">
                    {cand['name_kr']} ({cand.get('name_en','')})
                  </div>
                  <div style="font-size:0.85rem;color:#666;margin-top:4px">{owned_badge}</div>
                </div>
                <div style="background:{prio_color};color:#fff;padding:4px 12px;
                     border-radius:14px;font-size:0.8rem;font-weight:700">
                  {prio.upper()}
                </div>
              </div>

              <div style="display:flex;gap:24px;margin-top:14px;flex-wrap:wrap">
                <div>
                  <div style="font-size:0.7rem;color:#888;text-transform:uppercase">현재 APLB 농도</div>
                  <div style="font-size:1.1rem;font-weight:700;color:#444">{current_aplb}</div>
                </div>
                <div>
                  <div style="font-size:0.7rem;color:#888;text-transform:uppercase">제안 Black 농도</div>
                  <div style="font-size:1.1rem;font-weight:700;color:{prio_color}">{proposed}</div>
                </div>
                <div>
                  <div style="font-size:0.7rem;color:#888;text-transform:uppercase">임상 max</div>
                  <div style="font-size:1.1rem;font-weight:700;color:#444">{clinical_max}</div>
                </div>
                <div>
                  <div style="font-size:0.7rem;color:#888;text-transform:uppercase">VOC 강도</div>
                  <div style="font-size:1.1rem;font-weight:700;color:#444">
                    {'⭐' * cand.get('voc_intensity', 0)}
                  </div>
                </div>
              </div>

              <div style="margin-top:14px;color:#444;font-size:0.9rem">
                💡 <b>근거</b>: {rationale}
              </div>
            </div>
            """, unsafe_allow_html=True)

            cols = st.columns(2)
            with cols[0]:
                if voc_quotes:
                    st.markdown("**🗣️ VOC 인용**")
                    for q in voc_quotes[:3]:
                        st.caption(f"💬 {q}")
            with cols[1]:
                if pair_partners:
                    st.markdown("**🔗 시너지 페어 후보**")
                    for p in pair_partners[:4]:
                        st.caption(f"• {p}")
                if evidence_pmids:
                    pmid_links = ", ".join(
                        f"[{p}](https://pubmed.ncbi.nlm.nih.gov/{p}/)" for p in evidence_pmids[:5]
                    )
                    st.markdown(f"**📄 임상 근거**: {pmid_links}")

    # ── VOC 데이터 추가 가이드 ─────────────────────────────────
    st.divider()
    with st.expander("🔧 VOC 데이터 보강 방법", expanded=False):
        st.markdown(f"""
        **`config/aplb_black_voc.yaml` 직접 편집** — 또는 다음 자동 수집 옵션:
        - Reddit (r/SkincareAddiction, r/AsianBeauty)
        - Naver 카페 (글로우픽, 화장품 커뮤니티)
        - 올리브영/예스스타일 리뷰

        **수동 부트스트랩 가능 (사용 추천)**:
        ```yaml
        candidates:
          - id: tranexamic_3pct
            name_kr: 트라넥삼산 (3% 이상)
            voc_intensity: 5  # 1-5 scale
            voc_quotes: ["3% 이상이어야 효과 본다는 후기 다수", "..."]
            aplb_currently_owns: true
            aplb_current_concentration: "~1%"
            proposed_black_concentration: "3%"
            clinical_max_concentration: "5% (외용 RCT)"
            synergy_pairs: ["niacinamide", "vitamin C"]
            evidence_pmids: ["xxxx", "yyyy"]
            priority: high
            rationale: "..."
        ```
        """)


def _bootstrap_black_candidates() -> list[dict]:
    """VOC 데이터 없을 때 사용하는 초기 후보 (Katie 인사이트 + PubMed 결과 기반)"""
    return [
        {
            "id": "tranexamic_3pct",
            "name_kr": "트라넥삼산 (외용 3%+)",
            "name_en": "Tranexamic Acid 3%+",
            "voc_intensity": 5,
            "voc_quotes": [
                "후기에서 '3% 이상이어야 효과' 의견 다수 (Katie 직접 청취)",
                "북미 derma 사용자: 'good morning® / The Inkey List 3% 비교 후기 多'",
                "예스스타일 타임딜 상위지만 농도 표기 모호 — 신뢰도 이슈",
            ],
            "aplb_currently_owns": True,
            "aplb_current_concentration": "표기 불명 (~1% 추정)",
            "proposed_black_concentration": "3%",
            "clinical_max_concentration": "5% (외용 RCT, 기미 8주 개선)",
            "synergy_pairs": ["niacinamide", "vitamin C", "azelaic acid", "kojic acid"],
            "evidence_pmids": [],
            "priority": "high",
            "rationale": "예스스타일 베스트셀러인데 농도 미표기 → Black '3% Concentrate' 차별화. PubMed에서 tranexamic×melasma·niacinamide 모두 10건+ 임상.",
        },
        {
            "id": "azelaic_15pct",
            "name_kr": "아젤라산 (외용 15~20%)",
            "name_en": "Azelaic Acid 15-20%",
            "voc_intensity": 5,
            "voc_quotes": [
                "'OTC 10%로는 약함, 처방 15-20% 수준 원함' (북미 reddit)",
                "Skinoren 20% (RX) → cosmetic 15% 수요 증가",
            ],
            "aplb_currently_owns": True,
            "aplb_current_concentration": "표기 불명 (cosmetic-grade)",
            "proposed_black_concentration": "15%",
            "clinical_max_concentration": "20% (RX), 15% OTC 안전",
            "synergy_pairs": ["niacinamide", "salicylic acid", "centella"],
            "evidence_pmids": [],
            "priority": "high",
            "rationale": "Azelaic은 북미 sensitive·rosacea 시장 폭발. 15% 진입 시 'almost-RX' 포지셔닝 가능. APLB Centella 자산과 결합으로 자극 완화.",
        },
        {
            "id": "exosome_premium",
            "name_kr": "엑소좀 (식물성 고농도)",
            "name_en": "Plant-derived Exosome (high-conc)",
            "voc_intensity": 4,
            "voc_quotes": [
                "시술 후 회복 앰플 고가 라인 수요 (북미 medspa)",
                "한국 derma clinic 채널: '시술 직후 1-2주 회복' 클레임 강함",
            ],
            "aplb_currently_owns": False,
            "aplb_current_concentration": "—",
            "proposed_black_concentration": "1-3% plant exosome (식약처 등재 가능 범위)",
            "clinical_max_concentration": "조사 필요 (식물 유래 제한 적음)",
            "synergy_pairs": ["glutathione", "niacinamide", "ceramide", "hyaluronic acid"],
            "evidence_pmids": [],
            "priority": "high",
            "rationale": "엑소좀×HA 10건, 엑소좀×regen 10건 임상 강함. APLB 미보유 → Black 1순위. plant-derived가 규제·안전성 유리.",
        },
        {
            "id": "retinal_high",
            "name_kr": "레티날 (고농도 0.1%+)",
            "name_en": "Retinaldehyde 0.1%+",
            "voc_intensity": 4,
            "voc_quotes": [
                "'레티놀보다 1단계 빠르고 자극 적음' 인지 확산",
                "Avene Retrinal·Medik8 0.1% 수준 수요",
            ],
            "aplb_currently_owns": False,
            "aplb_current_concentration": "—",
            "proposed_black_concentration": "0.1%",
            "clinical_max_concentration": "0.1% 외용 안전 (Avene 임상)",
            "synergy_pairs": ["peptide", "centella", "ceramide"],
            "evidence_pmids": [],
            "priority": "medium",
            "rationale": "안티에이징 차세대. APLB 레티놀 라인 보유 → Black은 레티날로 업그레이드. 자극 완화 위한 Centella·Cera 결합.",
        },
        {
            "id": "glutathione_high",
            "name_kr": "글루타치온 (고농도 + 안정화)",
            "name_en": "Glutathione (stabilized high)",
            "voc_intensity": 3,
            "voc_quotes": [
                "'1000ppm는 입문, 진짜 효과는 5000ppm+'",
                "K-beauty 시장: '글루타치온 함량 표기 신뢰도' 이슈",
            ],
            "aplb_currently_owns": True,
            "aplb_current_concentration": "1000ppm (0.1%)",
            "proposed_black_concentration": "5000ppm (0.5%) + liposome 안정화",
            "clinical_max_concentration": "조사 필요",
            "synergy_pairs": ["niacinamide", "vitamin C", "tranexamic acid"],
            "evidence_pmids": [],
            "priority": "medium",
            "rationale": "현재 1000ppm — Black은 5x 농도 + liposome 안정화로 '클리닉급' 포지셔닝. LIPO GLUTA NIAC EXO 차세대.",
        },
    ]


# ─────────────────────────────────────────────────────────────────
# 🎯 Executive Brief — 6개 데이터 소스 종합 의사결정 페이지
# ─────────────────────────────────────────────────────────────────
def view_executive_brief():
    BRIEF_LATEST = Path(__file__).parent / "data" / "executive_brief" / "latest.json"

    # 헤더
    st.markdown("""
    <div style="margin-bottom:18px">
      <div style="font-size:0.78rem;color:#9ca3af;letter-spacing:0.08em;
           text-transform:uppercase;font-weight:600">EXECUTIVE BRIEF</div>
      <div style="font-size:2.1rem;font-weight:800;letter-spacing:-0.025em;
           background:linear-gradient(135deg,#0f0f12 0%,#3b3b44 100%);
           -webkit-background-clip:text;-webkit-text-fill-color:transparent;
           line-height:1.1;margin-top:2px">
        🎯 오늘 무엇을 결정해야 하는가?
      </div>
      <div style="color:#6b7280;font-size:0.95rem;margin-top:6px">
        6개 데이터 소스를 종합한 매일 5분 의사결정 도구
      </div>
    </div>
    """, unsafe_allow_html=True)

    if not BRIEF_LATEST.exists():
        st.warning(
            "Executive Brief 데이터 없음.\n\n"
            "터미널에서: `python collect/executive_brief.py`"
        )
        return

    brief = json.loads(BRIEF_LATEST.read_text(encoding="utf-8"))
    kpi = brief.get("kpi", {})

    # ── 1. KPI 대시보드 ───────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("🔬 추적 성분", kpi.get("total_tracked", 0))
    k2.metric("🔥 임박 신호", kpi.get("imminent", 0))
    k3.metric("🚀 Pioneer 후보", kpi.get("pioneer", 0))
    k4.metric("✅ 클레임 PASS", f"{kpi.get('claim_pass_rate', 0):.0f}%")
    k5.metric("🧬 활성 임상", kpi.get("active_clinical", 0))

    # 데이터 신선도 알림
    days = kpi.get("days_since_data", -1)
    fresh = kpi.get("data_freshness", "")
    if fresh == "very_stale":
        st.error(f"🔴 데이터 누락 — V-Index {days}일 전 마지막 수집. cron 점검 필요.")
    elif fresh == "stale":
        st.warning(f"🟡 데이터 신선도 — V-Index {days}일 전. 최신 아님.")

    st.caption(f"📅 분석: {brief.get('generated_at','')[:19]}")
    st.divider()

    # ── 2. AI 종합 시사점 (가장 위, 강조) ──────────────────────
    ai_text = brief.get("ai_synthesis", "")
    if ai_text:
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#fdf2f8 0%,#f3e8ff 50%,#cffafe 100%);
             border-radius:14px;padding:24px 28px;margin-bottom:24px;
             border:1px solid rgba(236,72,153,0.15)">
          <div style="font-size:0.78rem;color:#be185d;font-weight:700;
               letter-spacing:0.06em;margin-bottom:10px">🤖 AI 종합 시사점</div>
          <div style="color:#1f2937;line-height:1.75;font-size:0.95rem;
               white-space:pre-wrap;font-weight:500">{ai_text}</div>
        </div>
        """, unsafe_allow_html=True)

    # ── 3. TOP 의사결정 카드 (페이지 deep-link 포함) ──────────
    st.markdown("### 📋 오늘의 의사결정 TOP")

    # 결정 유형 → 이동할 페이지 매핑
    NAV_MAP = {
        "🚀 즉시 신제품": ("🏪 시장 경쟁 진단", "Pioneer 후보 + 브랜드 분석 보기"),
        "⚡ 마케팅 강화": ("📈 시계열 분석", "V-Index 시계열 + AI 시사점 보기"),
        "💎 Black 프리미엄": ("⚫ APLB Black 후보", "Black 라인 후보 + 임상 max 보기"),
        "🌍 글로벌 출시": ("✨ APLB 마케팅 클레임", "PASS 클레임 카드 + 인용 논문 보기"),
        "⛔ 회피/축소": ("🏪 시장 경쟁 진단", "포화 시장 경쟁 분석 보기"),
    }

    decisions = brief.get("top_decisions", [])
    if not decisions:
        st.caption("의사결정 추출 데이터 부족. 더 많은 데이터 수집 후 재실행 필요.")
    else:
        priority_color = {"high":"#dc2626", "medium":"#f59e0b", "low":"#9ca3af"}
        for i, d in enumerate(decisions, 1):
            color = priority_color.get(d.get("priority", "low"), "#9ca3af")
            d_type = d.get('type', '')
            target_page, btn_label = NAV_MAP.get(d_type, (None, None))

            st.markdown(f"""
            <div style="background:#fff;border:1px solid #ececef;border-left:5px solid {color};
                 border-radius:10px;padding:18px 22px;margin-bottom:6px;
                 box-shadow:0 1px 3px rgba(0,0,0,0.03)">
              <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:8px">
                <div>
                  <div style="font-size:0.72rem;color:#9ca3af;font-weight:700;
                       letter-spacing:0.05em">#{i}  {d_type}</div>
                  <div style="font-size:1.15rem;font-weight:700;color:#111;margin-top:2px">
                    {d.get('title','')}
                  </div>
                </div>
                <span style="background:{color};color:#fff;padding:3px 12px;
                     border-radius:12px;font-size:0.72rem;font-weight:700;
                     letter-spacing:0.04em">{d.get('priority','').upper()}</span>
              </div>
              <div style="color:#4b5563;font-size:0.88rem;line-height:1.6;margin-top:10px">
                <b style="color:#374151">📊 근거</b>: {d.get('rationale','')}
              </div>
              <div style="color:#374151;font-size:0.88rem;line-height:1.6;margin-top:6px;
                   background:#f9fafb;padding:8px 12px;border-radius:7px;border-left:3px solid #ec4899">
                <b style="color:#be185d">💡 다음 액션</b>: {d.get('next_action','')}
              </div>
              <div style="color:#9ca3af;font-size:0.72rem;margin-top:10px">
                근거 데이터: {' · '.join(d.get('supporting_data', []))}
              </div>
            </div>
            """, unsafe_allow_html=True)

            # 페이지 deep-link 버튼
            if target_page:
                # ingredient_id 또는 complex가 있으면 미리 전달
                ing_id = d.get("ingredient_id")
                complexes = d.get("complexes", [])
                btn_key = f"nav_btn_{i}"
                if st.button(f"→ {btn_label}", key=btn_key, use_container_width=False):
                    st.session_state["main_nav"] = target_page
                    if ing_id:
                        st.session_state["jump_to_ingredient"] = ing_id
                    if complexes:
                        st.session_state["jump_to_complex"] = complexes[0]
                    st.rerun()

            st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)

    # ── 4. 주의 시그널 ────────────────────────────────────────
    warnings = brief.get("warning_signals", [])
    if warnings:
        st.markdown("### ⚠️ 주의 시그널")
        for w in warnings:
            sev = w.get("severity", "low")
            if sev == "high":
                st.error(f"{w.get('type','')}: {w.get('msg','')}")
            elif sev == "medium":
                st.warning(f"{w.get('type','')}: {w.get('msg','')}")
            else:
                st.info(f"{w.get('type','')}: {w.get('msg','')}")

    # ── 5. Hot Topics ────────────────────────────────────────
    st.markdown("### 🔥 Hot Topics — 모니터링 우선")
    hot = brief.get("hot_topics", {})
    h1, h2, h3 = st.columns(3)
    with h1:
        st.markdown("""<div style="background:#fef2f2;border-radius:10px;padding:14px;
                     border-left:4px solid #dc2626">
                     <div style="font-size:0.72rem;color:#991b1b;font-weight:700;
                          letter-spacing:0.05em;margin-bottom:6px">🔥 임박 신호</div>""",
                    unsafe_allow_html=True)
        for x in hot.get("imminent", []):
            st.markdown(f"<div style='font-size:0.88rem;color:#374151;margin-bottom:4px'>"
                        f"• <b>{x['name_kr']}</b> (점수 {x['score']:.0f})</div>",
                        unsafe_allow_html=True)
        if not hot.get("imminent"):
            st.caption("(없음)")
        st.markdown("</div>", unsafe_allow_html=True)
    with h2:
        st.markdown("""<div style="background:#f0f9ff;border-radius:10px;padding:14px;
                     border-left:4px solid #0284c7">
                     <div style="font-size:0.72rem;color:#075985;font-weight:700;
                          letter-spacing:0.05em;margin-bottom:6px">🚀 Pioneer 후보</div>""",
                    unsafe_allow_html=True)
        for x in hot.get("pioneer", []):
            st.markdown(f"<div style='font-size:0.88rem;color:#374151;margin-bottom:4px'>"
                        f"• <b>{x['name_kr']}</b></div>",
                        unsafe_allow_html=True)
        if not hot.get("pioneer"):
            st.caption("(없음)")
        st.markdown("</div>", unsafe_allow_html=True)
    with h3:
        st.markdown("""<div style="background:#f0fdf4;border-radius:10px;padding:14px;
                     border-left:4px solid #16a34a">
                     <div style="font-size:0.72rem;color:#15803d;font-weight:700;
                          letter-spacing:0.05em;margin-bottom:6px">🧬 임상시험 활성</div>""",
                    unsafe_allow_html=True)
        for x in hot.get("ct_active", []):
            st.markdown(f"<div style='font-size:0.88rem;color:#374151;margin-bottom:4px'>"
                        f"• <b>{x['name_kr']}</b> ({x['active']}건)</div>",
                        unsafe_allow_html=True)
        if not hot.get("ct_active"):
            st.caption("(없음)")
        st.markdown("</div>", unsafe_allow_html=True)

    # ── 6. 이번 주 변화 ────────────────────────────────────────
    st.markdown("### 📈 이번 주 V-Index 변화")
    wk = brief.get("weekly_changes", {})
    gainers = wk.get("biggest_gainers", [])
    losers = wk.get("biggest_losers", [])
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**🔼 가장 많이 오른 성분**")
        if gainers:
            for ing, delta in gainers[:5]:
                st.markdown(f"- <b style='color:#047857'>{ing}</b>: +{delta:.1f}",
                            unsafe_allow_html=True)
        else:
            st.caption("(데이터 부족)")
    with g2:
        st.markdown("**🔽 가장 많이 떨어진 성분**")
        if losers:
            for ing, delta in losers[:5]:
                st.markdown(f"- <b style='color:#b91c1c'>{ing}</b>: {delta:.1f}",
                            unsafe_allow_html=True)
        else:
            st.caption("(데이터 부족)")

    st.divider()
    st.caption(
        "💡 갱신: 매일 새벽 6시 자동 (cron). 수동: `python collect/executive_brief.py`"
    )


# ── 메인 ───────────────────────────────────────────────────────────
def main():
    ingredients = load_ingredients_config()
    df_raw, df_manual = load_sheets_data()
    view = sidebar()

    if view == "🎯 Executive Brief":
        view_executive_brief()
    elif view == "📊 As-Is 매트릭스":
        view_matrix(ingredients, df_raw, df_manual)
    elif view == "📅 주간 트래킹":
        view_weekly_tracking(ingredients, df_raw, df_manual)
    elif view == "📈 시계열 분석":
        view_timeseries(ingredients, df_raw)
    elif view == "📋 판매 검증 입력":
        view_manual_input(ingredients, df_manual)
    elif view == "🔬 성분 연구 인사이트":
        view_ingredient_research()
    elif view == "✨ APLB 마케팅 클레임":
        view_aplb_marketing_claims()
    elif view == "🔭 신성분 발굴 (3-Tier)":
        view_emerging_ingredients()
    elif view == "🏪 시장 경쟁 진단":
        view_commercial_landscape()
    elif view == "🔬 왜 안 뜨는가 진단":
        view_why_not_trending(ingredients, df_raw)
    elif view == "⚫ APLB Black 후보":
        view_aplb_black()
    elif view == "⚙️ 지표 방법론":
        view_methodology()
    elif view == "📺 채널 관리":
        view_channel_admin()
    elif view == "🛠️ 관리자 가이드":
        view_admin_guide()


if __name__ == "__main__":
    run_with_auth()

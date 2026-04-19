"""
뷰티 성분 트렌드 대시보드
streamlit run dashboard.py
"""

import os
import yaml
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

# ── 페이지 설정 ────────────────────────────────────────────────────
st.set_page_config(
    page_title="Beauty Ingredient Trends",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 전역 스타일: 카드 내 <b> 태그 색상 보정, 경고 배너 개선
st.markdown("""
<style>
    /* 섹션 제목 스타일 */
    h3 { margin-top: 0.5rem !important; }
    /* 경고 배너 덜 눈에 띄게 */
    .stAlert > div { font-size: 0.82rem; padding: 8px 12px; }
    /* 데이터프레임 헤더 */
    .dataframe thead th { background: #f0f0f0 !important; color: #111 !important; }
</style>
""", unsafe_allow_html=True)

YAML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "ingredients.yaml")

STATUS_EMOJI = {"rising": "🟢", "falling": "🔴", "watching": "🟡"}
STATUS_COLOR = {"rising": "#00C48C", "falling": "#FF6B6B", "watching": "#FFB800"}

# ── 데이터 로딩 ────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_ingredients_config() -> list[dict]:
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["ingredients"]


@st.cache_data(ttl=300)
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
                ("r_score",     base_r[ing_id],      dr,     0, 100),
                ("r_score_weighted", base_r[ing_id]+3, dr, 0, 100),
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


def get_latest_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """성분별 최신 지표 추출. 숫자 메트릭은 mean, 문자열 메트릭(pain_points 등)은 last."""
    if df.empty:
        return pd.DataFrame()
    latest_date = df["date"].max()
    recent = df[df["date"] >= latest_date - timedelta(days=8)].copy()

    numeric_mask = pd.to_numeric(recent["value"], errors="coerce").notna()

    # 숫자 메트릭: 평균
    numeric_pivot = (
        recent[numeric_mask]
        .groupby(["ingredient_id", "metric_name"])["value"]
        .mean()
        .unstack(fill_value=None)
    )

    # 문자열 메트릭(pain_points 등): 최신값
    string_pivot = (
        recent[~numeric_mask]
        .groupby(["ingredient_id", "metric_name"])["value"]
        .last()
        .unstack(fill_value=None)
    )

    pivot = pd.concat([numeric_pivot, string_pivot], axis=1).reset_index()
    return pivot


# ── 사이드바 ────────────────────────────────────────────────────────
def sidebar():
    st.sidebar.title("✨ Beauty Trend Dashboard")
    st.sidebar.caption("뷰티 성분 트렌드 추적기")
    st.sidebar.divider()

    view = st.sidebar.radio(
        "뷰 선택",
        ["📊 As-Is 매트릭스", "📈 시계열 분석", "📋 수동 입력 (TikTok/Amazon)", "⚙️ 지표 방법론", "📺 채널 관리"],
        label_visibility="collapsed",
    )

    st.sidebar.divider()
    st.sidebar.caption(f"마지막 업데이트: {date.today().isoformat()}")

    if st.sidebar.button("🔄 데이터 새로고침"):
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
        r      = _val(iid, "r_score_weighted") or _val(iid, "r_score")
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
            "R-Score":      round(r, 1) if r is not None else None,
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
    st.title("📊 성분 트렌드 매트릭스 — As-Is")
    st.caption(f"기준일: {date.today().isoformat()} | V-Index(Google Trends) + R-Score(Reddit) + ET-KR/US(전문의 YouTube) | ★FinalScore = V×0.3 + R×0.3 + K-ET×0.4")

    # ── 내보내기 ────────────────────────────────────────────────
    with st.expander("📥 데이터 내보내기 (Excel / JSON)", expanded=False):
        export_df = build_export_df(ingredients, df)
        st.dataframe(export_df, use_container_width=True, hide_index=True)

        col_xl, col_js, col_note = st.columns([1, 1, 3])
        with col_xl:
            import io
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                export_df.to_excel(writer, index=False, sheet_name="출시유망순위")
            st.download_button(
                label="⬇️ Excel 다운로드",
                data=buf.getvalue(),
                file_name=f"beauty_trends_{date.today().isoformat()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        with col_js:
            import json as _json
            json_str = export_df.to_json(orient="records", force_ascii=False, indent=2)
            st.download_button(
                label="⬇️ JSON 다운로드",
                data=json_str,
                file_name=f"beauty_trends_{date.today().isoformat()}.json",
                mime="application/json",
            )
        with col_note:
            st.caption("FinalScore 기준 내림차순 정렬. 데이터 수집 후 실제 점수 반영됩니다.")

    latest = get_latest_metrics(df)

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
                r     = get_val(ing["id"], "r_score_weighted") or get_val(ing["id"], "r_score")
                et_kr = get_val(ing["id"], "et_score_kr")
                et_us = get_val(ing["id"], "et_score_us")
                c     = get_c_ratio(ing["id"])
                fs    = compute_final_score(v, r, et_kr)
                is_seasonal = get_val(ing["id"], "is_seasonal") == "1"
                pain_raw  = get_val(ing["id"], "pain_points")
                pain_pts  = [p.strip() for p in pain_raw.split("|") if p.strip()] if pain_raw != "—" else []
                note      = ing.get("notes", "")[:65] + ("…" if len(ing.get("notes", "")) > 65 else "")

                def score_color(val_str, lo=-100, hi=100):
                    if val_str == "—": return "#aaa"
                    val = float(val_str)
                    # V-Index는 음수 가능 → 중간값(0) 기준
                    mid = (lo + hi) / 2
                    pct = (val - lo) / (hi - lo)  # 0~1
                    if pct >= 0.7: return "#111"
                    if pct >= 0.5: return "#444"
                    if pct >= 0.3: return "#888"
                    return "#cc3333"  # 하락

                def v_display(val_str):
                    """V-Index: 양수면 +표시, 음수면 빨간색"""
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

                badges_html = build_relation_badges(ing)
                relation_note = ing.get("relation_note", "")
                relation_section = ""
                if badges_html:
                    rel_tooltip = f'<div style="font-size:0.67rem;color:#888;margin-top:3px;">{relation_note}</div>' if relation_note else ""
                    relation_section = f'<div style="margin-bottom:8px;">{badges_html}{rel_tooltip}</div>'

                seasonal_flag = '<span style="background:#fff3e0;color:#e65100;border:1px solid #ffcc80;border-radius:4px;padding:1px 6px;font-size:0.65rem;font-weight:600;margin-left:4px;">⚠️ 계절성</span>' if is_seasonal else ""
                v_str, v_col = v_display(v)
                fs_text_col, fs_bg_col = final_score_color(fs)
                et_kr_display = et_kr if et_kr != "—" else "—"
                et_us_display = et_us if et_us != "—" else "—"
                et_kr_col = score_color(et_kr, 0, 100) if et_kr != "—" else "#aaa"
                et_us_col = score_color(et_us, 0, 100) if et_us != "—" else "#aaa"

                pain_html = ""
                if pain_pts:
                    tags = "".join([f'<span style="background:#fff3f3;color:#c62828;border:1px solid #ffcdd2;border-radius:3px;padding:1px 5px;font-size:0.65rem;margin-right:3px;">{p}</span>' for p in pain_pts])
                    pain_html = f'<div style="margin-top:6px;"><span style="font-size:0.65rem;color:#999;font-weight:600;">⚠ PAIN</span> {tags}</div>'

                st.markdown(f"""
<div style="border-left:5px solid {color};border-radius:8px;padding:14px 16px;margin-bottom:12px;background:#ffffff;box-shadow:0 1px 4px rgba(0,0,0,0.08);">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:2px;">
    <div style="font-size:1.05rem;font-weight:700;color:#111;">{ing['name_kr']}{seasonal_flag}</div>
    <div style="background:{fs_bg_col};color:{fs_text_col};border-radius:6px;padding:3px 9px;font-size:0.8rem;font-weight:800;min-width:36px;text-align:center;" title="Final Score = V×0.3 + R×0.3 + ET×0.4">★ {fs}</div>
  </div>
  <div style="font-size:0.72rem;color:#777;margin-bottom:8px;">{ing['name_en']} · {ing.get('category','')}</div>
  {relation_section}
  <div style="display:flex;justify-content:space-between;text-align:center;gap:4px;margin-bottom:6px;align-items:stretch;">
    <div style="flex:1;background:#f5f5f5;border-radius:6px;padding:8px 3px;display:flex;flex-direction:column;justify-content:center;min-width:0;">
      <div style="font-size:0.58rem;color:#777;font-weight:600;letter-spacing:0.04em;white-space:nowrap;">V-INDEX</div>
      <div style="font-size:1.2rem;font-weight:800;color:{v_col};line-height:1.3;margin-top:3px;">{v_str}</div>
    </div>
    <div style="flex:1;background:#f5f5f5;border-radius:6px;padding:8px 3px;display:flex;flex-direction:column;justify-content:center;min-width:0;">
      <div style="font-size:0.58rem;color:#777;font-weight:600;letter-spacing:0.04em;white-space:nowrap;">R-SCORE</div>
      <div style="font-size:1.2rem;font-weight:800;color:{score_color(r,0,100)};line-height:1.3;margin-top:3px;">{r}</div>
    </div>
    <div style="flex:1.8;background:#f0f4ff;border-radius:6px;padding:6px 4px;display:flex;flex-direction:column;justify-content:center;min-width:0;">
      <div style="font-size:0.55rem;color:#5c6bc0;font-weight:700;letter-spacing:0.03em;margin-bottom:3px;white-space:nowrap;">ET-INDEX</div>
      <div style="display:flex;justify-content:space-around;align-items:center;">
        <div style="flex:1;min-width:0;">
          <div style="font-size:0.5rem;color:#888;font-weight:600;">🇰🇷KR</div>
          <div style="font-size:0.95rem;font-weight:800;color:{et_kr_col};line-height:1.3;word-break:keep-all;">{et_kr_display}</div>
        </div>
        <div style="width:1px;background:#dde;align-self:stretch;margin:0 3px;"></div>
        <div style="flex:1;min-width:0;">
          <div style="font-size:0.5rem;color:#888;font-weight:600;">🇺🇸US</div>
          <div style="font-size:0.95rem;font-weight:800;color:{et_us_col};line-height:1.3;word-break:keep-all;">{et_us_display}</div>
        </div>
      </div>
    </div>
    <div style="flex:1;background:#f5f5f5;border-radius:6px;padding:8px 3px;display:flex;flex-direction:column;justify-content:center;min-width:0;">
      <div style="font-size:0.58rem;color:#777;font-weight:600;letter-spacing:0.04em;white-space:nowrap;">C-RATIO</div>
      <div style="font-size:1.2rem;font-weight:800;color:#555;line-height:1.3;margin-top:3px;">{c}</div>
    </div>
  </div>
  {pain_html}
  <div style="font-size:0.72rem;color:#555;margin-top:8px;line-height:1.5;border-top:1px solid #eee;padding-top:8px;">{note}</div>
</div>
""", unsafe_allow_html=True)

        st.divider()

    # 종합 레이더 차트
    st.subheader("종합 포지셔닝 맵 (V-Index vs R-Score)")
    _scatter_map(ingredients, latest)


def _scatter_map(ingredients, latest):
    if latest.empty:
        st.info("데이터 수집 후 차트가 표시됩니다.")
        return

    chart_data = []
    for ing in ingredients:
        row = latest[latest["ingredient_id"] == ing["id"]]
        if row.empty:
            continue
        v = row.iloc[0].get("v_index", None)
        r = row.iloc[0].get("r_score", None)
        et_kr = row.iloc[0].get("et_score_kr", None)
        et_us = row.iloc[0].get("et_score_us", None)
        if v is None or pd.isna(v):
            continue
        # r_score 없으면 ET-Index로 대체 (KR 우선, 없으면 US, 없으면 50)
        if r is None or pd.isna(r):
            if et_kr is not None and not pd.isna(et_kr) and float(et_kr) > 0:
                r = float(et_kr)
            elif et_us is not None and not pd.isna(et_us) and float(et_us) > 0:
                r = float(et_us)
            else:
                r = 50
        chart_data.append({
            "name_kr": ing["name_kr"],
            "v_index": float(v),
            "r_score": float(r),
            "status": ing["status"],
            "category": ing.get("category", ""),
        })

    if not chart_data:
        st.info("데이터 수집 후 차트가 표시됩니다.")
        return

    df_chart = pd.DataFrame(chart_data)
    color_map = STATUS_COLOR

    fig = px.scatter(
        df_chart,
        x="v_index", y="r_score",
        color="status",
        color_discrete_map=color_map,
        size=[20] * len(df_chart),
        hover_name="name_kr",
        hover_data={"category": True, "status": True, "v_index": True, "r_score": True},
        labels={"v_index": "V-Index (검색 가속도)", "r_score": "R-Score (커뮤니티 신뢰도)"},
    )

    # 사분면 구분선 (V-Index 기준: 20 / R-Score 기준: 60)
    fig.add_hline(y=60, line_dash="dot", line_color="gray", opacity=0.4)
    fig.add_vline(x=20, line_dash="dot", line_color="gray", opacity=0.4)
    # 0선 강조 (V-Index 0 = 변화 없음)
    fig.add_vline(x=0, line_dash="solid", line_color="#ccc", opacity=0.6)

    # 사분면 레이블 — paper 좌표계로 고정 (데이터 포인트와 겹치지 않음)
    # xref/yref="paper": 0=왼쪽/하단, 1=오른쪽/상단
    fig.add_annotation(xref="paper", yref="paper", x=0.99, y=0.99,
                       text="⭐ 핵심 유망성분", showarrow=False,
                       xanchor="right", yanchor="top",
                       font=dict(color="#9e9e9e", size=10),
                       bgcolor="rgba(255,255,255,0.7)")
    fig.add_annotation(xref="paper", yref="paper", x=0.99, y=0.02,
                       text="⚡ 바이럴 but 검증 필요", showarrow=False,
                       xanchor="right", yanchor="bottom",
                       font=dict(color="#9e9e9e", size=10),
                       bgcolor="rgba(255,255,255,0.7)")
    fig.add_annotation(xref="paper", yref="paper", x=0.01, y=0.99,
                       text="💎 숨은 고관여 성분", showarrow=False,
                       xanchor="left", yanchor="top",
                       font=dict(color="#9e9e9e", size=10),
                       bgcolor="rgba(255,255,255,0.7)")
    fig.add_annotation(xref="paper", yref="paper", x=0.01, y=0.02,
                       text="📉 관심 저하", showarrow=False,
                       xanchor="left", yanchor="bottom",
                       font=dict(color="#9e9e9e", size=10),
                       bgcolor="rgba(255,255,255,0.7)")

    fig.update_traces(textposition="top center", textfont_size=9)
    fig.update_layout(
        height=500,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f8f9fa",
        font_color="#111",
        legend_title="Status",
        xaxis=dict(range=[-105, 105], gridcolor="#e0e0e0", zerolinecolor="#aaa",
                   title="V-Index (← 하락 | 0 | 상승 →)"),
        yaxis=dict(range=[0, 105], gridcolor="#e0e0e0", zerolinecolor="#ccc"),
        legend=dict(bgcolor="#ffffff", bordercolor="#ddd", borderwidth=1),
    )
    st.plotly_chart(fig, use_container_width=True)


# ── View 2: 시계열 분석 ────────────────────────────────────────────
def view_timeseries(ingredients: list[dict], df: pd.DataFrame):
    st.title("📈 성분별 시계열 분석")

    if df.empty:
        st.info("Google Sheets에 데이터가 없습니다. 수집기를 먼저 실행하세요.")
        return

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
        metric = st.selectbox("지표", ["v_index", "r_score"], format_func=lambda x: {
            "v_index": "V-Index (검색 가속도)", "r_score": "R-Score (커뮤니티 신뢰도)"
        }[x])
    with col3:
        period = st.selectbox("기간", ["3M", "6M", "12M"])

    days = {"3M": 90, "6M": 180, "12M": 365}[period]
    cutoff = pd.Timestamp(date.today()) - timedelta(days=days)

    filtered = df[
        (df["ingredient_id"].isin(selected_ids)) &
        (df["metric_name"] == metric) &
        (df["date"] >= cutoff)
    ]

    if filtered.empty:
        st.info("선택한 조건에 해당하는 데이터가 없습니다.")
        return

    fig = go.Figure()
    for ing_id in selected_ids:
        ing_data = filtered[filtered["ingredient_id"] == ing_id].sort_values("date")
        if ing_data.empty:
            continue
        ing_info = next((i for i in ingredients if i["id"] == ing_id), {})
        color = STATUS_COLOR.get(ing_info.get("status", "watching"), "#888")

        fig.add_trace(go.Scatter(
            x=ing_data["date"],
            y=ing_data["value"],
            name=ing_info.get("name_kr", ing_id),
            mode="lines+markers",
            line=dict(color=color, width=2),
            marker=dict(size=5),
            hovertemplate=f"<b>{ing_info.get('name_kr', ing_id)}</b><br>%{{x|%Y-%m-%d}}<br>{metric}: %{{y:.1f}}<extra></extra>",
        ))

    fig.update_layout(
        height=420,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f8f9fa",
        font_color="#111",
        xaxis=dict(gridcolor="#e0e0e0", zerolinecolor="#ccc"),
        yaxis=dict(gridcolor="#e0e0e0", zerolinecolor="#ccc", range=[0, 105]),
        legend=dict(bgcolor="#ffffff", bordercolor="#ddd", borderwidth=1),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # 변화율 요약 테이블
    st.subheader("변화율 요약")
    summary_rows = []
    for ing_id in selected_ids:
        ing_data = filtered[filtered["ingredient_id"] == ing_id].sort_values("date")
        if len(ing_data) < 2:
            continue
        first_val = ing_data.iloc[0]["value"]
        last_val = ing_data.iloc[-1]["value"]
        change = last_val - first_val
        pct = (change / first_val * 100) if first_val > 0 else 0
        ing_info = next((i for i in ingredients if i["id"] == ing_id), {})
        summary_rows.append({
            "성분": ing_info.get("name_kr", ing_id),
            "상태": STATUS_EMOJI.get(ing_info.get("status", ""), "") + " " + ing_info.get("status", ""),
            "시작값": f"{first_val:.1f}",
            "현재값": f"{last_val:.1f}",
            "변화": f"{'▲' if change > 0 else '▼'} {abs(change):.1f}",
            "변화율": f"{'+'if pct > 0 else ''}{pct:.1f}%",
        })

    if summary_rows:
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)


# ── View 3: 수동 입력 ──────────────────────────────────────────────
def view_manual_input(ingredients: list[dict], df_manual: pd.DataFrame):
    st.title("📋 수동 데이터 입력 — TikTok / Amazon")
    st.caption("C-Ratio와 TikTok 조회수는 자동 수집이 불가해 직접 입력합니다. Google Sheets에도 동시 저장됩니다.")

    with st.form("manual_form"):
        col1, col2 = st.columns(2)
        with col1:
            selected_id = st.selectbox(
                "성분",
                options=[i["id"] for i in ingredients],
                format_func=lambda x: next((f"{i['name_kr']} ({i['name_en']})" for i in ingredients if i["id"] == x), x),
            )
            tiktok_views = st.number_input("TikTok 해시태그 조회수 (만)", min_value=0.0, step=0.1)
        with col2:
            amazon_bsr = st.number_input("Amazon BSR Top 진입 제품 수", min_value=0, step=1)
            c_ratio_note = st.selectbox("C-Ratio 판단", ["높음", "중간", "낮음", "데이터 없음"])
        manual_note = st.text_area("메모 (선택)", height=80)
        submitted = st.form_submit_button("저장", type="primary")

    if submitted:
        try:
            from config.sheets_client import append_rows, TAB_MANUAL_INPUT
            ing_info = next(i for i in ingredients if i["id"] == selected_id)
            row = [
                date.today().isoformat(),
                selected_id,
                ing_info["name_kr"],
                tiktok_views,
                amazon_bsr,
                c_ratio_note,
                manual_note,
            ]
            append_rows(TAB_MANUAL_INPUT, [row])
            st.success(f"✅ {ing_info['name_kr']} 데이터 저장 완료")
            st.cache_data.clear()
        except Exception as e:
            st.error(f"저장 실패: {e}")

    st.divider()
    st.subheader("저장된 수동 데이터")
    if df_manual.empty:
        st.info("아직 입력된 데이터가 없습니다.")
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

    # ── R-Score ──────────────────────────────────────────────────
    st.divider()
    r = cfg["r_score"]
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
        f"R-Score `{int(fw['r_score']*100)}%` + "
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
    """로그인 래퍼. auth_config.yaml이 없거나 비밀번호 미설정 시 로그인 없이 실행."""
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

        name, auth_status, username = authenticator.login("Beauty OS — 로그인", "main")

        if auth_status is False:
            st.error("아이디 또는 비밀번호가 틀렸습니다.")
        elif auth_status is None:
            st.info("아이디와 비밀번호를 입력하세요.")
        else:
            authenticator.logout("로그아웃", "sidebar")
            st.sidebar.caption(f"👤 {name}")
            main()

    except FileNotFoundError:
        main()  # auth_config.yaml 없으면 로그인 없이 실행
    except ImportError:
        main()  # streamlit-authenticator 미설치 시 로그인 없이 실행
    except Exception as e:
        st.warning(f"로그인 설정 오류 (로그인 없이 실행): {e}")
        main()


# ── 메인 ───────────────────────────────────────────────────────────
def main():
    ingredients = load_ingredients_config()
    df_raw, df_manual = load_sheets_data()
    view = sidebar()

    if view == "📊 As-Is 매트릭스":
        view_matrix(ingredients, df_raw, df_manual)
    elif view == "📈 시계열 분석":
        view_timeseries(ingredients, df_raw)
    elif view == "📋 수동 입력 (TikTok/Amazon)":
        view_manual_input(ingredients, df_manual)
    elif view == "⚙️ 지표 방법론":
        view_methodology()
    elif view == "📺 채널 관리":
        view_channel_admin()


if __name__ == "__main__":
    run_with_auth()

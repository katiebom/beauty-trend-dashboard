"""
Google Trends 수집기 v2
─────────────────────────────────────────────────────
변경 사항:
  1. V-Index 베이스라인 수정: 변화없음=0, 하락=음수(-100~+100)
  2. 절대값 로그 스케일 적용: 신규 성분 착시 보정
  3. YoY 계절성 필터: 봄 자외선차단제 등 계절적 급등 페널티
─────────────────────────────────────────────────────
"""

import sys
import os
import time
import yaml
import numpy as np
from datetime import datetime, date
from pytrends.request import TrendReq

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.sheets_client import append_rows, TAB_RAW_TRENDS

YAML_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "ingredients.yaml")
REQUEST_DELAY = 6


def load_ingredients() -> list[dict]:
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["ingredients"]


def log_scale(raw: float) -> float:
    """
    절대 관심도를 로그 스케일로 변환 (0~100 유지)
    - 목적: 히알루론산(raw=90)과 신규 성분(raw=15)의 절대값 착시 완화
    - 5→15 (3배 급등): 선형 5→15,  로그 38.8→60.1 (차이를 더 잘 포착)
    - 90→95 (소폭 상승): 선형 5p,  로그 97.5→98.6 (스테디셀러 과대평가 억제)
    """
    return np.log1p(raw) / np.log1p(100) * 100


def calculate_yoy_factor(weekly_values: list[float]) -> tuple[float, bool]:
    """
    전년 동기 대비(YoY) 성장률 계산
    - 반환: (yoy_ratio, is_seasonal_spike)
    - is_seasonal_spike=True: 계절성으로 인한 단기 급등 의심 → 페널티 적용
    """
    if len(weekly_values) < 56:   # 최소 52주 + 4주 여유
        return 1.0, False

    recent_4w = np.mean(weekly_values[-4:])
    same_period_ly = np.mean(weekly_values[-56:-52])  # 1년 전 같은 시기

    if same_period_ly < 1:
        return 1.0, False

    yoy_ratio = recent_4w / same_period_ly

    # 계절성 의심: 최근 3개월 급등이지만 YoY로는 별로 안 올랐을 때
    recent_12w = np.mean(weekly_values[-12:])
    prev_12w_avg = np.mean(weekly_values[-24:-12])
    short_term_ratio = recent_12w / max(prev_12w_avg, 1)
    is_seasonal = (short_term_ratio > 1.4) and (yoy_ratio < 1.2)

    return round(yoy_ratio, 3), is_seasonal


def calculate_v_index(weekly_values: list[float]) -> dict:
    """
    V-Index v2 계산
    ─────────────────────────────────────────────────────
    반환: dict with keys
      v_index      : 최종 점수 (-100 ~ +100)
      velocity     : 순수 가속도 (-100 ~ +100), 0 = 변화없음
      log_absolute : 로그 스케일 절대값 (0~100)
      yoy_ratio    : 전년 동기 대비 (1.0 = 동일)
      is_seasonal  : 계절성 급등 의심 여부
    ─────────────────────────────────────────────────────
    """
    if len(weekly_values) < 8:
        return {"v_index": 0.0, "velocity": 0.0, "log_absolute": 0.0,
                "yoy_ratio": 1.0, "is_seasonal": False}

    recent = weekly_values[-12:] if len(weekly_values) >= 12 else weekly_values
    prev_end = len(weekly_values) - 12
    prev_start = max(0, prev_end - 12)
    previous = weekly_values[prev_start:prev_end] if prev_end > prev_start else weekly_values[:len(weekly_values) // 2]

    recent_avg = float(np.mean(recent)) if recent else 0.0
    prev_avg = float(np.mean(previous)) if previous else 1.0

    # ── 가속도: 1.0 기준, 음수 허용 ───────────────────────────────
    if prev_avg < 1:
        velocity = 0.0
    else:
        ratio = recent_avg / prev_avg
        # (ratio - 1.0) × 100  → 0배=−100, 1.0배=0, 2.0배=+100
        velocity = float(np.clip((ratio - 1.0) * 100, -100, 100))

    # ── 절대값 로그 스케일 ────────────────────────────────────────
    log_abs = log_scale(recent_avg)

    # ── YoY 계절성 필터 ──────────────────────────────────────────
    yoy_ratio, is_seasonal = calculate_yoy_factor(weekly_values)
    seasonality_factor = 0.65 if is_seasonal else 1.0

    # ── 최종 합산: velocity 60% + log_absolute 40% + 계절성 조정 ─
    v_raw = velocity * 0.6 + log_abs * 0.4
    v_index = float(np.clip(v_raw * seasonality_factor, -100, 100))

    return {
        "v_index": round(v_index, 1),
        "velocity": round(velocity, 1),
        "log_absolute": round(log_abs, 1),
        "yoy_ratio": yoy_ratio,
        "is_seasonal": is_seasonal,
    }


def collect_ingredient(pytrends: TrendReq, ingredient: dict, today: str) -> list[list]:
    rows = []
    keywords = ingredient.get("google_keywords", [])
    if not keywords:
        return rows

    kw_batch = keywords[:5]

    try:
        # 5년 데이터 요청: YoY 계절성 계산을 위해
        pytrends.build_payload(kw_batch, timeframe="today 5-y", geo="")
        interest_df = pytrends.interest_over_time()

        if interest_df.empty:
            print(f"  [trends] 데이터 없음: {ingredient['id']}")
            return rows

        collected_at = datetime.now().isoformat(timespec="seconds")

        for kw in kw_batch:
            if kw not in interest_df.columns:
                continue
            values = interest_df[kw].tolist()
            result = calculate_v_index(values)

            # V-Index 최종값
            rows.append([today, ingredient["id"], ingredient["name_kr"],
                         "google_trends", "v_index", result["v_index"], collected_at])
            # 세부 지표들
            rows.append([today, ingredient["id"], ingredient["name_kr"],
                         "google_trends", "velocity", result["velocity"], collected_at])
            rows.append([today, ingredient["id"], ingredient["name_kr"],
                         "google_trends", "log_absolute", result["log_absolute"], collected_at])
            rows.append([today, ingredient["id"], ingredient["name_kr"],
                         "google_trends", "yoy_ratio", result["yoy_ratio"], collected_at])
            rows.append([today, ingredient["id"], ingredient["name_kr"],
                         "google_trends", "is_seasonal", int(result["is_seasonal"]), collected_at])

        seasonal_flag = "⚠️ 계절성 의심" if result.get("is_seasonal") else ""
        print(f"  [trends] {ingredient['name_kr']} → "
              f"V-Index: {result['v_index']} "
              f"(velocity={result['velocity']}, log_abs={result['log_absolute']}, "
              f"yoy={result['yoy_ratio']}) {seasonal_flag}")

    except Exception as e:
        print(f"  [trends] 오류 {ingredient['id']}: {e}")

    return rows


def run():
    print("=== Google Trends 수집 시작 (v2) ===")
    ingredients = load_ingredients()
    today = date.today().isoformat()
    pytrends = TrendReq(hl="en-US", tz=540, timeout=(10, 25), retries=2, backoff_factor=0.5)

    all_rows = []
    for i, ing in enumerate(ingredients):
        print(f"[{i+1}/{len(ingredients)}] {ing['name_kr']} 수집 중...")
        rows = collect_ingredient(pytrends, ing, today)
        all_rows.extend(rows)
        if i < len(ingredients) - 1:
            time.sleep(REQUEST_DELAY)

    if all_rows:
        append_rows(TAB_RAW_TRENDS, all_rows)
        print(f"\n✅ Google Trends 수집 완료 — {len(all_rows)}행 저장")
    else:
        print("\n⚠️  저장된 데이터 없음")


if __name__ == "__main__":
    run()

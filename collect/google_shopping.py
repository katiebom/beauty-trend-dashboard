"""
Google Shopping Trends 수집기
─────────────────────────────────────────────────────
일반 Google Trends(검색 관심도)와 달리 Google Shopping 검색에 특화.
gprop='froogle' → 실제 구매 의도(상품 검색)를 측정하므로 V-Index보다
판매 전환에 훨씬 가까운 신호.

지표: gs_index (-100 ~ +100)  — V-Index와 동일 공식, Shopping 데이터 기반
     gs_velocity / gs_log_absolute 보조 지표

V-Index(일반 검색) vs GS-Index(쇼핑 검색) 격차가 크면:
  - V↑ GS↓ → 관심은 있지만 아직 살 생각은 없음 (인지 단계)
  - V↑ GS↑ → 관심 + 구매 의도 동시 상승 → 가장 강한 런치 신호
─────────────────────────────────────────────────────
"""

import sys
import os
import time
import yaml
import numpy as np
from datetime import datetime, date
from pytrends.request import TrendReq
from pytrends.exceptions import TooManyRequestsError

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.sheets_client import append_rows, TAB_RAW_TRENDS

YAML_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "ingredients.yaml")
REQUEST_DELAY = 7   # Shopping API는 일반보다 약간 더 보수적으로
MAX_RETRIES = 3


def load_ingredients() -> list[dict]:
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["ingredients"]


def calculate_gs_index(weekly_values: list[float]) -> dict:
    """V-Index와 동일 공식 — Shopping 데이터용"""
    if len(weekly_values) < 8:
        return {"gs_index": 0.0, "gs_velocity": 0.0, "gs_log_absolute": 0.0}

    recent = weekly_values[-12:] if len(weekly_values) >= 12 else weekly_values
    prev_end = len(weekly_values) - 12
    prev_start = max(0, prev_end - 12)
    previous = weekly_values[prev_start:prev_end] if prev_end > prev_start else weekly_values[:len(weekly_values) // 2]

    recent_avg = float(np.mean(recent)) if recent else 0.0
    prev_avg = float(np.mean(previous)) if previous else 1.0

    if prev_avg < 1:
        velocity = 0.0
    else:
        velocity = float(np.clip((recent_avg / prev_avg - 1.0) * 100, -100, 100))

    log_abs = float(np.log1p(recent_avg) / np.log1p(100) * 100)
    gs_index = float(np.clip(velocity * 0.6 + log_abs * 0.4, -100, 100))

    return {
        "gs_index":        round(gs_index, 1),
        "gs_velocity":     round(velocity, 1),
        "gs_log_absolute": round(log_abs, 1),
    }


def collect_one(pytrends: TrendReq, ingredient: dict, today: str) -> list[list]:
    """US Google Shopping 트렌드 수집 (영어 키워드만)"""
    keywords = [
        kw for kw in ingredient.get("google_keywords", [])
        if not any("가" <= ch <= "힣" for ch in kw)
    ]
    if not keywords:
        return []

    kw_batch = keywords[:5]
    rows = []
    interest_df = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            pytrends.build_payload(
                kw_batch,
                timeframe="today 5-y",
                geo="US",
                gprop="froogle",   # ← Shopping 검색 특화
            )
            interest_df = pytrends.interest_over_time()
            break
        except TooManyRequestsError:
            wait = 30 * (2 ** (attempt - 1))
            print(f"  [shopping] 429 — {wait}s 대기 ({attempt}/{MAX_RETRIES})")
            time.sleep(wait)
            if attempt == MAX_RETRIES:
                print(f"  [shopping] 재시도 초과: {ingredient['id']}")
                return []
        except Exception as e:
            print(f"  [shopping] 오류 {ingredient['id']}: {e}")
            return []

    if interest_df is None or interest_df.empty:
        print(f"  [shopping] 데이터 없음: {ingredient['id']}")
        return []

    collected_at = datetime.now().isoformat(timespec="seconds")
    result = {}

    for kw in kw_batch:
        if kw not in interest_df.columns:
            continue
        values = interest_df[kw].tolist()
        result = calculate_gs_index(values)

        rows.append([today, ingredient["id"], ingredient["name_kr"],
                     "google_shopping", "gs_index", result["gs_index"], collected_at])
        rows.append([today, ingredient["id"], ingredient["name_kr"],
                     "google_shopping", "gs_velocity", result["gs_velocity"], collected_at])
        rows.append([today, ingredient["id"], ingredient["name_kr"],
                     "google_shopping", "gs_log_absolute", result["gs_log_absolute"], collected_at])

    if result:
        diff = ""
        print(f"  [US Shopping] {ingredient['name_kr']} → gs_index: {result['gs_index']} "
              f"(velocity={result['gs_velocity']})")

    return rows


def run():
    print("=== Google Shopping Trends 수집 시작 ===")
    ingredients = load_ingredients()
    today = date.today().isoformat()
    pytrends = TrendReq(hl="en-US", tz=540, timeout=(10, 25))

    all_rows = []
    for i, ing in enumerate(ingredients):
        print(f"[{i+1}/{len(ingredients)}] {ing['name_kr']}...")
        rows = collect_one(pytrends, ing, today)
        all_rows.extend(rows)
        if i < len(ingredients) - 1:
            time.sleep(REQUEST_DELAY)

    if all_rows:
        append_rows(TAB_RAW_TRENDS, all_rows, dedup_source="google_shopping")
        print(f"\n✅ Google Shopping 수집 완료 — {len(all_rows)}행 저장")
    else:
        print("\n⚠️  저장된 데이터 없음")


if __name__ == "__main__":
    run()

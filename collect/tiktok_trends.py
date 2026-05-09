"""
TikTok T-Score 수집기 v1
─────────────────────────────────────────────────────
데이터: TikTok 해시태그 공개 엔드포인트 (로그인/API키 불필요)
지표:   T-Score (0~100) — TikTok 해시태그 성장 모멘텀

T-Score 계산 방식:
  - 누적 조회수(viewCount)를 매주 스냅샷으로 저장
  - 첫 실행: T-Score = 50 (베이스라인 기록만)
  - 이후 실행: 주간 증가량 기반 모멘텀 계산
    weekly_delta = current - prev
    growth_rate  = weekly_delta / prev  (%)
    T-Score      = clip(50 + growth_rate × 800, 0, 100)
      → 주간 +6% 성장이면 T-Score ≈ 98 (폭발적)
      → 주간 +1% 성장이면 T-Score ≈ 58 (안정 성장)
      → 주간 +0% 성장이면 T-Score ≈ 50 (정체)

절대 규모 보정:
  - viewCount 자체도 log 스케일로 정규화 → 작은 성분의 급등 포착
  - T-Score = growth_score × 0.7 + size_score × 0.3
─────────────────────────────────────────────────────
"""

import os
import sys
import time
import yaml
import json
import math
import requests
from datetime import date, datetime
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.sheets_client import append_rows, read_all, TAB_RAW_TRENDS

load_dotenv()

YAML_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "ingredients.yaml")
TIKTOK_API = "https://www.tiktok.com/api/challenge/detail/"
REQUEST_DELAY = 0.8

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.tiktok.com/",
}


def load_ingredients() -> list[dict]:
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["ingredients"]


def get_tiktok_hashtags(ing: dict) -> list[str]:
    """성분별 TikTok 해시태그 목록 반환 (tiktok_hashtags 필드 우선, 없으면 name_en 기반 자동 생성)"""
    if ing.get("tiktok_hashtags"):
        return ing["tiktok_hashtags"]

    name_en = ing["name_en"].split()[0].lower()  # 첫 단어만
    # 괄호 제거
    name_en = name_en.replace("(", "").replace(")", "").strip()
    return [name_en, f"{name_en}skincare"]


def fetch_hashtag_views(hashtag: str) -> int | None:
    """해시태그 누적 조회수 반환. 실패 시 None."""
    try:
        r = requests.get(
            TIKTOK_API,
            params={"challengeName": hashtag},
            headers=HEADERS,
            timeout=10,
        )
        if r.status_code == 404:
            return None  # 해시태그 없음 — 정상적 부재
        if r.status_code != 200:
            print(f"  [tiktok] #{hashtag} HTTP {r.status_code}")
            return None
        data = r.json()
        sv2 = data.get("challengeInfo", {}).get("statsV2", {})
        vc = sv2.get("viewCount", "0")
        views = int(vc)
        return views if views > 0 else None  # 0은 None 처리 (미존재와 동일)
    except (ValueError, TypeError):
        return None
    except Exception as e:
        print(f"  [tiktok] #{hashtag} 오류: {e}")
        return None


def get_best_view_count(hashtags: list[str]) -> tuple[int, str]:
    """여러 해시태그 중 가장 많은 조회수를 가진 것 반환"""
    best = 0
    best_tag = hashtags[0]
    for tag in hashtags:
        views = fetch_hashtag_views(tag)
        if views and views > best:
            best = views
            best_tag = tag
        time.sleep(REQUEST_DELAY)
    return best, best_tag


def load_prev_view_counts(ingredients: list[dict]) -> dict[str, int]:
    """
    Sheets에서 직전 t_view_count 로드.
    현재 사용할 최대 해시태그 조회수보다 10배 이상 크면 해시태그 변경으로 간주, 리셋.
    """
    prev = {}
    try:
        rows = read_all(TAB_RAW_TRENDS)
        for row in rows:
            if row.get("source") == "tiktok" and row.get("metric_name") == "t_view_count":
                ing_id = row["ingredient_id"]
                try:
                    v = int(float(row["value"]))
                    # 가장 최근(최대) 값 보관
                    if ing_id not in prev or v > prev[ing_id]:
                        prev[ing_id] = v
                except (ValueError, TypeError):
                    pass
    except Exception as e:
        print(f"  [tiktok] 이전 데이터 로드 실패: {e}")
    return prev


def is_valid_comparison(current: int, prev: int) -> bool:
    """
    해시태그 변경 감지: current가 prev의 20% 미만이면 해시태그 변경으로 간주 → 비교 무효
    """
    if prev == 0:
        return True
    return current >= prev * 0.5


def calculate_t_score(current_views: int, prev_views: int | None) -> dict:
    """
    T-Score 계산
    - 첫 실행(prev=None): size 기반 베이스라인만
    - 이후: 주간 성장률 × 0.7 + size × 0.3
    """
    # 절대 규모 점수 (log 스케일, 1억 조회 = ~75점)
    size_score = min(100.0, math.log1p(current_views) / math.log1p(5e10) * 100)

    if prev_views is None or prev_views == 0:
        # 첫 실행: size만 반영, 중간값으로 보정
        t_score = size_score * 0.5 + 50 * 0.5
        growth_rate = None
        weekly_delta = None
    else:
        weekly_delta = current_views - prev_views
        growth_rate = weekly_delta / prev_views if prev_views > 0 else 0
        # 성장 점수: 주간 +6% → 98점, +1% → 58점, 0% → 50점
        growth_score = min(100.0, max(0.0, 50 + growth_rate * 800))
        t_score = growth_score * 0.7 + size_score * 0.3

    return {
        "t_score": round(t_score, 1),
        "t_view_count": current_views,
        "t_weekly_delta": weekly_delta,
        "t_growth_rate": round(growth_rate * 100, 2) if growth_rate is not None else None,
        "t_size_score": round(size_score, 1),
    }


def run():
    print("=== T-Score 수집 시작 (TikTok Hashtag) ===")
    ingredients = load_ingredients()
    today = date.today().isoformat()
    collected_at = datetime.now().isoformat(timespec="seconds")

    # 이전 데이터 로드
    prev_counts = load_prev_view_counts(ingredients)
    is_first_run = len(prev_counts) == 0
    if is_first_run:
        print("  → 첫 실행: 베이스라인 저장 (T-Score는 다음 실행부터 의미 있음)")
    else:
        print(f"  → 이전 데이터 {len(prev_counts)}개 성분 로드됨")

    all_rows = []

    for i, ing in enumerate(ingredients):
        ing_id = ing["id"]
        hashtags = get_tiktok_hashtags(ing)
        print(f"[{i+1}/{len(ingredients)}] {ing['name_kr']} ({', '.join(['#'+h for h in hashtags[:2]])})...")

        current_views, best_tag = get_best_view_count(hashtags)

        if current_views == 0:
            tried = ', '.join(['#' + h for h in hashtags])
            print(f"  → 데이터 없음 — 시도한 해시태그: {tried}")
            print(f"     → tiktok_hashtags 필드를 ingredients.yaml에 수동 지정 권장")
            continue

        prev = prev_counts.get(ing_id)
        # 해시태그 변경으로 인한 이상 비교 방지
        if prev is not None and not is_valid_comparison(current_views, prev):
            print(f"  → 해시태그 변경 감지 (이전:{prev/1e8:.1f}억 → 현재:{current_views/1e8:.1f}억) → 베이스라인 리셋")
            prev = None
        scores = calculate_t_score(current_views, prev)

        growth_str = f"+{scores['t_growth_rate']:.2f}%/주" if scores['t_growth_rate'] is not None else "첫수집"
        print(f"  → #{best_tag}: {current_views/1e8:.1f}억 조회 | T-Score: {scores['t_score']} ({growth_str})")

        for metric, value in scores.items():
            if value is None:
                continue
            all_rows.append([
                today, ing_id, ing["name_kr"],
                "tiktok", metric, value, collected_at,
            ])

    if all_rows:
        append_rows(TAB_RAW_TRENDS, all_rows, dedup_source="tiktok")
        print(f"\n✅ T-Score 수집 완료 — {len(all_rows)}행 저장")
        if is_first_run:
            print("  ℹ️  다음 주 실행 시 성장률 기반 T-Score가 계산됩니다")
    else:
        print("\n⚠️  저장된 데이터 없음")


if __name__ == "__main__":
    run()

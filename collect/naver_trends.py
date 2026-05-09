"""
Naver DataLab N-Score 수집기 v1
─────────────────────────────────────────────────────
데이터: 네이버 데이터랩 검색어 트렌드 API (무료)
지표:   N-Score (0~100) — 한국 네이버 검색 트렌드 기반 모멘텀

N-Score 계산:
  - 최근 3개월 avg vs 이전 3개월 avg → velocity
  - 로그 절대값 보정 (신규 성분 착시 방지)
  - N-Score = velocity×0.6 + log_absolute×0.4  →  0~100 클리핑

준비:
  .env에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 필요
  → developers.naver.com → 앱 등록 → 데이터랩(검색어트렌드) 권한
─────────────────────────────────────────────────────
"""

import os
import sys
import time
import json
import yaml
import numpy as np
import requests
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.sheets_client import append_rows, TAB_RAW_TRENDS

load_dotenv()

YAML_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "ingredients.yaml")
NAVER_API_URL = "https://openapi.naver.com/v1/datalab/search"
REQUEST_DELAY = 1.0
MAX_RETRIES = 3


def load_ingredients() -> list[dict]:
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["ingredients"]


def get_naver_keywords(ing: dict) -> list[str]:
    """
    성분별 네이버 검색 키워드 추출.
    naver_keywords 필드가 있으면 우선 사용, 없으면 name_kr + 한국어 google_keywords 추출.
    """
    if ing.get("naver_keywords"):
        return ing["naver_keywords"][:5]

    kws = [ing["name_kr"]]
    for gk in ing.get("google_keywords", []):
        # 한글 포함 키워드만 추출
        if any("가" <= ch <= "힣" for ch in gk):
            kws.append(gk)
    return list(dict.fromkeys(kws))[:5]  # 중복 제거, 최대 5개


def calculate_n_score(monthly_values: list[float]) -> dict:
    """
    N-Score 계산 (월간 데이터 기반)
    반환: {n_score, velocity, log_absolute}
    """
    if len(monthly_values) < 4:
        return {"n_score": 50.0, "velocity": 0.0, "log_absolute": 50.0}

    recent = monthly_values[-3:]
    prev_end = len(monthly_values) - 3
    prev_start = max(0, prev_end - 3)
    previous = monthly_values[prev_start:prev_end]

    recent_avg = float(np.mean(recent))
    prev_avg = float(np.mean(previous)) if previous else 1.0

    if prev_avg < 1:
        velocity = 0.0
    else:
        ratio = recent_avg / prev_avg
        velocity = float(np.clip((ratio - 1.0) * 100, -100, 100))

    # 로그 절대값 (0~100 유지)
    log_abs = float(np.log1p(recent_avg) / np.log1p(100) * 100)

    # velocity를 -100~+100에서 0~100으로 정규화
    v_normalized = (velocity + 100) / 2

    n_score = float(np.clip(v_normalized * 0.6 + log_abs * 0.4, 0, 100))

    return {
        "n_score": round(n_score, 1),
        "velocity": round(velocity, 1),
        "log_absolute": round(log_abs, 1),
    }


def fetch_naver_batch(client_id: str, client_secret: str, groups: list[dict]) -> dict:
    """
    groups: [{"groupName": str, "keywords": [str]}]  — 최대 5개 그룹
    반환: {groupName: [ratio 값 리스트]}
    """
    end_date = date.today().replace(day=1) - relativedelta(days=1)
    start_date = end_date - relativedelta(months=12)

    payload = {
        "startDate": start_date.strftime("%Y-%m-%d"),
        "endDate":   end_date.strftime("%Y-%m-%d"),
        "timeUnit":  "month",
        "keywordGroups": groups,
    }
    headers = {
        "X-Naver-Client-Id":     client_id,
        "X-Naver-Client-Secret": client_secret,
        "Content-Type":          "application/json",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        resp = requests.post(NAVER_API_URL, json=payload, headers=headers, timeout=15)
        if resp.status_code == 429:
            wait = 20 * (2 ** (attempt - 1))  # 20s, 40s, 80s
            print(f"  [naver] 429 Rate limit — {wait}s 대기 후 재시도 ({attempt}/{MAX_RETRIES})")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        break
    else:
        raise requests.HTTPError(f"429 rate limit: {MAX_RETRIES}회 재시도 모두 실패")

    data = resp.json()
    result = {}
    for item in data.get("results", []):
        values = [pt["ratio"] for pt in item.get("data", [])]
        result[item["title"]] = values
    return result


def run():
    client_id     = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("⚠️  NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수 없음 — N-Score 수집 스킵")
        return

    print("=== N-Score 수집 시작 (Naver DataLab) ===")
    ingredients = load_ingredients()
    today = date.today().isoformat()
    collected_at = datetime.now().isoformat(timespec="seconds")

    # 5개씩 배치
    BATCH = 5
    all_rows = []

    for batch_start in range(0, len(ingredients), BATCH):
        batch = ingredients[batch_start: batch_start + BATCH]
        groups = []
        for ing in batch:
            kws = get_naver_keywords(ing)
            groups.append({"groupName": ing["id"], "keywords": kws})

        batch_names = [ing["name_kr"] for ing in batch]
        print(f"[{batch_start+1}~{batch_start+len(batch)}] 수집 중: {', '.join(batch_names)}")

        try:
            results = fetch_naver_batch(client_id, client_secret, groups)
        except requests.HTTPError as e:
            print(f"  [naver] HTTP 오류: {e}")
            time.sleep(REQUEST_DELAY * 2)
            continue
        except Exception as e:
            print(f"  [naver] 오류: {e}")
            time.sleep(REQUEST_DELAY * 2)
            continue

        for ing in batch:
            values = results.get(ing["id"], [])
            if not values:
                print(f"  [naver] 데이터 없음: {ing['name_kr']}")
                continue

            score = calculate_n_score(values)

            for metric, value in score.items():
                all_rows.append([
                    today, ing["id"], ing["name_kr"],
                    "naver_datalab", metric, value, collected_at,
                ])

            print(f"  {ing['name_kr']} → N-Score: {score['n_score']} "
                  f"(velocity={score['velocity']}, log_abs={score['log_absolute']})")

        time.sleep(REQUEST_DELAY)

    if all_rows:
        append_rows(TAB_RAW_TRENDS, all_rows, dedup_source="naver_datalab")
        print(f"\n✅ N-Score 수집 완료 — {len(all_rows)}행 저장")
    else:
        print("\n⚠️  저장된 데이터 없음")


if __name__ == "__main__":
    run()

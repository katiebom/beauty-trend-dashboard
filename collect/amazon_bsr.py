"""
Amazon BSR (Best Seller Rank) 자동 수집기
─────────────────────────────────────────────────────
Amazon US Beauty 카테고리에서 성분별 검색 결과를 분석.
판매 실적과 직결되는 신호 — Google Trends / TikTok보다 "실제 구매" 에 가장 가까운 데이터.

수집 지표:
  amazon_bsr_rank        — 카테고리 내 BSR (숫자 낮을수록 잘 팔림). 상위 제품 기준.
  amazon_bestseller_count — 검색 결과 1페이지 내 Best Seller 배지 개수
  amazon_result_count    — 검색 결과 총 건수 (시장 규모 proxy)
  amazon_avg_rating      — 상위 5개 제품 평균 별점
  amazon_review_total    — 상위 5개 제품 리뷰수 합계

⚠️  Amazon 봇 감지 주의:
  - fake-useragent로 UA 로테이션
  - 요청 간 랜덤 딜레이 (3~8초)
  - 봇 감지(403/503/CAPTCHA) 시 해당 성분 스킵 후 계속
  - 너무 많은 요청 시 IP 차단 가능 → 하루 1회 실행 권장
─────────────────────────────────────────────────────
"""

import os
import sys
import time
import random
import re
import yaml
import requests
from datetime import date, datetime
from bs4 import BeautifulSoup

try:
    from fake_useragent import UserAgent
    _ua = UserAgent()
    def get_ua() -> str:
        return _ua.random
except Exception:
    _FALLBACK_UAS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    ]
    def get_ua() -> str:
        return random.choice(_FALLBACK_UAS)


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.sheets_client import append_rows, TAB_RAW_TRENDS

YAML_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "ingredients.yaml")

SEARCH_URL = "https://www.amazon.com/s"
REQUEST_DELAY_MIN = 3.5
REQUEST_DELAY_MAX = 8.0
MAX_RETRIES = 2


def load_ingredients() -> list[dict]:
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["ingredients"]


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


def _is_bot_blocked(resp: requests.Response) -> bool:
    """봇 차단 여부 감지"""
    if resp.status_code in (403, 503):
        return True
    text = resp.text[:2000].lower()
    return "robot check" in text or "captcha" in text or "automated" in text or "api.amazon" in text


def _parse_int(text: str) -> int | None:
    """숫자 문자열 파싱 ('1,234' → 1234)"""
    if not text:
        return None
    cleaned = re.sub(r"[^\d]", "", text)
    return int(cleaned) if cleaned else None


def fetch_amazon_search(session: requests.Session, query: str) -> dict | None:
    """
    Amazon US Beauty 검색 결과 1페이지 파싱.
    봇 감지 시 None 반환.
    """
    params = {
        "k": query,
        "i": "beauty",
        "s": "review-rank",  # 리뷰 많은 순 정렬 (인기 제품 우선)
        "ref": "nb_sb_noss",
    }
    session.headers["User-Agent"] = get_ua()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(SEARCH_URL, params=params, timeout=15)
            if _is_bot_blocked(resp):
                print(f"  [amazon] 봇 감지 — 쿼리: '{query}' (HTTP {resp.status_code})")
                return None
            if resp.status_code != 200:
                print(f"  [amazon] HTTP {resp.status_code} — '{query}'")
                if attempt < MAX_RETRIES:
                    time.sleep(20)
                continue
            return _parse_search_page(resp.text)
        except requests.Timeout:
            print(f"  [amazon] 타임아웃 — '{query}' ({attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES:
                time.sleep(10)
        except Exception as e:
            print(f"  [amazon] 오류 — '{query}': {e}")
            return None

    return None


def _parse_search_page(html: str) -> dict:
    """검색 결과 HTML 파싱 → 지표 dict"""
    soup = BeautifulSoup(html, "html.parser")

    # 검색 결과 총 건수
    result_count = None
    count_el = soup.select_one("span.a-color-state.a-text-bold")
    if count_el:
        result_count = _parse_int(count_el.get_text())

    # 상위 제품 카드 추출
    products = soup.select("div[data-component-type='s-search-result']")

    bestseller_count = 0
    ratings = []
    review_counts = []
    bsr_candidates = []

    for prod in products[:10]:  # 상위 10개만
        # Best Seller 배지
        badge_text = prod.get_text()
        if "Best Seller" in badge_text or "best seller" in badge_text.lower():
            bestseller_count += 1

        # 별점
        rating_el = prod.select_one("span.a-icon-alt")
        if rating_el:
            m = re.search(r"([\d.]+) out of 5", rating_el.get_text())
            if m:
                try:
                    ratings.append(float(m.group(1)))
                except ValueError:
                    pass

        # 리뷰 수
        review_el = prod.select_one("span.s-underline-text")
        if review_el:
            rc = _parse_int(review_el.get_text())
            if rc:
                review_counts.append(rc)

        # BSR 힌트 (검색 결과 페이지에서는 직접 노출 안 됨 — 리뷰수로 순위 proxy)
        if review_counts:
            bsr_candidates.append(review_counts[-1])

    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None
    review_total = sum(review_counts[:5]) if review_counts else None

    # BSR rank: 검색 결과 상위 제품의 리뷰수 기반 proxy
    # 실제 카테고리 BSR은 제품 상세 페이지에서만 확인 가능
    # → 여기서는 review_total을 proxy로 저장, 별도 필드로 구분
    bsr_proxy = review_counts[0] if review_counts else None  # 상위 제품 리뷰수

    return {
        "result_count": result_count,
        "bestseller_count": bestseller_count,
        "avg_rating": avg_rating,
        "review_total": review_total,
        "top_product_reviews": bsr_proxy,  # 상위 제품 리뷰수 (인기 proxy)
    }


def get_search_query(ing: dict) -> str:
    """성분별 Amazon 검색 쿼리 생성"""
    # amazon_keywords 필드 우선, 없으면 name_en 기반
    if ing.get("amazon_keywords"):
        return ing["amazon_keywords"][0]
    name_en = ing["name_en"].split("(")[0].strip()  # 괄호 제거
    return f"{name_en} serum"


def collect_one(session: requests.Session, ing: dict, today: str) -> list[list]:
    query = get_search_query(ing)
    print(f"  검색: '{query}'")

    data = fetch_amazon_search(session, query)
    if data is None:
        return []

    collected_at = datetime.now().isoformat(timespec="seconds")
    rows = []

    metric_map = {
        "amazon_result_count":     data.get("result_count"),
        "amazon_bestseller_count": data.get("bestseller_count"),
        "amazon_avg_rating":       data.get("avg_rating"),
        "amazon_review_total":     data.get("review_total"),
        "amazon_top_reviews":      data.get("top_product_reviews"),
    }

    for metric_name, value in metric_map.items():
        if value is None:
            continue
        rows.append([
            today, ing["id"], ing["name_kr"],
            "amazon_search", metric_name, value, collected_at,
        ])

    if rows:
        print(f"  → 결과: {data.get('result_count', '?')}건 | "
              f"배지: {data.get('bestseller_count', 0)}개 | "
              f"별점: {data.get('avg_rating', '?')} | "
              f"리뷰: {data.get('review_total', '?')}")

    return rows


def run():
    print("=== Amazon Search 수집 시작 ===")
    print("  ⚠️  봇 감지 가능 — 차단 시 해당 성분 스킵")
    ingredients = load_ingredients()
    today = date.today().isoformat()
    session = _make_session()

    all_rows = []
    blocked_count = 0

    for i, ing in enumerate(ingredients):
        print(f"[{i+1}/{len(ingredients)}] {ing['name_kr']}...")
        rows = collect_one(session, ing, today)

        if not rows:
            blocked_count += 1
            if blocked_count >= 3:
                print("\n🚨 연속 3회 차단 — 수집 중단. 내일 다시 시도하거나 VPN 사용 권장.")
                break
        else:
            blocked_count = 0
            all_rows.extend(rows)

        if i < len(ingredients) - 1:
            delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
            time.sleep(delay)

    if all_rows:
        append_rows(TAB_RAW_TRENDS, all_rows, dedup_source="amazon_search")
        print(f"\n✅ Amazon 수집 완료 — {len(all_rows)}행 저장")
    else:
        print("\n⚠️  저장된 데이터 없음 (전체 차단 또는 파싱 실패)")


if __name__ == "__main__":
    run()

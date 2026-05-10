"""
APLB Hero SKU VOC 수집기 — iHerb + YesStyle
────────────────────────────────────────────────────────────
수집 대상:
  - iHerb : 제품 리뷰 (별점, 리뷰 텍스트, 작성일, 국가)
  - YesStyle: 제품 리뷰 (별점, 리뷰 텍스트, 작성일)

결과 → Google Sheets: voc_raw 탭
  컬럼: collected_at, sku_id, name_kr, channel, rating, review_text,
         reviewer_country, review_date, review_id

실행:
  python collect/voc_scraper.py
  python collect/voc_scraper.py --sku gluta_niac_serum
  python collect/voc_scraper.py --dry-run   (Sheets 저장 없이 콘솔 출력)

⚠️  실행 전 aplb_products.yaml의 voc_sources에 실제 URL 입력 필요
    iHerb URL:    https://www.iherb.com/pr/.../XXXXX  (끝 숫자 = product_code)
    YesStyle URL: https://www.yesstyle.com/en/.../info.html/pid.XXXXXXX
────────────────────────────────────────────────────────────
"""

import os
import sys
import re
import time
import random
import json
import argparse
from datetime import datetime, date
from pathlib import Path

import requests
import yaml
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


ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))

APLB_YAML = ROOT / "config" / "aplb_products.yaml"
DELAY_MIN = 3.0
DELAY_MAX = 7.0
MAX_PAGES = 5       # 채널당 최대 페이지 (iHerb 10개/페이지 → 최대 50개)
MAX_REVIEWS = 100   # SKU당 채널당 최대 수집 건수


# ── 공통 유틸 ──────────────────────────────────────────────────────────────

def _sleep():
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


def _session(referer: str = "") -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": get_ua(),
        "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": referer,
    })
    return s


def load_hero_skus(target_sku: str | None = None) -> list[dict]:
    """voc_sources가 정의된 hero SKU만 반환."""
    with open(APLB_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    skus = []
    for p in data.get("products", []):
        if not p.get("bestseller"):
            continue
        sources = p.get("voc_sources", [])
        # URL이 비어있는 채널은 제외
        active_sources = [s for s in sources if s.get("url", "").strip()]
        if not active_sources:
            continue
        if target_sku and p["id"] != target_sku:
            continue
        p = dict(p)
        p["voc_sources"] = active_sources
        skus.append(p)
    return skus


# ── iHerb 스크래퍼 ─────────────────────────────────────────────────────────

def _iherb_reviews(product_code: str, max_reviews: int = MAX_REVIEWS) -> list[dict]:
    """
    iHerb 리뷰 수집.
    1차: 내부 JSON API 시도 (가장 깔끔)
    2차: HTML 파싱 fallback
    """
    reviews = _iherb_api(product_code, max_reviews)
    if reviews:
        return reviews
    print(f"  [iherb] API 실패 → HTML 파싱 시도")
    return _iherb_html(product_code, max_reviews)


def _iherb_api(product_code: str, max_reviews: int) -> list[dict]:
    """iHerb 내부 리뷰 API — JSON 응답."""
    results = []
    page = 1
    session = _session("https://www.iherb.com/")
    session.headers["Accept"] = "application/json, text/plain, */*"
    session.headers["X-Requested-With"] = "XMLHttpRequest"

    while len(results) < max_reviews and page <= MAX_PAGES:
        url = (
            f"https://www.iherb.com/ugc/api/products/{product_code}/reviews"
            f"?sortBy=date&pageSize=10&pageNumber={page}&lang=en-US"
        )
        try:
            r = session.get(url, timeout=20)
            if r.status_code != 200:
                break
            data = r.json()
            items = data.get("reviews") or data.get("items") or data.get("data") or []
            if not items:
                break
            for item in items:
                text = item.get("comments") or item.get("review") or item.get("body", "")
                rating = item.get("rating") or item.get("overallRating") or 0
                rev_date = item.get("date") or item.get("submissionTime") or ""
                country = item.get("userLocation") or item.get("countryCode") or ""
                rev_id = str(item.get("id") or item.get("reviewId") or "")
                if text and len(text.strip()) > 10:
                    results.append({
                        "channel": "iherb",
                        "rating": str(rating),
                        "review_text": text.strip(),
                        "reviewer_country": country,
                        "review_date": rev_date[:10] if rev_date else "",
                        "review_id": rev_id,
                    })
            if len(items) < 10:
                break
            page += 1
            _sleep()
        except Exception as e:
            print(f"  [iherb] API 오류 (page {page}): {e}")
            break

    return results


def _iherb_html(product_code: str, max_reviews: int) -> list[dict]:
    """iHerb 제품 페이지 HTML 파싱 fallback."""
    results = []
    session = _session("https://www.iherb.com/")
    base_url = f"https://www.iherb.com/pr/aplb/{product_code}"

    for page in range(1, MAX_PAGES + 1):
        url = base_url if page == 1 else f"{base_url}?p={page}"
        try:
            r = session.get(url, timeout=25)
            if r.status_code != 200:
                print(f"  [iherb-html] {r.status_code} — 차단 또는 잘못된 URL")
                break
            soup = BeautifulSoup(r.text, "html.parser")

            # iHerb 리뷰 컨테이너 — 실제 DOM 구조에 따라 selector 조정 필요
            review_blocks = (
                soup.select(".review-item")
                or soup.select("[data-qa='review-item']")
                or soup.select(".reviews-container .review")
            )
            if not review_blocks:
                # JSON-LD에서 리뷰 추출 시도
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        ld = json.loads(script.string or "")
                        for rev in ld.get("review", []):
                            text = rev.get("reviewBody", "")
                            rating = rev.get("reviewRating", {}).get("ratingValue", 0)
                            rev_date = rev.get("datePublished", "")[:10]
                            if text:
                                results.append({
                                    "channel": "iherb",
                                    "rating": str(rating),
                                    "review_text": text.strip(),
                                    "reviewer_country": "",
                                    "review_date": rev_date,
                                    "review_id": "",
                                })
                    except Exception:
                        pass
                if not results:
                    print("  [iherb-html] 리뷰 블록 없음. URL 또는 selector 확인 필요.")
                break

            for block in review_blocks:
                text_el = (
                    block.select_one(".review-content")
                    or block.select_one(".review-text")
                    or block.select_one("p")
                )
                rating_el = block.select_one("[class*='rating']")
                date_el = block.select_one(".review-date, time, [datetime]")
                country_el = block.select_one(".reviewer-location, .reviewer-country")

                text = text_el.get_text(strip=True) if text_el else ""
                rating = ""
                if rating_el:
                    rating_match = re.search(r"(\d[\d.]*)", rating_el.get("aria-label", "") or rating_el.get_text())
                    rating = rating_match.group(1) if rating_match else ""
                rev_date = (date_el.get("datetime") or date_el.get_text(strip=True))[:10] if date_el else ""
                country = country_el.get_text(strip=True) if country_el else ""

                if text and len(text) > 10:
                    results.append({
                        "channel": "iherb",
                        "rating": rating,
                        "review_text": text,
                        "reviewer_country": country,
                        "review_date": rev_date,
                        "review_id": "",
                    })

            if len(results) >= max_reviews:
                break
            _sleep()

        except Exception as e:
            print(f"  [iherb-html] 오류: {e}")
            break

    return results[:max_reviews]


# ── YesStyle 스크래퍼 ──────────────────────────────────────────────────────

def _yesstyle_reviews(product_id: str, url: str, max_reviews: int = MAX_REVIEWS) -> list[dict]:
    """YesStyle 제품 리뷰 수집."""
    results = []
    session = _session("https://www.yesstyle.com/")
    session.headers["Accept-Language"] = "en-US,en;q=0.9"

    # YesStyle 리뷰 AJAX API
    pid_clean = product_id.split("-")[0] if "-" in product_id else product_id

    for page in range(1, MAX_PAGES + 1):
        # 방법 1: AJAX 리뷰 API
        api_url = (
            f"https://www.yesstyle.com/en/pwa-api/product-reviews.json"
            f"?productId={pid_clean}&page={page}&pageSize=10&sortBy=recent"
        )
        try:
            r = session.get(api_url, timeout=20)
            if r.status_code == 200:
                data = r.json()
                items = (
                    data.get("reviews")
                    or data.get("data", {}).get("reviews")
                    or data.get("items")
                    or []
                )
                if items:
                    for item in items:
                        text = item.get("content") or item.get("comment") or item.get("review", "")
                        rating = item.get("rating") or item.get("score") or 0
                        rev_date = (item.get("createdAt") or item.get("date") or "")[:10]
                        rev_id = str(item.get("id") or "")
                        if text and len(text.strip()) > 5:
                            results.append({
                                "channel": "yesstyle",
                                "rating": str(rating),
                                "review_text": text.strip(),
                                "reviewer_country": "",
                                "review_date": rev_date,
                                "review_id": rev_id,
                            })
                    if len(items) < 10:
                        break
                    _sleep()
                    continue
        except Exception:
            pass

        # 방법 2: HTML 파싱 fallback
        page_url = url if page == 1 else f"{url}?page={page}"
        try:
            r = session.get(page_url, timeout=25)
            if r.status_code != 200:
                print(f"  [yesstyle] {r.status_code}")
                break
            soup = BeautifulSoup(r.text, "html.parser")

            # YesStyle 리뷰 selectors (실제 DOM에 따라 조정 가능)
            review_blocks = (
                soup.select(".review-item")
                or soup.select("[class*='reviewItem']")
                or soup.select(".product-review-item")
                or soup.select("[data-testid='review-item']")
            )
            if not review_blocks:
                print(f"  [yesstyle-html] 리뷰 블록 없음 (page {page}). URL/selector 확인 필요.")
                break

            for block in review_blocks:
                text_el = (
                    block.select_one(".review-content")
                    or block.select_one(".review-description")
                    or block.select_one("p")
                )
                rating_el = block.select_one("[class*='star'], [class*='rating']")
                date_el = block.select_one("time, .review-date, [class*='date']")

                text = text_el.get_text(strip=True) if text_el else ""
                rating_text = rating_el.get("aria-label", "") or (rating_el.get_text() if rating_el else "")
                rating_match = re.search(r"(\d[\d.]*)", rating_text)
                rating = rating_match.group(1) if rating_match else ""
                rev_date = (date_el.get("datetime") or date_el.get_text(strip=True))[:10] if date_el else ""

                if text and len(text) > 5:
                    results.append({
                        "channel": "yesstyle",
                        "rating": rating,
                        "review_text": text,
                        "reviewer_country": "",
                        "review_date": rev_date,
                        "review_id": "",
                    })

            if len(results) >= max_reviews or not review_blocks:
                break
            _sleep()

        except Exception as e:
            print(f"  [yesstyle-html] 오류: {e}")
            break

    return results[:max_reviews]


# ── 메인 ──────────────────────────────────────────────────────────────────

def collect_all(target_sku: str | None = None, dry_run: bool = False):
    skus = load_hero_skus(target_sku)
    if not skus:
        print("⚠️  수집 대상 SKU 없음.")
        print("   aplb_products.yaml의 hero SKU에 voc_sources URL을 입력하세요.")
        return

    all_rows = []
    collected_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    today = str(date.today())

    for sku in skus:
        sku_id = sku["id"]
        name_kr = sku["name_kr"]
        print(f"\n{'='*55}")
        print(f"SKU: {sku_id} | {name_kr}")

        for src in sku["voc_sources"]:
            channel = src["channel"]
            url = src.get("url", "").strip()
            if not url:
                print(f"  [{channel}] URL 미설정 — 스킵")
                continue

            print(f"  [{channel}] 수집 시작 → {url[:60]}...")

            if channel == "iherb":
                product_code = src.get("product_code", "").strip()
                if not product_code:
                    # URL에서 코드 추출 시도 (끝 숫자)
                    match = re.search(r"/(\d+)/?$", url)
                    product_code = match.group(1) if match else ""
                if not product_code:
                    print(f"  [iherb] product_code 없음 — URL 확인 필요")
                    continue
                reviews = _iherb_reviews(product_code)

            elif channel == "yesstyle":
                product_id = src.get("product_id", "").strip()
                if not product_id:
                    # URL에서 pid 추출 시도
                    match = re.search(r"pid\.([A-Z0-9\-]+)", url)
                    product_id = match.group(1) if match else ""
                reviews = _yesstyle_reviews(product_id, url)

            else:
                print(f"  [{channel}] 지원하지 않는 채널")
                continue

            print(f"  [{channel}] {len(reviews)}건 수집")
            for rev in reviews:
                all_rows.append([
                    collected_at,
                    sku_id,
                    name_kr,
                    rev["channel"],
                    rev["rating"],
                    rev["review_text"][:2000],  # Sheets 셀 한도
                    rev["reviewer_country"],
                    rev["review_date"],
                    rev["review_id"],
                    today,  # batch_date (dedup 키)
                ])
            _sleep()

    print(f"\n✅ 총 {len(all_rows)}건 수집 완료")

    if dry_run:
        print("\n[DRY-RUN] Sheets 저장 생략. 샘플 출력:")
        for row in all_rows[:3]:
            print(f"  {row[1]} | {row[3]} | ★{row[4]} | {row[5][:60]}...")
        return

    if not all_rows:
        print("저장할 데이터 없음.")
        return

    from config.sheets_client import append_rows, TAB_VOC_RAW
    append_rows(TAB_VOC_RAW, all_rows, dedup_col="batch_date")
    print(f"✅ Sheets [{TAB_VOC_RAW}] 저장 완료: {len(all_rows)}행")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="APLB VOC 수집기")
    parser.add_argument("--sku", default=None, help="특정 SKU ID만 수집 (예: gluta_niac_serum)")
    parser.add_argument("--dry-run", action="store_true", help="Sheets 저장 없이 테스트")
    args = parser.parse_args()
    collect_all(target_sku=args.sku, dry_run=args.dry_run)

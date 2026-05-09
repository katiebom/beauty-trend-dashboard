"""
CIR (Cosmetic Ingredient Review) 안전성 보고서 파서
─────────────────────────────────────────────────────────────────
대상 사이트: https://cir-safety.org/ingredients
방식:
  1. 성분명으로 CIR 검색 → 보고서 페이지 URL 탐색
  2. PDF 링크 발견 시 다운로드 → pdfplumber로 텍스트 추출
  3. 웹페이지 직접 파싱도 병행 (PDF 없는 경우)
  4. 저장: data/research_cache/{ingredient_id}/cir_{date}.json

참고:
  - CIR은 robots.txt 기반 공개 접근 허용 (비상업적 연구용)
  - 과도한 요청 방지: REQUEST_DELAY = 2.0s
─────────────────────────────────────────────────────────────────
"""

import os
import sys
import time
import json
import yaml
import re
import argparse
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

# ── 설정 ──────────────────────────────────────────────────────────
YAML_PATH = Path(__file__).parent.parent / "config" / "ingredients.yaml"
CACHE_DIR  = Path(__file__).parent.parent / "data" / "research_cache"
PDF_DIR    = Path(__file__).parent.parent / "data" / "cir_pdfs"

CIR_BASE   = "https://cir-safety.org"
CIR_SEARCH = "https://cir-safety.org/ingredients"

REQUEST_DELAY = 2.0
MAX_RETRIES   = 3
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; BeautyRD-Research-Bot/1.0; "
        "+mailto:research@beautyrd.internal)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def load_ingredients() -> list[dict]:
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["ingredients"]


def _get(url: str, stream: bool = False, retries: int = MAX_RETRIES) -> requests.Response | None:
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30, stream=stream)
            r.raise_for_status()
            time.sleep(REQUEST_DELAY)
            return r
        except requests.RequestException as e:
            wait = 2 ** (attempt + 1)
            print(f"  [cir] 재시도 {attempt+1}/{retries} ({url[:60]}…) — {e} (대기 {wait}s)")
            time.sleep(wait)
    return None


def search_cir_page(ingredient_name: str) -> str | None:
    """CIR 검색으로 성분 페이지 URL 반환"""
    params = {"term": ingredient_name, "field_status_value": "All"}
    r = _get(f"{CIR_SEARCH}?{requests.compat.urlencode(params)}")
    if not r:
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    # 검색 결과 링크 탐색
    for a in soup.select("a[href*='/ingredients/']"):
        href = a.get("href", "")
        text = a.get_text(strip=True).lower()
        if ingredient_name.lower().split()[0] in text:
            url = href if href.startswith("http") else CIR_BASE + href
            return url

    # 더 넓은 검색: 첫 번째 결과
    first = soup.select_one("table.views-table tbody tr td a")
    if first:
        href = first.get("href", "")
        return href if href.startswith("http") else CIR_BASE + href

    return None


def extract_pdf_link(page_url: str) -> str | None:
    """성분 페이지에서 PDF 보고서 링크 추출"""
    r = _get(page_url)
    if not r:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf"):
            return href if href.startswith("http") else CIR_BASE + href
    return None


def download_pdf(pdf_url: str, save_path: Path) -> bool:
    """PDF 다운로드"""
    r = _get(pdf_url, stream=True)
    if not r:
        return False
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    return True


def parse_pdf_text(pdf_path: Path) -> str:
    """pdfplumber로 PDF 텍스트 추출"""
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages[:30]:  # 최대 30페이지
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        return "\n\n".join(text_parts)
    except ImportError:
        print("  [cir] pdfplumber 미설치. pip install pdfplumber")
        return ""
    except Exception as e:
        print(f"  [cir] PDF 파싱 오류 {pdf_path.name}: {e}")
        return ""


def extract_structured_from_text(text: str, ingredient_name: str) -> dict:
    """
    정규식 기반 핵심 정보 추출 (Claude 분석 전 전처리)
    CIR 보고서 특유의 섹션 구조 활용
    """
    result = {
        "max_concentration": "N/A",
        "safety_conclusion": "N/A",
        "reported_uses": [],
        "skin_effects": "N/A",
        "key_sections": {},
    }

    if not text:
        return result

    # 최대 농도 추출 (예: "up to 10%", "concentrations as high as 5%")
    conc_patterns = [
        r"up to\s+([\d\.]+)\s*%",
        r"concentrations?\s+(?:as high as|of)\s+([\d\.]+)\s*%",
        r"([\d\.]+)\s*%\s+(?:in|for)\s+(?:leave-on|rinse-off)",
        r"maximum\s+concentration[s]?\s+(?:of\s+)?([\d\.]+)\s*%",
    ]
    for pat in conc_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result["max_concentration"] = m.group(1) + "%"
            break

    # 안전성 결론 섹션
    conclusion_match = re.search(
        r"(CONCLUSION|SAFETY ASSESSMENT CONCLUSION)[:\s]+(.*?)(?=\n\n|\Z)",
        text, re.IGNORECASE | re.DOTALL
    )
    if conclusion_match:
        result["safety_conclusion"] = conclusion_match.group(2).strip()[:500]

    # 피부 효과 섹션
    skin_match = re.search(
        r"(SKIN\s+(?:IRRITATION|SENSITIZATION|EFFECTS?))[:\s]+(.*?)(?=\n[A-Z]{3,}|\Z)",
        text, re.IGNORECASE | re.DOTALL
    )
    if skin_match:
        result["skin_effects"] = skin_match.group(2).strip()[:400]

    # 주요 섹션 추출 (앞 2000자)
    result["key_sections"]["full_text_preview"] = text[:2000]

    return result


def scrape_page_content(page_url: str) -> str:
    """PDF 없는 경우 웹페이지 텍스트 직접 스크래핑"""
    r = _get(page_url)
    if not r:
        return ""
    soup = BeautifulSoup(r.text, "html.parser")
    # 본문 영역만 추출
    main = soup.find("main") or soup.find("div", class_="field-body") or soup.find("article")
    if main:
        return main.get_text(separator="\n", strip=True)
    return soup.get_text(separator="\n", strip=True)[:3000]


def crawl_ingredient(ing: dict) -> dict:
    """성분 1개 CIR 데이터 수집"""
    ing_id   = ing["id"]
    name_en  = ing.get("name_en", ing_id)
    name_kr  = ing.get("name_kr", "")

    print(f"  [{ing_id}] CIR 검색: {name_en}")

    result = {
        "ingredient_id": ing_id,
        "name_en": name_en,
        "name_kr": name_kr,
        "source": "cir",
        "cir_page_url": None,
        "pdf_url": None,
        "pdf_path": None,
        "raw_text_preview": "",
        "structured": {},
        "crawled_at": datetime.now().isoformat(),
        "status": "not_found",
    }

    # 1. CIR 페이지 탐색
    page_url = search_cir_page(name_en)
    if not page_url:
        # 별명/약칭으로 재시도
        alt_name = name_en.split()[0]
        print(f"  [{ing_id}] 재시도: {alt_name}")
        page_url = search_cir_page(alt_name)

    if not page_url:
        print(f"  [{ing_id}] CIR 페이지 없음")
        result["status"] = "not_found"
        return result

    result["cir_page_url"] = page_url
    print(f"  [{ing_id}] 페이지 발견: {page_url}")

    # 2. PDF 링크 탐색
    pdf_url = extract_pdf_link(page_url)
    if pdf_url:
        result["pdf_url"] = pdf_url
        pdf_save = PDF_DIR / ing_id / f"cir_{date.today().isoformat()}.pdf"
        PDF_DIR.mkdir(parents=True, exist_ok=True)

        if download_pdf(pdf_url, pdf_save):
            result["pdf_path"] = str(pdf_save)
            print(f"  [{ing_id}] PDF 다운로드 완료: {pdf_save.name}")
            text = parse_pdf_text(pdf_save)
        else:
            text = scrape_page_content(page_url)
    else:
        print(f"  [{ing_id}] PDF 없음 → 웹페이지 텍스트 파싱")
        text = scrape_page_content(page_url)

    result["raw_text_preview"] = text[:1500]
    result["structured"] = extract_structured_from_text(text, name_en)
    result["status"] = "success" if text else "empty"

    return result


def save_result(result: dict):
    out_dir = CACHE_DIR / result["ingredient_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = out_dir / f"cir_{date.today().isoformat()}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  [{result['ingredient_id']}] 저장: {fname}")
    return fname


def run(target_id: str | None = None):
    ingredients = load_ingredients()
    if target_id:
        ingredients = [i for i in ingredients if i["id"] == target_id]
        if not ingredients:
            print(f"[cir] 성분 '{target_id}' 없음")
            return

    print(f"\n=== CIR 안전성 데이터 수집 ({len(ingredients)}개 성분) ===")
    results = []
    for ing in ingredients:
        r = crawl_ingredient(ing)
        save_result(r)
        results.append(r)
        print()

    ok = sum(1 for r in results if r["status"] == "success")
    print(f"=== CIR 수집 완료 — 성공 {ok}/{len(results)} ===\n")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CIR 안전성 보고서 수집기")
    parser.add_argument("--ingredient", help="특정 성분 ID만 수집")
    args = parser.parse_args()
    run(target_id=args.ingredient)

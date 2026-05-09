"""
PubMed 논문 수집기
─────────────────────────────────────────────────────────────────
NCBI Entrez API (무료, 공개):
  - API 키 없이: 3 req/sec
  - NCBI_API_KEY 설정 시: 10 req/sec

수집 항목:
  - 성분별 최신 논문 초록(Abstract) + 메타데이터
  - 저장: data/research_cache/{ingredient_id}/pubmed_{date}.json

사용법:
  python collect/pubmed_crawler.py                  # 전체 성분
  python collect/pubmed_crawler.py --ingredient ectoin
  python collect/pubmed_crawler.py --max 30         # 성분당 최대 30건
─────────────────────────────────────────────────────────────────
"""

import os
import sys
import time
import json
import yaml
import argparse
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

# ── 설정 ──────────────────────────────────────────────────────────
YAML_PATH = Path(__file__).parent.parent / "config" / "ingredients.yaml"
CACHE_DIR = Path(__file__).parent.parent / "data" / "research_cache"

NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

REQUEST_DELAY = 0.34 if not NCBI_API_KEY else 0.11  # 3 req/s or 10 req/s
MAX_RETRIES = 3

# 검색 쿼리 수식어 — 피부/화장품 관련 논문에 집중
SEARCH_SUFFIX = "(skin OR cosmetic OR dermatology OR topical OR epidermis OR keratinocyte)"


def load_ingredients() -> list[dict]:
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["ingredients"]


def _get(url: str, params: dict, retries: int = MAX_RETRIES) -> requests.Response | None:
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            time.sleep(REQUEST_DELAY)
            return r
        except requests.RequestException as e:
            wait = 2 ** attempt
            print(f"  [pubmed] 재시도 {attempt+1}/{retries} — {e} (대기 {wait}s)")
            time.sleep(wait)
    return None


def search_pmids(query: str, max_results: int = 20) -> list[str]:
    """PubMed에서 PMID 목록 검색"""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "sort": "date",
        "retmode": "json",
        "usehistory": "n",
    }
    r = _get(ESEARCH_URL, params)
    if not r:
        return []
    data = r.json()
    return data.get("esearchresult", {}).get("idlist", [])


def fetch_abstracts(pmids: list[str]) -> list[dict]:
    """PMID 목록으로 논문 메타데이터 + 초록 가져오기"""
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "abstract",
        "retmode": "xml",
    }
    r = _get(EFETCH_URL, params)
    if not r:
        return []

    articles = []
    try:
        root = ET.fromstring(r.text)
    except ET.ParseError as e:
        print(f"  [pubmed] XML 파싱 오류: {e}")
        return []

    for article in root.findall(".//PubmedArticle"):
        pmid_el  = article.find(".//PMID")
        title_el = article.find(".//ArticleTitle")
        abs_el   = article.find(".//AbstractText")
        year_el  = article.find(".//PubDate/Year")
        journal_el = article.find(".//Journal/Title")

        # 저자 목록
        authors = []
        for au in article.findall(".//Author"):
            last  = au.findtext("LastName", "")
            fore  = au.findtext("ForeName", "")
            if last:
                authors.append(f"{last} {fore}".strip())

        # MeSH 키워드
        mesh_terms = [m.text for m in article.findall(".//MeshHeading/DescriptorName") if m.text]

        articles.append({
            "pmid":    pmid_el.text if pmid_el is not None else "",
            "title":   title_el.text if title_el is not None else "",
            "abstract": abs_el.text if abs_el is not None else "",
            "year":    year_el.text if year_el is not None else "",
            "journal": journal_el.text if journal_el is not None else "",
            "authors": authors[:5],
            "mesh_terms": mesh_terms[:10],
            "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid_el.text}/" if pmid_el is not None else "",
        })

    return articles


def crawl_ingredient(ing: dict, max_results: int = 20) -> dict:
    """성분 1개 수집 → dict 반환"""
    ing_id   = ing["id"]
    name_en  = ing.get("name_en", ing_id)
    name_kr  = ing.get("name_kr", "")
    category = ing.get("category", "")

    # 검색어 구성: 영문명 + 카테고리 힌트
    query = f'"{name_en}" AND {SEARCH_SUFFIX}'
    print(f"  [{ing_id}] 검색: {query}")

    pmids = search_pmids(query, max_results)
    print(f"  [{ing_id}] 논문 {len(pmids)}건 발견")

    if not pmids:
        return {
            "ingredient_id": ing_id,
            "name_en": name_en,
            "name_kr": name_kr,
            "query": query,
            "paper_count": 0,
            "articles": [],
            "crawled_at": datetime.now().isoformat(),
            "source": "pubmed",
        }

    articles = fetch_abstracts(pmids)

    return {
        "ingredient_id": ing_id,
        "name_en": name_en,
        "name_kr": name_kr,
        "category": category,
        "query": query,
        "paper_count": len(articles),
        "articles": articles,
        "crawled_at": datetime.now().isoformat(),
        "source": "pubmed",
    }


def save_result(result: dict):
    """JSON으로 저장 — data/research_cache/{ingredient_id}/pubmed_{date}.json"""
    ing_id = result["ingredient_id"]
    out_dir = CACHE_DIR / ing_id
    out_dir.mkdir(parents=True, exist_ok=True)

    fname = out_dir / f"pubmed_{date.today().isoformat()}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  [{ing_id}] 저장 완료: {fname}")
    return fname


def run(target_id: str | None = None, max_results: int = 20):
    """메인 수집 루프"""
    ingredients = load_ingredients()
    if target_id:
        ingredients = [i for i in ingredients if i["id"] == target_id]
        if not ingredients:
            print(f"[pubmed] 성분 '{target_id}' YAML에서 찾을 수 없음")
            return

    print(f"\n=== PubMed 수집 시작 ({len(ingredients)}개 성분, 성분당 최대 {max_results}건) ===")
    results = []
    for ing in ingredients:
        result = crawl_ingredient(ing, max_results)
        save_result(result)
        results.append(result)
        print()

    total = sum(r["paper_count"] for r in results)
    print(f"=== 수집 완료 — 총 {total}건 논문 저장 ===\n")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PubMed 논문 수집기")
    parser.add_argument("--ingredient", help="특정 성분 ID만 수집 (예: ectoin)")
    parser.add_argument("--max", type=int, default=20, help="성분당 최대 논문 수 (기본 20)")
    args = parser.parse_args()
    run(target_id=args.ingredient, max_results=args.max)

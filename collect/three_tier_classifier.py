"""
3-Tier 저널 분류기 (하이브리드)
─────────────────────────────────────────────────────────────────
입력: PubMed 논문 메타 (journal, mesh_terms, year)
출력: T1 / T2 / T3 / unknown

분류 순서:
  1) 화이트리스트 부분일치 (config/journal_tiers.yaml)
  2) 매칭 실패 시 → Gemini 배치 분류 (선택, fallback_to_gemini=True 일 때)

사용법 (단독):
  from collect.three_tier_classifier import classify_articles
  tier_dist = classify_articles(articles)
─────────────────────────────────────────────────────────────────
"""

import os
import sys
import json
import yaml
from pathlib import Path
from collections import Counter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

TIERS_PATH = Path(__file__).parent.parent / "config" / "journal_tiers.yaml"


def load_tier_config() -> dict:
    with open(TIERS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def classify_one(journal: str, tier_cfg: dict) -> str:
    """단일 논문 1개 분류 → 'T1' / 'T2' / 'T3' / 'unknown'"""
    if not journal:
        return "unknown"
    j = journal.lower().strip()
    # priority order에 따라 검사 (T1 → T2 → T3)
    order = tier_cfg.get("classification", {}).get(
        "priority_order",
        ["T1_medical_aesthetic", "T2_skinceutical_dermocosmetic", "T3_mass_cosmetic"],
    )
    short_map = {
        "T1_medical_aesthetic": "T1",
        "T2_skinceutical_dermocosmetic": "T2",
        "T3_mass_cosmetic": "T3",
    }
    for tier_key in order:
        keywords = tier_cfg.get(tier_key, {}).get("keywords", [])
        for kw in keywords:
            if kw.lower() in j:
                return short_map.get(tier_key, "unknown")
    return "unknown"


def gemini_batch_classify(articles: list[dict]) -> dict:
    """unknown 논문들을 Gemini로 한 번에 분류
    Returns: {pmid: 'T1'/'T2'/'T3'} 매핑
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {}
    try:
        from google import genai
        from google.genai import types as genai_types
        client = genai.Client(api_key=api_key)
    except ImportError:
        return {}

    payload = [
        {
            "pmid": a.get("pmid", ""),
            "journal": a.get("journal", ""),
            "title": (a.get("title") or "")[:200],
        }
        for a in articles if a.get("pmid")
    ]
    if not payload:
        return {}

    prompt = f"""당신은 의학·화장품 논문 분류 전문가입니다.
아래 논문들의 저널과 제목을 보고 각각을 다음 3개 티어 중 하나로 분류하세요:

T1 = Medical / Medical Aesthetic (의료·시술용. 외과/피부과 처방, 레이저 시술, 주사제, 줄기세포/엑소좀 의료)
T2 = Skinceutical / Dermocosmetic (스킨수티컬, 더마코스메틱. Skinceuticals/La Roche-Posay/Avene 같은 브랜드 영역)
T3 = Mass Cosmetic (일반 매스 화장품, 소비재 화장품, fragrance, color cosmetics)

판단이 애매하면 가장 가까운 티어 선택. JSON만 응답:
{{"results": [{{"pmid": "...", "tier": "T1|T2|T3"}}]}}

논문:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""
    last_err = None
    for model_name in ["gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gemini-2.0-flash"]:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=4000,
                    response_mime_type="application/json",
                ),
            )
            text = (response.text or "").strip()
            d = json.loads(text)
            return {r["pmid"]: r["tier"] for r in d.get("results", []) if r.get("pmid")}
        except Exception as e:
            last_err = str(e)
            if "429" in last_err or "RESOURCE_EXHAUSTED" in last_err:
                continue
            return {}
    return {}


def classify_articles(articles: list[dict], use_gemini: bool = True) -> dict:
    """
    Returns: {
      'distribution': {'T1': n, 'T2': n, 'T3': n, 'unknown': n},
      'by_pmid': {pmid: tier},
      'by_tier': {'T1': [pmids], 'T2': [pmids], ...},
    }
    """
    tier_cfg = load_tier_config()
    by_pmid = {}
    unknown_articles = []

    for a in articles:
        pmid = a.get("pmid", "")
        if not pmid:
            continue
        tier = classify_one(a.get("journal", ""), tier_cfg)
        by_pmid[pmid] = tier
        if tier == "unknown":
            unknown_articles.append(a)

    # Gemini 보강
    if use_gemini and unknown_articles and tier_cfg.get("classification", {}).get("fallback_to_gemini"):
        batch_size = tier_cfg["classification"].get("gemini_batch_size", 20)
        for i in range(0, len(unknown_articles), batch_size):
            batch = unknown_articles[i:i + batch_size]
            mapping = gemini_batch_classify(batch)
            for pmid, tier in mapping.items():
                if tier in ("T1", "T2", "T3"):
                    by_pmid[pmid] = tier

    distribution = Counter(by_pmid.values())
    by_tier = {"T1": [], "T2": [], "T3": [], "unknown": []}
    for pmid, t in by_pmid.items():
        by_tier.setdefault(t, []).append(pmid)

    return {
        "distribution": dict(distribution),
        "by_pmid": by_pmid,
        "by_tier": by_tier,
        "total": len(by_pmid),
    }


if __name__ == "__main__":
    # 테스트: 기존 수집된 PubMed 캐시 1개 읽고 분류
    cache = Path(__file__).parent.parent / "data" / "research_cache"
    if cache.exists():
        first_ing = next(cache.iterdir(), None)
        if first_ing:
            files = sorted(first_ing.glob("pubmed_*.json"))
            if files:
                d = json.loads(files[-1].read_text())
                print(f"테스트 성분: {d['ingredient_id']}")
                result = classify_articles(d.get("articles", []), use_gemini=False)
                print(f"분류 결과: {result['distribution']}")
                for tier in ("T1", "T2", "T3", "unknown"):
                    print(f"  {tier}: {len(result['by_tier'].get(tier, []))}건")

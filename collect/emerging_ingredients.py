"""
신성분 발굴 시그널 엔진 (Phase 4 Section B)
─────────────────────────────────────────────────────────────────
3-Tier funnel 가설:
  T1 (Medical/Aesthetic) → T2 (Dermocosmetic) → T3 (Mass) 흐름.
  T1+T2에 등장하지만 T3 미진입 + V-Index 가속도 = "다음에 뜰 성분".

데이터 소스:
  - data/research_cache/{ingredient_id}/pubmed_*.json (기존)
  - config/journal_tiers.yaml (분류 규칙)
  - config/ingredients.yaml (성분 + 추적 V-Index)
  - config/journal_tiers.yaml -> emerging_candidates (추가 후보)

출력:
  data/emerging_signals/signals_{date}.json
    - per_ingredient: {tier_dist, recency, has_clinical_trial, signal_score}
    - ranked: 시그널 점수 내림차순

사용법:
  python collect/emerging_ingredients.py             # 전체 분석
  python collect/emerging_ingredients.py --pubmed    # PubMed 신규 후보 먼저 수집
─────────────────────────────────────────────────────────────────
"""

import os
import sys
import json
import yaml
import argparse
from pathlib import Path
from datetime import date, datetime
from collections import Counter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from collect.three_tier_classifier import classify_articles, load_tier_config
from collect.pubmed_crawler import search_pmids, fetch_abstracts

INGREDIENTS_YAML = Path(__file__).parent.parent / "config" / "ingredients.yaml"
TIERS_YAML       = Path(__file__).parent.parent / "config" / "journal_tiers.yaml"
RESEARCH_CACHE   = Path(__file__).parent.parent / "data" / "research_cache"
EMERGING_CACHE   = Path(__file__).parent.parent / "data" / "emerging_signals"


def load_ingredients():
    return yaml.safe_load(INGREDIENTS_YAML.read_text(encoding="utf-8"))["ingredients"]


def load_emerging_candidates():
    cfg = yaml.safe_load(TIERS_YAML.read_text(encoding="utf-8"))
    return cfg.get("emerging_candidates", [])


def has_clinical_trial(article: dict) -> bool:
    mesh = [m.lower() for m in (article.get("mesh_terms") or [])]
    return any("clinical trial" in m or "randomized controlled" in m for m in mesh)


def recency_score(article: dict) -> float:
    """2024~2026 가중. 5점=2026, 3점=2024, 1점=2020 이전."""
    try:
        y = int(article.get("year") or 0)
    except Exception:
        return 0
    if y >= 2026: return 5
    if y >= 2025: return 4
    if y >= 2024: return 3
    if y >= 2022: return 2
    if y >= 2020: return 1
    return 0


def load_pubmed_cache(ing_id: str) -> dict | None:
    """가장 최근 pubmed_*.json 로드"""
    d = RESEARCH_CACHE / ing_id
    if not d.exists():
        return None
    files = sorted(d.glob("pubmed_*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))


def fetch_emerging_pubmed(cand: dict, max_results: int = 25) -> dict:
    """emerging_candidates는 ingredients.yaml에 없을 수 있음 → 직접 PubMed 조회"""
    query = cand.get("pubmed_query") or f'"{cand["name_en"]}" AND skin'
    print(f"  [{cand['id']}] PubMed 조회: {query[:60]}...")
    pmids = search_pmids(query, max_results=max_results)
    articles = fetch_abstracts(pmids) if pmids else []
    return {
        "ingredient_id": cand["id"],
        "name_en": cand.get("name_en", ""),
        "name_kr": cand.get("name_kr", ""),
        "category": cand.get("category", ""),
        "query": query,
        "paper_count": len(articles),
        "articles": articles,
        "crawled_at": datetime.now().isoformat(),
        "source": "pubmed_emerging",
    }


def save_emerging_pubmed(result: dict):
    out = RESEARCH_CACHE / result["ingredient_id"]
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"pubmed_{date.today().isoformat()}.json"
    f.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def compute_signal(ing: dict, pubmed_data: dict | None, tier_cfg: dict, v_index: float | None = None) -> dict:
    """단일 성분의 3-Tier 분포 + 시그널 점수 계산"""
    if not pubmed_data or not pubmed_data.get("articles"):
        return {
            "ingredient_id": ing.get("id"),
            "name_kr": ing.get("name_kr", ""),
            "name_en": ing.get("name_en", ""),
            "category": ing.get("category", ""),
            "tier_dist": {"T1": 0, "T2": 0, "T3": 0, "unknown": 0},
            "total_papers": 0,
            "recent_papers": 0,
            "clinical_trials": 0,
            "v_index": v_index,
            "signal_score": 0,
            "signal_label": "🔵 데이터 없음",
            "top_t1_papers": [],
            "top_t2_papers": [],
        }

    articles = pubmed_data["articles"]
    classification = classify_articles(articles, use_gemini=False)
    tier_dist = classification["distribution"]
    by_tier = classification["by_tier"]

    # 점수 가중치
    weights = tier_cfg.get("signal_scoring", {}).get("weights", {})
    thresholds = tier_cfg.get("signal_scoring", {}).get("signal_thresholds", {
        "imminent": 12, "emerging": 7, "nascent": 3
    })

    t1 = tier_dist.get("T1", 0)
    t2 = tier_dist.get("T2", 0)
    t3 = tier_dist.get("T3", 0)
    recent = sum(1 for a in articles if recency_score(a) >= 3)  # 2024+
    clinical = sum(1 for a in articles if has_clinical_trial(a))

    unknown = tier_dist.get("unknown", 0)
    score = (
        t1 * weights.get("t1_paper_count", 1.5)
        + t2 * weights.get("t2_paper_count", 1.5)
        + t3 * weights.get("t3_paper_count", -1.0)
        + unknown * weights.get("unknown_paper_count", -0.2)  # ★ 신규
        + (recent / max(len(articles), 1) * 10) * weights.get("recency_2024_2026", 1.0)
        + min(clinical, 3) * weights.get("has_clinical_trial", 2.0)
    )
    if v_index is not None and v_index < 30:
        score += weights.get("v_index_low", 1.0) * 5

    # 라벨
    if score >= thresholds["imminent"]:
        label = "🔥 임박 (T+6mo)"
    elif score >= thresholds["emerging"]:
        label = "🟡 등장 중 (T+12mo)"
    elif score >= thresholds["nascent"]:
        label = "🟢 잠재 (T+24mo)"
    else:
        label = "⚪ 약함"

    # 상위 논문 (T1, T2)
    by_pmid_lookup = {a["pmid"]: a for a in articles if a.get("pmid")}
    top_t1 = []
    for pmid in by_tier.get("T1", [])[:3]:
        a = by_pmid_lookup.get(pmid)
        if a:
            top_t1.append({"pmid": pmid, "title": (a.get("title") or "")[:120],
                           "year": a.get("year", ""), "journal": a.get("journal", "")})
    top_t2 = []
    for pmid in by_tier.get("T2", [])[:3]:
        a = by_pmid_lookup.get(pmid)
        if a:
            top_t2.append({"pmid": pmid, "title": (a.get("title") or "")[:120],
                           "year": a.get("year", ""), "journal": a.get("journal", "")})

    return {
        "ingredient_id": ing.get("id"),
        "name_kr": ing.get("name_kr", ""),
        "name_en": ing.get("name_en", ""),
        "category": ing.get("category", ""),
        "tier_dist": {"T1": t1, "T2": t2, "T3": t3, "unknown": tier_dist.get("unknown", 0)},
        "total_papers": len(articles),
        "recent_papers": recent,
        "clinical_trials": clinical,
        "v_index": v_index,
        "signal_score": round(score, 2),
        "signal_label": label,
        "top_t1_papers": top_t1,
        "top_t2_papers": top_t2,
    }


def run(fetch_emerging: bool = False):
    EMERGING_CACHE.mkdir(parents=True, exist_ok=True)
    tier_cfg = load_tier_config()
    ingredients = load_ingredients()
    candidates = load_emerging_candidates()

    print(f"\n=== 3-Tier 신성분 시그널 분석 ===")
    print(f"  추적 성분: {len(ingredients)}개 (ingredients.yaml)")
    print(f"  추가 후보: {len(candidates)}개 (emerging_candidates)\n")

    # 추가 후보 PubMed 수집 (ingredients.yaml 외부)
    if fetch_emerging:
        print("── 신성분 후보 PubMed 수집 ──")
        for cand in candidates:
            cache_file = RESEARCH_CACHE / cand["id"] / f"pubmed_{date.today().isoformat()}.json"
            if cache_file.exists():
                print(f"  [{cand['id']}] 오늘 캐시 존재 — 스킵")
                continue
            result = fetch_emerging_pubmed(cand)
            save_emerging_pubmed(result)
        print()

    # 시그널 계산
    all_signals = []

    print("── 기존 성분 분석 ──")
    for ing in ingredients:
        cache = load_pubmed_cache(ing["id"])
        sig = compute_signal(ing, cache, tier_cfg)
        all_signals.append(sig)
        if sig["total_papers"] > 0:
            d = sig["tier_dist"]
            print(f"  {sig['signal_label']:<20} {ing['id']:<25} "
                  f"T1:{d['T1']:>2} T2:{d['T2']:>2} T3:{d['T3']:>2} "
                  f"score={sig['signal_score']}")

    print("\n── 신성분 후보 분석 ──")
    for cand in candidates:
        cache = load_pubmed_cache(cand["id"])
        sig = compute_signal(cand, cache, tier_cfg)
        all_signals.append(sig)
        if sig["total_papers"] > 0:
            d = sig["tier_dist"]
            print(f"  {sig['signal_label']:<20} {cand['id']:<25} "
                  f"T1:{d['T1']:>2} T2:{d['T2']:>2} T3:{d['T3']:>2} "
                  f"score={sig['signal_score']}")

    # 정렬
    all_signals.sort(key=lambda x: -x["signal_score"])

    # 저장
    out = {
        "generated_at": datetime.now().isoformat(),
        "total_ingredients": len(all_signals),
        "signals": all_signals,
    }
    out_file = EMERGING_CACHE / f"signals_{date.today().isoformat()}.json"
    out_file.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    # 최신 스냅샷 (대시보드 로드용)
    latest = EMERGING_CACHE / "latest.json"
    latest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # 상위 10개 요약
    print("\n" + "=" * 60)
    print("📊 신성분 시그널 TOP 10 (시그널 점수 정렬)")
    print("=" * 60)
    for i, s in enumerate(all_signals[:10], 1):
        if s["total_papers"] == 0:
            continue
        d = s["tier_dist"]
        print(f"{i:>2}. {s['signal_label']} {s['name_kr']} ({s['name_en']})")
        print(f"     T1:{d['T1']} T2:{d['T2']} T3:{d['T3']}  "
              f"최근(24+):{s['recent_papers']}  임상시험:{s['clinical_trials']}  "
              f"score={s['signal_score']}")

    print(f"\n✅ 저장: {out_file.name}\n")
    return all_signals


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="3-Tier 신성분 시그널 분석")
    parser.add_argument("--pubmed", action="store_true",
                        help="emerging_candidates의 PubMed 데이터를 먼저 수집")
    args = parser.parse_args()
    run(fetch_emerging=args.pubmed)

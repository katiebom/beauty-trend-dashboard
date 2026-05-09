"""
APLB 컴플렉스 페어 시너지 PubMed 검색
─────────────────────────────────────────────────────────────────
APLB의 시그니처 컴플렉스는 단일 성분이 아니라 '페어/트리오 배합'.
→ 페어 PubMed 쿼리로 임상적 시너지 근거 존재 여부를 검증.

쿼리 형태:
  ("ingredient_a"[Title/Abstract] AND "ingredient_b"[Title/Abstract])
   AND (skin OR cosmetic OR dermatology OR topical)

저장: data/aplb_research/{complex_id}/{ing_a}__{ing_b}_{date}.json

사용법:
  python collect/aplb_pair_search.py                    # 전체 컴플렉스
  python collect/aplb_pair_search.py --complex lipo_gluta_niac_cen
  python collect/aplb_pair_search.py --max 10
─────────────────────────────────────────────────────────────────
"""

import os
import sys
import json
import yaml
import argparse
from datetime import date, datetime
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collect.pubmed_crawler import search_pmids, fetch_abstracts

YAML_PATH = Path(__file__).parent.parent / "config" / "aplb_products.yaml"
CACHE_DIR = Path(__file__).parent.parent / "data" / "aplb_research"

SKIN_FILTER = "(skin OR cosmetic OR dermatology OR topical OR epidermis OR keratinocyte)"


def load_aplb() -> dict:
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_pair_query(ing_a: str, ing_b: str) -> str:
    """페어 검색 쿼리 — 두 성분 모두 초록/제목에 등장"""
    return (
        f'("{ing_a}"[Title/Abstract] AND "{ing_b}"[Title/Abstract]) '
        f'AND {SKIN_FILTER}'
    )


def build_trio_query(ings: list[str]) -> str:
    """트리오 검색 쿼리 — 세 성분 모두 등장"""
    parts = " AND ".join(f'"{i}"[Title/Abstract]' for i in ings)
    return f"({parts}) AND {SKIN_FILTER}"


def search_trio(ings: list[str], max_results: int = 10) -> dict:
    query = build_trio_query(ings)
    print(f"  🔺 [{' × '.join(ings)}]")
    pmids = search_pmids(query, max_results=max_results)
    print(f"     발견: {len(pmids)}건")
    articles = fetch_abstracts(pmids) if pmids else []
    return {
        "ingredients": ings,
        "query": query,
        "paper_count": len(articles),
        "articles": articles,
        "crawled_at": datetime.now().isoformat(),
    }


def search_pair(ing_a: str, ing_b: str, max_results: int = 15) -> dict:
    """단일 페어에 대한 PubMed 검색 → 메타+초록"""
    query = build_pair_query(ing_a, ing_b)
    print(f"  🔍 [{ing_a} × {ing_b}]")
    print(f"     query: {query[:80]}...")

    pmids = search_pmids(query, max_results=max_results)
    print(f"     발견: {len(pmids)}건")

    articles = fetch_abstracts(pmids) if pmids else []

    return {
        "ingredient_a": ing_a,
        "ingredient_b": ing_b,
        "query": query,
        "paper_count": len(articles),
        "articles": articles,
        "crawled_at": datetime.now().isoformat(),
    }


def save_pair(complex_id: str, result: dict):
    out_dir = CACHE_DIR / complex_id
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_a = result["ingredient_a"].replace(" ", "_")
    safe_b = result["ingredient_b"].replace(" ", "_")
    fname = out_dir / f"{safe_a}__{safe_b}_{date.today().isoformat()}.json"

    with open(fname, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def run(target_complex: str | None = None, max_results: int = 15):
    """모든 컴플렉스의 페어 쿼리 실행"""
    data = load_aplb()
    complexes = (
        data.get("complexes", [])
        + data.get("single_actives", [])
        + data.get("candidate_ingredients", [])
    )

    if target_complex:
        complexes = [c for c in complexes if c["id"] == target_complex]
        if not complexes:
            print(f"[aplb] 컴플렉스 '{target_complex}' 없음")
            return

    print(f"\n=== APLB 페어 시너지 PubMed 검색 ({len(complexes)}개 컴플렉스) ===\n")

    summary = []
    for cx in complexes:
        cx_id = cx["id"]
        cx_name = cx.get("name_kr", cx_id)
        pairs = cx.get("pair_queries", [])

        print(f"━━━ {cx.get('trade_mark', cx_name)} ━━━")
        if not pairs:
            print(f"  pair_queries 없음 — 스킵\n")
            continue

        cx_summary = {
            "complex_id": cx_id,
            "trade_mark": cx.get("trade_mark", ""),
            "pair_results": [],
        }

        for pair in pairs:
            if len(pair) != 2:
                continue
            result = search_pair(pair[0], pair[1], max_results)
            save_pair(cx_id, result)

            cx_summary["pair_results"].append({
                "pair": pair,
                "paper_count": result["paper_count"],
                "top_titles": [(a.get("title") or "(제목 없음)") for a in result["articles"][:3]],
            })

        # 트리오 쿼리 처리
        trios = cx.get("trio_queries", [])
        cx_summary["trio_results"] = []
        for trio in trios:
            if len(trio) < 3:
                continue
            result = search_trio(trio, max_results)
            # 파일명: 트리오 표기
            safe = "__".join(t.replace(" ", "_") for t in trio)
            out_dir = CACHE_DIR / cx_id
            out_dir.mkdir(parents=True, exist_ok=True)
            with open(out_dir / f"TRIO_{safe}_{date.today().isoformat()}.json", "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            cx_summary["trio_results"].append({
                "trio": trio,
                "paper_count": result["paper_count"],
                "top_titles": [(a.get("title") or "(제목 없음)") for a in result["articles"][:3]],
            })

        summary.append(cx_summary)
        print()

    # ── 전체 요약 출력 ──────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📊 페어 시너지 요약 — Evidence Snapshot")
    print("=" * 60)
    for cx_sum in summary:
        print(f"\n[{cx_sum['trade_mark']}]")
        for pr in cx_sum["pair_results"]:
            count = pr["paper_count"]
            badge = "🟢" if count >= 5 else ("🟡" if count >= 1 else "🔴")
            print(f"  {badge} {pr['pair'][0]} × {pr['pair'][1]}: {count}건")
            for t in pr["top_titles"][:2]:
                t_safe = (t or "(제목 없음)")[:90]
                print(f"      └ {t_safe}")
        for tr in cx_sum.get("trio_results", []):
            count = tr["paper_count"]
            badge = "🟢" if count >= 5 else ("🟡" if count >= 1 else "🔴")
            print(f"  {badge} 🔺 {' × '.join(tr['trio'])}: {count}건")
            for t in tr["top_titles"][:2]:
                t_safe = (t or "(제목 없음)")[:90]
                print(f"      └ {t_safe}")

    # 요약 JSON 저장
    summary_file = CACHE_DIR / f"_summary_{date.today().isoformat()}.json"
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 요약 저장: {summary_file}\n")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="APLB 페어 시너지 PubMed 검색")
    parser.add_argument("--complex", help="특정 컴플렉스 ID만 (예: lipo_gluta_niac_cen)")
    parser.add_argument("--max", type=int, default=15, help="페어당 최대 논문 수 (기본 15)")
    args = parser.parse_args()
    run(target_complex=args.complex, max_results=args.max)

"""
APLB 마케팅 클레임 QA/QC
─────────────────────────────────────────────────────────────────
검증 항목:
  1) 인용 PMID가 실제 PubMed 캐시에 존재하는가? (환각 방지)
  2) 회피 키워드 자동 검출 (treat/cure/prevent/100% 등)
  3) 클레임당 PMID 매핑 누락 여부
  4) 한국 광고법 위반 표현 (의약품 효과 표현)
  5) 클레임 카드 완성도 점수 (Hero/RTB/Tech/papers 모두 있는가)

사용법:
  python collect/aplb_claim_qc.py                  # 모든 클레임 카드 검증
  python collect/aplb_claim_qc.py --complex lipo_gluta_niac_cen
─────────────────────────────────────────────────────────────────
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CLAIMS_DIR   = Path(__file__).parent.parent / "data" / "aplb_claims"
RESEARCH_DIR = Path(__file__).parent.parent / "data" / "aplb_research"

# ── 위반 위험 표현 (한국 화장품법 + FDA 가이드) ────────────────
# 화장품 클레임에서 절대 쓰면 안 되는 의학 효과 동사
DANGEROUS_VERBS_EN = [
    r"\btreats?\b",
    r"\bcures?\b",
    r"\bheal(s|ed|ing)?\b",
    r"\bprevents?\b",        # 예방 (광고 위반)
    r"\beradicate(s|d)?\b",
    r"\beliminate(s|d)?\b",
    r"\bremoves? (wrinkles|acne|spots) permanently\b",
    r"\bdiagnose(s|d)?\b",
    r"\bpharmaceutical\b",
    r"\bdrug-?like\b",
]
DANGEROUS_VERBS_KR = [
    "치료", "치유", "예방", "근절", "개선시킵니다", "완벽 제거",
    "약효", "의약품 효과", "병변 제거", "주름을 없앱니다", "재생시킵니다",
]
ABSOLUTE_CLAIMS = [
    r"\b100%\b", r"\bguaranteed?\b", r"\binstant(ly)?\b",
    "100%", "완전히", "즉시", "단 1회로", "보장", "확실히",
]


def collect_pmids_from_cache(complex_id: str) -> set[str]:
    """이 컴플렉스의 PubMed 검색 결과에서 모든 PMID 수집"""
    pmids = set()
    cx_dir = RESEARCH_DIR / complex_id
    if not cx_dir.exists():
        return pmids
    for f in cx_dir.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            for art in d.get("articles", []):
                pmid = art.get("pmid", "").strip()
                if pmid:
                    pmids.add(pmid)
        except Exception:
            continue
    return pmids


def find_violations(text) -> list[str]:
    """위반 표현 탐지 (dict/list가 들어와도 안전하게)"""
    flags = []
    if not text:
        return flags
    if not isinstance(text, str):
        # dict/list면 JSON 문자열화하여 검사
        try:
            text = json.dumps(text, ensure_ascii=False)
        except Exception:
            return flags
    low = text.lower()
    for pat in DANGEROUS_VERBS_EN:
        m = re.search(pat, low)
        if m:
            flags.append(f"⚠️ 영문 위반 동사: '{m.group()}'")
    for kw in DANGEROUS_VERBS_KR:
        if kw in text:
            flags.append(f"⚠️ 국문 위반 표현: '{kw}'")
    for pat in ABSOLUTE_CLAIMS:
        m = re.search(pat, low) if isinstance(pat, str) and pat.startswith("\\") else (
            pat if pat in text or pat in low else None
        )
        if m:
            flags.append(f"⚠️ 절대적 표현: '{pat}'")
    return flags


def extract_pmid_mentions(text: str) -> list[str]:
    """텍스트에서 PMID:xxxx 패턴 추출"""
    if not text:
        return []
    return re.findall(r"PMID[:\s]+(\d+)", text)


def qc_one(claim_file: Path) -> dict:
    """단일 클레임 카드 QC"""
    data = json.loads(claim_file.read_text(encoding="utf-8"))
    cx_id = data.get("complex_id", "")
    c = data.get("claims", {})
    valid_pmids = collect_pmids_from_cache(cx_id)

    # ── 1) PMID validity ────────────────────────────────────────
    cited_pmids = set()
    for p in c.get("citation_ready_papers", []):
        if p.get("pmid"):
            cited_pmids.add(str(p["pmid"]).strip())

    # RTB / scientific_basis 안의 PMID도 추출
    text_blobs = []
    if c.get("hero_claim", {}).get("scientific_basis"):
        text_blobs.append(c["hero_claim"]["scientific_basis"])
    for r in c.get("rtb_points", []):
        text_blobs.append(r.get("evidence", ""))

    inline_pmids = set()
    for blob in text_blobs:
        for pmid in extract_pmid_mentions(blob):
            inline_pmids.add(pmid)

    all_cited = cited_pmids | inline_pmids
    valid_cited = all_cited & valid_pmids
    hallucinated = all_cited - valid_pmids
    pmid_validity_pct = (len(valid_cited) / len(all_cited) * 100) if all_cited else 0

    # ── 2) 위반 표현 검사 (영/한 모두) ─────────────────────────
    violations = []
    if c.get("hero_claim"):
        h = c["hero_claim"]
        # 영문 + 국문 둘 다 검사 (신/구 스키마 모두 지원)
        for field in ("headline", "headline_en", "headline_kr",
                      "subheadline", "subheadline_en", "subheadline_kr",
                      "scientific_basis", "scientific_basis_en", "scientific_basis_kr"):
            for v in find_violations(h.get(field, "")):
                violations.append(f"[Hero.{field}] {v}")
    for i, r in enumerate(c.get("rtb_points", [])):
        for field in ("point", "point_en", "point_kr"):
            for v in find_violations(r.get(field, "")):
                violations.append(f"[RTB#{i+1}.{field}] {v}")
    t = c.get("tech_story", {})
    for field in ("headline", "headline_en", "headline_kr"):
        for v in find_violations(t.get(field, "")):
            violations.append(f"[Tech.{field}] {v}")
    for facts_field in ("supporting_facts", "supporting_facts_en", "supporting_facts_kr"):
        for i, fact in enumerate(t.get(facts_field, []) or []):
            for v in find_violations(fact):
                violations.append(f"[Tech.{facts_field}#{i+1}] {v}")

    # ── 3) 완성도 (신/구 스키마 모두 지원) ──────────────────────
    h = c.get("hero_claim", {})
    t = c.get("tech_story", {})
    completeness = {
        "has_hero_headline":     bool(h.get("headline_en") or h.get("headline")),
        "has_hero_headline_kr":  bool(h.get("headline_kr")),
        "has_subheadline":       bool(h.get("subheadline_en") or h.get("subheadline")),
        "has_scientific_basis":  bool(h.get("scientific_basis_en") or h.get("scientific_basis")),
        "has_rtb_points":        len(c.get("rtb_points", [])) >= 2,
        "has_rtb_kr":            any(r.get("point_kr") for r in c.get("rtb_points", [])),
        "has_tech_story":        bool(t.get("headline_en") or t.get("headline")),
        "has_citations":         len(c.get("citation_ready_papers", [])) >= 3,
        "has_north_america":     bool(c.get("north_america_angle_en") or c.get("north_america_angle")),
        "has_north_america_kr":  bool(c.get("north_america_angle_kr")),
        "has_risky_claims":      len(c.get("risky_claims_to_avoid_en") or c.get("risky_claims_to_avoid", [])) >= 2,
    }
    completeness_pct = sum(completeness.values()) / len(completeness) * 100

    # ── 4) 최종 등급 ───────────────────────────────────────────
    issues_count = len(violations) + len(hallucinated)
    if issues_count == 0 and completeness_pct == 100:
        grade = "🟢 PASS — 마케팅 사용 가능"
    elif issues_count == 0 and completeness_pct >= 75:
        grade = "🟡 CONDITIONAL — 누락 항목 보완 권장"
    elif len(hallucinated) > 0:
        grade = "🔴 FAIL — 환각 PMID 검출, 재생성 필요"
    elif len(violations) > 0:
        grade = "🟠 REVISE — 위반 표현 수정 필요"
    else:
        grade = "🟡 PARTIAL — 완성도 부족"

    return {
        "complex_id": cx_id,
        "trade_mark": data.get("trade_mark", ""),
        "grade": grade,
        "pmid_validity_pct": round(pmid_validity_pct, 1),
        "completeness_pct": round(completeness_pct, 1),
        "cited_pmids_count": len(all_cited),
        "valid_pmids_count": len(valid_cited),
        "hallucinated_pmids": sorted(hallucinated),
        "violations": violations,
        "completeness_detail": completeness,
        "checked_at": datetime.now().isoformat(),
    }


def run(target_complex: str | None = None):
    files = sorted(CLAIMS_DIR.glob("*_claims.json"))
    if target_complex:
        files = [f for f in files if f.name.startswith(f"{target_complex}_")]

    if not files:
        print("❌ 검증할 클레임 카드 없음")
        return

    print(f"\n=== APLB 클레임 카드 QA/QC ({len(files)}개) ===\n")
    all_results = []
    for f in files:
        result = qc_one(f)
        all_results.append(result)

        print(f"━━━ {result['trade_mark'] or result['complex_id']} ━━━")
        print(f"  {result['grade']}")
        print(f"  PMID 유효성: {result['pmid_validity_pct']}% "
              f"({result['valid_pmids_count']}/{result['cited_pmids_count']})")
        print(f"  완성도: {result['completeness_pct']}%")
        if result["hallucinated_pmids"]:
            print(f"  🔴 환각 PMID ({len(result['hallucinated_pmids'])}건): "
                  f"{', '.join(result['hallucinated_pmids'][:5])}")
        if result["violations"]:
            print(f"  🟠 위반 표현 ({len(result['violations'])}건):")
            for v in result["violations"][:3]:
                print(f"     - {v}")
        missing = [k.replace("has_", "") for k, v in result["completeness_detail"].items() if not v]
        if missing:
            print(f"  📋 누락: {', '.join(missing)}")
        print()

    # 요약 저장
    out_file = CLAIMS_DIR / f"_qc_report_{datetime.now().strftime('%Y%m%d')}.json"
    out_file.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ QC 리포트 저장: {out_file.name}\n")

    # 종합 요약
    pass_count = sum(1 for r in all_results if "PASS" in r["grade"])
    fail_count = sum(1 for r in all_results if "FAIL" in r["grade"])
    print("━" * 50)
    print(f"📊 종합: 🟢 PASS {pass_count} / 🔴 FAIL {fail_count} / 전체 {len(all_results)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="APLB 클레임 QA/QC")
    parser.add_argument("--complex", help="특정 컴플렉스만")
    args = parser.parse_args()
    run(target_complex=args.complex)

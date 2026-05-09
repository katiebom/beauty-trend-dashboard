"""
APLB 마케팅 클레임 빌더
─────────────────────────────────────────────────────────────────
입력: data/aplb_research/{complex_id}/*.json (PubMed 페어/트리오 검색 결과)
출력: data/aplb_claims/{complex_id}_claims.json
       — Hero / Reason-to-Believe (RTB) / Tech / 인용가능 논문 / 위험 클레임

Gemini 1회 호출당 1개 컴플렉스 처리. 토큰 절감을 위해:
  - 페어당 상위 3건 abstract만 (1500자 이내)
  - 트리오 결과 0건이면 "세계 최초 클레임 가능" 플래그
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

from dotenv import load_dotenv
load_dotenv()

YAML_PATH    = Path(__file__).parent.parent / "config" / "aplb_products.yaml"
RESEARCH_DIR = Path(__file__).parent.parent / "data" / "aplb_research"
CLAIMS_DIR   = Path(__file__).parent.parent / "data" / "aplb_claims"

MAX_ABSTRACT_CHARS = 800       # 1200→800 (33% 절감)
MAX_PAPERS_PER_PAIR = 2        # 3→2
MAX_TOP_PAIRS = 8              # 모든 페어 대신 상위 8개만 (논문수 정렬)
# 모델 우선순위: 작은 → 큰 (cost 우선)
MODELS = [
    "gemini-2.5-flash-lite",    # 가장 저렴/빠름 (별도 quota), 1차
    "gemini-2.0-flash-lite",    # 2차
    "gemini-2.5-flash",         # 3차
    "gemini-2.0-flash",         # 4차
    "gemini-flash-latest",      # alias fallback
]


def load_aplb() -> dict:
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def gather_evidence(complex_id: str) -> dict:
    """컴플렉스의 모든 페어/트리오 검색 결과를 모음"""
    cx_dir = RESEARCH_DIR / complex_id
    if not cx_dir.exists():
        return {"pairs": [], "trios": []}

    pairs, trios = [], []
    for f in sorted(cx_dir.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        # 트리오는 파일명 prefix로 구분
        if f.name.startswith("TRIO_"):
            trios.append({
                "ingredients": d.get("ingredients", []),
                "paper_count": d["paper_count"],
                "articles": d["articles"][:MAX_PAPERS_PER_PAIR],
            })
        else:
            pairs.append({
                "pair": [d["ingredient_a"], d["ingredient_b"]],
                "paper_count": d["paper_count"],
                "articles": d["articles"][:MAX_PAPERS_PER_PAIR],
            })
    return {"pairs": pairs, "trios": trios}


def build_evidence_brief(complex_info: dict, evidence: dict) -> str:
    """Gemini에 넘길 압축 텍스트 (토큰 절감)"""
    lines = []
    lines.append(f"# 컴플렉스: {complex_info.get('trade_mark', complex_info['id'])}")
    lines.append(f"이름: {complex_info.get('name_kr', '')}")
    comp = complex_info.get('composition', {})
    if comp:
        lines.append(f"배합: {json.dumps(comp, ensure_ascii=False)}")
    lines.append(f"타겟: {', '.join(complex_info.get('target_indications', []))}")
    lines.append("")

    # 트리오 (가장 차별화 강한 시그널)
    if evidence["trios"]:
        lines.append("## 트리오 시너지 임상 근거")
        for tr in evidence["trios"]:
            ings = " + ".join(tr["ingredients"])
            lines.append(f"- {ings}: {tr['paper_count']}건")
            if tr["paper_count"] == 0:
                lines.append(f"  → ⚠️ 세계 최초 트리오 컴플렉스 마케팅 가능 시그널")
        lines.append("")

    # 페어 (높은 건수 우선) — 상위 N개만 (토큰 절감)
    pairs_sorted = sorted(evidence["pairs"], key=lambda x: -x["paper_count"])[:MAX_TOP_PAIRS]
    lines.append(f"## 페어 시너지 (상위 {len(pairs_sorted)}개, 논문수 정렬)")
    for p in pairs_sorted:
        a, b = p["pair"]
        lines.append(f"### {a} × {b} ({p['paper_count']}건)")
        for art in p["articles"][:2]:  # 상위 2건만
            title = (art.get("title") or "").strip()[:120]
            abs_text = (art.get("abstract") or "").strip()[:MAX_ABSTRACT_CHARS]
            year = art.get("year", "")
            journal = art.get("journal", "")
            pmid = art.get("pmid", "")
            lines.append(f"  • [{year}] {title}")
            lines.append(f"    {journal} | PMID:{pmid}")
            if abs_text:
                lines.append(f"    {abs_text}")
        lines.append("")
    return "\n".join(lines)


def call_gemini_for_claims(brief: str, complex_info: dict) -> dict | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY 없음")
        return None

    try:
        from google import genai
        from google.genai import types as genai_types
        client = genai.Client(api_key=api_key)
    except ImportError:
        print("❌ google-genai 패키지 미설치")
        return None

    prompt = f"""당신은 화장품 마케팅 + 의학 클레임 검증 전문가입니다.
아래는 APLB 컴플렉스의 PubMed 임상/기초 연구 근거 모음입니다.
이 자료를 토대로 **마케팅팀이 한국시장(KR)·북미시장(EN) 모두에서 그대로 사용할 수 있는 영/한 병기 클레임 카드**를 작성하세요.

{brief}

다음 형식의 JSON으로 응답 (JSON만, 다른 텍스트 없이).
**모든 텍스트 필드를 영문(_en)·국문(_kr) 두 가지로 작성**:

{{
  "hero_claim": {{
    "headline_en": "한 줄 영문 헤드라인",
    "headline_kr": "한 줄 한국어 헤드라인 (직역 아닌 자연스러운 한국 마케팅 카피)",
    "subheadline_en": "30자 영문 부제",
    "subheadline_kr": "30자 국문 부제",
    "scientific_basis_en": "왜 이 클레임이 가능한지 (PMID 인용 포함, 영문)",
    "scientific_basis_kr": "왜 이 클레임이 가능한지 (PMID 인용 포함, 국문)",
    "tier": "strong / moderate / weak"
  }},
  "rtb_points": [
    {{
      "point_en": "구체적 메커니즘 1줄 (영문)",
      "point_kr": "구체적 메커니즘 1줄 (국문)",
      "evidence": "PMID와 논문 제목 (영문 그대로 — 학술 인용)"
    }}
  ],
  "tech_story": {{
    "headline_en": "기술/공법 차별화 한 줄 (영문)",
    "headline_kr": "기술/공법 차별화 한 줄 (국문)",
    "supporting_facts_en": ["...", "..."],
    "supporting_facts_kr": ["...", "..."]
  }},
  "citation_ready_papers": [
    {{"pmid": "...", "title": "...", "year": "...",
      "use_case_en": "어디에 어떻게 인용할지 (영문)",
      "use_case_kr": "어디에 어떻게 인용할지 (국문)"}}
  ],
  "world_first_opportunity_en": "트리오/특정 조합이 0건이면 '세계 최초' 클레임 (영문), 없으면 null",
  "world_first_opportunity_kr": "트리오/특정 조합이 0건이면 '세계 최초' 클레임 (국문), 없으면 null",
  "risky_claims_to_avoid_en": ["회피 클레임 영문 1", "..."],
  "risky_claims_to_avoid_kr": ["회피 클레임 국문 1", "..."],
  "north_america_angle_en": "북미 시장 어필 포인트 (영문)",
  "north_america_angle_kr": "북미 시장 어필 포인트 (국문 — 글로벌팀/한국 브랜드 매니저용)"
}}

원칙:
- 모든 클레임에 PMID 근거 매핑. 근거 없는 클레임 금지.
- 한국 화장품 광고법 + FDA cosmetic claim 가이드 위반 위험 표현 회피.
  - 영문 금지: treat, cure, prevent, eliminate, 100%, guarantee
  - 국문 금지: 치료, 치유, 예방, 완벽 제거, 100%, 보장
- 안전 동사 사용:
  - 영문: help, support, visibly improve, promote, contribute
  - 국문: 도움, 케어, 관리, 가꾸어주는, 결을 정돈
- 트리오 0건이면 "세계 최초" 기회로 적극 활용.
- 국문은 직역하지 말고 한국 화장품 카피 톤 사용 ("빛나는 톤", "결을 정돈하는" 등).
- JSON만 응답. 마크다운/설명 없이."""

    last_err = None
    for model_name in MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=8000,
                    response_mime_type="application/json",
                ),
            )
            text = (response.text or "").strip()
            # 디버그: 원문 저장
            (CLAIMS_DIR / f"_last_raw_response.txt").write_text(text, encoding="utf-8")
            # 코드펜스 제거
            if "```" in text:
                # 첫 ``` 와 마지막 ``` 사이만 추출
                parts = text.split("```")
                if len(parts) >= 3:
                    text = parts[1]
                    if text.startswith("json"):
                        text = text[4:]
            text = text.strip()
            print(f"  ✓ {model_name} 응답 ({len(text)}자)")
            return json.loads(text)
        except Exception as e:
            last_err = str(e)
            if "429" in last_err or "RESOURCE_EXHAUSTED" in last_err:
                print(f"  ⚠️ {model_name} quota 소진 — 다음 모델 시도")
                continue
            elif "404" in last_err:
                print(f"  ⚠️ {model_name} 없음 — 다음 모델 시도")
                continue
            else:
                print(f"  ❌ Gemini 오류 ({model_name}): {last_err[:100]}")
                return None
    print(f"  ⏭️ 모든 모델 quota 소진 — 내일 재시도")
    return None


def run(target_complex: str | None = None):
    data = load_aplb()
    all_complexes = (
        data.get("complexes", [])
        + data.get("single_actives", [])
        + data.get("candidate_ingredients", [])
    )

    if target_complex:
        all_complexes = [c for c in all_complexes if c["id"] == target_complex]
        if not all_complexes:
            print(f"❌ 컴플렉스 '{target_complex}' 없음")
            return

    CLAIMS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n=== APLB 마케팅 클레임 빌더 ({len(all_complexes)}개 컴플렉스) ===\n")

    for cx in all_complexes:
        cx_id = cx["id"]
        print(f"━━━ {cx.get('trade_mark') or cx.get('name_kr')} ━━━")

        evidence = gather_evidence(cx_id)
        if not evidence["pairs"]:
            print(f"  ⚠️ 검색 결과 없음 — aplb_pair_search 먼저 실행\n")
            continue

        brief = build_evidence_brief(cx, evidence)
        print(f"  📚 페어 {len(evidence['pairs'])}개, 트리오 {len(evidence['trios'])}개 입력")

        claims = call_gemini_for_claims(brief, cx)
        if not claims:
            print(f"  ⏭️ 스킵\n")
            continue

        out_file = CLAIMS_DIR / f"{cx_id}_claims.json"
        out_file.write_text(
            json.dumps({
                "complex_id": cx_id,
                "trade_mark": cx.get("trade_mark", ""),
                "name_kr": cx.get("name_kr", ""),
                "generated_at": datetime.now().isoformat(),
                "claims": claims,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  ✅ 저장: {out_file.name}")
        print(f"  📌 Hero: {claims.get('hero_claim', {}).get('headline', '')[:80]}")
        if claims.get("world_first_opportunity"):
            print(f"  🏆 세계 최초: {claims['world_first_opportunity'][:80]}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="APLB 마케팅 클레임 빌더")
    parser.add_argument("--complex", help="특정 컴플렉스만 (예: lipo_gluta_niac_cen)")
    args = parser.parse_args()
    run(target_complex=args.complex)

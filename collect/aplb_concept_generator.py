"""
APLB 신제품 컨셉 자동 생성기 (Gemini)
─────────────────────────────────────────────────────────────────
입력:
  - 신성분 시그널 (data/emerging_signals/latest.json) — 임박/등장 신호
  - APLB 보유 성분 (config/aplb_products.yaml)
  - 페어 시너지 (data/aplb_research/_summary_*.json)

출력:
  data/aplb_concepts/concepts_{date}.json
  - 각 컨셉: 제품명, 핵심 클레임, 농도, 시너지 페어, 임상 근거 PMID
  - 우선순위: 신호 강도 × APLB 자산 활용도 × 트리오 0건 (세계최초)

사용법:
  python collect/aplb_concept_generator.py
  python collect/aplb_concept_generator.py --top 10
─────────────────────────────────────────────────────────────────
"""

import os
import sys
import json
import yaml
import argparse
from pathlib import Path
from datetime import date, datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent
EMERGING_LATEST  = ROOT / "data" / "emerging_signals" / "latest.json"
APLB_YAML        = ROOT / "config" / "aplb_products.yaml"
RESEARCH_DIR     = ROOT / "data" / "aplb_research"
CONCEPTS_DIR     = ROOT / "data" / "aplb_concepts"
LANDSCAPE_LATEST = ROOT / "data" / "commercial_landscape" / "latest.json"

MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]


def load_data():
    sig = {}
    if EMERGING_LATEST.exists():
        sig = json.loads(EMERGING_LATEST.read_text(encoding="utf-8"))
    aplb = yaml.safe_load(APLB_YAML.read_text(encoding="utf-8"))
    landscape = {}
    if LANDSCAPE_LATEST.exists():
        landscape = json.loads(LANDSCAPE_LATEST.read_text(encoding="utf-8")).get("results", {})
    return sig, aplb, landscape


def get_aplb_owned(aplb: dict) -> list[str]:
    owned = set()
    for cx in aplb.get("complexes", []) + aplb.get("single_actives", []):
        for ing in cx.get("primary_ingredients", []):
            owned.add(ing.lower())
    return sorted(owned)


def get_trio_zero_pairs(target_emerging: list[str], aplb_owned: list[str]) -> list[dict]:
    """페어 검색 결과에서 trio 0건 = 세계 최초 가능 조합 추출"""
    zero_trios = []
    for cx_dir in RESEARCH_DIR.iterdir():
        if not cx_dir.is_dir():
            continue
        for f in cx_dir.glob("TRIO_*.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                if d.get("paper_count", 0) == 0:
                    zero_trios.append({
                        "ingredients": d.get("ingredients", []),
                        "complex_id": cx_dir.name,
                    })
            except Exception:
                continue
    return zero_trios


def call_gemini_for_concepts(emerging_top: list, aplb_owned: list[str],
                              zero_trios: list[dict], aplb_data: dict,
                              landscape: dict = None) -> dict | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types as genai_types
        client = genai.Client(api_key=api_key)
    except ImportError:
        return None

    # 입력 압축 (상업 정보 통합)
    landscape = landscape or {}
    def _comm(ing_id):
        c = landscape.get(ing_id, {})
        if not c:
            return ""
        kr_brand = (c.get("top_brands_kr", [{}])[0] if c.get("top_brands_kr") else {}).get("brand", "")
        us_brand = (c.get("top_brands_us", [{}])[0] if c.get("top_brands_us") else {}).get("brand", "")
        return (f", 상업={c.get('commercial_tier','?')}/{c.get('aplb_strategic_posture','-')}, "
                f"강자=KR:{kr_brand or '-'}/US:{us_brand or '-'}, "
                f"갭={c.get('market_gap','')[:60]}")

    emerging_brief = "\n".join([
        f"- {s['name_kr']} ({s['name_en']}): "
        f"신호={s['signal_label']}, T1={s['tier_dist']['T1']}, T2={s['tier_dist']['T2']}, 점수={s['signal_score']}"
        f"{_comm(s.get('ingredient_id') or s.get('id') or '')}"
        for s in emerging_top[:15]
    ])
    trio_brief = "\n".join([
        f"- {' + '.join(t['ingredients'])} (현재 0 임상 → 세계 최초 가능)"
        for t in zero_trios[:10]
    ])

    aplb_complex_summary = []
    for cx in aplb_data.get("complexes", []):
        aplb_complex_summary.append(
            f"- {cx.get('trade_mark', cx.get('id'))}: "
            f"{', '.join(cx.get('primary_ingredients', []))}"
        )

    prompt = f"""당신은 K-beauty 신제품 컨셉 디자이너입니다.
APLB(에이필리비) 브랜드의 신제품 5개 컨셉을 제안하세요.

## APLB 자산
보유 핵심 성분: {', '.join(aplb_owned)}

기존 컴플렉스 (재활용 후보):
{chr(10).join(aplb_complex_summary)}

## 신성분 시그널 (PubMed 3-Tier 분석)
{emerging_brief}

## 세계 최초 가능 트리오 (현재 임상 0건)
{trio_brief or '(데이터 없음)'}

## 작성 요구사항
다음 JSON 형식으로 응답 (JSON만):
{{
  "concepts": [
    {{
      "rank": 1,
      "product_name_kr": "한국어 제품명",
      "product_name_en": "English product name",
      "complex_trademark": "신규 컴플렉스 상표명 (예: LIPO GLUTA NIAC EXO™)",
      "category": "serum/cream/ampoule/mask/...",
      "target_audience": "예: 30대 여성 + 시술 후 회복 사용자",
      "core_claim": "한 줄 클레임 (안전 동사 사용 — 'help, support, visibly improve')",
      "key_ingredients": [
        {{"name": "성분명", "concentration": "권장 농도", "role": "역할"}}
      ],
      "synergy_rationale": "이 조합이 왜 시너지 있는지 (PMID 인용 가능하면 포함)",
      "world_first_aspect": "세계 최초 요소 (없으면 null)",
      "channel_strategy": "유통 채널 제안 (clinic, premium ecom, mass)",
      "price_band_kr": "예: 5만원대",
      "differentiation_vs_competitors": "경쟁사(Skinceuticals, Beauty of Joseon 등) 대비 차별점",
      "regulatory_risk": "한국 식약처/FDA 등록 가능성 평가 (low/medium/high)",
      "rd_complexity": "low/medium/high",
      "expected_voc_appeal": "예상 후기 키워드 (어떤 후기가 나올 것 같은가)"
    }}
  ]
}}

원칙:
- APLB 보유 성분과 신성분을 적극 결합 (자산 활용 우선)
- 트리오 0건 조합 우선 (세계 최초 마케팅)
- 한국 광고법 위반 표현(치료, 예방, 100% 등) 절대 금지
- 5개 컨셉은 다양해야 함 (카테고리·가격대·타겟 분산)
- regulatory_risk가 high이면 plant-derived 등 안전 대안 명시
- ★ 상업 정보(상업 티어, 강자 브랜드, 시장 갭)를 적극 반영:
  · C0/C1 성분: 선점 진입 컨셉 — 빠른 출시 강조
  · C2 성분: 차별화 (농도/페어/기술) 강조 — 'differentiation_vs_competitors'에 강자 직접 언급
  · C3 성분: 프리미엄/Black 라인만 — 가격대 5~10만원대
"""
    last_err = None
    for model in MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.5,
                    max_output_tokens=8000,
                    response_mime_type="application/json",
                ),
            )
            text = (response.text or "").strip()
            # 디버그
            CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)
            (CONCEPTS_DIR / "_last_raw_response.txt").write_text(text, encoding="utf-8")
            print(f"  ✓ {model} 응답 ({len(text)}자)")
            return json.loads(text)
        except Exception as e:
            last_err = str(e)
            if "429" in last_err or "RESOURCE_EXHAUSTED" in last_err:
                print(f"  ⚠️ {model} quota — 다음 모델")
                continue
            elif "404" in last_err:
                continue
            else:
                print(f"  ❌ {model}: {last_err[:120]}")
                return None
    print(f"  ⏭️ 모든 모델 실패")
    return None


def run(top_n: int = 5):
    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)
    sig_data, aplb, landscape = load_data()
    if not sig_data.get("signals"):
        print("❌ 신성분 시그널 없음 — emerging_ingredients 먼저 실행")
        return None

    aplb_owned = get_aplb_owned(aplb)
    zero_trios = get_trio_zero_pairs([], aplb_owned)
    emerging_top = [s for s in sig_data["signals"]
                    if s["total_papers"] >= 3 and "약함" not in s["signal_label"]][:15]

    print(f"\n=== APLB 신제품 컨셉 생성 (Gemini, 상업 분석 통합) ===")
    print(f"  APLB 보유 성분: {len(aplb_owned)}개")
    print(f"  신성분 후보: {len(emerging_top)}개")
    print(f"  세계 최초 트리오 가능: {len(zero_trios)}개")
    print(f"  상업 분석 데이터: {len(landscape)}개\n")

    result = call_gemini_for_concepts(emerging_top, aplb_owned, zero_trios, aplb, landscape)
    if not result:
        return None

    out = {
        "generated_at": datetime.now().isoformat(),
        "input_summary": {
            "aplb_owned_count": len(aplb_owned),
            "emerging_top_count": len(emerging_top),
            "zero_trio_count": len(zero_trios),
        },
        "concepts": result.get("concepts", []),
    }
    out_file = CONCEPTS_DIR / f"concepts_{date.today().isoformat()}.json"
    out_file.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = CONCEPTS_DIR / "latest.json"
    latest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 저장: {out_file.name}\n")

    # 요약
    print("━" * 60)
    print(f"📊 {len(result.get('concepts', []))}개 신제품 컨셉")
    print("━" * 60)
    for c in result.get("concepts", [])[:top_n]:
        print(f"\n#{c.get('rank')} [{c.get('category', '')}] {c.get('product_name_kr', '')}")
        print(f"  상표: {c.get('complex_trademark', '')}")
        print(f"  Hero: {c.get('core_claim', '')[:100]}")
        if c.get("world_first_aspect"):
            print(f"  🏆 세계 최초: {c['world_first_aspect'][:90]}")
    print()
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="APLB 신제품 컨셉 생성")
    parser.add_argument("--top", type=int, default=5, help="요약 출력 개수")
    args = parser.parse_args()
    run(top_n=args.top)

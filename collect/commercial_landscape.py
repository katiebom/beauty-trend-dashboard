"""
상업 시장 경쟁 분석 (Commercial Tier C0~C3)
─────────────────────────────────────────────────────────────────
학술 시그널(T1/T2/T3)과 별개로 "이미 브랜드가 점유했는가" 추적.

상업 티어:
  C0 무주공산: 시장 부재, 브랜드 강자 0~1개
  C1 진입기:  소수 브랜드 시작, 미점유 영역 多
  C2 성장기:  3~5개 강자 형성 중, 차별화 가능
  C3 포화기:  Top 1~3 브랜드가 70%+ 점유, 진입 장벽 높음

APLB 전략 포지션 (학술 × 상업 매트릭스):
  Pioneer        T2/T3 학술 강 + C0/C1 → 시장 선점 (최우선)
  Differentiator T2/T3 학술 강 + C2    → 차별화 (농도/페어/기술)
  Late Entry     T2 강 + C3            → 프리미엄/Black 라인만
  Skip           T 약 + C3             → 회피
  Watch          T 약 + C0/C1          → 후속 모니터링

데이터 소스:
  - 정량 시그널 (raw_trends): V-Index, T-Score, N-Score, amazon_result_count
  - 정성 평가 (Gemini): 시장 점유 브랜드 + 강도 + 갭

저장: data/commercial_landscape/latest.json
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
INGREDIENTS_YAML = ROOT / "config" / "ingredients.yaml"
TIERS_YAML       = ROOT / "config" / "journal_tiers.yaml"
EMERGING_LATEST  = ROOT / "data" / "emerging_signals" / "latest.json"
APLB_YAML        = ROOT / "config" / "aplb_products.yaml"
OUT_DIR          = ROOT / "data" / "commercial_landscape"

MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]
BATCH_SIZE = 8   # 한 번에 분석할 성분 수 (토큰 절감)


def load_ingredients() -> list[dict]:
    """ingredients.yaml + emerging_candidates 통합"""
    ings = yaml.safe_load(INGREDIENTS_YAML.read_text(encoding="utf-8")).get("ingredients", [])
    tiers = yaml.safe_load(TIERS_YAML.read_text(encoding="utf-8"))
    for c in tiers.get("emerging_candidates", []):
        if not any(i.get("id") == c["id"] for i in ings):
            ings.append(c)
    return ings


def load_emerging_signals() -> dict:
    """학술 시그널 로드 (T1/T2/T3, signal_score)"""
    if not EMERGING_LATEST.exists():
        return {}
    d = json.loads(EMERGING_LATEST.read_text(encoding="utf-8"))
    return {s["ingredient_id"]: s for s in d.get("signals", [])}


def load_aplb_owned() -> set[str]:
    if not APLB_YAML.exists():
        return set()
    aplb = yaml.safe_load(APLB_YAML.read_text(encoding="utf-8"))
    owned = set()
    for cx in aplb.get("complexes", []) + aplb.get("single_actives", []):
        for ing in cx.get("primary_ingredients", []):
            owned.add(ing.lower())
    return owned


def build_brief(ings: list[dict], academic_signals: dict, aplb_owned: set[str]) -> str:
    """배치 분석용 압축 텍스트"""
    lines = []
    for ing in ings:
        ing_id = ing["id"]
        sig = academic_signals.get(ing_id, {})
        owned = "✅ APLB 보유" if any(o in ing.get("name_en", "").lower() or o == ing_id.lower()
                                    for o in aplb_owned) else "🆕 APLB 미보유"
        td = sig.get("tier_dist", {})
        lines.append(
            f"- [{ing_id}] {ing.get('name_kr','')} ({ing.get('name_en','')}) {owned}\n"
            f"  카테고리: {ing.get('category','')}, "
            f"학술 T1={td.get('T1',0)} T2={td.get('T2',0)} T3={td.get('T3',0)}, "
            f"학술점수={sig.get('signal_score',0)}, "
            f"학술라벨={sig.get('signal_label','-')}"
        )
    return "\n".join(lines)


def call_gemini_for_landscape(ings: list[dict], academic_signals: dict,
                               aplb_owned: set[str]) -> dict | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types as genai_types
        client = genai.Client(api_key=api_key)
    except ImportError:
        return None

    brief = build_brief(ings, academic_signals, aplb_owned)
    prompt = f"""당신은 K-beauty 화장품 시장 경쟁 분석 전문가입니다.
아래 성분들에 대해 **2025년 현재 시점 글로벌(특히 한국 + 북미) 시장 경쟁 구도**를 평가하세요.

분석할 성분:
{brief}

각 성분에 대해 다음 JSON 형식으로 응답 (JSON만):
{{
  "ingredients": [
    {{
      "id": "성분 id",
      "commercial_tier": "C0|C1|C2|C3",
      "tier_rationale": "왜 이 티어인지 한 줄",
      "top_brands_kr": [
        {{"brand": "브랜드명", "product_example": "대표 제품", "strength": "high|medium|low"}}
      ],
      "top_brands_us": [
        {{"brand": "브랜드명", "product_example": "대표 제품", "strength": "high|medium|low"}}
      ],
      "marketing_intensity": "low|medium|high|extreme",
      "market_gap": "어떤 차별화 지점이 비어 있는지 한 줄 (농도/페어/타겟/가격대 등)",
      "aplb_strategic_posture": "Pioneer|Differentiator|Late_Entry_Premium|Skip|Watch",
      "aplb_action_kr": "APLB가 취해야 할 구체 액션 1~2문장 (한국어)",
      "key_competitor_to_beat": "가장 위협적인 1개 브랜드명 또는 'none'"
    }}
  ]
}}

상업 티어 정의:
- C0 무주공산: 매스 시장 거의 없음, 시술/derma 영역만
- C1 진입기: 소수 브랜드, 점유 미정 (10~30개 제품 추정)
- C2 성장기: 3~5개 강자 형성 중, 시장 다양성 있음
- C3 포화기: Top 1~3 브랜드 70%+ 점유, 신규 진입 어려움

APLB 전략 포지션 정의:
- Pioneer: 학술 강 + 상업 약 → 선점 진입
- Differentiator: 학술 강 + 상업 중 → 차별화 (농도·페어·기술)
- Late_Entry_Premium: 학술 강 + 상업 강 → 프리미엄/Black 라인만
- Skip: 학술 약 + 상업 강 → 회피
- Watch: 학술 약 + 상업 약 → 모니터링

원칙:
- ★ **실제 알려진 브랜드만** 사용. 가짜 브랜드 만들지 말 것.

【한국 K-beauty 주요 브랜드 — 반드시 검토 후 해당하면 Top 브랜드에 포함】
대중/매스: 메디큐브 (APR/AGR), 아누아 (Anua), 코스알엑스 (COSRX), 달바 (d'Alba),
  구다이글로벌 (Goodai Global), 바닐라코, 에뛰드, 미샤, 토니모리, 더샘
더마/스킨수티컬: 닥터지 (Dr.G), 닥터자르트 (Dr.Jart+), 일리윤 (ILLIYOON),
  스킨1004 (Skin1004), 아누아, 라운드랩, 토리든 (Torriden), 셀퓨전씨,
  스킨앤랩, 닥터오라클, 메디힐, 셀더마, 셀바이오랩
이너뷰티/기능성: 비레디 (Vrady), 정관장, 쥬랩 (Joon Lab)
성분 특화: 마녀공장, 어노브, 어퓨, 어반다이브, 라카, 아이소이, 헤라
인디/MZ: 라네즈, 닥터우즈, 어딕션, 메이크프렘, 어퓨, 필리밀리, 토리든

【한국 시술/약국 (T1 medical-aesthetic 영역 - 화장품 라인 별도 보유)】
ExoCoBio (엑소코바이오) — 본업은 의료용 엑소좀(BENEV, ASCEsphere 의료기기/시술용),
  화장품 라인은 ASCEsphere 데일리 케어 (medspa·올리브영 일부)
Rejuran (리쥬란) — 본업은 PDRN 시술용 주사제, 화장품 라인 'Rejuran Healer' 별도

【북미/글로벌】
The Ordinary, Paula's Choice, La Roche-Posay, Skinceuticals, CeraVe, Cetaphil,
Olay, Eucerin, Avene, Bioderma, Drunk Elephant, Glow Recipe, Beauty of Joseon,
Inkey List, Naturium, Versed, Good Molecules, Trinny London, Herbivore

규칙:
- 모르는 성분이면 brand: "unknown" 명시
- 한국 시장(올리브영/네이버/CJ온스타일) + 북미 시장(Sephora/Ulta/Amazon) 모두 평가
- 시술용 회사(ExoCoBio, Rejuran 등)는 화장품 라인이 있는 경우에만 cosmetic top brand로 포함하고
  product_example에 정확한 cosmetic 라인명 명시 (예: "ASCEsphere", "Rejuran Healer")
- 단순 시술용/의약품은 Top brand에서 제외 (학술/T1에 속함)
- JSON만 응답"""

    import time as _time
    last_err = None
    for model in MODELS:
        for attempt in range(2):  # 모델당 2회 재시도
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0.2,
                        max_output_tokens=8000,
                        response_mime_type="application/json",
                    ),
                )
                text = (response.text or "").strip()
                return json.loads(text)
            except Exception as e:
                last_err = str(e)
                if "429" in last_err or "RESOURCE_EXHAUSTED" in last_err:
                    print(f"  ⚠️ {model} quota — 다음 모델")
                    break  # 다음 모델로
                elif "503" in last_err or "UNAVAILABLE" in last_err:
                    if attempt == 0:
                        print(f"  ⏳ {model} 일시 과부하 — 5s 후 재시도")
                        _time.sleep(5)
                        continue
                    else:
                        print(f"  ⚠️ {model} 과부하 지속 — 다음 모델")
                        break
                elif "404" in last_err:
                    break
                else:
                    print(f"  ❌ {model}: {last_err[:120]}")
                    return None
    print(f"  ⏭️ 모든 모델 실패: {last_err[:120] if last_err else ''}")
    return None


def run(top_n: int = 30, force: bool = False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ings = load_ingredients()
    academic_signals = load_emerging_signals()
    aplb_owned = load_aplb_owned()

    # 우선순위: 학술 시그널 점수 높은 것 + APLB 미보유 우선
    def priority(ing):
        sig = academic_signals.get(ing["id"], {})
        return -(sig.get("signal_score", 0))
    ings_sorted = sorted(ings, key=priority)[:top_n]

    print(f"\n=== 상업 시장 경쟁 분석 (Commercial Landscape) ===")
    print(f"  분석 대상: {len(ings_sorted)}개 성분 (학술 시그널 점수 정렬)\n")

    all_results = {}
    today = date.today().isoformat()
    today_file = OUT_DIR / f"landscape_{today}.json"

    # 기존 오늘 데이터 있으면 이어서
    if today_file.exists() and not force:
        existing = json.loads(today_file.read_text(encoding="utf-8"))
        all_results = existing.get("results", {})
        print(f"  ℹ️ 오늘 캐시 발견 — {len(all_results)}개 이미 분석됨, 나머지 진행\n")

    pending = [ing for ing in ings_sorted if ing["id"] not in all_results]
    print(f"  잔여 분석: {len(pending)}개\n")

    # 배치 처리
    for i in range(0, len(pending), BATCH_SIZE):
        batch = pending[i:i + BATCH_SIZE]
        batch_ids = [ing["id"] for ing in batch]
        print(f"  배치 {i//BATCH_SIZE + 1}: {len(batch)}개 — {batch_ids}")

        result = call_gemini_for_landscape(batch, academic_signals, aplb_owned)
        if not result:
            print(f"  ⏭️ 배치 실패, 스킵")
            break

        for r in result.get("ingredients", []):
            all_results[r["id"]] = r

        # 진행 저장
        out = {
            "generated_at": datetime.now().isoformat(),
            "total_analyzed": len(all_results),
            "results": all_results,
        }
        today_file.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # latest 갱신 (빈 결과면 기존 데이터 보존)
    out = {
        "generated_at": datetime.now().isoformat(),
        "total_analyzed": len(all_results),
        "results": all_results,
    }
    latest_file = OUT_DIR / "latest.json"
    if all_results:
        latest_file.write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        print("  ⚠️ 결과 비어있음 — latest.json 보존 (덮어쓰기 안 함)")

    # 요약 출력
    print("\n" + "=" * 70)
    print("📊 상업 티어 분포 + APLB 전략 포지션")
    print("=" * 70)

    by_tier = {"C0": [], "C1": [], "C2": [], "C3": []}
    by_posture = {}
    for r in all_results.values():
        tier = r.get("commercial_tier", "?")
        if tier in by_tier:
            by_tier[tier].append(r)
        posture = r.get("aplb_strategic_posture", "?")
        by_posture.setdefault(posture, []).append(r)

    print(f"\n[티어별 분포]")
    for tier, items in by_tier.items():
        print(f"  {tier}: {len(items)}개")
        for r in items[:3]:
            print(f"     • {r['id']}: {r.get('tier_rationale','')[:80]}")

    print(f"\n[APLB 전략 포지션 — 우선순위]")
    posture_order = ["Pioneer", "Differentiator", "Late_Entry_Premium", "Watch", "Skip"]
    for p in posture_order:
        items = by_posture.get(p, [])
        if not items:
            continue
        emoji = {"Pioneer":"🚀", "Differentiator":"⚡", "Late_Entry_Premium":"💎",
                 "Watch":"👀", "Skip":"⛔"}.get(p, "")
        print(f"\n  {emoji} {p}: {len(items)}개")
        for r in items[:5]:
            print(f"     • [{r.get('commercial_tier')}] {r['id']}: {r.get('aplb_action_kr','')[:90]}")

    print(f"\n✅ 저장: {OUT_DIR / 'latest.json'}\n")
    return all_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="상업 시장 경쟁 분석")
    parser.add_argument("--top", type=int, default=30, help="분석 대상 N개")
    parser.add_argument("--force", action="store_true", help="오늘 캐시 무시")
    args = parser.parse_args()
    run(top_n=args.top, force=args.force)

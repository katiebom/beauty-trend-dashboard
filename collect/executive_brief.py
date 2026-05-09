"""
Executive Brief — 6개 데이터 소스 종합 의사결정 엔진
─────────────────────────────────────────────────────────────────
입력 통합:
  - raw_trends                       (V/N/T/ET 점수, df_raw)
  - data/emerging_signals/latest     (3-Tier 학술 시그널)
  - data/commercial_landscape/latest (브랜드 점유 + APLB 전략)
  - data/aplb_claims/*               (마케팅 클레임 + QC)
  - data/clinical_trials/latest      (활성 임상시험)
  - data/aplb_concepts/latest        (Gemini 신제품 컨셉)
  - df_manual                        (실판매 입력)

출력:
  data/executive_brief/latest.json
  - top_decisions (5개 의사결정 카드)
  - weekly_changes (TOP 3 상승/하락)
  - warning_signals (데이터 누락, 신호 흔들림 등)
  - hot_topics (긴급 monitoring)
  - kpi (전체 상태)
  - ai_synthesis (Gemini 200자 요약)

매일 cron으로 자동 갱신. Gemini 1회 호출 (배치).

사용:
  python collect/executive_brief.py
─────────────────────────────────────────────────────────────────
"""

import os
import sys
import json
import yaml
import argparse
from pathlib import Path
from datetime import date, datetime, timedelta
from collections import Counter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent
INGREDIENTS_YAML = ROOT / "config" / "ingredients.yaml"
APLB_YAML        = ROOT / "config" / "aplb_products.yaml"
EMERGING_LATEST  = ROOT / "data" / "emerging_signals" / "latest.json"
LANDSCAPE_LATEST = ROOT / "data" / "commercial_landscape" / "latest.json"
CT_LATEST        = ROOT / "data" / "clinical_trials" / "latest.json"
CONCEPTS_LATEST  = ROOT / "data" / "aplb_concepts" / "latest.json"
CLAIMS_DIR       = ROOT / "data" / "aplb_claims"
RESEARCH_CACHE   = ROOT / "data" / "research_cache"
OUT_DIR          = ROOT / "data" / "executive_brief"

MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]


# ═══════════════════════════════════════════════════════════════
# 데이터 로딩
# ═══════════════════════════════════════════════════════════════
def load_aplb_owned() -> set[str]:
    if not APLB_YAML.exists():
        return set()
    aplb = yaml.safe_load(APLB_YAML.read_text(encoding="utf-8"))
    owned = set()
    for cx in aplb.get("complexes", []) + aplb.get("single_actives", []):
        for ing in cx.get("primary_ingredients", []):
            owned.add(ing.lower())
    return owned


def load_raw_trends() -> dict:
    """raw_trends에서 latest V-Index per ingredient + 7일 변화"""
    try:
        from config.sheets_client import read_all, TAB_RAW_TRENDS
        import pandas as pd
        rows = read_all(TAB_RAW_TRENDS)
        if not rows:
            return {"latest": {}, "changes": {}, "data_freshness": "no_data"}
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value"])

        latest_date = df["date"].max()
        v_df = df[df["metric_name"] == "v_index"]
        if v_df.empty:
            return {"latest": {}, "changes": {}, "data_freshness": "no_v_index"}

        latest = (v_df.sort_values("date").groupby("ingredient_id").tail(1)
                  .set_index("ingredient_id")["value"].to_dict())

        # 7일 전 값 (있으면)
        cutoff = latest_date - timedelta(days=7)
        old = (v_df[v_df["date"] <= cutoff].sort_values("date")
               .groupby("ingredient_id").tail(1)
               .set_index("ingredient_id")["value"].to_dict())
        changes = {}
        for ing, cur in latest.items():
            if ing in old:
                changes[ing] = cur - old[ing]

        days_since_latest = (datetime.now().date() - latest_date.date()).days
        return {
            "latest": latest,
            "changes": changes,
            "latest_date": str(latest_date.date()),
            "days_since_latest": days_since_latest,
            "data_freshness": "fresh" if days_since_latest <= 2 else (
                "stale" if days_since_latest <= 7 else "very_stale"),
        }
    except Exception as e:
        return {"latest": {}, "changes": {}, "data_freshness": f"error: {e}"}


def load_emerging() -> dict:
    if not EMERGING_LATEST.exists():
        return {}
    return json.loads(EMERGING_LATEST.read_text(encoding="utf-8"))


def load_landscape() -> dict:
    if not LANDSCAPE_LATEST.exists():
        return {}
    return json.loads(LANDSCAPE_LATEST.read_text(encoding="utf-8")).get("results", {})


def load_clinical_trials() -> list:
    if not CT_LATEST.exists():
        return []
    return json.loads(CT_LATEST.read_text(encoding="utf-8")).get("summary", [])


def load_concepts() -> list:
    if not CONCEPTS_LATEST.exists():
        return []
    return json.loads(CONCEPTS_LATEST.read_text(encoding="utf-8")).get("concepts", [])


def load_claim_qc() -> dict:
    """기존 QC 리포트 또는 즉시 계산"""
    qc_files = sorted(CLAIMS_DIR.glob("_qc_report_*.json"), reverse=True)
    if not qc_files:
        return {"total": 0, "pass": 0, "revise": 0, "fail": 0, "by_complex": []}
    qc = json.loads(qc_files[0].read_text(encoding="utf-8"))
    total = len(qc)
    p = sum(1 for r in qc if "PASS" in r.get("grade", ""))
    rv = sum(1 for r in qc if "REVISE" in r.get("grade", "") or "CONDITIONAL" in r.get("grade", ""))
    fl = sum(1 for r in qc if "FAIL" in r.get("grade", ""))
    return {
        "total": total, "pass": p, "revise": rv, "fail": fl,
        "by_complex": [{"id": r["complex_id"], "grade": r["grade"]} for r in qc],
    }


# ═══════════════════════════════════════════════════════════════
# 의사결정 추출 로직 (룰 기반 1차 — Gemini 보강 2차)
# ═══════════════════════════════════════════════════════════════
def extract_decisions(emerging: dict, landscape: dict, raw: dict,
                       aplb_owned: set, ct: list, concepts: list,
                       claim_qc: dict) -> list[dict]:
    """6 데이터 소스 교차 분석 → TOP 의사결정 후보 추출"""
    decisions = []

    signals = emerging.get("signals", [])
    sig_map = {s["ingredient_id"]: s for s in signals}
    ct_map = {c["ingredient_id"]: c for c in ct}

    # ── 결정 1: 즉시 신제품 (Pioneer) ──────────────────────────
    pioneer_candidates = []
    for ing_id, comm in landscape.items():
        if comm.get("aplb_strategic_posture") != "Pioneer":
            continue
        sig = sig_map.get(ing_id, {})
        if "약함" in sig.get("signal_label", "") or sig.get("total_papers", 0) < 3:
            continue
        # APLB 미보유 (en 매칭)
        en_lower = (sig.get("name_en", "") or "").lower()
        if any(o in en_lower for o in aplb_owned):
            continue
        pioneer_candidates.append({
            "ingredient_id": ing_id,
            "name_kr": sig.get("name_kr", comm.get("id", ing_id)),
            "score": sig.get("signal_score", 0),
            "commercial_tier": comm.get("commercial_tier", ""),
            "key_competitor": comm.get("key_competitor_to_beat", ""),
            "market_gap": comm.get("market_gap", "")[:120],
            "ct_active": ct_map.get(ing_id, {}).get("active_count", 0),
        })
    pioneer_candidates.sort(key=lambda x: -x["score"])
    if pioneer_candidates:
        top = pioneer_candidates[0]
        decisions.append({
            "type": "🚀 즉시 신제품",
            "priority": "high",
            "title": f"{top['name_kr']} — 시장 선점 (Pioneer)",
            "rationale": (
                f"학술 시그널 강 (점수 {top['score']}) + 상업 {top['commercial_tier']} (미점유) + "
                f"활성 임상 {top['ct_active']}건. 가장 큰 위협: {top['key_competitor'] or '없음'}."
            ),
            "next_action": f"R&D 6주 안에 컴플렉스 컨셉 → 시장 갭: {top['market_gap']}",
            "supporting_data": ["emerging_signals", "commercial_landscape", "clinical_trials"],
            "ingredient_id": top["ingredient_id"],
        })

    # ── 결정 2: 마케팅 강화 (V-Index 폭발 + APLB 보유) ──────────
    marketing_boost = []
    for ing_id, comm in landscape.items():
        sig = sig_map.get(ing_id, {})
        en_lower = (sig.get("name_en", "") or "").lower()
        is_owned = any(o in en_lower for o in aplb_owned)
        if not is_owned:
            continue
        v = raw.get("latest", {}).get(ing_id, 0)
        chg = raw.get("changes", {}).get(ing_id, 0)
        if v >= 60 or chg >= 5:
            marketing_boost.append({
                "ingredient_id": ing_id,
                "name_kr": sig.get("name_kr", ing_id),
                "v_index": v,
                "v_change": chg,
                "tier": comm.get("commercial_tier", ""),
            })
    marketing_boost.sort(key=lambda x: -(x["v_index"] + x["v_change"] * 2))
    if marketing_boost:
        top = marketing_boost[0]
        decisions.append({
            "type": "⚡ 마케팅 강화",
            "priority": "high" if top["v_change"] > 5 else "medium",
            "title": f"{top['name_kr']} — APLB 자산, 신호 폭발",
            "rationale": (
                f"V-Index {top['v_index']:.0f} (7일 변화 {top['v_change']:+.1f}) + APLB 보유. "
                f"상업 {top['tier']}."
            ),
            "next_action": "기존 라인 콘텐츠/광고 강화 + SNS 캠페인",
            "supporting_data": ["raw_trends", "commercial_landscape"],
            "ingredient_id": top["ingredient_id"],
        })

    # ── 결정 3: Black 프리미엄 라인 (학술 강 + C3 포화 + 보유) ──
    black_candidates = []
    for ing_id, comm in landscape.items():
        if comm.get("commercial_tier") != "C3":
            continue
        sig = sig_map.get(ing_id, {})
        if sig.get("total_papers", 0) < 5:
            continue
        en_lower = (sig.get("name_en", "") or "").lower()
        is_owned = any(o in en_lower for o in aplb_owned)
        if not is_owned:
            continue
        black_candidates.append({
            "ingredient_id": ing_id,
            "name_kr": sig.get("name_kr", ing_id),
            "score": sig.get("signal_score", 0),
            "competitor": comm.get("key_competitor_to_beat", ""),
        })
    black_candidates.sort(key=lambda x: -x["score"])
    if black_candidates:
        top = black_candidates[0]
        decisions.append({
            "type": "💎 Black 프리미엄",
            "priority": "medium",
            "title": f"{top['name_kr']} Black 라인 신설",
            "rationale": (
                f"포화 시장(C3) + APLB 보유 + 학술 점수 {top['score']}. "
                f"매스 진입은 어렵지만 고농도/안정화 기술로 차별화."
            ),
            "next_action": "고농도 (예: 3~5x) + microfluidizer 안정화 → 5~10만원대 채널",
            "supporting_data": ["commercial_landscape", "emerging_signals"],
            "ingredient_id": top["ingredient_id"],
        })

    # ── 결정 4: 글로벌 출시 (클레임 PASS + 트리오 0건) ──────────
    pass_complexes = [c["id"] for c in claim_qc.get("by_complex", []) if "PASS" in c.get("grade", "")]
    if pass_complexes:
        decisions.append({
            "type": "🌍 글로벌 출시",
            "priority": "high",
            "title": f"클레임 PASS 컴플렉스 {len(pass_complexes)}개 글로벌 진출 검토",
            "rationale": (
                f"QC PASS {claim_qc.get('pass',0)}/{claim_qc.get('total',0)}, "
                f"PMID 100% 검증. 일부는 트리오 0건 = 세계 최초 클레임 가능."
            ),
            "next_action": "마케팅팀에 클레임 카드 전달 + 북미 채널(Sephora/Amazon) 진입",
            "supporting_data": ["aplb_claims"],
            "complexes": pass_complexes[:3],
        })

    # ── 결정 5: 회피/축소 (V 약 + C3 포화) ──────────────────────
    avoid_candidates = []
    for ing_id, comm in landscape.items():
        sig = sig_map.get(ing_id, {})
        v = raw.get("latest", {}).get(ing_id, 0)
        chg = raw.get("changes", {}).get(ing_id, 0)
        if comm.get("commercial_tier") == "C3" and v < 30 and chg <= 0:
            avoid_candidates.append({
                "ingredient_id": ing_id,
                "name_kr": sig.get("name_kr", ing_id),
                "v_index": v,
            })
    if avoid_candidates:
        top = avoid_candidates[0]
        decisions.append({
            "type": "⛔ 회피/축소",
            "priority": "low",
            "title": f"{top['name_kr']} 라인 정리 검토",
            "rationale": f"V-Index {top['v_index']:.0f} 약세 + 상업 포화 — 신규 진입 가치 낮음",
            "next_action": "기존 SKU만 유지, 신규 투자 중단",
            "supporting_data": ["raw_trends", "commercial_landscape"],
            "ingredient_id": top["ingredient_id"],
        })

    return decisions


def extract_warnings(raw: dict, claim_qc: dict, landscape: dict) -> list[dict]:
    """⚠️ 주의 시그널"""
    warnings = []

    # 데이터 신선도
    days_since = raw.get("days_since_latest", 999)
    if days_since > 7:
        warnings.append({
            "type": "🔴 데이터 누락",
            "msg": f"V-Index 마지막 수집 {days_since}일 전 ({raw.get('latest_date','?')}). cron 점검 필요.",
            "severity": "high",
        })
    elif days_since > 2:
        warnings.append({
            "type": "🟡 데이터 신선도",
            "msg": f"V-Index 마지막 수집 {days_since}일 전. 수집기 정상 작동 확인.",
            "severity": "medium",
        })

    # 클레임 위반
    fail_count = claim_qc.get("fail", 0)
    revise_count = claim_qc.get("revise", 0)
    if fail_count > 0:
        warnings.append({
            "type": "🔴 클레임 환각 검출",
            "msg": f"FAIL {fail_count}개 — 마케팅 사용 전 재생성 필수.",
            "severity": "high",
        })
    if revise_count > 0:
        warnings.append({
            "type": "🟠 클레임 위반 표현",
            "msg": f"REVISE {revise_count}개 — 한국 광고법 위반 표현(예방/치료 등) 수정 필요.",
            "severity": "medium",
        })

    return warnings


def extract_hot_topics(emerging: dict, landscape: dict, ct: list) -> dict:
    """🔥 Hot Topics — 우선 모니터링 대상"""
    signals = emerging.get("signals", [])
    imminent = [s for s in signals if "임박" in s.get("signal_label", "")]
    pioneer = [s for s in signals
               if landscape.get(s["ingredient_id"], {}).get("aplb_strategic_posture") == "Pioneer"]
    ct_top = sorted(ct, key=lambda x: -x.get("future_signal_score", 0))[:3]

    return {
        "imminent": [{"name_kr": s["name_kr"], "score": s["signal_score"]}
                     for s in imminent[:3]],
        "pioneer": [{"name_kr": s["name_kr"]} for s in pioneer[:3]],
        "ct_active": [{"name_kr": c["name_kr"], "active": c["active_count"]}
                      for c in ct_top[:3]],
    }


def compute_kpi(emerging: dict, landscape: dict, raw: dict, claim_qc: dict,
                concepts: list, ct: list) -> dict:
    signals = emerging.get("signals", [])
    return {
        "total_tracked": len(signals),
        "imminent": sum(1 for s in signals if "임박" in s.get("signal_label", "")),
        "pioneer": sum(1 for r in landscape.values() if r.get("aplb_strategic_posture") == "Pioneer"),
        "differentiator": sum(1 for r in landscape.values() if r.get("aplb_strategic_posture") == "Differentiator"),
        "claim_pass_rate": (claim_qc["pass"] / claim_qc["total"] * 100) if claim_qc.get("total") else 0,
        "concept_count": len(concepts),
        "active_clinical": sum(c.get("active_count", 0) for c in ct),
        "data_freshness": raw.get("data_freshness", "unknown"),
        "days_since_data": raw.get("days_since_latest", -1),
    }


# ═══════════════════════════════════════════════════════════════
# Gemini 종합 시사점 (200자)
# ═══════════════════════════════════════════════════════════════
def call_gemini_synthesis(decisions: list, warnings: list, hot: dict, kpi: dict) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return ""
    try:
        from google import genai
        from google.genai import types as genai_types
        client = genai.Client(api_key=api_key)
    except ImportError:
        return ""

    decisions_brief = "\n".join([
        f"- {d['type']} ({d.get('priority','?')}): {d.get('title','')} — {d.get('rationale','')[:120]}"
        for d in decisions[:5]
    ])
    warnings_brief = "\n".join([f"- {w['type']}: {w['msg']}" for w in warnings[:3]])

    prompt = f"""당신은 K-beauty 브랜드(APLB) CSO에게 보고하는 전략 애널리스트입니다.
6개 데이터 소스를 종합하여, **이번 주 APLB가 우선순위로 해야 할 일**을 200자 이내로 작성하세요.

## KPI
- 추적 성분: {kpi.get('total_tracked',0)}개
- 임박 신호: {kpi.get('imminent',0)}개
- Pioneer 후보: {kpi.get('pioneer',0)}개
- 클레임 PASS율: {kpi.get('claim_pass_rate',0):.0f}%

## TOP 의사결정
{decisions_brief}

## 주의 시그널
{warnings_brief or '(없음)'}

## Hot Topics
- 🔥 임박: {', '.join([h['name_kr'] for h in hot.get('imminent',[])][:3]) or '없음'}
- 🚀 Pioneer: {', '.join([h['name_kr'] for h in hot.get('pioneer',[])][:3]) or '없음'}

요청:
- 한국어 200자 이내, 불릿 3개
- 구체적·실행 가능한 액션
- "검토하세요" 같은 모호한 표현 금지 — "X를 N주 안에 Y" 식으로
- 단일 문단 또는 불릿 3개"""

    for model in MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=600,
                ),
            )
            return (response.text or "").strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err or "503" in err:
                continue
            return f"(Gemini 오류: {err[:80]})"
    return "(모든 Gemini 모델 quota 소진 — 내일 재시도)"


# ═══════════════════════════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════════════════════════
def run():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("\n=== Executive Brief 생성 ===")

    aplb_owned = load_aplb_owned()
    raw = load_raw_trends()
    emerging = load_emerging()
    landscape = load_landscape()
    ct = load_clinical_trials()
    concepts = load_concepts()
    claim_qc = load_claim_qc()

    print(f"  ✓ APLB 보유 성분: {len(aplb_owned)}")
    print(f"  ✓ raw_trends: {len(raw.get('latest', {}))}개 V-Index, 신선도={raw.get('data_freshness')}")
    print(f"  ✓ emerging_signals: {len(emerging.get('signals', []))}")
    print(f"  ✓ commercial_landscape: {len(landscape)}")
    print(f"  ✓ clinical_trials: {len(ct)}")
    print(f"  ✓ aplb_concepts: {len(concepts)}")
    print(f"  ✓ claim_qc: {claim_qc.get('total',0)} (PASS {claim_qc.get('pass',0)})")

    decisions = extract_decisions(emerging, landscape, raw, aplb_owned, ct, concepts, claim_qc)
    warnings = extract_warnings(raw, claim_qc, landscape)
    hot = extract_hot_topics(emerging, landscape, ct)
    kpi = compute_kpi(emerging, landscape, raw, claim_qc, concepts, ct)

    print(f"\n  📊 의사결정 추출: {len(decisions)}개")
    print(f"  ⚠️ 주의 시그널: {len(warnings)}개")

    print("\n  🤖 Gemini 종합 시사점 생성...")
    ai_synthesis = call_gemini_synthesis(decisions, warnings, hot, kpi)

    out = {
        "generated_at": datetime.now().isoformat(),
        "kpi": kpi,
        "top_decisions": decisions,
        "weekly_changes": {
            "biggest_gainers": sorted(
                [(k, v) for k, v in raw.get("changes", {}).items() if v > 0],
                key=lambda x: -x[1]
            )[:5],
            "biggest_losers": sorted(
                [(k, v) for k, v in raw.get("changes", {}).items() if v < 0],
                key=lambda x: x[1]
            )[:5],
        },
        "warning_signals": warnings,
        "hot_topics": hot,
        "ai_synthesis": ai_synthesis,
    }
    out_file = OUT_DIR / f"brief_{date.today().isoformat()}.json"
    out_file.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "latest.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 콘솔 출력
    print("\n" + "═" * 60)
    print("📋 EXECUTIVE BRIEF — 의사결정 요약")
    print("═" * 60)
    print(f"\n[KPI] 추적 {kpi['total_tracked']} | 임박 {kpi['imminent']} | "
          f"Pioneer {kpi['pioneer']} | 클레임 PASS {kpi['claim_pass_rate']:.0f}%")
    print(f"\n[TOP 의사결정 {len(decisions)}개]")
    for i, d in enumerate(decisions, 1):
        print(f"  {i}. {d['type']} ({d['priority']}) — {d['title']}")
        print(f"     ▸ {d['rationale'][:100]}")
        print(f"     ▸ 액션: {d['next_action'][:100]}")
    if warnings:
        print(f"\n[⚠️ 주의 시그널 {len(warnings)}개]")
        for w in warnings:
            print(f"  - {w['type']}: {w['msg']}")
    print(f"\n[🤖 AI 종합 시사점]\n{ai_synthesis}")
    print(f"\n✅ 저장: {OUT_DIR / 'latest.json'}\n")
    return out


if __name__ == "__main__":
    run()

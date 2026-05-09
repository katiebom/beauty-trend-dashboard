"""
ClinicalTrials.gov 진행 중 임상시험 추적
─────────────────────────────────────────────────────────────────
ClinicalTrials.gov v2 API (무료, key 불필요):
  GET https://clinicaltrials.gov/api/v2/studies
  query.term: 검색어
  filter.overallStatus: RECRUITING|ACTIVE_NOT_RECRUITING|ENROLLING_BY_INVITATION

T1 미래 시그널: 진행 중 임상시험 = 12~24개월 후 논문 출판 → 2~3년 후 코스메틱 진입.
신성분 후보 + APLB 보유 성분에 대해 활성 임상 추적.

저장: data/clinical_trials/{ingredient_id}_{date}.json
요약: data/clinical_trials/latest.json

사용법:
  python collect/clinical_trials.py
  python collect/clinical_trials.py --ingredient exosome
─────────────────────────────────────────────────────────────────
"""

import os
import sys
import json
import yaml
import time
import argparse
import requests
from pathlib import Path
from datetime import date, datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).parent.parent
INGREDIENTS_YAML = ROOT / "config" / "ingredients.yaml"
TIERS_YAML       = ROOT / "config" / "journal_tiers.yaml"
OUT_DIR          = ROOT / "data" / "clinical_trials"

API_URL = "https://clinicaltrials.gov/api/v2/studies"
ACTIVE_STATUS = "RECRUITING|ACTIVE_NOT_RECRUITING|ENROLLING_BY_INVITATION|NOT_YET_RECRUITING"


def fetch_active_trials(query: str, max_results: int = 30) -> list[dict]:
    """ClinicalTrials.gov v2 API — 활성 임상시험 검색
    v2 API: filter.overallStatus는 콤마 구분, fields는 생략 → 전체 받고 클라이언트 필터.
    """
    params = {
        "query.term": query,
        "filter.overallStatus": "RECRUITING,ACTIVE_NOT_RECRUITING,ENROLLING_BY_INVITATION,NOT_YET_RECRUITING",
        "pageSize": min(max_results, 100),
    }
    try:
        r = requests.get(API_URL, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  ❌ API 실패: {e}")
        return []

    studies = []
    for s in data.get("studies", []):
        proto = s.get("protocolSection", {})
        ident = proto.get("identificationModule", {})
        status = proto.get("statusModule", {})
        cond = proto.get("conditionsModule", {})
        arms = proto.get("armsInterventionsModule", {})
        sponsor = proto.get("sponsorCollaboratorsModule", {})
        design = proto.get("designModule", {})

        nct = ident.get("nctId", "")
        studies.append({
            "nct_id": nct,
            "title": ident.get("briefTitle", ""),
            "status": status.get("overallStatus", ""),
            "phases": design.get("phases", []),
            "study_type": design.get("studyType", ""),
            "conditions": cond.get("conditions", []),
            "interventions": [
                {"type": i.get("type", ""), "name": i.get("name", "")}
                for i in arms.get("interventions", [])
            ],
            "sponsor": sponsor.get("leadSponsor", {}).get("name", ""),
            "primary_completion": status.get("primaryCompletionDateStruct", {}).get("date", ""),
            "url": f"https://clinicaltrials.gov/study/{nct}" if nct else "",
        })
    return studies


def load_target_ingredients() -> list[dict]:
    """ingredients.yaml + journal_tiers.yaml의 emerging_candidates"""
    targets = []
    ings = yaml.safe_load(INGREDIENTS_YAML.read_text(encoding="utf-8")).get("ingredients", [])
    targets.extend(ings)
    tiers = yaml.safe_load(TIERS_YAML.read_text(encoding="utf-8"))
    cands = tiers.get("emerging_candidates", [])
    for c in cands:
        if not any(t.get("id") == c["id"] for t in targets):
            targets.append(c)
    return targets


def build_query(ing: dict) -> str:
    """검색 쿼리 — 영문명 + 'skin' 또는 'topical' 조합"""
    name = ing.get("name_en") or ing.get("id", "")
    aliases = ing.get("aliases", [])
    terms = [name] + aliases
    or_term = " OR ".join(f'"{t}"' for t in terms if t)
    return f"({or_term}) AND (skin OR topical OR cosmetic OR dermatology)"


def run(target_id: str | None = None):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = load_target_ingredients()
    if target_id:
        targets = [t for t in targets if t.get("id") == target_id]
        if not targets:
            print(f"❌ '{target_id}' 없음")
            return

    print(f"\n=== ClinicalTrials.gov 활성 임상 추적 ({len(targets)}개) ===\n")
    summary = []
    for ing in targets:
        ing_id = ing["id"]
        query = build_query(ing)
        print(f"  [{ing_id}] {query[:60]}...")
        trials = fetch_active_trials(query, max_results=30)

        # 최근 완료 예정만 (핫한 진행 시그널)
        recent_trials = [t for t in trials if t.get("primary_completion", "")[:4] in
                          ("2025", "2026", "2027", "2028")]

        out = {
            "ingredient_id": ing_id,
            "name_kr": ing.get("name_kr", ""),
            "name_en": ing.get("name_en", ing_id),
            "query": query,
            "active_count": len(trials),
            "recent_complete_count": len(recent_trials),
            "trials": trials,
            "fetched_at": datetime.now().isoformat(),
        }
        out_file = OUT_DIR / f"{ing_id}_{date.today().isoformat()}.json"
        out_file.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

        # 시그널 점수 (T1 미래 가중)
        future_signal = len(recent_trials) * 2 + len(trials)
        summary.append({
            "ingredient_id": ing_id,
            "name_kr": ing.get("name_kr", ""),
            "name_en": ing.get("name_en", ing_id),
            "active_count": len(trials),
            "recent_complete_count": len(recent_trials),
            "future_signal_score": future_signal,
            "top_trials": [
                {
                    "nct_id": t["nct_id"],
                    "title": t["title"][:120],
                    "status": t["status"],
                    "phases": t["phases"],
                    "completion": t["primary_completion"],
                    "sponsor": t["sponsor"],
                    "url": t["url"],
                } for t in trials[:5]
            ],
        })

        active = len(trials)
        recent = len(recent_trials)
        badge = "🔥" if recent >= 3 else ("🟡" if recent >= 1 else ("🟢" if active >= 1 else "⚪"))
        print(f"     {badge} 활성 {active}건, 2025-2028 완료예정 {recent}건")

        time.sleep(0.4)  # API rate limit

    # 요약 정렬 + 저장
    summary.sort(key=lambda x: -x["future_signal_score"])
    latest = {
        "generated_at": datetime.now().isoformat(),
        "total_ingredients": len(summary),
        "summary": summary,
    }
    (OUT_DIR / "latest.json").write_text(
        json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n" + "━" * 60)
    print("📊 ClinicalTrials.gov TOP 10 (미래 시그널 점수)")
    print("━" * 60)
    for i, s in enumerate(summary[:10], 1):
        if s["active_count"] == 0:
            continue
        print(f"{i:>2}. {s['name_kr']} ({s['name_en']})")
        print(f"     활성 {s['active_count']}건 · 2025-28 완료예정 {s['recent_complete_count']}건 · "
              f"score={s['future_signal_score']}")
        for t in s["top_trials"][:2]:
            print(f"     • [{t['phases'] or '?'}] {t['title'][:80]}")
            print(f"       {t['sponsor']} | {t['url']}")

    print(f"\n✅ 저장: {OUT_DIR / 'latest.json'}\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ClinicalTrials.gov 추적")
    parser.add_argument("--ingredient", help="특정 성분만")
    args = parser.parse_args()
    run(target_id=args.ingredient)

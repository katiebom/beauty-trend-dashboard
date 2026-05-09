"""
TikTok 신규 성분 발굴기
─────────────────────────────────────────────────────────────────
기존 tiktok_trends.py: 미리 등록된 성분의 T-Score 추적
이 파일:               아직 YAML에 없는 새로운 버즈 성분 자동 발굴

방식:
  1. 200+ 뷰티/스킨케어 Discovery 해시태그 조회수 수집
  2. 직전 스냅샷 대비 급등 해시태그 선별 (LLM 없음)
  3. Gemini 1회 배치 호출 → "이게 화장품 성분인가?" 분류
  4. YAML에 없는 것만 → data/tiktok_discovery_{date}.json 저장

토큰 효율:
  - 해시태그 수집/순위: LLM 없음 (순수 API + 수학)
  - Gemini 호출: 하루 1회, 상위 20개 배치 → ~500 토큰
─────────────────────────────────────────────────────────────────
"""

import os
import sys
import time
import json
import yaml
import math
import requests
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

# ── 설정 ──────────────────────────────────────────────────────────
YAML_PATH   = Path(__file__).parent.parent / "config" / "ingredients.yaml"
DATA_DIR    = Path(__file__).parent.parent / "data"
SNAP_FILE   = DATA_DIR / "tiktok_discovery_snapshot.json"   # 누적 조회수 기록
OUT_DIR     = DATA_DIR / "tiktok_discovery"

REQUEST_DELAY = 1.0   # 초
GROWTH_THRESHOLD = 0.03   # 주간 3% 이상 증가 시 플래그

TIKTOK_API = "https://www.tiktok.com/api/challenge/detail/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.tiktok.com/",
}

# ── 해시태그 목록 ────────────────────────────────────────────────
# [A] 트렌드 모니터링용 — 조회수만 추적, 성분 후보 절대 아님
MONITOR_HASHTAGS = [
    "skintok", "skincare", "skincareroutine", "skincaretips",
    "beautyreview", "ingredientcheck", "glowskin", "glasskin",
    "dermatologist", "actives", "chemicalexfoliant", "slugging",
    "kbeauty", "koreanskincare", "glassskin", "dewyskin",
    "cleanbeauty", "skincareproduct", "beautytips",
]

# [B] 성분 후보 해시태그 — Gemini로 성분 여부 분류
INGREDIENT_HASHTAGS = [
    "spermidine", "meroterpene", "urolithin", "urolithina",
    "coq10skin", "coq10skincare", "mitochondriaskin",
    "atp skincare", "adenosine", "adenosineskincare",
    "palmitoyl", "palmitoylpentapeptide", "matrixyl",
    "argireline", "acetylhexapeptide",
    "hydroxypinacolone", "hpr", "granactive",
    "bidens pilosa", "bidenspilosa",
    "sea buckthorn", "seabuckthorn", "hippophae",
    "snow mushroom", "snowmushroom", "tremella",
    "fulvic acid", "fulvicacid",
    "turmeric skincare", "curcumin skincare",
    "willow bark", "willowbark", "salicin",
    "licorice root", "licoriceroot", "glabridin",
    "kojic acid", "kojicacid",
    "mandelic acid", "mandelicacid",
    "phytic acid", "phyticacid",
    "ferulic acid", "ferulicacid",
    "lactobionic acid",
    "gluconolactone",
    "bisabolol",
    "centella", "centellaasiatica", "tigc",
    "panthenol", "provitaminb5",
    "ceramide", "ceramidenp", "ceramideap",
    "sphingosine",
    "cholesterol skincare",
    "fatty acid skincare", "linoleicacid",
    "squalene", "squalane",
    "jojoba", "jojobaoil",
    "marula", "marulaoil",
    "rosehip", "rosehipoil",
    "sea kelp", "seakelp", "fucoidan",
    "spirulina skincare",
    "chlorella skincare",
    "red algae skincare", "carrageenan",
    "hyaluronic acid", "hyaluronicacid", "sodiumhyaluronate",
    "polyglutamicacid", "pga serum",
    "beta glucan", "betaglucan",
    "oat extract", "avenaextract", "colloidal oat",
    "lactobacillus", "fermented skincare",
    "postbiotic", "postbioticskin",
    "saccharomyces", "yeast skincare",
    "galactomyces",
    "pitera",
    "snail mucin", "snailmucin",
    "bee venom", "beevenom",
    "propolis serum",
    "red ginseng", "redginseng",
    "fermented ginseng",
    "mugwort", "artemisia",
    "houttuynia", "heartleaf",
    "centella serum",
    "rice bran", "ricebran",
    "sake skincare",
    "kombucha skincare",
    "pomegranate extract",
    "sea daffodil", "narcissus extract",
    "acai skincare",
    "bakuchiol",
    "retinaldehyde", "retinal serum",
    "hydroxyacids",
    "lha skincare",
    "pdo thread", "polydioxanone",
    "pdrn", "salmon dna",
    "exosome serum", "exosomeskincare",
    "stem cell skincare", "stemcell",
    "growth factor serum", "egfserum",
    "peptide serum", "peptides",
    "ghkcu", "copper peptide",
    "niacinamide",
    "tranexamic acid", "tranexamicacid",
    "azelaic acid", "azelaicacid",
    "alpha arbutin", "alphaarbutin",
    "kojic acid", "kojicacid",
    "cysteamine",
    "vitamin c serum", "ascorbicacid",
    "thd ascorbate",
    "ectoin", "ectoinskincare",
    "spermidine serum",
    "idebenone skincare",
    "astaxanthin skincare",
    "ergothioneine", "ergothioneineskin",
    "glutathione serum", "glutathioneskin",
    "resveratrol serum",
    "quercetin skincare",
    "melatonin skincare",
    "taurine skincare",
    "carnosine skincare",
    "zinc pca", "zincpca",
    "succinic acid", "succinicacid",
    "sodium pca",
    "urea cream", "urea skincare",
    "lactic acid", "lacticacid",
    "mandelic acid",
    "salicylic acid", "salicylicacid", "bha",
]

# 전체 수집 대상 (모니터링 + 성분 후보 합산)
DISCOVERY_HASHTAGS = list(dict.fromkeys(MONITOR_HASHTAGS + INGREDIENT_HASHTAGS))
# 성분 후보만 별도 관리 (set으로 빠른 조회)
INGREDIENT_CANDIDATE_SET = set(INGREDIENT_HASHTAGS)


def load_yaml_ingredients() -> set[str]:
    """YAML에 이미 등록된 성분 ID + 영문명 (소문자) 반환"""
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    registered = set()
    for ing in data["ingredients"]:
        registered.add(ing["id"].lower())
        registered.add(ing["name_en"].lower().split("(")[0].strip())
    return registered


def load_snapshot() -> dict:
    """이전 조회수 스냅샷 로드"""
    if SNAP_FILE.exists():
        with open(SNAP_FILE, "r") as f:
            return json.load(f)
    return {}


def save_snapshot(snapshot: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SNAP_FILE, "w") as f:
        json.dump(snapshot, f, indent=2)


def fetch_view_count(hashtag: str) -> int | None:
    """TikTok 해시태그 누적 조회수 반환"""
    try:
        r = requests.get(
            TIKTOK_API,
            params={"challengeName": hashtag},
            headers=HEADERS,
            timeout=10,
        )
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            return None
        data = r.json()
        challenge = data.get("challengeInfo", {}).get("challenge", {}) or \
                    data.get("challengeInfo", {}).get("stats", {})
        stats = data.get("challengeInfo", {}).get("stats", {})
        views = stats.get("viewCount") or challenge.get("viewCount", 0)
        return int(views) if views else None
    except Exception:
        return None


def collect_views(hashtags: list[str]) -> dict[str, int]:
    """모든 discovery 해시태그 조회수 수집"""
    results = {}
    total = len(hashtags)
    for i, tag in enumerate(hashtags, 1):
        views = fetch_view_count(tag)
        if views:
            results[tag] = views
            if i % 20 == 0:
                print(f"  [{i}/{total}] #{tag}: {views:,}")
        time.sleep(REQUEST_DELAY)
    return results


def calculate_growth(current: dict[str, int], prev_snapshot: dict) -> list[dict]:
    """조회수 증가율 계산 — 급등 해시태그 반환"""
    today = date.today().isoformat()
    scored = []

    for tag, views in current.items():
        prev_entry = prev_snapshot.get(tag)
        if not prev_entry:
            # 첫 수집 — 베이스라인만 기록
            growth_rate = 0.0
            weekly_delta = 0
        else:
            prev_views = prev_entry.get("views", 0)
            weekly_delta = views - prev_views
            growth_rate = weekly_delta / prev_views if prev_views > 0 else 0.0

        # 절대 규모 점수 (log 정규화, 1B 기준)
        size_score = min(math.log10(views + 1) / 9, 1.0) if views > 0 else 0

        scored.append({
            "hashtag": tag,
            "views": views,
            "weekly_delta": weekly_delta,
            "growth_rate": round(growth_rate, 4),
            "size_score": round(size_score, 3),
        })

    # 성장률 × 규모 복합 정렬
    scored.sort(key=lambda x: x["growth_rate"] * 0.7 + x["size_score"] * 0.3, reverse=True)
    return scored


def classify_with_gemini(hashtags: list[str]) -> tuple[dict[str, dict], bool]:
    """
    Gemini 1회 배치 호출 — 해시태그가 화장품 성분인지 분류
    반환: (분류결과 dict, 성공 여부)
    실패 시: 빈 dict + False 반환 → 호출부에서 pending 처리
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("  [discovery] GEMINI_API_KEY 없음 — 분류 스킵")
        return {}, False

    # 시도할 모델 순서 (quota 소진 시 다음 모델로)
    models_to_try = ["gemini-2.0-flash", "gemini-1.5-flash-latest", "gemini-1.5-flash-002"]

    for model_name in models_to_try:
        try:
            from google import genai
            from google.genai import types as genai_types

            client = genai.Client(api_key=api_key)
            hashtag_list = "\n".join(f"- {h}" for h in hashtags)

            prompt = f"""다음 TikTok 해시태그들이 화장품/스킨케어 성분인지 분류하세요.

해시태그 목록:
{hashtag_list}

각 항목에 대해 JSON 배열로 응답하세요:
{{"results": [{{"hashtag": "해시태그명", "is_ingredient": true/false,
  "ingredient_name_en": "공식 성분명(INCI)", "ingredient_name_kr": "한국어명",
  "category": "barrier|anti_aging|brightening|exfoliant|hydration|regeneration|natural|기타",
  "confidence": "high|medium|low"}}]}}

is_ingredient=true 기준: 실제 화장품 원료·활성 성분. 브랜드명·루틴명·일반 뷰티 용어는 false.
JSON만 반환."""

            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=2048,
                ),
            )

            text = response.text
            if "```json" in text:
                text = text[text.find("```json") + 7: text.rfind("```")].strip()
            elif "```" in text:
                text = text[text.find("```") + 3: text.rfind("```")].strip()

            data = json.loads(text)
            print(f"  [discovery] {model_name} 분류 성공")
            return {r["hashtag"]: r for r in data.get("results", [])}, True

        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
                print(f"  [discovery] {model_name} quota 소진 → 다음 모델 시도")
                continue
            print(f"  [discovery] Gemini 분류 실패 ({model_name}): {e}")
            return {}, False

    print("  [discovery] 모든 모델 quota 소진 → classification_pending=True 로 저장")
    return {}, False


def run(top_n: int = 20):
    """메인 실행
    - 오늘 파일이 있고 classification_pending=True 면 → Gemini만 재시도
    - 오늘 파일이 있고 pending=False 면 → 완전 스킵
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    out_file = OUT_DIR / f"discovery_{today}.json"

    # ── Gemini 재시도 모드 ──────────────────────────────────────────
    if out_file.exists():
        existing = json.loads(out_file.read_text())
        if not existing.get("classification_pending"):
            print(f"[discovery] 오늘 이미 완료됨 — 스킵 ({out_file.name})")
            return existing
        # pending 상태: 수집은 완료됐으므로 Gemini만 재시도
        print(f"[discovery] classification_pending 감지 — Gemini 분류 재시도")
        pending_tags = [c["hashtag"] for c in existing.get("raw_candidates", [])]
        classifications, success = classify_with_gemini(pending_tags)
        if success:
            flagged = _build_flagged(existing.get("raw_candidates", []), classifications)
            existing.update({
                "classification_pending": False,
                "new_candidates": len(flagged),
                "flagged": flagged,
            })
            out_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
            print(f"  재시도 성공 — 성분 후보 {len(flagged)}개")
        else:
            print("  재시도 실패 — 내일 다시 시도")
        return existing

    print(f"\n=== TikTok 신규 성분 발굴 ({len(DISCOVERY_HASHTAGS)}개 해시태그) ===")

    # 1. 기존 YAML 성분 목록 로드
    registered = load_yaml_ingredients()
    print(f"  YAML 등록 성분: {len(registered)}개")

    # 2. 이전 스냅샷 로드
    prev_snapshot = load_snapshot()
    print(f"  이전 스냅샷: {'있음' if prev_snapshot else '없음 (첫 실행)'}")

    # 3. 조회수 수집
    print(f"\n  조회수 수집 중 (약 {len(DISCOVERY_HASHTAGS) * REQUEST_DELAY:.0f}초 소요)...")
    current_views = collect_views(DISCOVERY_HASHTAGS)
    print(f"  수집 완료: {len(current_views)}/{len(DISCOVERY_HASHTAGS)}개")

    # 4. 스냅샷 업데이트
    new_snapshot = {tag: {"views": v, "date": today} for tag, v in current_views.items()}
    save_snapshot({**prev_snapshot, **new_snapshot})

    # 5. 성장률 계산
    growth_data = calculate_growth(current_views, prev_snapshot)

    # 6. 후보 필터링:
    #    - INGREDIENT_CANDIDATE_SET에 포함된 것만 (모니터링용 제외)
    #    - YAML 미등록
    #    - 최소 100만 뷰
    raw_candidates = [
        g for g in growth_data
        if g["hashtag"] in INGREDIENT_CANDIDATE_SET
        and not any(kw in g["hashtag"].lower().replace(" ", "") for kw in registered)
        and g["views"] > 1_000_000
    ][:top_n]

    print(f"\n  성분 후보 (YAML 미등록): {len(raw_candidates)}개")
    for c in raw_candidates[:5]:
        print(f"    #{c['hashtag']}: {c['views']/1e6:.1f}M views (주간 +{c['growth_rate']*100:.1f}%)")

    # 7. Gemini 분류 (1회 배치)
    candidate_tags = [c["hashtag"] for c in raw_candidates]
    classifications, gemini_ok = {}, False
    if candidate_tags:
        print(f"\n  Gemini 분류 중 ({len(candidate_tags)}개 배치)...")
        classifications, gemini_ok = classify_with_gemini(candidate_tags)
        if gemini_ok:
            ingredient_count = sum(1 for v in classifications.values() if v.get("is_ingredient"))
            print(f"  성분으로 확인: {ingredient_count}개")

    # 8. 최종 결과 구성
    flagged = _build_flagged(raw_candidates, classifications) if gemini_ok else []

    result = {
        "date": today,
        "total_hashtags_checked": len(DISCOVERY_HASHTAGS),
        "views_collected": len(current_views),
        "new_candidates": len(flagged),
        "classification_pending": not gemini_ok,   # Gemini 실패 시 True → 내일 재시도
        "raw_candidates": raw_candidates,           # pending 재시도용
        "flagged": flagged,
        "top_overall": growth_data[:10],
        # 모니터링 해시태그 조회수 별도 기록
        "monitor": {
            tag: {"views": current_views.get(tag, 0), "views_M": round(current_views.get(tag, 0)/1e6, 1)}
            for tag in MONITOR_HASHTAGS if tag in current_views
        },
    }

    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    status = "⏳ Gemini 분류 대기 중 (내일 자동 재시도)" if not gemini_ok else f"✅ 성분 후보 {len(flagged)}개"
    print(f"\n  저장: {out_file.name} — {status}")
    print(f"=== 발굴 완료 ===\n")
    return result


def _build_flagged(raw_candidates: list[dict], classifications: dict) -> list[dict]:
    """Gemini 분류 결과로 최종 flagged 리스트 구성"""
    flagged = []
    for g in raw_candidates:
        cls = classifications.get(g["hashtag"], {})
        if cls.get("is_ingredient"):
            flagged.append({
                **g,
                "ingredient_name_en": cls.get("ingredient_name_en", g["hashtag"]),
                "ingredient_name_kr": cls.get("ingredient_name_kr", ""),
                "category": cls.get("category", "기타"),
                "confidence": cls.get("confidence", "low"),
                "in_yaml": False,
            })
    return flagged


def load_latest() -> dict | None:
    """대시보드에서 최신 발굴 결과 로드"""
    if not OUT_DIR.exists():
        return None
    files = sorted(OUT_DIR.glob("discovery_*.json"), reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text())


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TikTok 신규 성분 발굴기")
    parser.add_argument("--top", type=int, default=20, help="상위 N개 후보 (기본 20)")
    args = parser.parse_args()
    run(top_n=args.top)

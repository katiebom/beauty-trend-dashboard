"""
성분 연구 데이터 분석기 — Gemini Flash API 기반 (무료)
─────────────────────────────────────────────────────────────────
PubMed / CIR 수집 데이터를 읽어 Gemini API로 구조화 추출:
  - 성분명 (Target Ingredient)
  - 작용 기전 (Mechanism of Action)
  - 효능 및 결과 (Efficacy & Results)
  - 유효 농도 (Optimal Concentration)
  - 시너지 성분 (Synergy Formulation)
  - 충돌 / 불안정 (Conflict / Instability)
  - R&D 인사이트 (R&D Insight)

무료 한도: Gemini 2.0 Flash — 1,500 req/일, 1M TPM
저장: data/research_cache/{ingredient_id}/analyzed_{date}.json
      Google Sheets TAB_RD_INSIGHTS (설정 시)

사용법:
  python collect/research_analyzer.py                   # 전체 성분
  python collect/research_analyzer.py --ingredient ectoin
  python collect/research_analyzer.py --source pubmed   # 특정 소스만
─────────────────────────────────────────────────────────────────
"""

import os
import sys
import json
import time
import argparse
from datetime import date, datetime
from pathlib import Path

from google import genai
from google.genai import types as genai_types
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

# ── 설정 ──────────────────────────────────────────────────────────
CACHE_DIR  = Path(__file__).parent.parent / "data" / "research_cache"

# Gemini 2.0 Flash: 무료 tier (1,500 req/일, 1M TPM)
# 더 높은 품질이 필요하면 "gemini-1.5-pro"로 변경 (유료)
MODEL = "gemini-2.0-flash"

MAX_ABSTRACT_CHARS = 800   # 논문당 초록 최대 문자 수 (1500→800, 약 47% 절감)
MAX_PAPERS_PER_CALL = 2    # API 호출당 논문 수 (3→2, 약 33% 절감)
REQUEST_DELAY = 4.0         # API 호출 간 딜레이 (초) — RPM 30 한도 안전 (15 RPM)
MAX_RETRIES = 3
DAILY_BUDGET = 60           # 하루 최대 호출 수 (안전 cap)

# ── 시스템 프롬프트 (캐시됨) ────────────────────────────────────
# 변경하면 캐시 미스 발생하므로 안정적으로 유지
SYSTEM_PROMPT = """You are a senior cosmetic formulation scientist and clinical data analyst.
Your role: analyze cosmetic/pharmaceutical ingredient research papers and extract structured insights for product development teams.

OUTPUT RULES:
- Base ONLY on explicit data in the provided text. Do not hallucinate.
- Mark as "N/A" when data is insufficient or not mentioned.
- All text output in Korean (한국어).
- Be concise and actionable — this data feeds into product development decisions.
- For concentration ranges, include the unit (%, mg/mL, etc.)
- For efficacy results, include sample sizes (n=X) and statistical significance if mentioned.

You MUST return valid JSON matching the exact schema below. No other text outside the JSON block."""

# ── 추출 스키마 ──────────────────────────────────────────────────
EXTRACTION_SCHEMA = {
    "ingredient_id": "string",
    "name_en": "string",
    "name_kr": "string",
    "analysis_date": "string (ISO date)",
    "paper_count_analyzed": "integer",
    "source": "string",
    "extracted": {
        "mechanism_of_action": "피부 작용 기전 요약 (3줄 이내). 근거 논문 없으면 N/A",
        "efficacy_results": "임상/논문에서 입증된 효능과 유의미한 결과값. 수치 포함. 없으면 N/A",
        "optimal_concentration": "논문에서 확인된 유효 농도 범위 (%). 없으면 N/A",
        "synergy_formulation": "시너지 성분과 이유. 없으면 N/A",
        "conflict_instability": "길항 성분 또는 안정성 저해 조건 (pH, 온도 등). 없으면 N/A",
        "rnd_insight": "이 데이터 기반 신제품 기획 시사점 2~3문장. 시장 기회 포함",
        "key_findings": ["논문에서 발견된 주요 팩트 목록 (최대 5개)"],
        "data_quality": "high | medium | low — 분석한 논문의 임상 데이터 신뢰도",
        "research_stage": "기초연구 | 임상연구 | 더마코스메틱전환 | 코스메슈티컬 | 메인스트림",
    }
}


def already_analyzed_today(ingredient_id: str) -> bool:
    """오늘 이미 분석 완료된 성분이면 True → API 호출 스킵"""
    today = date.today().isoformat()
    analyzed = list((CACHE_DIR / ingredient_id).glob(f"analyzed_{today}.json"))
    return len(analyzed) > 0


def pubmed_cache_unchanged(ingredient_id: str, source: str) -> bool:
    """PubMed 캐시가 어제와 동일하면 True → 재분석 불필요 (토큰 절감)
    동일 PMID 셋트면 분석 결과 똑같으므로 재호출 의미 없음.
    """
    import hashlib
    ing_dir = CACHE_DIR / ingredient_id
    if not ing_dir.exists():
        return False
    files = sorted(ing_dir.glob(f"{source}_*.json"), reverse=True)
    if len(files) < 2:
        return False
    # 오늘 vs 가장 최근 다른 날짜
    today_data = json.loads(files[0].read_text(encoding="utf-8"))
    today_pmids = sorted([a.get("pmid", "") for a in today_data.get("articles", [])])
    today_hash = hashlib.md5(",".join(today_pmids).encode()).hexdigest()

    # analyzed cache에 prev_hash 저장 → 비교
    last_analyzed = sorted(ing_dir.glob("analyzed_*.json"), reverse=True)
    if not last_analyzed:
        return False
    prev = json.loads(last_analyzed[0].read_text(encoding="utf-8"))
    return prev.get("pubmed_hash") == today_hash


# 일일 호출 카운터 (메모리)
_daily_call_count = {"pubmed": 0, "cir": 0}


def get_daily_call_count() -> int:
    return sum(_daily_call_count.values())


def load_cached_data(ingredient_id: str, source: str) -> dict | None:
    """캐시된 수집 데이터 로드"""
    ing_dir = CACHE_DIR / ingredient_id
    if not ing_dir.exists():
        return None

    # 가장 최근 파일 선택
    pattern = f"{source}_*.json"
    files = sorted(ing_dir.glob(pattern), reverse=True)
    if not files:
        return None

    with open(files[0], "r", encoding="utf-8") as f:
        return json.load(f)


def build_analysis_prompt(ing_data: dict, source: str) -> str:
    """논문 데이터를 Claude에게 전달할 프롬프트 구성"""
    ing_id  = ing_data.get("ingredient_id", "unknown")
    name_en = ing_data.get("name_en", "")
    name_kr = ing_data.get("name_kr", "")

    if source == "pubmed":
        articles = ing_data.get("articles", [])
        if not articles:
            return ""

        # 논문 텍스트 구성 (최대 MAX_PAPERS_PER_CALL 건, 초록 MAX_ABSTRACT_CHARS 자)
        paper_texts = []
        for i, art in enumerate(articles[:MAX_PAPERS_PER_CALL]):
            abstract = (art.get("abstract") or "")[:MAX_ABSTRACT_CHARS]
            if not abstract:
                continue
            paper_texts.append(
                f"[Paper {i+1}] PMID:{art.get('pmid','')} ({art.get('year','')})\n"
                f"Title: {art.get('title','')}\n"
                f"Abstract: {abstract}"
            )

        if not paper_texts:
            return ""

        papers_block = "\n\n".join(paper_texts)
        return f"""Analyze these research papers about {name_en} ({name_kr}) and extract structured data.

INGREDIENT: {name_en} (ID: {ing_id})
PAPERS ANALYZED: {len(paper_texts)} of {len(articles)} available

--- PAPER DATA ---
{papers_block}
--- END ---

Extract insights following the schema. Return JSON ONLY:
{json.dumps(EXTRACTION_SCHEMA, ensure_ascii=False, indent=2)}

Important: Set ingredient_id="{ing_id}", name_en="{name_en}", name_kr="{name_kr}",
analysis_date="{date.today().isoformat()}", paper_count_analyzed={len(paper_texts)}, source="pubmed" """

    elif source == "cir":
        structured = ing_data.get("structured", {})
        raw_text   = ing_data.get("raw_text_preview", "")
        page_url   = ing_data.get("cir_page_url", "")

        if not raw_text and not structured.get("safety_conclusion"):
            return ""

        cir_block = (
            f"CIR Page: {page_url}\n"
            f"Safety Conclusion: {structured.get('safety_conclusion', 'N/A')}\n"
            f"Max Concentration: {structured.get('max_concentration', 'N/A')}\n"
            f"Skin Effects: {structured.get('skin_effects', 'N/A')}\n"
            f"Text Preview: {raw_text[:2000]}"
        )

        return f"""Analyze this CIR safety assessment for {name_en} ({name_kr}) and extract structured data.

INGREDIENT: {name_en} (ID: {ing_id})
SOURCE: CIR (Cosmetic Ingredient Review)

--- CIR DATA ---
{cir_block}
--- END ---

Extract insights following the schema. For research fields not covered by safety data, use N/A.
Return JSON ONLY:
{json.dumps(EXTRACTION_SCHEMA, ensure_ascii=False, indent=2)}

Important: Set ingredient_id="{ing_id}", name_en="{name_en}", name_kr="{name_kr}",
analysis_date="{date.today().isoformat()}", paper_count_analyzed=1, source="cir" """

    return ""


def call_gemini(client: genai.Client, prompt: str) -> dict | None:
    """Gemini API 호출 — rate limit 시 즉시 스킵 (재시도 없음)"""
    full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}"

    # 서버 오류(5xx)만 1회 재시도, rate limit은 재시도 없이 즉시 스킵
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=full_prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=4096,
                ),
            )
            text = response.text
            result = _parse_json_from_text(text)
            if result:
                print(f"    ✅ Gemini 응답 수신 ({len(text)} chars)")
            return result

        except Exception as e:
            err = str(e)
            # 429 Rate limit → 재시도 없이 즉시 스킵
            if "429" in err or "quota" in err.lower() or "RESOURCE_EXHAUSTED" in err:
                print(f"    ⏭️ Rate limit — 스킵 (재시도 없음)")
                return None
            # 5xx 서버 오류 → 1회만 재시도
            elif ("500" in err or "503" in err) and attempt == 0:
                print(f"    ⚠️ 서버 오류. 5s 후 1회 재시도...")
                time.sleep(5)
            else:
                print(f"    ❌ Gemini 오류: {e}")
                return None

    return None


def _parse_json_from_text(text: str) -> dict | None:
    """응답 텍스트에서 JSON 블록 파싱"""
    if not text:
        return None

    # ```json ... ``` 블록 제거
    if "```json" in text:
        start = text.find("```json") + 7
        end   = text.find("```", start)
        text  = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end   = text.find("```", start)
        text  = text[start:end].strip()

    # 첫 번째 { } 블록 추출
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None

    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError as e:
        print(f"    ❌ JSON 파싱 실패: {e}")
        return None


def save_analysis(result: dict, ingredient_id: str):
    """분석 결과 저장"""
    out_dir = CACHE_DIR / ingredient_id
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = out_dir / f"analyzed_{date.today().isoformat()}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return fname


def write_to_sheets(results: list[dict]):
    """Google Sheets TAB_RD_INSIGHTS에 분석 결과 저장"""
    try:
        from config.sheets_client import get_spreadsheet, TAB_RD_INSIGHTS
        ss = get_spreadsheet()
        existing = [ws.title for ws in ss.worksheets()]

        headers = [
            "date", "ingredient_id", "name_kr", "name_en",
            "source", "paper_count", "data_quality", "research_stage",
            "mechanism", "efficacy", "concentration", "synergy",
            "conflict", "rnd_insight", "analyzed_at"
        ]

        if TAB_RD_INSIGHTS not in existing:
            ws = ss.add_worksheet(title=TAB_RD_INSIGHTS, rows=1000, cols=len(headers))
            ws.append_row(headers)
            print(f"  [sheets] 탭 생성: {TAB_RD_INSIGHTS}")
        else:
            ws = ss.worksheet(TAB_RD_INSIGHTS)

        rows = []
        today = date.today().isoformat()
        for r in results:
            ex = r.get("extracted", {})
            rows.append([
                today,
                r.get("ingredient_id", ""),
                r.get("name_kr", ""),
                r.get("name_en", ""),
                r.get("source", ""),
                r.get("paper_count_analyzed", 0),
                ex.get("data_quality", ""),
                ex.get("research_stage", ""),
                ex.get("mechanism_of_action", "")[:300],
                ex.get("efficacy_results", "")[:300],
                ex.get("optimal_concentration", ""),
                ex.get("synergy_formulation", "")[:200],
                ex.get("conflict_instability", "")[:200],
                ex.get("rnd_insight", "")[:300],
                r.get("analysis_date", today),
            ])

        if rows:
            ws.append_rows(rows, value_input_option="USER_ENTERED")
            print(f"  [sheets] {len(rows)}행 저장 완료 → {TAB_RD_INSIGHTS}")

    except Exception as e:
        sheet_id = os.getenv("GOOGLE_SHEET_ID")
        if sheet_id:
            print(f"  [sheets] 저장 실패: {e}")
        else:
            print(f"  [sheets] GOOGLE_SHEET_ID 미설정 — 로컬 JSON만 저장")


def analyze_ingredient(client: genai.Client, ingredient_id: str,
                       sources: list[str] = None, force: bool = False) -> list[dict]:
    """성분 1개 분석 — 토큰 효율화 적용
    스킵 조건 (force=False):
      1) 오늘 이미 분석 완료
      2) PubMed 캐시(PMID 셋트)가 변하지 않음
      3) 일일 호출 한도(DAILY_BUDGET) 초과
    """
    if sources is None:
        sources = ["pubmed", "cir"]

    # 1) 오늘 이미 분석
    if not force and already_analyzed_today(ingredient_id):
        print(f"  [{ingredient_id}] 오늘 이미 분석 — 스킵")
        return []

    # 2) 일일 호출 한도 체크
    if not force and get_daily_call_count() >= DAILY_BUDGET:
        print(f"  [{ingredient_id}] ⚠️ 일일 한도({DAILY_BUDGET}) 도달 — 내일 재시도")
        return []

    results = []
    for source in sources:
        # 3) PubMed 캐시 hash 비교 — 변화 없으면 스킵
        if not force and source == "pubmed" and pubmed_cache_unchanged(ingredient_id, source):
            print(f"  [{ingredient_id}] PubMed 변화 없음 — 분석 스킵 (토큰 절감)")
            continue

        raw_data = load_cached_data(ingredient_id, source)
        if not raw_data:
            print(f"  [{ingredient_id}] {source} 캐시 데이터 없음")
            continue

        prompt = build_analysis_prompt(raw_data, source)
        if not prompt:
            print(f"  [{ingredient_id}] {source} 분석 불가")
            continue

        print(f"  [{ingredient_id}] {source} 분석 중... (오늘 {get_daily_call_count()+1}회차)")
        result = call_gemini(client, prompt)
        _daily_call_count[source] = _daily_call_count.get(source, 0) + 1

        if result:
            # PMID hash 저장 → 다음 실행 시 비교
            import hashlib
            pmids = sorted([a.get("pmid", "") for a in raw_data.get("articles", [])])
            result["pubmed_hash"] = hashlib.md5(",".join(pmids).encode()).hexdigest()
            result["ingredient_id"] = ingredient_id
            result["source"] = source
            fname = save_analysis(result, ingredient_id)
            print(f"  [{ingredient_id}] ✓ 분석 완료 → {fname.name}")
            results.append(result)
        else:
            print(f"  [{ingredient_id}] {source} 분석 실패 (rate limit 가능)")

        time.sleep(REQUEST_DELAY)

    return results


def run(target_id: str | None = None, sources: list[str] = None, push_sheets: bool = True):
    """메인 분석 루프"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY 환경변수 미설정")
        print("   aistudio.google.com → Get API Key → .env에 GEMINI_API_KEY= 추가")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    print(f"    🤖 모델: {MODEL} (무료 tier)")

    if sources is None:
        sources = ["pubmed", "cir"]

    # 분석 대상 성분 목록 결정
    if target_id:
        ingredient_ids = [target_id]
    else:
        # 캐시 디렉토리에 수집 데이터 있는 성분들
        ingredient_ids = [
            d.name for d in CACHE_DIR.iterdir()
            if d.is_dir() and any(
                d.glob(f"{s}_*.json") for s in sources
            )
        ]
        if not ingredient_ids:
            print("분석할 수집 데이터가 없음. 먼저 pubmed_crawler.py 또는 cir_parser.py를 실행하세요.")
            return

    print(f"\n=== 성분 연구 분석 시작 ({len(ingredient_ids)}개 성분, 소스: {sources}) ===")
    print(f"    모델: {MODEL} | 시스템 프롬프트 캐싱 활성화\n")

    all_results = []
    for ing_id in ingredient_ids:
        print(f"\n▶ {ing_id}")
        results = analyze_ingredient(client, ing_id, sources)
        all_results.extend(results)

    if all_results and push_sheets:
        write_to_sheets(all_results)

    # 일일 토큰 사용량 리포트
    used = get_daily_call_count()
    skipped = len(ingredient_ids) - len([r for r in all_results])
    print(f"\n=== 분석 완료 ===")
    print(f"  ✓ 저장: {len(all_results)}건")
    print(f"  💰 Gemini 호출: {used}회 / 한도 {DAILY_BUDGET}회 ({used/DAILY_BUDGET*100:.0f}%)")
    print(f"  ⏭️ 스킵: {skipped}건 (cache hit + 한도 + 변화 없음)")
    print()
    return all_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Claude API 성분 연구 분석기")
    parser.add_argument("--ingredient", help="특정 성분 ID만 분석 (예: ectoin)")
    parser.add_argument("--source", choices=["pubmed", "cir", "all"],
                        default="all", help="분석 소스 (기본: all)")
    args = parser.parse_args()

    src = None if args.source == "all" else [args.source]
    run(target_id=args.ingredient, sources=src)

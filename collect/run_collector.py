"""
수집 오케스트레이터
- Google Trends(Global+US) → N-Score(Naver) → T-Score(TikTok) → ET-Index(YouTube US) 순서 실행
- 성분 마스터 시트 동기화
- GitHub Actions 또는 로컬 수동 실행

사용법:
  python collect/run_collector.py             # 전체 실행
  python collect/run_collector.py --trends    # Google Trends만
  python collect/run_collector.py --naver     # N-Score(Naver DataLab)만
  python collect/run_collector.py --tiktok    # T-Score(TikTok)만
  python collect/run_collector.py --et        # ET-Index(YouTube US)만
  python collect/run_collector.py --shopping  # Google Shopping Trends만
  python collect/run_collector.py --amazon    # Amazon 검색 수집만
  python collect/run_collector.py --research  # R&D 파이프라인 (PubMed+CIR+Claude 분석)
  python collect/run_collector.py --pubmed    # PubMed만
  python collect/run_collector.py --cir       # CIR 안전성 보고서만
  python collect/run_collector.py --analyze   # Claude 분석만 (캐시된 데이터 사용)
  python collect/run_collector.py --init      # 시트 탭 초기 생성

비활성: --reddit  (계정 블록으로 현재 미사용)
"""

import sys
import os
import argparse
import yaml
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

YAML_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "ingredients.yaml")


def load_ingredients() -> list[dict]:
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["ingredients"]


def init_sheets():
    from config.sheets_client import ensure_tabs_exist, upsert_ingredients_master
    print("=== Google Sheets 초기화 ===")
    ensure_tabs_exist()
    ingredients = load_ingredients()
    upsert_ingredients_master(ingredients)
    print(f"✅ 시트 초기화 완료 — {len(ingredients)}개 성분 동기화")


def run_trends():
    from collect.google_trends import run
    run()


def run_naver():
    from collect.naver_trends import run
    run()


def run_tiktok():
    from collect.tiktok_trends import run
    run()


def run_reddit():
    from collect.reddit_score import run
    run()


def run_et():
    from collect.et_index import run
    run()


def run_shopping():
    from collect.google_shopping import run
    run()


def run_amazon():
    from collect.amazon_bsr import run
    run()


def run_discovery():
    from collect.tiktok_discovery import run
    run()


def run_pubmed(target_id=None, max_results=10):
    # 토큰 절감: 성분당 10건으로 제한 (20→10)
    from collect.pubmed_crawler import run
    run(target_id=target_id, max_results=max_results)


def run_cir(target_id=None):
    from collect.cir_parser import run
    run(target_id=target_id)


def run_analyze(target_id=None, push_sheets=True):
    from collect.research_analyzer import run
    run(target_id=target_id, push_sheets=push_sheets)


def run_emerging():
    """신성분 시그널 분석 (3-Tier funnel + emerging candidates PubMed 수집)"""
    from collect.emerging_ingredients import run
    run(fetch_emerging=True)


def run_aplb_pairs(target_complex=None):
    """APLB 컴플렉스 페어/트리오 PubMed 검색"""
    from collect.aplb_pair_search import run
    run(target_complex=target_complex)


def run_aplb_claims(target_complex=None):
    """APLB 마케팅 클레임 카드 (Gemini)"""
    from collect.aplb_claim_builder import run
    run(target_complex=target_complex)


def run_aplb_qc():
    """APLB 클레임 QA/QC 검증"""
    from collect.aplb_claim_qc import run
    run()


def run_clinical_trials():
    """ClinicalTrials.gov 진행 중 임상시험 추적"""
    try:
        from collect.clinical_trials import run
        run()
    except ImportError:
        print("  ⏭️ clinical_trials 모듈 미설치 — 스킵")


def run_commercial():
    """상업 시장 경쟁 분석 (Commercial Tier C0~C3)"""
    try:
        from collect.commercial_landscape import run
        run(top_n=30)
    except ImportError:
        print("  ⏭️ commercial_landscape 모듈 미설치 — 스킵")


def run_concepts():
    """APLB 신제품 컨셉 자동 생성"""
    try:
        from collect.aplb_concept_generator import run
        run(top_n=5)
    except ImportError:
        print("  ⏭️ aplb_concept_generator 모듈 미설치 — 스킵")


def run_brief():
    """Executive Brief — 6개 데이터 종합 의사결정"""
    try:
        from collect.executive_brief import run
        run()
    except ImportError:
        print("  ⏭️ executive_brief 모듈 미설치 — 스킵")


def _is_monday():
    from datetime import datetime
    return datetime.now().weekday() == 0  # 0 = 월요일


def run_research(target_id=None):
    """R&D 파이프라인 — 토큰 효율 최적화 (Lite/Full 모드 자동)

    매일 (Lite, ~10 Gemini calls):
      - PubMed 수집 (캐시 비교 후 변화 있는 것만 분석)
      - 신성분 시그널 (3-Tier — 화이트리스트 우선, Gemini fallback only)
      - Executive Brief (1 call)

    월요일 (Full, ~50 Gemini calls):
      - 위 + CIR + ClinicalTrials + APLB 페어/클레임/QC + Commercial + Concepts

    토큰 한도 (gemini-2.5-flash-lite 무료):
      - RPD 1500 (request/day) — 충분
      - RPM 30 — REQUEST_DELAY 4초로 안전 (15 RPM)
      - DAILY_BUDGET 60 calls/day cap
    """
    print("\n── R&D 파이프라인 시작 ──")

    # 0/7 TikTok 신규 발굴 (target_id 없을 때만)
    if not target_id:
        print("0/7  TikTok 신규 성분 발굴...")
        run_discovery()
        print()

    # 1/7 PubMed 수집
    print("1/7  PubMed 수집 (성분당 최대 10건)...")
    run_pubmed(target_id=target_id)
    print()

    # 2/7 CIR (월요일만)
    if target_id or _is_monday():
        print("2/7  CIR 안전성 데이터 수집...")
        run_cir(target_id=target_id)
    else:
        print("2/7  CIR 스킵 (월요일만 수집 — 토큰 절감)")
    print()

    # 3/7 신성분 시그널 분석 (3-Tier)
    if not target_id:
        print("3/7  신성분 시그널 분석 (3-Tier Funnel)...")
        try:
            run_emerging()
        except Exception as e:
            print(f"  ⚠️ 신성분 분석 실패: {e}")
    else:
        print("3/7  신성분 분석 스킵 (target_id 지정 시)")
    print()

    # 4/7 ClinicalTrials.gov (매주 월요일)
    if not target_id and _is_monday():
        print("4/7  ClinicalTrials.gov 활성 임상시험 추적...")
        try:
            run_clinical_trials()
        except Exception as e:
            print(f"  ⚠️ 실패: {e}")
    else:
        print("4/7  ClinicalTrials.gov 스킵 (월요일만)")
    print()

    # 5/7 APLB 페어 검색 (월요일만 — 페어 결과는 자주 안 바뀜)
    if not target_id and _is_monday():
        print("5/7  APLB 컴플렉스 페어/트리오 PubMed 검색...")
        try:
            run_aplb_pairs()
        except Exception as e:
            print(f"  ⚠️ 실패: {e}")
    else:
        print("5/7  APLB 페어 검색 스킵 (월요일만)")
    print()

    # 6/7 Gemini 분석 + Sheets 업로드
    print("6/7  Gemini 분석 및 Sheets 업로드...")
    run_analyze(target_id=target_id, push_sheets=True)
    print()

    # 7/9 APLB 클레임 카드 + QC (월요일만)
    if not target_id and _is_monday():
        print("7/9  APLB 클레임 카드 (Gemini) + QC...")
        try:
            run_aplb_claims()
            run_aplb_qc()
        except Exception as e:
            print(f"  ⚠️ 실패: {e}")
    else:
        print("7/9  APLB 클레임 갱신 스킵 (월요일만)")
    print()

    # 8/9 상업 경쟁 분석 (월요일만 — Gemini 비싼 작업)
    if not target_id and _is_monday():
        print("8/9  상업 시장 경쟁 분석 (Commercial Tier C0~C3)...")
        try:
            run_commercial()
        except Exception as e:
            print(f"  ⚠️ 실패: {e}")
    else:
        print("8/9  상업 분석 스킵 (월요일만)")
    print()

    # 9/10 신제품 컨셉 자동 생성 (월요일만)
    if not target_id and _is_monday():
        print("9/10 Gemini 신제품 컨셉 자동 생성...")
        try:
            run_concepts()
        except Exception as e:
            print(f"  ⚠️ 실패: {e}")
    else:
        print("9/10 신제품 컨셉 스킵 (월요일만)")
    print()

    # 10/10 Executive Brief — 매일 (가장 마지막에, 모든 데이터 종합)
    if not target_id:
        print("10/10 Executive Brief 종합 의사결정...")
        try:
            run_brief()
        except Exception as e:
            print(f"  ⚠️ 실패: {e}")
    else:
        print("10/10 Executive Brief 스킵 (target_id 지정 시)")

    print("\n── R&D 파이프라인 완료 ──\n")


def main():
    parser = argparse.ArgumentParser(description="뷰티 트렌드 데이터 수집기")
    parser.add_argument("--trends", action="store_true", help="Google Trends만 실행")
    parser.add_argument("--naver", action="store_true", help="N-Score(Naver DataLab)만 실행")
    parser.add_argument("--tiktok", action="store_true", help="T-Score(TikTok)만 실행")
    parser.add_argument("--reddit", action="store_true", help="Reddit만 실행")
    parser.add_argument("--et", action="store_true", help="ET-Index(YouTube)만 실행")
    parser.add_argument("--shopping", action="store_true", help="Google Shopping Trends만 실행")
    parser.add_argument("--amazon", action="store_true", help="Amazon 검색 수집만 실행")
    parser.add_argument("--discovery", action="store_true", help="TikTok 신규 성분 발굴")
    parser.add_argument("--research", action="store_true", help="R&D 풀 파이프라인 (PubMed+CIR+Claude 분석)")
    parser.add_argument("--pubmed", action="store_true", help="PubMed 논문 수집만 실행")
    parser.add_argument("--cir", action="store_true", help="CIR 안전성 보고서 수집만 실행")
    parser.add_argument("--analyze", action="store_true", help="Claude 분석만 실행 (캐시 데이터 사용)")
    parser.add_argument("--ingredient", help="특정 성분 ID만 처리 (research/pubmed/cir/analyze에 적용)")
    parser.add_argument("--emerging", action="store_true", help="신성분 시그널 분석 (3-Tier)")
    parser.add_argument("--aplb-pairs", action="store_true", help="APLB 컴플렉스 페어/트리오 PubMed 검색")
    parser.add_argument("--aplb-claims", action="store_true", help="APLB 마케팅 클레임 카드 (Gemini)")
    parser.add_argument("--aplb-qc", action="store_true", help="APLB 클레임 QA/QC")
    parser.add_argument("--clinical-trials", action="store_true", help="ClinicalTrials.gov 추적")
    parser.add_argument("--commercial", action="store_true", help="상업 시장 경쟁 분석 (C0~C3)")
    parser.add_argument("--concepts", action="store_true", help="APLB 신제품 컨셉 자동 생성")
    parser.add_argument("--brief", action="store_true", help="Executive Brief 종합 의사결정")
    parser.add_argument("--init", action="store_true", help="Google Sheets 탭 초기 생성")
    args = parser.parse_args()

    start = datetime.now()
    print(f"\n{'='*50}")
    print(f"뷰티 트렌드 수집 시작: {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    if args.init:
        init_sheets()
        return

    if args.trends:
        run_trends()
    elif args.naver:
        run_naver()
    elif args.tiktok:
        run_tiktok()
    elif args.reddit:
        run_reddit()
    elif args.et:
        run_et()
    elif args.shopping:
        run_shopping()
    elif args.amazon:
        run_amazon()
    elif args.discovery:
        run_discovery()
    elif args.research:
        run_research(target_id=args.ingredient)
    elif args.pubmed:
        run_pubmed(target_id=args.ingredient)
    elif args.cir:
        run_cir(target_id=args.ingredient)
    elif args.analyze:
        run_analyze(target_id=args.ingredient, push_sheets=True)
    elif args.emerging:
        run_emerging()
    elif args.aplb_pairs:
        run_aplb_pairs()
    elif args.aplb_claims:
        run_aplb_claims()
    elif args.aplb_qc:
        run_aplb_qc()
    elif args.clinical_trials:
        run_clinical_trials()
    elif args.commercial:
        run_commercial()
    elif args.concepts:
        run_concepts()
    elif args.brief:
        run_brief()
    else:
        # 전체 실행
        init_sheets()
        print()
        run_trends()
        print()
        run_naver()
        print()
        run_tiktok()
        print()
        run_et()
        print()
        run_shopping()
        print()
        run_amazon()

    elapsed = (datetime.now() - start).seconds
    print(f"\n{'='*50}")
    print(f"전체 수집 완료 — 소요시간: {elapsed}초")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()

"""
수집 오케스트레이터
- Google Trends + Reddit + ET-Index 순서대로 실행
- 성분 마스터 시트 동기화
- GitHub Actions 또는 로컬 수동 실행

사용법:
  python collect/run_collector.py             # 전체 실행
  python collect/run_collector.py --trends    # Google Trends만
  python collect/run_collector.py --reddit    # Reddit만
  python collect/run_collector.py --et        # ET-Index(YouTube)만
  python collect/run_collector.py --init      # 시트 탭 초기 생성
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


def run_reddit():
    from collect.reddit_score import run
    run()


def run_et():
    from collect.et_index import run
    run()


def main():
    parser = argparse.ArgumentParser(description="뷰티 트렌드 데이터 수집기")
    parser.add_argument("--trends", action="store_true", help="Google Trends만 실행")
    parser.add_argument("--reddit", action="store_true", help="Reddit만 실행")
    parser.add_argument("--et", action="store_true", help="ET-Index(YouTube)만 실행")
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
    elif args.reddit:
        run_reddit()
    elif args.et:
        run_et()
    else:
        # 전체 실행
        init_sheets()
        print()
        run_trends()
        print()
        run_reddit()
        print()
        run_et()

    elapsed = (datetime.now() - start).seconds
    print(f"\n{'='*50}")
    print(f"전체 수집 완료 — 소요시간: {elapsed}초")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()

"""
APLB VOC Claude 분석기
────────────────────────────────────────────────────────────
Sheets voc_raw 탭의 미분석 리뷰를 Claude API로 배치 분석.
결과 → Sheets voc_insights 탭

분석 항목 (SKU × Channel 단위 집계):
  loves         — 소비자가 좋아하는 점 (Top 5)
  pains         — 불만/아쉬운 점 (Top 5)
  use_cases     — 실제 사용 용도/스킨케어 루틴 (Top 3)
  ingredient_mentions — 리뷰에서 직접 언급된 성분
  rep_quotes    — 대표 긍정/부정 인용문 각 2개
  sentiment_pct — 긍정/중립/부정 비율
  avg_rating    — 평균 별점
  review_count  — 분석된 리뷰 수

실행:
  python collect/voc_analyzer.py
  python collect/voc_analyzer.py --sku gluta_niac_serum --channel iherb
  python collect/voc_analyzer.py --force   (이미 분석된 것도 재분석)
────────────────────────────────────────────────────────────
"""

import os
import sys
import json
import argparse
from datetime import datetime, date
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))

from config.sheets_client import (
    read_all, append_rows,
    TAB_VOC_RAW, TAB_VOC_INSIGHTS,
)

# Claude 모델 — prompt caching 지원 모델 사용
MODEL = "claude-sonnet-4-20250514"
BATCH_SIZE = 30        # 리뷰 N건씩 묶어서 Claude에 전송
MAX_TOKENS = 1500


# ── 시스템 프롬프트 (캐시 대상) ────────────────────────────────────────────

SYSTEM_PROMPT = """당신은 K-뷰티 브랜드 마케팅/R&D 전략가입니다.
주어진 소비자 리뷰 배치를 분석하여 제품 개선, 마케팅 메시지, 성분 클레임에 활용할 수 있는
실행 가능한 인사이트를 추출합니다.

출력은 반드시 아래 JSON 스키마를 엄격히 따르세요. 다른 텍스트 없이 JSON만 반환하세요.

{
  "loves": ["소비자가 좋아하는 점 1", "..."],          // 최대 5개, 구체적으로
  "pains": ["불만/아쉬운 점 1", "..."],                 // 최대 5개, 없으면 []
  "use_cases": ["실제 사용 용도/타깃 피부고민 1", "..."], // 최대 3개
  "ingredient_mentions": ["리뷰에서 언급된 성분명"],    // 원문 그대로
  "rep_quotes_positive": ["긍정 인용문 (원문)"],        // 최대 2개, 20-80자
  "rep_quotes_negative": ["부정/개선 인용문 (원문)"],   // 최대 2개, 없으면 []
  "sentiment": {"positive": 0.0, "neutral": 0.0, "negative": 0.0},  // 합 = 1.0
  "key_insight": "한 문장 핵심 인사이트 (전략적 시사점)"
}"""


# ── 데이터 로드 ────────────────────────────────────────────────────────────

def load_raw_reviews(
    target_sku: str | None = None,
    target_channel: str | None = None,
    force: bool = False,
) -> dict[tuple, list[dict]]:
    """
    voc_raw에서 리뷰 로드.
    force=False면 voc_insights에 이미 분석된 (sku, channel) 쌍은 스킵.
    반환: {(sku_id, channel): [row_dict, ...]}
    """
    raw = read_all(TAB_VOC_RAW)
    if not raw:
        print("voc_raw 탭이 비었습니다. voc_scraper.py를 먼저 실행하세요.")
        return {}

    # 이미 분석된 (sku, channel) 파악
    analyzed_pairs: set[tuple] = set()
    if not force:
        try:
            insights = read_all(TAB_VOC_INSIGHTS)
            for row in insights:
                analyzed_pairs.add((row.get("sku_id", ""), row.get("channel", "")))
        except Exception:
            pass

    grouped: dict[tuple, list[dict]] = {}
    for row in raw:
        sku_id = row.get("sku_id", "")
        channel = row.get("channel", "")
        if target_sku and sku_id != target_sku:
            continue
        if target_channel and channel != target_channel:
            continue
        if (sku_id, channel) in analyzed_pairs:
            continue
        key = (sku_id, channel)
        grouped.setdefault(key, []).append(row)

    return grouped


# ── Claude 분석 ────────────────────────────────────────────────────────────

def _build_review_block(reviews: list[dict]) -> str:
    lines = []
    for i, r in enumerate(reviews, 1):
        rating = r.get("rating", "?")
        text = r.get("review_text", "").strip()
        country = r.get("reviewer_country", "")
        rev_date = r.get("review_date", "")
        meta = f"★{rating}"
        if country:
            meta += f" | {country}"
        if rev_date:
            meta += f" | {rev_date}"
        lines.append(f"[{i}] ({meta})\n{text}")
    return "\n\n".join(lines)


def _analyze_batch(
    client: anthropic.Anthropic,
    sku_id: str,
    name_kr: str,
    channel: str,
    reviews: list[dict],
) -> dict | None:
    """리뷰 배치를 Claude로 분석. JSON dict 반환."""
    review_block = _build_review_block(reviews)
    user_msg = (
        f"제품: {name_kr} (SKU: {sku_id})\n"
        f"채널: {channel}\n"
        f"리뷰 {len(reviews)}건:\n\n"
        f"{review_block}\n\n"
        f"위 리뷰를 분석하여 지정된 JSON 형식으로 인사이트를 추출하세요."
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_msg}],
        )
        raw_text = response.content[0].text.strip()
        # JSON 코드블록 제거
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        return json.loads(raw_text)
    except json.JSONDecodeError as e:
        print(f"  [claude] JSON 파싱 오류: {e}")
        return None
    except Exception as e:
        print(f"  [claude] API 오류: {e}")
        return None


def _merge_batches(batch_results: list[dict]) -> dict:
    """여러 배치 결과를 하나로 병합."""
    if not batch_results:
        return {}
    if len(batch_results) == 1:
        return batch_results[0]

    # 아이템 빈도로 우선순위 집계
    from collections import Counter

    def merge_lists(key: str, max_n: int) -> list:
        counter = Counter()
        for b in batch_results:
            for item in b.get(key, []):
                counter[item] += 1
        return [item for item, _ in counter.most_common(max_n)]

    loves = merge_lists("loves", 5)
    pains = merge_lists("pains", 5)
    use_cases = merge_lists("use_cases", 3)
    ingredient_mentions = merge_lists("ingredient_mentions", 10)
    rep_pos = merge_lists("rep_quotes_positive", 2)
    rep_neg = merge_lists("rep_quotes_negative", 2)

    # sentiment 가중 평균
    total = len(batch_results)
    sentiment = {
        "positive": sum(b.get("sentiment", {}).get("positive", 0) for b in batch_results) / total,
        "neutral":  sum(b.get("sentiment", {}).get("neutral",  0) for b in batch_results) / total,
        "negative": sum(b.get("sentiment", {}).get("negative", 0) for b in batch_results) / total,
    }

    # key_insight는 마지막 배치 사용 (전체 리뷰 보고 나온 결론이 더 정확)
    key_insight = batch_results[-1].get("key_insight", "")

    return {
        "loves": loves,
        "pains": pains,
        "use_cases": use_cases,
        "ingredient_mentions": ingredient_mentions,
        "rep_quotes_positive": rep_pos,
        "rep_quotes_negative": rep_neg,
        "sentiment": sentiment,
        "key_insight": key_insight,
    }


# ── Sheets 저장 ────────────────────────────────────────────────────────────

def _to_sheet_row(
    sku_id: str,
    name_kr: str,
    channel: str,
    review_count: int,
    avg_rating: float,
    result: dict,
    analyzed_at: str,
) -> list:
    s = result.get("sentiment", {})
    return [
        analyzed_at,
        sku_id,
        name_kr,
        channel,
        review_count,
        round(avg_rating, 2),
        " | ".join(result.get("loves", [])),
        " | ".join(result.get("pains", [])),
        " | ".join(result.get("use_cases", [])),
        ", ".join(result.get("ingredient_mentions", [])),
        " | ".join(result.get("rep_quotes_positive", [])),
        " | ".join(result.get("rep_quotes_negative", [])),
        round(s.get("positive", 0), 3),
        round(s.get("neutral", 0), 3),
        round(s.get("negative", 0), 3),
        result.get("key_insight", ""),
    ]


# ── 메인 ──────────────────────────────────────────────────────────────────

def analyze_all(
    target_sku: str | None = None,
    target_channel: str | None = None,
    force: bool = False,
):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY 환경 변수 없음")
        return

    client = anthropic.Anthropic(api_key=api_key)
    grouped = load_raw_reviews(target_sku, target_channel, force)

    if not grouped:
        print("분석할 신규 리뷰 없음. (--force로 재분석 가능)")
        return

    analyzed_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    output_rows = []

    for (sku_id, channel), reviews in grouped.items():
        name_kr = reviews[0].get("name_kr", sku_id)
        print(f"\n{'='*55}")
        print(f"분석: {sku_id} | {channel} | {len(reviews)}건")

        # 별점 평균
        ratings = []
        for r in reviews:
            try:
                ratings.append(float(r.get("rating", 0) or 0))
            except ValueError:
                pass
        avg_rating = sum(ratings) / len(ratings) if ratings else 0.0

        # 배치 분석
        batch_results = []
        for i in range(0, len(reviews), BATCH_SIZE):
            chunk = reviews[i: i + BATCH_SIZE]
            print(f"  배치 {i//BATCH_SIZE + 1}: {len(chunk)}건 분석 중...")
            result = _analyze_batch(client, sku_id, name_kr, channel, chunk)
            if result:
                batch_results.append(result)

        if not batch_results:
            print(f"  ⚠️  {sku_id}/{channel} 분석 실패 — 스킵")
            continue

        merged = _merge_batches(batch_results)

        print(f"  ✅ 완료")
        print(f"     loves: {merged.get('loves', [])[:2]}")
        print(f"     pains: {merged.get('pains', [])[:2]}")
        print(f"     sentiment: {merged.get('sentiment', {})}")
        print(f"     insight: {merged.get('key_insight', '')[:80]}")

        row = _to_sheet_row(sku_id, name_kr, channel, len(reviews), avg_rating, merged, analyzed_at)
        output_rows.append(row)

    if output_rows:
        append_rows(TAB_VOC_INSIGHTS, output_rows)
        print(f"\n✅ Sheets [{TAB_VOC_INSIGHTS}] 저장 완료: {len(output_rows)}행")
    else:
        print("\n저장할 인사이트 없음.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="APLB VOC Claude 분석기")
    parser.add_argument("--sku", default=None, help="특정 SKU만 (예: gluta_niac_serum)")
    parser.add_argument("--channel", default=None, help="iherb 또는 yesstyle")
    parser.add_argument("--force", action="store_true", help="이미 분석된 것도 재분석")
    args = parser.parse_args()
    analyze_all(target_sku=args.sku, target_channel=args.channel, force=args.force)

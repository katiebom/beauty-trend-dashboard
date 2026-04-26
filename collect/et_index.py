"""
ET-Index (Expert Trust Index) 수집기 v4
─────────────────────────────────────────────────────
[v4] API 없는 키워드 매칭 방식으로 완전 교체
  수집: YouTube Data API playlistItems (1유닛/채널)
  분석: 키워드 매칭 (AI API 불필요, 비용 $0)

  US 피부과 채널은 영상 제목에 성분명을 직접 씀
  → "retinol", "niacinamide", "peptides" 등 제목 스캔이 충분히 유효

[KR ET 비활성화]
  한국 채널은 "주름", "미백" 등 고민 기반 제목 → V-Index(Google Trends)로 대체

채점 로직:
  제목/설명에서 성분 발견 시:
  - 부정어 주변: 20점 (caution)
  - 강추천 단어 주변: 85점 (strong_recommend)
  - 기본 언급: 70점 (moderate_recommend)
─────────────────────────────────────────────────────
"""

import sys
import os
import re
import time
import yaml
from datetime import datetime, date
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.sheets_client import append_rows, TAB_RAW_TRENDS

load_dotenv()

YAML_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "ingredients.yaml")
CHANNELS_YAML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "youtube_channels.yaml")

# 감정 키워드 (영어 — US 채널 대상)
NEGATIVE_WORDS = [
    "avoid", "don't use", "dont use", "stop using", "harmful", "dangerous",
    "causes", "irritating", "irritation", "bad for", "never use", "worse",
    "reaction", "allergy", "toxic", "burns", "burning",
]
STRONG_POSITIVE_WORDS = [
    "best", "love", "holy grail", "game changer", "must have", "must-have",
    "highly recommend", "amazing", "incredible", "obsessed", "favorite",
    "favourite", "top", "number one", "#1",
]


def load_config():
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        ingredients = yaml.safe_load(f)["ingredients"]
    with open(CHANNELS_YAML, "r", encoding="utf-8") as f:
        channels_cfg = yaml.safe_load(f)
    return ingredients, channels_cfg


def get_youtube_client():
    from googleapiclient.discovery import build
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY 환경변수 없음")
    return build("youtube", "v3", developerKey=api_key)


def fetch_recent_videos(youtube, channel_id: str, max_videos: int) -> list[dict]:
    """
    채널 최신 영상 수집 — playlistItems.list 사용 (1유닛, search의 1/100)
    업로드 재생목록 ID = channel_id의 UC → UU 교체
    """
    uploads_playlist_id = "UU" + channel_id[2:]
    try:
        resp = (
            youtube.playlistItems()
            .list(part="snippet", playlistId=uploads_playlist_id, maxResults=max_videos)
            .execute()
        )
        videos = []
        for item in resp.get("items", []):
            snippet = item["snippet"]
            videos.append({
                "video_id": snippet.get("resourceId", {}).get("videoId", ""),
                "title": snippet.get("title", ""),
                "description": snippet.get("description", "")[:300],
            })
        return [v for v in videos if v["video_id"]]
    except Exception as e:
        print(f"  [yt] 영상 수집 오류: {e}")
        return []


def keyword_score(text: str, keywords: list[str]) -> dict | None:
    """
    텍스트에서 성분 키워드 탐색 → 감정 분석 → 점수 반환
    미발견 시 None 반환
    """
    text_lower = text.lower()

    # 성분 존재 여부 확인
    found = any(kw.lower() in text_lower for kw in keywords)
    if not found:
        return None

    # 감정 판단: 부정 우선, 이후 강추천, 기본
    if any(neg in text_lower for neg in NEGATIVE_WORDS):
        return {"score": 20, "strength": "caution"}
    if any(pos in text_lower for pos in STRONG_POSITIVE_WORDS):
        return {"score": 85, "strength": "strong_recommend"}
    return {"score": 70, "strength": "moderate_recommend"}


def scan_all_ingredients(channel: dict, videos: list[dict], ingredients: list[dict]) -> dict:
    """
    채널 영상 전체에서 모든 성분 키워드 스캔
    반환: {ingredient_id: {"score": 0~100, "strength": str}}
    """
    if not videos:
        return {}

    authority = channel.get("authority_weight", 1.0)

    # 영상 전체 텍스트 합치기
    full_text = " ".join(
        v["title"] + " " + v["description"] for v in videos
    )

    result = {}
    for ing in ingredients:
        # 영어 키워드 우선 (US 채널), 한국어도 포함
        keywords = [ing["name_en"]]
        # 별칭이 있으면 추가
        if ing.get("aliases_en"):
            keywords.extend(ing["aliases_en"])

        match = keyword_score(full_text, keywords)
        if match:
            raw_score = match["score"]
            et_score = 50 + (raw_score - 50) * authority
            et_score = max(0, min(100, round(et_score, 1)))
            result[ing["id"]] = {
                "score": et_score,
                "strength": match["strength"],
            }

    return result


def run():
    print("=== ET-Index 수집 시작 v4 (키워드 매칭, API 불필요) ===")
    ingredients, channels_cfg = load_config()
    today = date.today().isoformat()
    collected_at = datetime.now().isoformat(timespec="seconds")

    all_channels = [c for c in channels_cfg["channels"] if c.get("active", False)]
    us_channels = [c for c in all_channels if c.get("market", "us") == "us"]

    valid_us = [ch for ch in us_channels if ch.get("channel_id")]
    skipped = [ch["name"] for ch in us_channels if not ch.get("channel_id")]
    if skipped:
        print(f"  [스킵] channel_id 없음: {', '.join(skipped)}")

    collection_cfg = channels_cfg.get("collection", {})
    max_videos = collection_cfg.get("max_videos_per_channel", 15)

    print(f"활성 채널 — KR: 0개 (비활성), US: {len(valid_us)}개")
    print(f"분석 방식: 키워드 매칭 (API 불필요)")

    youtube = get_youtube_client()
    ing_scores = {ing["id"]: {"us": []} for ing in ingredients}

    for ch in valid_us:
        print(f"\n[US] {ch['name']} 처리 중...")
        videos = fetch_recent_videos(youtube, ch["channel_id"], max_videos)
        print(f"  → 최신 영상 {len(videos)}개 수집")
        if not videos:
            continue

        results = scan_all_ingredients(ch, videos, ingredients)
        print(f"  → {len(results)}개 성분 언급 발견")

        for ing_id, data in results.items():
            if ing_id in ing_scores:
                ing_scores[ing_id]["us"].append(data)

        time.sleep(0.5)  # YouTube API 여유

    # 성분별 집계 → Sheets 저장
    all_rows = []
    for ing in ingredients:
        ing_id = ing["id"]
        us_data = ing_scores[ing_id]["us"]

        et_us = round(sum(d["score"] for d in us_data) / len(us_data), 1) if us_data else 0.0
        us_strong = sum(1 for d in us_data if d["strength"] in ("strong_recommend", "moderate_recommend"))

        metrics = {
            "et_score_us":            et_us,
            "et_channel_count_us":    len(us_data),
            "et_mention_videos_us":   len(us_data),
            "et_strong_recommend_us": us_strong,
        }
        for metric_name, value in metrics.items():
            all_rows.append([
                today, ing_id, ing["name_kr"],
                "youtube", metric_name, value, collected_at,
            ])

        if us_data:
            print(f"  {ing['name_kr']}: US-ET={et_us} (채널 {len(us_data)}개, 강추천 {us_strong}개)")

    if all_rows:
        append_rows(TAB_RAW_TRENDS, all_rows)
        print(f"\n✅ ET-Index 수집 완료 — {len(all_rows)}행 저장")
    else:
        print("\n⚠️  저장된 데이터 없음")


if __name__ == "__main__":
    run()

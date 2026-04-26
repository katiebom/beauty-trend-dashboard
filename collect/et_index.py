"""
ET-Index (Expert Trust Index) 수집기 v3
─────────────────────────────────────────────────────
[v3] Claude API(유료) → Gemini Flash(무료)로 교체
  수집: YouTube Data API playlistItems (1유닛/채널, 쿼터 부담 없음)
  분석: Gemini Flash (무료 티어 — 하루 1,500건 무료)

[KR ET 비활성화]
  이유: 한국 채널은 영상 제목에 성분명 대신 피부 고민/시술명 사용
  대안: V-Index(Google Trends)가 KR 시장 신호 담당
        US ET만 수집 — 글로벌 전문가 검증 신호

필요한 것:
  - YOUTUBE_API_KEY: 기존 키 그대로 사용
  - GEMINI_API_KEY: aistudio.google.com → "Get API Key" (무료)
─────────────────────────────────────────────────────
"""

import sys
import os
import time
import json
import yaml
import google.generativeai as genai
from datetime import datetime, date
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.sheets_client import append_rows, TAB_RAW_TRENDS

load_dotenv()

YAML_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "ingredients.yaml")
CHANNELS_YAML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "youtube_channels.yaml")


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
    uploads_playlist_id = "UU" + channel_id[2:]  # UCxxx → UUxxx
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


def scan_all_ingredients_gemini(channel: dict, videos: list[dict], ingredients: list[dict]) -> dict:
    """
    Gemini Flash로 채널 영상 전체 스캔 — 모든 성분 한 번에 분석
    무료 티어: 15 RPM / 1,500 RPD
    반환: {ingredient_id: {"score": 0~100, "strength": str}}
    """
    if not videos:
        return {}

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("  [gemini] GEMINI_API_KEY 없음 — .env에 추가 필요")
        return {}

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    authority = channel.get("authority_weight", 1.0)
    lang = channel.get("language", "en")

    # 영상 텍스트
    video_texts = [f"- {v['title']} | {v['description']}" for v in videos[:15]]
    videos_block = "\n".join(video_texts)

    # 성분 목록
    if lang == "ko":
        ing_list = [f"{i['id']}: {i['name_kr']} ({i['name_en']})" for i in ingredients]
    else:
        ing_list = [f"{i['id']}: {i['name_en']} ({i['name_kr']})" for i in ingredients]
    ingredients_block = "\n".join(ing_list)

    prompt = f"""You are analyzing YouTube content from a skincare/dermatology expert channel.

Channel: {channel['name']} (market: {channel.get('market','us')}, specialty: {channel.get('specialty','dermatology')})

Recent {len(videos)} videos (title | description snippet):
{videos_block}

Check which of these skincare ingredients appear in the videos above:
{ingredients_block}

For EACH ingredient actually mentioned, estimate the expert's stance.
Skip ingredients with no mention.

Respond in EXACT JSON array only (no markdown):
[
  {{
    "id": "<ingredient_id>",
    "score": <0-100, 100=strongly recommends, 50=neutral, 0=warns against>,
    "strength": "<strong_recommend|moderate_recommend|neutral|caution|against>"
  }}
]

If NO ingredients are mentioned, respond with: []"""

    try:
        response = model.generate_content(prompt)
        raw = response.text.strip().replace("```json", "").replace("```", "").strip()
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start == -1:
            return {}

        data = json.loads(raw[start:end])
        result = {}
        for item in data:
            ing_id = item.get("id")
            if not ing_id:
                continue
            raw_score = float(item.get("score", 50))
            et_score = 50 + (raw_score - 50) * authority
            et_score = max(0, min(100, round(et_score, 1)))
            result[ing_id] = {
                "score": et_score,
                "strength": item.get("strength", "neutral"),
            }
        return result

    except Exception as e:
        print(f"  [gemini] 스캔 오류: {e}")
        return {}


def run():
    print("=== ET-Index 수집 시작 v3 (YouTube API + Gemini Flash 무료) ===")
    ingredients, channels_cfg = load_config()
    today = date.today().isoformat()
    collected_at = datetime.now().isoformat(timespec="seconds")

    all_channels = [c for c in channels_cfg["channels"] if c.get("active", False)]
    # KR ET 비활성화 — V-Index(Google Trends)가 KR 시장 신호 담당
    us_channels = [c for c in all_channels if c.get("market", "us") == "us"]
    collection_cfg = channels_cfg.get("collection", {})
    max_videos = collection_cfg.get("max_videos_per_channel", 15)

    # channel_id 없는 채널 사전 필터링
    valid_us = [ch for ch in us_channels if ch.get("channel_id")]
    skipped = [ch["name"] for ch in us_channels if not ch.get("channel_id")]
    if skipped:
        print(f"  [스킵] channel_id 없음: {', '.join(skipped)}")
    print(f"활성 채널 — KR: 0개 (비활성), US: {len(valid_us)}개")

    youtube = get_youtube_client()
    ing_scores = {ing["id"]: {"us": []} for ing in ingredients}

    for ch in valid_us:
        print(f"\n[US] {ch['name']} 처리 중...")
        videos = fetch_recent_videos(youtube, ch["channel_id"], max_videos)
        print(f"  → 최신 영상 {len(videos)}개 수집")
        if not videos:
            continue

        results = scan_all_ingredients_gemini(ch, videos, ingredients)
        print(f"  → {len(results)}개 성분 언급 발견")

        for ing_id, data in results.items():
            if ing_id in ing_scores:
                ing_scores[ing_id]["us"].append(data)

        # Gemini 무료 티어 15 RPM — 채널 간 5초 대기
        time.sleep(5)

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

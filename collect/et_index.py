"""
ET-Index (Expert Trust Index) 수집기 v2
─────────────────────────────────────────────────────
[구조 변경] 성분별 → 채널별로 루프 변경
  이전: 성분(42) × 채널(20) = 840번 API 호출
  이후: 채널(20) → 최근 영상 수집 → 전체 성분(42) 동시 스캔 = ~20번 API 호출

흐름:
  1. 채널 ID 확인 (handle → channel_id)
  2. 채널 최근 영상 N개 제목+설명 수집
  3. Claude에게 42개 성분 전체를 한 번에 분석 요청
  4. 성분별 ET-Score 추출 → Google Sheets 저장
─────────────────────────────────────────────────────
"""

import sys
import os
import time
import json
import yaml
import anthropic
from datetime import datetime, date, timedelta, timezone
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


def resolve_channel_id(youtube, channel: dict) -> str | None:
    """handle → channel_id 변환. 이미 있으면 API 호출 없음 (캐시 효과)."""
    if channel.get("channel_id"):
        return channel["channel_id"]

    handle = channel.get("handle", "").lstrip("@")
    if not handle:
        return None

    # channels().list는 1유닛 (search는 100유닛 — 사용 금지)
    try:
        resp = youtube.channels().list(forHandle=handle, part="id", maxResults=1).execute()
        items = resp.get("items", [])
        if items:
            ch_id = items[0]["id"]
            # yaml에 캐시 저장
            _save_channel_id_to_yaml(channel.get("id", ""), ch_id)
            return ch_id
    except Exception as e:
        print(f"  [et] channel_id 조회 실패 ({channel['name']}): {e}")

    return None


def _save_channel_id_to_yaml(channel_yaml_id: str, channel_id: str):
    """조회된 channel_id를 yaml에 저장 (다음 실행부터 API 호출 불필요)"""
    try:
        with open(CHANNELS_YAML, "r", encoding="utf-8") as f:
            content = f.read()
        # 해당 채널의 channel_id: "" 를 실제 ID로 교체
        old = f'id: {channel_yaml_id}\n    name:'
        if old in content:
            content = content.replace(
                f'channel_id: ""\n    market:',
                f'channel_id: "{channel_id}"\n    market:',
                1  # 첫 번째 매칭만 (같은 채널 id가 없으니 사실상 정확)
            )
            with open(CHANNELS_YAML, "w", encoding="utf-8") as f:
                f.write(content)
    except Exception:
        pass  # 저장 실패해도 수집은 계속


def fetch_recent_videos(youtube, channel_id: str, max_videos: int) -> list[dict]:
    """
    채널 최근 영상 수집 — playlistItems.list 사용 (1유닛, search.list의 1/100)
    채널 업로드 재생목록 ID = channel_id의 UC → UU 교체
    """
    uploads_playlist_id = "UU" + channel_id[2:]  # UCxxx → UUxxx
    try:
        resp = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist_id,
            maxResults=max_videos,
        ).execute()

        videos = []
        for item in resp.get("items", []):
            snippet = item["snippet"]
            videos.append({
                "video_id": snippet.get("resourceId", {}).get("videoId", ""),
                "title": snippet.get("title", ""),
                "description": snippet.get("description", "")[:200],
            })
        return [v for v in videos if v["video_id"]]
    except Exception as e:
        print(f"  [et] 영상 수집 오류: {e}")
        return []


def scan_all_ingredients(channel: dict, videos: list[dict], ingredients: list[dict]) -> dict:
    """
    채널 영상 전체를 Claude에게 넘겨 모든 성분을 한 번에 스캔.
    반환: {ingredient_id: {"score": 0~100, "strength": str, "mentioned": bool}}
    """
    if not videos:
        return {}

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    authority = channel.get("authority_weight", 1.0)
    lang = channel.get("language", "en")

    # 영상 텍스트 합치기
    video_texts = []
    for v in videos[:15]:
        video_texts.append(f"- {v['title']} | {v['description']}")
    videos_block = "\n".join(video_texts)

    # 성분 목록 (언어에 따라 KR/EN 조합)
    ing_list = []
    for ing in ingredients:
        if lang == "ko":
            ing_list.append(f"{ing['id']}: {ing['name_kr']} ({ing['name_en']})")
        else:
            ing_list.append(f"{ing['id']}: {ing['name_en']} ({ing['name_kr']})")
    ingredients_block = "\n".join(ing_list)

    prompt = f"""You are analyzing YouTube content from a skincare/dermatology expert channel.

Channel: {channel['name']} (market: {channel.get('market','kr')}, language: {lang}, specialty: {channel.get('specialty','medical')})

Recent {len(videos)} videos (title | description):
{videos_block}

Check which of these ingredients appear in the videos above:
{ingredients_block}

For EACH ingredient that appears, estimate the expert's stance.
Only include ingredients actually mentioned. Skip ingredients with no mention.

Respond in EXACT JSON (array):
[
  {{
    "id": "<ingredient_id>",
    "mentioned": true,
    "score": <0-100, 100=strongly recommends with evidence, 50=neutral, 0=warns against>,
    "strength": "<strong_recommend|moderate_recommend|neutral|caution|against>"
  }},
  ...
]

If NO ingredients are mentioned, respond with: []"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # JSON 배열 추출
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
            # authority 가중치 적용
            et_score = 50 + (raw_score - 50) * authority
            et_score = max(0, min(100, round(et_score, 1)))
            result[ing_id] = {
                "score": et_score,
                "strength": item.get("strength", "neutral"),
                "mentioned": True,
            }
        return result

    except Exception as e:
        print(f"  [claude] 스캔 오류: {e}")
        return {}


def run():
    print("=== ET-Index 수집 시작 v2 (채널별 전체 성분 스캔) ===")
    ingredients, channels_cfg = load_config()
    today = date.today().isoformat()
    collected_at = datetime.now().isoformat(timespec="seconds")

    all_channels = [c for c in channels_cfg["channels"] if c.get("active", False)]
    kr_channels = [c for c in all_channels if c.get("market", "kr") == "kr"]
    us_channels = [c for c in all_channels if c.get("market", "us") == "us"]
    collection_cfg = channels_cfg.get("collection", {})
    lookback_days = collection_cfg.get("lookback_days", 90)
    max_videos = collection_cfg.get("max_videos_per_channel", 15)

    print(f"활성 채널 — KR: {len(kr_channels)}개, US: {len(us_channels)}개")

    youtube = get_youtube_client()

    # 성분별 결과 누적: {ing_id: {kr: [scores], us: [scores]}}
    ing_scores = {ing["id"]: {"kr": [], "us": []} for ing in ingredients}

    def process_channels(channels, market_label):
        for ch in channels:
            print(f"\n[{market_label}] {ch['name']} 처리 중...")
            ch_id = resolve_channel_id(youtube, ch)
            if not ch_id:
                print(f"  → channel_id 없음, 스킵")
                continue

            videos = fetch_recent_videos(youtube, ch_id, lookback_days, max_videos)
            print(f"  → 최근 영상 {len(videos)}개 수집")
            if not videos:
                continue

            results = scan_all_ingredients(ch, videos, ingredients)
            print(f"  → {len(results)}개 성분 언급 발견")

            for ing_id, data in results.items():
                if ing_id in ing_scores:
                    ing_scores[ing_id][market_label.lower()].append(data)

            time.sleep(1)

    process_channels(kr_channels, "KR")
    process_channels(us_channels, "US")

    # 성분별 집계 → Sheets 저장
    all_rows = []
    for ing in ingredients:
        ing_id = ing["id"]
        kr_data = ing_scores[ing_id]["kr"]
        us_data = ing_scores[ing_id]["us"]

        et_kr = round(sum(d["score"] for d in kr_data) / len(kr_data), 1) if kr_data else 0.0
        et_us = round(sum(d["score"] for d in us_data) / len(us_data), 1) if us_data else 0.0
        kr_strong = sum(1 for d in kr_data if d["strength"] in ("strong_recommend", "moderate_recommend"))
        us_strong = sum(1 for d in us_data if d["strength"] in ("strong_recommend", "moderate_recommend"))

        metrics = {
            "et_score_kr":            et_kr,
            "et_channel_count_kr":    len(kr_data),
            "et_mention_videos_kr":   len(kr_data),
            "et_strong_recommend_kr": kr_strong,
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

        if kr_data or us_data:
            print(f"  {ing['name_kr']}: K-ET={et_kr} (채널{len(kr_data)}개), US-ET={et_us} (채널{len(us_data)}개)")

    if all_rows:
        append_rows(TAB_RAW_TRENDS, all_rows)
        print(f"\n✅ ET-Index 수집 완료 — {len(all_rows)}행 저장")
    else:
        print("\n⚠️  저장된 데이터 없음")


if __name__ == "__main__":
    run()

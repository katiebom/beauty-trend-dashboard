"""
ET-Index (Expert Trust Index) 수집기
─────────────────────────────────────────────────────
YouTube 피부과 전문의 채널에서 성분 언급 빈도 + 권장 강도 분석
→ K-ET Score (한국 전문의) + US-ET Score (미국 전문의) 별도 계산

의존성:
  pip install google-api-python-client youtube-transcript-api

환경변수:
  YOUTUBE_API_KEY  ← Google Cloud Console에서 YouTube Data API v3 활성화 후 발급
─────────────────────────────────────────────────────
"""

import sys
import os
import time
import json
import yaml
import anthropic
from datetime import datetime, date, timedelta
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
    """YouTube Data API v3 클라이언트"""
    try:
        from googleapiclient.discovery import build
        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            raise ValueError("YOUTUBE_API_KEY 환경변수 없음")
        return build("youtube", "v3", developerKey=api_key)
    except ImportError:
        raise ImportError("google-api-python-client 미설치: pip install google-api-python-client")


def get_channel_id(youtube, channel: dict) -> str | None:
    """
    handle(@username)로 channel_id 조회 (handle 우선)
    - 빈 channel_id는 handle로 자동 조회
    - handle 조회 실패 시 제공된 channel_id fallback
    """
    handle = channel.get("handle", "").lstrip("@")

    # channel_id가 있으면 바로 사용
    if channel.get("channel_id"):
        return channel["channel_id"]

    if not handle:
        return None

    # 1차: YouTube API forHandle 파라미터 (가장 정확)
    try:
        resp = youtube.channels().list(
            forHandle=handle, part="id", maxResults=1
        ).execute()
        items = resp.get("items", [])
        if items:
            resolved_id = items[0]["id"]
            print(f"  [et] handle 조회 성공: @{handle} → {resolved_id}")
            return resolved_id
    except Exception:
        pass

    # 2차: search API fallback
    try:
        resp = youtube.search().list(
            q=handle, type="channel", part="id", maxResults=1
        ).execute()
        items = resp.get("items", [])
        if items:
            resolved_id = items[0]["id"]["channelId"]
            print(f"  [et] search 조회 성공: @{handle} → {resolved_id}")
            return resolved_id
    except Exception as e:
        print(f"  [et] handle 조회 실패 ({channel['name']}): {e}")

    return None


def search_ingredient_videos(youtube, channel_id: str, ingredient: dict,
                              lookback_days: int, max_videos: int,
                              channel: dict | None = None) -> list[dict]:
    """채널 내 성분 관련 영상 검색"""
    from datetime import timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()

    lang = (channel or {}).get("language", "en")
    if lang == "ko":
        search_terms = [ingredient["name_kr"]] + [ingredient["name_en"]]
    else:
        search_terms = [ingredient["name_en"]] + ingredient.get("reddit_terms", [])[:1]
    search_terms = search_terms[:3]

    videos = []
    for term in search_terms:
        try:
            resp = youtube.search().list(
                part="snippet",
                channelId=channel_id,
                q=term,
                type="video",
                publishedAfter=cutoff,
                maxResults=max_videos,
                order="relevance",
            ).execute()

            for item in resp.get("items", []):
                vid_id = item["id"]["videoId"]
                snippet = item["snippet"]
                videos.append({
                    "video_id": vid_id,
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", "")[:300],
                    "published_at": snippet.get("publishedAt", ""),
                    "channel_name": snippet.get("channelTitle", ""),
                })
            time.sleep(0.5)
        except Exception as e:
            print(f"  [et] 영상 검색 오류: {e}")

    # 중복 제거
    seen, unique = set(), []
    for v in videos:
        if v["video_id"] not in seen:
            seen.add(v["video_id"])
            unique.append(v)

    return unique[:max_videos]


def get_transcript(video_id: str, language: str = "ko") -> str:
    """YouTube 자막 가져오기"""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        langs = ["ko", "en"] if language == "ko" else ["en", "ko"]
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
        return " ".join([t["text"] for t in transcript])[:2000]
    except Exception:
        return ""


def calculate_et_score(ingredient: dict, channel: dict,
                        videos: list[dict], use_transcript: bool) -> dict:
    """
    Claude로 ET-Score 계산
    반환:
      et_score       : 0~100 (weighted by channel authority)
      raw_score      : 0~100 (authority 가중치 전)
      mention_count  : 언급 영상 수
      recommendation_strength: 권장 강도
      key_claims_kr  : 주요 주장 3가지
    """
    if not videos:
        return {"et_score": 0.0, "raw_score": 0.0, "mention_count": 0,
                "recommendation_strength": "no_data", "key_claims_kr": []}

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    authority = channel.get("authority_weight", 1.0)

    video_texts = []
    for v in videos[:5]:
        transcript = get_transcript(v["video_id"], channel.get("language", "en")) if use_transcript else ""
        text = f"Title: {v['title']}\nDescription: {v['description']}"
        if transcript:
            text += f"\nTranscript: {transcript[:800]}"
        video_texts.append(text)

    combined = "\n\n===\n\n".join(video_texts)

    prompt = f"""You are analyzing YouTube content from a dermatologist/skincare expert channel about the ingredient: {ingredient['name_en']} ({ingredient['name_kr']}).

Channel: {channel['name']} (market: {channel.get('market','kr')}, specialty: {channel.get('specialty', 'medical')}, language: {channel.get('language', 'en')})

Video content ({len(videos)} videos found):
{combined}

Analyze how this expert views this ingredient. Respond in EXACT JSON:
{{
  "mentions_ingredient": <true/false>,
  "raw_et_score": <0-100, where 100=strongly recommends with evidence, 50=neutral mention, 0=actively warns against>,
  "recommendation_strength": "<strong_recommend|moderate_recommend|neutral|caution|against>",
  "clinical_evidence_cited": <true/false, did they cite studies or clinical data?>,
  "key_claims_kr": ["<주요 주장1 (한국어)>", "<주장2>", "<주장3>"],
  "safety_concerns_kr": ["<안전 우려사항 (한국어)>"] or [],
  "insight_kr": "<핵심 인사이트 1~2문장 (한국어)>"
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(response.content[0].text.strip())

        if not data.get("mentions_ingredient", False):
            return {"et_score": 0.0, "raw_score": 0.0, "mention_count": 0,
                    "recommendation_strength": "not_mentioned", "key_claims_kr": []}

        raw = float(data.get("raw_et_score", 50))
        et_score = 50 + (raw - 50) * authority
        et_score = max(0, min(100, et_score))

        if data.get("clinical_evidence_cited", False):
            et_score = min(100, et_score + 5)

        return {
            "et_score": round(et_score, 1),
            "raw_score": round(raw, 1),
            "mention_count": len(videos),
            "recommendation_strength": data.get("recommendation_strength", "neutral"),
            "key_claims_kr": data.get("key_claims_kr", [])[:3],
            "safety_concerns_kr": data.get("safety_concerns_kr", []),
            "insight_kr": data.get("insight_kr", ""),
        }

    except Exception as e:
        print(f"  [claude/et] 오류: {e}")
        return {"et_score": 0.0, "raw_score": 0.0, "mention_count": len(videos),
                "recommendation_strength": "error", "key_claims_kr": []}


def aggregate_channel_scores(channel_scores: list[dict]) -> float:
    """채널별 ET-Score를 단순 평균으로 집계 (언급 없는 채널 제외)"""
    valid = [s for s in channel_scores if s["mention_count"] > 0]
    if not valid:
        return 0.0
    return round(sum(s["et_score"] for s in valid) / len(valid), 1)


def collect_for_market(youtube, ing: dict, channels: list[dict], collection_cfg: dict, market_label: str) -> list[dict]:
    """특정 마켓 채널들에서 성분 ET-Score 수집"""
    channel_scores = []
    for ch in channels:
        ch_id = get_channel_id(youtube, ch)
        if not ch_id:
            continue

        videos = search_ingredient_videos(
            youtube, ch_id, ing,
            collection_cfg.get("lookback_days", 90),
            collection_cfg.get("max_videos_per_channel", 10),
            channel=ch,
        )
        print(f"    [{market_label}] {ch['name']}: {len(videos)}개 영상")

        if videos:
            score_data = calculate_et_score(
                ing, ch, videos,
                collection_cfg.get("use_transcript", True)
            )
            channel_scores.append(score_data)
            time.sleep(1)

    return channel_scores


def run():
    print("=== ET-Index 수집 시작 (KR + US) ===")
    ingredients, channels_cfg = load_config()
    today = date.today().isoformat()
    collected_at = datetime.now().isoformat(timespec="seconds")

    all_channels = [c for c in channels_cfg["channels"] if c.get("active", False)]
    kr_channels = [c for c in all_channels if c.get("market", "kr") == "kr"]
    us_channels = [c for c in all_channels if c.get("market", "us") == "us"]
    collection_cfg = channels_cfg.get("collection", {})

    print(f"활성 채널 — KR: {len(kr_channels)}개, US: {len(us_channels)}개")

    if not all_channels:
        print("⚠️  활성화된 채널 없음.")
        return

    youtube = get_youtube_client()
    all_rows = []

    for ing in ingredients:
        print(f"\n[{ing['name_kr']}] ET-Index 수집 중...")

        # ── K-Expert (한국 전문의) ──
        kr_scores = collect_for_market(youtube, ing, kr_channels, collection_cfg, "KR")
        et_kr = aggregate_channel_scores(kr_scores)
        kr_mention_total = sum(s["mention_count"] for s in kr_scores)
        kr_strong = sum(1 for s in kr_scores
                        if s.get("recommendation_strength") in ("strong_recommend", "moderate_recommend"))

        # ── US-Expert (미국 전문의) ──
        us_scores = collect_for_market(youtube, ing, us_channels, collection_cfg, "US")
        et_us = aggregate_channel_scores(us_scores)
        us_mention_total = sum(s["mention_count"] for s in us_scores)
        us_strong = sum(1 for s in us_scores
                        if s.get("recommendation_strength") in ("strong_recommend", "moderate_recommend"))

        print(f"  → K-ET: {et_kr} (채널 {len(kr_scores)}개, 강추 {kr_strong}개)")
        print(f"  → US-ET: {et_us} (채널 {len(us_scores)}개, 강추 {us_strong}개)")

        metrics = {
            "et_score_kr":              et_kr,
            "et_channel_count_kr":      len(kr_scores),
            "et_mention_videos_kr":     kr_mention_total,
            "et_strong_recommend_kr":   kr_strong,
            "et_score_us":              et_us,
            "et_channel_count_us":      len(us_scores),
            "et_mention_videos_us":     us_mention_total,
            "et_strong_recommend_us":   us_strong,
        }
        for metric_name, value in metrics.items():
            all_rows.append([
                today, ing["id"], ing["name_kr"],
                "youtube", metric_name, value, collected_at,
            ])

    if all_rows:
        append_rows(TAB_RAW_TRENDS, all_rows)
        print(f"\n✅ ET-Index 수집 완료 — {len(all_rows)}행 저장 (KR/US 분리)")
    else:
        print("\n⚠️  저장된 데이터 없음")


if __name__ == "__main__":
    run()

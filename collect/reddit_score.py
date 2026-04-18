"""
Reddit R-Score 수집기 v3 — Large-Scale + 2-Stage Pipeline
──────────────────────────────────────────────────────────────
수집 규모:  상위 50개 게시글 × 댓글 수집 → 성분당 수백~수천 개 원본
필터링:     1단계 — 감정 키워드 포함 텍스트만 추출
클러스터링: 2단계 — 유사 의견 그룹화 → 대표 문장 + 빈도 도출
Claude 분석: 클러스터 요약(~15개)만 전달 → 비용 최소화 + 정확도 유지

R-Score 수식 (가중 합산):
  R_Score = Σ(sentiment_val × engagement_weight × authority_weight)
           ─────────────────────────────────────────────────────────
            Σ(engagement_weight × authority_weight)

  sentiment_val:      강추=+1.0, 긍정=+0.5, 중립/질문=0, 부정=-0.5, 강부정=-1.0
  engagement_weight:  log1p(upvotes) × log1p(comments+1) — 정규화
  authority_weight:   전문가 flair 2~3× / 고karma 계정 1.3× / 신규 계정 0.7×
──────────────────────────────────────────────────────────────
"""

import sys, os, re, time, json, math, yaml, praw, anthropic
from datetime import datetime, date, timedelta
from collections import Counter, defaultdict
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.sheets_client import append_rows, TAB_RAW_TRENDS

load_dotenv()

YAML_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "ingredients.yaml")

SUBREDDITS   = ["SkincareAddiction", "AsianBeauty", "DIYBeauty"]
LOOKBACK_DAYS = 90
MAX_POSTS_PER_SUB  = 50    # 서브레딧당 최대 수집 게시글
MAX_COMMENTS_PER_POST = 30 # 게시글당 최대 상위 댓글
MAX_CLUSTERS_TO_CLAUDE = 15  # Claude에 보낼 클러스터 수

# ── 감정 키워드 사전 (Stage 1 필터) ──────────────────────────────────
POSITIVE_KW = [
    "love", "holy grail", "hg", "amazing", "works", "helped", "recommend",
    "game changer", "repurchase", "results", "glowing", "cleared", "improved",
    "best", "obsessed", "must have", "worth", "effective", "noticeable",
    "skin has never", "transformed", "incredible", "changed my skin",
]
NEGATIVE_KW = [
    "purging", "breakout", "broke out", "irritating", "irritation", "burned",
    "burning", "rash", "reaction", "waste", "doesn't work", "did nothing",
    "made worse", "stinging", "peeling badly", "regret", "disappointed",
    "allergy", "clogged", "fungal", "not for", "avoid",
]
QUESTION_KW = [
    "has anyone", "does it", "should i", "is it worth", "can i", "will it",
    "any experience", "anyone tried", "thoughts on", "opinions on",
    "looking for", "help me", "advice on",
]

EXPERT_FLAIR = {
    "scientist": 3.0, "chemist": 3.0, "dermatologist": 3.0, "derm": 2.5,
    "physician": 2.5, "pharmacist": 2.5, "esthetician": 2.0, "mod": 2.0,
    "phd": 2.5, "md": 2.5, "verified": 2.0,
}

HYPE_THRESHOLD = 0.28
HYPE_PENALTY   = 12


# ══════════════════════════════════════════════════════════════════════
# 1. 데이터 수집 (대규모)
# ══════════════════════════════════════════════════════════════════════

def load_ingredients():
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["ingredients"]


def get_reddit() -> praw.Reddit:
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent="beauty_trend_dashboard/3.0",
    )


def _author_weight(flair: str | None, comment_karma: int = 0) -> float:
    """flair 전문가 여부 + karma 기반 신뢰 가중치"""
    weight = 1.0
    if flair:
        for kw, w in EXPERT_FLAIR.items():
            if kw in flair.lower():
                weight = max(weight, w)
    # karma 기반 보정 (실제 Reddit comment karma 조회는 API cost 높아 post score로 대체)
    # comment_karma > 10000 → 1.3x, < 100 → 0.7x
    if comment_karma > 10_000:
        weight *= 1.3
    elif comment_karma < 100 and weight == 1.0:
        weight *= 0.7
    return round(weight, 2)


def _engagement_weight(upvotes: int, num_comments: int = 0) -> float:
    """log1p(upvotes) × log1p(comments+1) — 고관여 콘텐츠 우선"""
    return math.log1p(max(upvotes, 0)) * math.log1p(num_comments + 1)


def collect_posts_and_comments(reddit: praw.Reddit, ingredient: dict) -> list[dict]:
    """게시글 + 댓글 대규모 수집"""
    terms = ingredient.get("reddit_terms", [ingredient["name_en"]])
    cutoff = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)
    items = []

    for sub_name in SUBREDDITS:
        sub = reddit.subreddit(sub_name)
        for term in terms[:2]:
            try:
                posts = list(sub.search(
                    query=term, time_filter="year",
                    sort="relevance", limit=MAX_POSTS_PER_SUB,
                ))
            except Exception as e:
                print(f"  [collect] 검색 오류 ({sub_name}/{term}): {e}")
                continue

            for post in posts:
                if datetime.utcfromtimestamp(post.created_utc) < cutoff:
                    continue

                flair   = getattr(post, "author_flair_text", None)
                eng_w   = _engagement_weight(post.score, post.num_comments)
                auth_w  = _author_weight(flair)

                # 게시글 본문
                if post.selftext.strip():
                    items.append({
                        "text": f"{post.title}. {post.selftext}"[:400],
                        "type": "post",
                        "upvotes": post.score,
                        "num_comments": post.num_comments,
                        "engagement_weight": eng_w,
                        "authority_weight": auth_w,
                        "flair": flair or "",
                        "subreddit": sub_name,
                    })

                # 댓글 수집
                try:
                    post.comments.replace_more(limit=0)
                    for comment in post.comments[:MAX_COMMENTS_PER_POST]:
                        if not hasattr(comment, "body") or not comment.body:
                            continue
                        c_eng  = _engagement_weight(comment.score)
                        c_auth = _author_weight(getattr(comment, "author_flair_text", None))
                        items.append({
                            "text": comment.body[:300],
                            "type": "comment",
                            "upvotes": comment.score,
                            "num_comments": 0,
                            "engagement_weight": c_eng,
                            "authority_weight": c_auth,
                            "flair": getattr(comment, "author_flair_text", "") or "",
                            "subreddit": sub_name,
                        })
                except Exception:
                    pass

            time.sleep(1.5)

    print(f"  [collect] 원본 수집: {len(items)}개")
    return items


# ══════════════════════════════════════════════════════════════════════
# 2. Stage 1: 감정 키워드 필터링
# ══════════════════════════════════════════════════════════════════════

def _classify_sentiment_type(text: str) -> str | None:
    """
    감정 키워드 포함 여부 → 'positive' / 'negative' / 'question' / None(제외)
    None이면 Stage 1에서 탈락
    """
    t = text.lower()
    neg_score = sum(1 for kw in NEGATIVE_KW if kw in t)
    pos_score = sum(1 for kw in POSITIVE_KW if kw in t)
    q_score   = sum(1 for kw in QUESTION_KW if kw in t)

    if neg_score >= 2:   return "strong_negative"
    if neg_score == 1:   return "negative"
    if pos_score >= 2:   return "strong_positive"
    if pos_score == 1:   return "positive"
    if q_score >= 1:     return "question"
    return None  # 감정 없음 → 제외


SENTIMENT_VAL = {
    "strong_positive": +1.0,
    "positive":        +0.5,
    "question":         0.0,
    "negative":        -0.5,
    "strong_negative": -1.0,
}


def stage1_filter(items: list[dict]) -> list[dict]:
    """감정 키워드 포함 항목만 추출 + sentiment_type 태깅"""
    filtered = []
    for item in items:
        stype = _classify_sentiment_type(item["text"])
        if stype is not None:
            item["sentiment_type"] = stype
            item["sentiment_val"]  = SENTIMENT_VAL[stype]
            filtered.append(item)

    # 감정 유형별 분포 출력
    counts = Counter(i["sentiment_type"] for i in filtered)
    print(f"  [stage1] 필터 후: {len(filtered)}개 "
          f"(++{counts.get('strong_positive',0)} +{counts.get('positive',0)} "
          f"?{counts.get('question',0)} -{counts.get('negative',0)} --{counts.get('strong_negative',0)})")
    return filtered


# ══════════════════════════════════════════════════════════════════════
# 3. Stage 2: 클러스터링 (토큰 유사도 기반)
# ══════════════════════════════════════════════════════════════════════

def _tokenize(text: str) -> set[str]:
    """소문자 알파벳 단어 집합 (3글자 이상)"""
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 3}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster_opinions(items: list[dict], similarity_threshold: float = 0.35) -> list[dict]:
    """
    토큰 Jaccard 유사도로 클러스터링
    반환: 클러스터 리스트 (대표 문장, 건수, 감정 유형, 총 engagement/authority)
    """
    # 감정 유형별로 먼저 분리
    by_type: dict[str, list] = defaultdict(list)
    for item in items:
        by_type[item["sentiment_type"]].append(item)

    clusters = []
    for stype, group in by_type.items():
        # 각 그룹 내에서 클러스터링
        merged: list[dict] = []  # {items, tokens, representative}
        for item in group:
            tokens = _tokenize(item["text"])
            placed = False
            for cluster in merged:
                if _jaccard(tokens, cluster["tokens"]) >= similarity_threshold:
                    cluster["items"].append(item)
                    cluster["tokens"] |= tokens  # 토큰 풀 확장
                    placed = True
                    break
            if not placed:
                merged.append({"items": [item], "tokens": tokens})

        for cluster in merged:
            citems = cluster["items"]
            # 대표 문장: engagement_weight 가장 높은 것
            rep = max(citems, key=lambda x: x["engagement_weight"] * x["authority_weight"])
            total_eng = sum(i["engagement_weight"] for i in citems)
            total_auth = sum(i["authority_weight"] for i in citems)

            clusters.append({
                "sentiment_type":     stype,
                "sentiment_val":      SENTIMENT_VAL[stype],
                "count":              len(citems),
                "representative_text": rep["text"][:200],
                "total_engagement":   round(total_eng, 2),
                "avg_authority":      round(total_auth / len(citems), 2),
                "subreddits":         list({i["subreddit"] for i in citems}),
            })

    # engagement × count 기준 정렬
    clusters.sort(key=lambda c: c["total_engagement"] * c["count"], reverse=True)
    print(f"  [stage2] 클러스터: {len(clusters)}개 "
          f"(원본 {len(items)}건 → 대표 {len(clusters)}개)")
    return clusters


# ══════════════════════════════════════════════════════════════════════
# 4. Hype 감지
# ══════════════════════════════════════════════════════════════════════

def detect_hype(items: list[dict]) -> tuple[bool, list[str], float]:
    brand_counter: Counter = Counter()
    for item in items:
        brands = re.findall(r'\b[A-Z][a-z]{2,}(?:\s[A-Z][a-z]+)?\b', item["text"])
        stopwords = {"The", "This", "That", "Reddit", "Edit", "Update", "Also",
                     "Love", "Just", "Very", "Really", "Would", "Could", "Should",
                     "Have", "Been", "With", "From", "Your", "Mine"}
        for b in brands:
            if b not in stopwords:
                brand_counter[b] += 1

    total = max(len(items), 1)
    flagged = [f"{b}({c}/{total}건)" for b, c in brand_counter.most_common(5)
               if c / total >= HYPE_THRESHOLD]
    is_hype = bool(flagged)
    return is_hype, flagged, HYPE_PENALTY * len(flagged) if is_hype else 0.0


# ══════════════════════════════════════════════════════════════════════
# 5. Weighted R-Score 계산 (수식 직접 적용)
# ══════════════════════════════════════════════════════════════════════

def compute_weighted_r_score(items: list[dict]) -> float:
    """
    R_Score = Σ(sentiment_val × eng_w × auth_w) / Σ(eng_w × auth_w)
    결과: -1.0 ~ +1.0 → 0~100 매핑
    """
    if not items:
        return 50.0

    numerator   = sum(i["sentiment_val"] * i["engagement_weight"] * i["authority_weight"]
                      for i in items)
    denominator = sum(i["engagement_weight"] * i["authority_weight"] for i in items)

    if denominator < 1e-9:
        return 50.0

    weighted_avg = numerator / denominator                  # -1 ~ +1
    score = (weighted_avg + 1.0) / 2.0 * 100               # 0 ~ 100
    return round(min(100.0, max(0.0, score)), 1)


def compute_volume_share(filtered_count: int, total_collected: int) -> float:
    """
    Share of Voice: 전체 수집 중 감정 언급 비중 (0~100)
    전체 수집이 0이면 0
    """
    if total_collected == 0:
        return 0.0
    return round(filtered_count / total_collected * 100, 1)


# ══════════════════════════════════════════════════════════════════════
# 6. Claude 분석 (클러스터 요약 기반)
# ══════════════════════════════════════════════════════════════════════

def analyze_clusters_with_claude(ingredient: dict, clusters: list[dict],
                                  filtered_count: int, total_count: int) -> dict:
    """
    Claude에 클러스터 요약만 전달 → pain points, positive reasons, insight 추출
    R-Score는 수식으로 직접 계산 (Claude가 숫자 임의로 안 내놓음)
    """
    if not clusters:
        return {"pain_points": [], "positive_reasons": [], "insight_kr": "데이터 없음",
                "hype_flag": False, "share_of_voice": 0.0}

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    top_clusters = clusters[:MAX_CLUSTERS_TO_CLAUDE]
    cluster_summary = "\n".join([
        f"[{c['sentiment_type'].upper()} ×{c['count']}건 eng:{c['total_engagement']:.1f}] "
        f"{c['representative_text']}"
        for c in top_clusters
    ])

    prompt = f"""You are a beauty industry analyst reviewing aggregated Reddit opinions about: {ingredient['name_en']} ({ingredient['name_kr']}).

Total raw mentions collected: {total_count}
Sentiment-bearing mentions: {filtered_count}
Clustered opinion groups ({len(top_clusters)} shown, sorted by engagement × volume):

{cluster_summary}

Based on these clustered community opinions, respond in EXACT JSON:
{{
  "pain_points_kr": ["<부작용/불만 핵심 키워드1>", "<키워드2>", "<키워드3>"],
  "positive_reasons_kr": ["<긍정 이유1>", "<이유2>", "<이유3>"],
  "hype_suspicion": <true/false — 광고성 or 바이럴 의심되는 패턴>,
  "hype_reason_kr": "<의심 이유 (없으면 빈 문자열)>",
  "insight_kr": "<이 성분에 대한 커뮤니티 핵심 분위기 2문장>",
  "unmet_needs_kr": ["<언맷니즈/개선요구 키워드>"]
}}"""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(resp.content[0].text.strip())
        return {
            "pain_points":     data.get("pain_points_kr", [])[:3],
            "positive_reasons": data.get("positive_reasons_kr", [])[:3],
            "hype_flag":       data.get("hype_suspicion", False),
            "hype_reason":     data.get("hype_reason_kr", ""),
            "insight_kr":      data.get("insight_kr", ""),
            "unmet_needs":     data.get("unmet_needs_kr", [])[:3],
            "share_of_voice":  compute_volume_share(filtered_count, total_count),
        }
    except Exception as e:
        print(f"  [claude] 오류: {e}")
        return {"pain_points": [], "positive_reasons": [], "insight_kr": "",
                "hype_flag": False, "share_of_voice": 0.0}


# ══════════════════════════════════════════════════════════════════════
# 7. 메인 실행
# ══════════════════════════════════════════════════════════════════════

def run():
    print("=== Reddit R-Score 수집 시작 (v3 — Large-Scale Pipeline) ===")
    ingredients = load_ingredients()
    today = date.today().isoformat()
    collected_at = datetime.now().isoformat(timespec="seconds")
    reddit = get_reddit()
    all_rows = []

    for i, ing in enumerate(ingredients):
        print(f"\n[{i+1}/{len(ingredients)}] {ing['name_kr']} ({ing['id']})")

        # 1. 대규모 수집
        raw_items = collect_posts_and_comments(reddit, ing)

        # 2. Stage 1: 감정 필터
        filtered = stage1_filter(raw_items)

        # 3. Stage 2: 클러스터링
        clusters = cluster_opinions(filtered)

        # 4. Hype 감지 (raw 전체 기준)
        is_hype, hype_brands, hype_penalty = detect_hype(raw_items)

        # 5. 가중 R-Score 직접 계산
        r_score_weighted = compute_weighted_r_score(filtered)
        if is_hype:
            r_score_weighted = max(0, r_score_weighted - hype_penalty)
            print(f"  [hype] 감점 -{hype_penalty}pt → {r_score_weighted}")

        # 6. Claude 질적 분석 (클러스터 요약만)
        analysis = analyze_clusters_with_claude(ing, clusters, len(filtered), len(raw_items))
        if analysis["hype_flag"] and not is_hype:
            r_score_weighted = max(0, r_score_weighted - hype_penalty)

        # 7. 단순 감정 비율 기반 베이스라인도 병행 (참고용)
        pos_count = sum(1 for f in filtered if f["sentiment_val"] > 0)
        neg_count = sum(1 for f in filtered if f["sentiment_val"] < 0)
        r_score_simple = round(pos_count / max(pos_count + neg_count, 1) * 100, 1)

        # 8. 저장
        metrics = {
            "r_score":          r_score_weighted,          # 가중 합산 (메인)
            "r_score_simple":   r_score_simple,            # 단순 비율 (참고)
            "r_score_weighted": r_score_weighted,          # 대시보드용 alias
            "mention_total":    len(raw_items),
            "mention_filtered": len(filtered),
            "cluster_count":    len(clusters),
            "share_of_voice":   analysis["share_of_voice"],
            "hype_flag":        int(is_hype or analysis["hype_flag"]),
            "pain_points":      " | ".join(analysis["pain_points"]),
            "positive_reasons": " | ".join(analysis["positive_reasons"]),
            "unmet_needs":      " | ".join(analysis.get("unmet_needs", [])),
            "insight":          analysis["insight_kr"],
        }
        for metric_name, value in metrics.items():
            all_rows.append([today, ing["id"], ing["name_kr"],
                             "reddit", metric_name, value, collected_at])

        print(f"  → R-Score(가중): {r_score_weighted} | R-Score(단순): {r_score_simple}")
        print(f"  → 클러스터 {len(clusters)}개 | SoV: {analysis['share_of_voice']}%")
        print(f"  → Pain: {analysis['pain_points']}")
        time.sleep(2)

    if all_rows:
        append_rows(TAB_RAW_TRENDS, all_rows)
        print(f"\n✅ Reddit R-Score 수집 완료 — {len(all_rows)}행 저장")
    else:
        print("\n⚠️  저장된 데이터 없음")


if __name__ == "__main__":
    run()

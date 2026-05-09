"""
Google Sheets 연동 클라이언트
- 인증: GOOGLE_CREDENTIALS 환경 변수 (JSON 문자열) 사용
  → 파일을 서버에 올릴 필요 없음, Railway Variables에만 저장
"""

import os
import json
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

# 시트 탭 이름 상수
TAB_RAW_TRENDS = "raw_trends"
TAB_MANUAL_INPUT = "manual_input"
TAB_INGREDIENTS = "ingredients_master"
TAB_RD_INSIGHTS = "rd_insights"


_spreadsheet_cache: gspread.Spreadsheet | None = None


def get_spreadsheet() -> gspread.Spreadsheet:
    """인증 + Spreadsheet 객체를 프로세스 내에서 재사용 (API 호출 절약)."""
    global _spreadsheet_cache
    if _spreadsheet_cache is not None:
        return _spreadsheet_cache
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise EnvironmentError(
            "GOOGLE_CREDENTIALS 환경 변수가 없습니다. "
            "Railway Variables에 서비스 계정 JSON 전체를 붙여넣으세요."
        )
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    _spreadsheet_cache = client.open_by_key(SHEET_ID)
    return _spreadsheet_cache


def ensure_tabs_exist():
    """최초 실행 시 필요한 탭과 헤더를 생성"""
    ss = get_spreadsheet()
    existing = [ws.title for ws in ss.worksheets()]

    tab_headers = {
        TAB_RAW_TRENDS: [
            "date", "ingredient_id", "name_kr", "source",
            "metric_name", "value", "collected_at"
        ],
        TAB_MANUAL_INPUT: [
            "date", "ingredient_id", "name_kr",
            "amazon_bsr_rank", "amazon_review_count", "sephora_new_launches",
            "sephora_bestseller", "price_usd_top1",
            "tiktok_hashtag_views_M", "c_ratio_note", "manual_note"
        ],
        TAB_INGREDIENTS: [
            "ingredient_id", "name_kr", "name_en",
            "status", "category", "added_date", "notes"
        ],
    }

    for tab_name, headers in tab_headers.items():
        if tab_name not in existing:
            ws = ss.add_worksheet(title=tab_name, rows=2000, cols=len(headers))
            ws.append_row(headers)
            print(f"[sheets] 탭 생성: {tab_name}")
        else:
            print(f"[sheets] 탭 확인: {tab_name} (already exists)")


def append_rows(tab_name: str, rows: list[list], dedup_source: str | None = None):
    """
    여러 행을 한 번에 추가.
    dedup_source 지정 시: 오늘 날짜 + 같은 source의 기존 행을 삭제 후 추가
    → 같은 날 수집기를 재실행해도 중복 행 쌓이지 않음
    """
    ss = get_spreadsheet()
    ws = ss.worksheet(tab_name)

    if dedup_source and rows:
        today = rows[0][0]  # 첫 행의 date 컬럼
        existing = ws.get_all_values()
        if len(existing) > 1:
            header = existing[0]
            try:
                date_col = header.index("date")
                source_col = header.index("source")
            except ValueError:
                date_col = source_col = None

            if date_col is not None:
                # 오늘 날짜 + 같은 source 행 번호 수집 (역순으로 삭제해야 행 번호 안 밀림)
                to_delete = [
                    i + 1  # 1-indexed (헤더=1)
                    for i, row in enumerate(existing[1:], start=1)
                    if len(row) > max(date_col, source_col)
                    and row[date_col] == str(today)
                    and row[source_col] == dedup_source
                ]
                for row_num in sorted(to_delete, reverse=True):
                    ws.delete_rows(row_num)
                if to_delete:
                    print(f"  [sheets] 기존 {len(to_delete)}행 교체 (dedup: {dedup_source}, {today})")

    ws.append_rows(rows, value_input_option="USER_ENTERED")


def read_all(tab_name: str) -> list[dict]:
    """탭 전체를 dict 리스트로 반환"""
    ss = get_spreadsheet()
    ws = ss.worksheet(tab_name)
    return ws.get_all_records()


def upsert_ingredients_master(ingredients: list[dict]):
    """ingredients_master 탭을 최신 yaml 기준으로 동기화"""
    ss = get_spreadsheet()
    ws = ss.worksheet(TAB_INGREDIENTS)

    existing = {row["ingredient_id"]: idx + 2
                for idx, row in enumerate(ws.get_all_records())}

    for ing in ingredients:
        row = [
            ing["id"],
            ing["name_kr"],
            ing["name_en"],
            ing["status"],
            ing.get("category", ""),
            ing.get("added_date", ""),
            ing.get("notes", ""),
        ]
        if ing["id"] in existing:
            row_num = existing[ing["id"]]
            ws.update(f"A{row_num}:G{row_num}", [row])
        else:
            ws.append_row(row)

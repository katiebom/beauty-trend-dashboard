"""
Google Sheets 연동 클라이언트
- 서비스 계정 인증
- 시트별 읽기/쓰기/upsert 헬퍼
"""

import os
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")

# 시트 탭 이름 상수
TAB_RAW_TRENDS = "raw_trends"          # 자동 수집 시계열 데이터
TAB_MANUAL_INPUT = "manual_input"      # Katie 수동 입력 (TikTok, Amazon)
TAB_INGREDIENTS = "ingredients_master"  # 성분 메타 정보


def get_client() -> gspread.Client:
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def get_spreadsheet() -> gspread.Spreadsheet:
    client = get_client()
    return client.open_by_key(SHEET_ID)


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
            "tiktok_hashtag_views_M", "amazon_bsr_top_count",
            "c_ratio_note", "manual_note"
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


def append_rows(tab_name: str, rows: list[list]):
    """여러 행을 한 번에 추가 (배치)"""
    ss = get_spreadsheet()
    ws = ss.worksheet(tab_name)
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

    existing = {row["ingredient_id"]: idx + 2  # 1-indexed, +1 for header
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

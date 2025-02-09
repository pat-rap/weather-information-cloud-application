from fastapi import FastAPI, Depends, Response, Request, BackgroundTasks, Query
from datetime import datetime
from typing import List, Optional
from .auth import get_current_user, set_auth_cookie, remove_auth_cookie, TokenData
from .rss_reader import fetch_rss_feed, parse_rss_feed
from .database import execute_sql, delete_old_entries
from .config import PUBLISHING_OFFICE_MAPPING, REGIONS  # config.py からインポート
import logging

# ルートロガーの設定
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

# last_modified をフィードタイプごとに保持する辞書
last_modified_times = {
    "regular": None,
    "extra": None,
    "eqvol": None,
    "other": None
}

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/start")
async def start(response: Response):
    # 本来は、ここでユーザー情報を取得・生成する処理が入る
    user_data = {"sub": "testuser"}
    set_auth_cookie(response, user_data)
    return {"message": "Authentication started.  Cookie set."}

@app.get("/items")
async def read_items(current_user: TokenData = Depends(get_current_user)):
    return {"message": f"Hello, {current_user.username}. You are authenticated."}

@app.get("/logout")
async def logout(response: Response):
    remove_auth_cookie(response)
    return {"message": "Logged out."}

@app.get("/rss/{feed_type}")
async def read_rss(feed_type: str, region: Optional[str] = Query(None), prefecture: Optional[str] = Query(None), publishing_office: Optional[str] = Query(None)):
    global last_modified_times

    # URL とカテゴリ、更新頻度種別を辞書にまとめる
    feed_info = {
        "regular": {"url": "https://www.data.jma.go.jp/developer/xml/feed/regular.xml", "category": "天気概況", "frequency_type": "高頻度"},
        "extra": {"url": "https://www.data.jma.go.jp/developer/xml/feed/extra.xml", "category": "警報・注意報", "frequency_type": "高頻度"},
        "eqvol": {"url": "https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml", "category": "地震・火山", "frequency_type": "高頻度"},
        "other": {"url": "https://www.data.jma.go.jp/developer/xml/feed/other.xml", "category": "その他", "frequency_type": "高頻度"},
    }

    if feed_type not in feed_info:
        return {"error": "Invalid feed type"}

    url = feed_info[feed_type]["url"]
    category = feed_info[feed_type]["category"]
    frequency_type = feed_info[feed_type]["frequency_type"]

    response = fetch_rss_feed(url, last_modified_times[feed_type])
    if response is None:
        return {"message": "No update or error fetching feed"}

    if response:
        entries, feed_title, feed_subtitle, feed_updated, feed_id_in_atom, rights = parse_rss_feed(response)

        # Last-Modified ヘッダーをパースして保存
        last_modified_str = response.headers.get('Last-Modified')
        if last_modified_str:
            last_modified_times[feed_type] = datetime.strptime(last_modified_str, '%a, %d %b %Y %H:%M:%S %Z')

        # データベース挿入処理
        # 1. feed_meta テーブルへの挿入/更新
        feed_updated_dt = datetime.strptime(feed_updated, '%Y-%m-%dT%H:%M:%S%z') if feed_updated else None

        existing_feed = execute_sql("SELECT id FROM feed_meta WHERE feed_url = %s", (url,), fetchone=True)
        if existing_feed:
            # 既存レコードの更新
            feed_id = existing_feed['id']
            execute_sql("""
                UPDATE feed_meta
                SET feed_title = %s, feed_subtitle = %s, feed_updated = %s, feed_id_in_atom = %s, rights = %s, category = %s, frequency_type = %s, last_fetched = %s
                WHERE id = %s
            """, (feed_title, feed_subtitle, feed_updated_dt, feed_id_in_atom, rights, category, frequency_type, datetime.now(), feed_id))
        else:
            # 新規レコードの挿入
            feed_id = execute_sql("""
                INSERT INTO feed_meta (feed_url, feed_title, feed_subtitle, feed_updated, feed_id_in_atom, rights, category, frequency_type, last_fetched)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (url, feed_title, feed_subtitle, feed_updated_dt, feed_id_in_atom, rights, category, frequency_type, datetime.now()), fetchone=True)['id']

        # 2. feed_entries テーブルへの挿入 (都道府県ごとに分割)
        logger.debug(f"read_rss entries: {entries}")
        for entry in entries:
            try:
                entry_updated_dt = datetime.strptime(entry['updated'], '%Y-%m-%dT%H:%M:%S%z') if entry['updated'] else None
            except ValueError:
                try:
                    entry_updated_dt = datetime.strptime(entry['updated'], '%Y-%m-%dT%H:%M:%S') if entry['updated'] else None
                except ValueError:
                    entry_updated_dt = None

            # 都道府県ごとにレコードを挿入
            for prefecture_item in entry['prefectures']:
                logger.debug(f"read_rss INSERT DATA: {feed_id}, {entry['id']}, {entry['title']}, {entry_updated_dt}, {entry['publishing_office']}, {entry['link']}, {entry['content']}, {prefecture_item}")
                execute_sql("""
                    INSERT INTO feed_entries (feed_id, entry_id_in_atom, entry_title, entry_updated, publishing_office, entry_link, entry_content, prefecture)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (feed_id, entry_id_in_atom, publishing_office) DO NOTHING  -- 重複時は何もしない
                """, (feed_id, entry['id'], entry['title'], entry_updated_dt, entry['publishing_office'], entry['link'], entry['content'], prefecture_item))

        # 3. フィルタリング (データベースから取得)
        query = "SELECT * FROM feed_entries WHERE feed_id = %s"
        params = [feed_id]

        if publishing_office:
            query += " AND publishing_office = %s"
            params.append(publishing_office)
        elif prefecture:
            # prefecture から publishing_office を特定
            offices = [office for office, prefs in PUBLISHING_OFFICE_MAPPING.items() if prefecture in prefs]
            if offices:
                placeholders = ', '.join(['%s'] * len(offices))
                query += f" AND publishing_office IN ({placeholders})"
                params.extend(offices)
            else: # prefectureに対応するofficeがない場合
                return Response(content=f"No data found for prefecture: {prefecture}", status_code=404)
        elif region:
            # regions辞書を使って、regionに対応するprefectureのリストを取得
            prefectures_in_region = REGIONS.get(region, [])
            if prefectures_in_region:
                # SQLのIN句を使うためのプレースホルダー文字列を作成
                placeholders = ', '.join(['%s'] * len(prefectures_in_region))
                query += f" AND prefecture IN ({placeholders})"
                params.extend(prefectures_in_region) # パラメータを追加
            else: #regionに対応する都道府県がない場合
                return Response(content=f"No data found for region: {region}", status_code=404)

        query += " ORDER BY entry_updated DESC" # 新しい順に取得
        filtered_entries = execute_sql(query, tuple(params), fetchall=True)

        return {"message": f"Data for {feed_type} inserted/updated successfully.", "entries": filtered_entries}

    else:
        return {"message": "No update or error fetching feed"}

@app.get("/delete_old_entries")
async def delete_old_entries_endpoint(background_tasks: BackgroundTasks):
    background_tasks.add_task(delete_old_entries, days=7)
    return {"message": "Scheduled deletion of old entries."}

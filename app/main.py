from fastapi import FastAPI, Depends, Response, Request, BackgroundTasks, Query
from .auth import get_current_user, set_auth_cookie, remove_auth_cookie, TokenData
from .rss_reader import fetch_rss_feed, parse_rss_feed
from .database import execute_sql, delete_old_entries
from datetime import datetime
from typing import List, Optional

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

# 地域と都道府県(地方)の対応 (必要に応じて拡充)
regions = {
    "北海道": ["宗谷地方", "上川・留萌地方", "網走・北見・紋別地方", "十勝地方", "釧路・根室地方", "胆振・日高地方", "石狩・空知・後志地方", "渡島・檜山地方"],
    "東北": ["青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県"],
    "関東甲信": ["茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県", "山梨県", "長野県"],
    "東海": ["岐阜県", "静岡県", "愛知県", "三重県"],
    "北陸": ["新潟県", "富山県", "石川県", "福井県"],
    "近畿": ["滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県"],
    "中国": ["鳥取県", "島根県", "岡山県", "広島県", "山口県"],
    "四国": ["徳島県", "香川県", "愛媛県", "高知県"],
    "九州": ["福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "奄美地方"],  # 山口県は含めない
    "沖縄": ["沖縄本島地方", "大東島地方", "宮古島地方", "八重山地方"],
    "空港": ["新千歳空港", "成田空港", "羽田空港", "中部国際空港", "関西国際空港", "福岡空港", "那覇空港"] # 必要に応じて
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
async def read_rss(feed_type: str, region: Optional[str] = Query(None), prefecture: Optional[str] = Query(None)):
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
                """, (feed_id, entry['id'], entry['title'], entry_updated_dt, entry['publishing_office'], entry['link'], entry['content'], prefecture_item))

        # 3. フィルタリング (データベースから取得)
        query = "SELECT * FROM feed_entries WHERE feed_id = %s"
        params = [feed_id]

        if region:
            # regions辞書を使って、regionに対応するprefectureのリストを取得
            prefectures_in_region = regions.get(region, [])
            if prefectures_in_region:
                # SQLのIN句を使うためのプレースホルダー文字列を作成
                placeholders = ', '.join(['%s'] * len(prefectures_in_region))
                query += f" AND prefecture IN ({placeholders})"
                params.extend(prefectures_in_region) # パラメータを追加
            else: #regionに対応する都道府県がない場合
                return {"message": f"No data found for region: {region}"}

        if prefecture:
            query += " AND prefecture = %s"
            params.append(prefecture)

        query += " ORDER BY entry_updated DESC" # 新しい順に取得
        filtered_entries = execute_sql(query, tuple(params), fetchall=True)

        return {"message": f"Data for {feed_type} inserted/updated successfully.", "entries": filtered_entries}

    else:
        return {"message": "No update or error fetching feed"}

@app.get("/delete_old_entries")
async def delete_old_entries_endpoint(background_tasks: BackgroundTasks):
    background_tasks.add_task(delete_old_entries, days=7)
    return {"message": "Scheduled deletion of old entries."}

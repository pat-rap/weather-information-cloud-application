from fastapi import FastAPI, Depends, Response, Request
from datetime import datetime
from .auth import get_current_user, set_auth_cookie, remove_auth_cookie, TokenData
from .rss_reader import fetch_rss_feed, parse_rss_feed
from .database import execute_sql

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
    user_data = {"sub": "testuser"}  # 仮のユーザーデータ
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
async def read_rss(feed_type: str):
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
    if response is None:  # 304 Not Modified
        return {"message": "No update or error fetching feed"}

    if response:
        entries, feed_title, feed_subtitle, feed_updated, feed_id_in_atom, rights = parse_rss_feed(response)

        # Last-Modified ヘッダーをパースして保存
        last_modified_str = response.headers.get('Last-Modified')
        if last_modified_str:
            last_modified_times[feed_type] = datetime.strptime(last_modified_str, '%a, %d %b %Y %H:%M:%S %Z')

        # --- データベース挿入処理 ---
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

        # 2. feed_entries テーブルへの挿入
        print(entries) #entriesの内容を確認
        for entry in entries:
            #entry_updated_dt = datetime.strptime(entry['updated'], '%Y-%m-%dT%H:%M:%S%z') if entry['updated'] else None
            try:
                entry_updated_dt = datetime.strptime(entry['updated'], '%Y-%m-%dT%H:%M:%S%z') if entry['updated'] else None
            except ValueError:
                try:
                    entry_updated_dt = datetime.strptime(entry['updated'], '%Y-%m-%dT%H:%M:%S') if entry['updated'] else None  # %z がない場合
                except ValueError:
                    entry_updated_dt = None #さらに柔軟に対応
            print(feed_id, entry['id'], entry['title'], entry_updated_dt, entry['author'], entry['link'], entry['content'])#挿入データを確認
            execute_sql("""
                INSERT INTO feed_entries (feed_id, entry_id_in_atom, entry_title, entry_updated, entry_author, entry_link, entry_content)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (feed_id, entry['id'], entry['title'], entry_updated_dt, entry['author'], entry['link'], entry['content']))

        return {"message": f"Data for {feed_type} inserted/updated successfully."}

    else:
        return {"message": "No update or error fetching feed"}

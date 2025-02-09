from fastapi import FastAPI, Depends, Response, Request, BackgroundTasks, Query, Form, HTTPException, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime
from typing import List, Optional
import logging
from urllib.parse import quote_plus
from .auth import get_current_user, set_auth_cookie, remove_auth_cookie, TokenData
from .rss_reader import fetch_rss_feed, parse_rss_feed
from .database import execute_sql, delete_old_entries
from .config import PUBLISHING_OFFICE_MAPPING, REGIONS, PREFECTURES

# ルートロガーの設定
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

# staticフォルダを静的ファイルとしてマウント
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# templatesフォルダを指定
templates = Jinja2Templates(directory="app/templates")

# last_modified をフィードタイプごとに保持する辞書
last_modified_times = {
    "regular": None,
    "extra": None,
    "eqvol": None,
    "other": None
}

@app.get("/", response_class=HTMLResponse)
async def root(request: Request,
               current_user: TokenData = Depends(get_current_user),
               selected_region: Optional[str] = Cookie(None), #Cookieから取得
               selected_prefecture: Optional[str] = Cookie(None), #Cookieから取得
               selected_feed_type: Optional[str] = Cookie("extra") #Cookieから取得
               ):
    """
    トップページを表示。
    ログイン状態に応じて、認証開始ボタンまたは項目表示ページへのリンクを表示。
    """
    # テンプレートに渡す変数
    context = {
        "request": request,
        "regions": REGIONS,
        "prefectures": PREFECTURES,
        "selected_region": selected_region,
        "selected_prefecture": selected_prefecture,
        "selected_feed_type": selected_feed_type, # 追加
        "username": current_user.username if current_user else None, # ユーザー名
    }
    return templates.TemplateResponse("index.html", context)

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
    # トップページにリダイレクト
    return RedirectResponse("/", status_code=302)

@app.post("/select_location")
async def select_location(response: Response, region: str = Form(...), prefecture: str = Form(...), feed_type: str = Form(...)):
    """
    選択された地域と都道府県をクッキーに保存し、/rss/{feed_type} にリダイレクト。
    """
    # URLエンコード (日本語などのマルチバイト文字を安全に扱うため)
    encoded_region = quote_plus(region)
    encoded_prefecture = quote_plus(prefecture)

    response.set_cookie(key="selected_region", value=encoded_region)
    response.set_cookie(key="selected_prefecture", value=encoded_prefecture)
    response.set_cookie(key="selected_feed_type", value=feed_type)  # feed_type を保存
    return RedirectResponse(f"/rss/{feed_type}", status_code=302) #選択されたfeed_typeのページにリダイレクト

@app.get("/rss/{feed_type}")
async def read_rss(feed_type: str, request: Request, region:  Optional[str] = Query(None), prefecture: Optional[str] = Query(None), current_user: TokenData = Depends(get_current_user)):
    global last_modified_times

    # URL とカテゴリ、更新頻度種別を辞書にまとめる
    feed_info = {
        #"regular": {"url": "https://www.data.jma.go.jp/developer/xml/feed/regular.xml", "category": "天気概況", "frequency_type": "高頻度"},
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
        #return {"message": "No update or error fetching feed"}
        # 更新がない場合は、DBから最新の10件を取得して表示
        query = "SELECT * FROM feed_entries"
        params = []

        if region:
            prefectures_in_region = REGIONS.get(region, [])
            if prefectures_in_region:
                placeholders = ', '.join(['%s'] * len(prefectures_in_region))
                query += f" WHERE prefecture IN ({placeholders})"
                params.extend(prefectures_in_region)
            else:
                raise HTTPException(status_code=404, detail=f"No data found for region: {region}")

        if prefecture:
            if "WHERE" in query:
                query += " AND prefecture = %s"
            else:
                query += " WHERE prefecture = %s"
            params.append(prefecture)

        query += " ORDER BY entry_updated DESC LIMIT 10" # 最新の10件を取得
        filtered_entries = execute_sql(query, tuple(params), fetchall=True)

        context = {
            "request": request,
            "feed_title": category,
            "entries": filtered_entries,
            "username": current_user.username if current_user else None,
        }
        return templates.TemplateResponse("feed_data.html", context) # feed_data.html を表示

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
                    ON CONFLICT (feed_id, entry_id_in_atom, publishing_office) DO NOTHING
                """, (feed_id, entry['id'], entry['title'], entry_updated_dt, entry['publishing_office'], entry['link'], entry['content'], prefecture_item))

        # 3. フィルタリング (データベースから取得)
        query = "SELECT * FROM feed_entries WHERE feed_id = %s"
        params = [feed_id]

        if region:
            # regions辞書を使って、regionに対応するprefectureのリストを取得
            prefectures_in_region = REGIONS.get(region, [])
            if prefectures_in_region:
                # SQLのIN句を使うためのプレースホルダー文字列を作成
                placeholders = ', '.join(['%s'] * len(prefectures_in_region))
                query += f" AND prefecture IN ({placeholders})"
                params.extend(prefectures_in_region) # パラメータを追加
            else: #regionに対応する都道府県がない場合
                #return {"message": f"No data found for region: {region}"}
                raise HTTPException(status_code=404, detail=f"No data found for region: {region}")

        if prefecture:
            query += " AND prefecture = %s"
            params.append(prefecture)

        query += " ORDER BY entry_updated DESC LIMIT 10" # 新しい順に取得
        filtered_entries = execute_sql(query, tuple(params), fetchall=True)

        #return {"message": f"Data for {feed_type} inserted/updated successfully.", "entries": filtered_entries}
        context = {
            "request": request,
            "feed_title": feed_title,
            "entries": filtered_entries,
            "username": current_user.username if current_user else None,
        }
        return templates.TemplateResponse("feed_data.html", context)

    else:
        #return {"message": "No update or error fetching feed"}
        # 更新がない場合は、DBから最新の10件を取得して表示
        query = "SELECT * FROM feed_entries"
        params = []

        if region:
            prefectures_in_region = REGIONS.get(region, [])
            if prefectures_in_region:
                placeholders = ', '.join(['%s'] * len(prefectures_in_region))
                query += f" WHERE prefecture IN ({placeholders})"
                params.extend(prefectures_in_region)
            else:
                raise HTTPException(status_code=404, detail=f"No data found for region: {region}")

        if prefecture:
            if "WHERE" in query:
                query += " AND prefecture = %s"
            else:
                query += " WHERE prefecture = %s"
            params.append(prefecture)

        query += " ORDER BY entry_updated DESC LIMIT 10" # 最新の10件を取得
        filtered_entries = execute_sql(query, tuple(params), fetchall=True)

        context = {
            "request": request,
            "feed_title": category,
            "entries": filtered_entries,
            "username": current_user.username if current_user else None,
        }
        return templates.TemplateResponse("feed_data.html", context) # feed_data.html を表示

@app.get("/delete_old_entries")
async def delete_old_entries_endpoint(background_tasks: BackgroundTasks):
    background_tasks.add_task(delete_old_entries, days=7)
    return {"message": "Scheduled deletion of old entries."}

@app.get("/get_prefectures")
async def get_prefectures(region: str = Query(...)):
    """
    指定された地域に対応する都道府県のリストを返す。
    """
    return REGIONS.get(region, [])

from fastapi import FastAPI, Depends, Response, Request, BackgroundTasks, Query, Form, HTTPException, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime
from typing import List, Optional
import logging
from urllib.parse import quote_plus, unquote_plus
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
               region: Optional[str] = Query(None),
               prefecture: Optional[str] = Query(None),
               feed_type: Optional[str] = Query(None)):
    """
    トップページを表示。
    ログイン状態に応じて、認証開始ボタンまたは項目表示ページへのリンクを表示。
    """
    # Cookieからの取得処理（後でクエリパラメータが優先されるようにする）
    selected_region = request.cookies.get("selected_region")
    selected_prefecture = request.cookies.get("selected_prefecture")
    selected_feed_type = request.cookies.get("selected_feed_type") or "extra"

    # クエリパラメータを優先
    context_region = region if region is not None else selected_region
    context_prefecture = prefecture if prefecture is not None else selected_prefecture
    context_feed_type = feed_type if feed_type is not None else selected_feed_type

    context = {
        "request": request,
        "regions": REGIONS,
        "prefectures": PREFECTURES,
        "selected_region": context_region,
        "selected_prefecture": context_prefecture,
        "selected_feed_type": context_feed_type,
        "username": current_user.username if current_user else None,
    }
    return templates.TemplateResponse("index.html", context)

@app.get("/start")
async def start(response: Response):
    # 本来は、ここでユーザー情報を取得・生成する処理が入る
    redirect_resp = RedirectResponse("/", status_code=302)
    user_data = {"sub": "testuser"}
    set_auth_cookie(redirect_resp, user_data)
    return redirect_resp

@app.get("/items")
async def read_items(current_user: TokenData = Depends(get_current_user)):
    return {"message": f"Hello, {current_user.username}. You are authenticated."}

@app.get("/logout")
async def logout(response: Response):
    # トップページにリダイレクト
    redirect_resp = RedirectResponse("/", status_code=302)
    remove_auth_cookie(redirect_resp)
    return redirect_resp

@app.get("/rss/{feed_type}")
async def read_rss(feed_type: str, request: Request, region:  Optional[str] = Query(None), prefecture: Optional[str] = Query(None), current_user: TokenData = Depends(get_current_user)):
    global last_modified_times

    # クッキーから値を取得
    selected_region = request.cookies.get("selected_region")
    selected_prefecture = request.cookies.get("selected_prefecture")
    # URLデコード
    if selected_region:
        selected_region = unquote_plus(selected_region)
    if selected_prefecture:
        selected_prefecture = unquote_plus(selected_prefecture)

    # region, prefecture が Query Parameter で指定されていない場合、クッキーの値を使う
    if region is None:
        region = selected_region
    if prefecture is None:
        prefecture = selected_prefecture

    # フィードの種類に応じて、対応するURLを取得
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
    response = fetch_rss_feed(url, last_modified_times[feed_type])
    # --- RSS フィードが取得できなかった場合 (更新がない、またはエラー) ---
    if response is None:
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

        query += f" AND feed_id = (SELECT id FROM feed_meta WHERE feed_url = '{url}')" # feed_idでフィルタリング
        query += " ORDER BY entry_updated DESC LIMIT 10"
        filtered_entries = execute_sql(query, tuple(params), fetchall=True)

        context = {
            "request": request,
            "feed_title": category,
            "entries": filtered_entries,
            "username": current_user.username if current_user else None,
        }
        return templates.TemplateResponse("feed_data.html", context)

    # --- RSS フィードが取得できた場合 ---
    if response:
        entries, feed_title, feed_subtitle, feed_updated, feed_id_in_atom, rights = parse_rss_feed(response)

        # Last-Modified ヘッダーをパースして保存
        last_modified_str = response.headers.get('Last-Modified')
        if last_modified_str:
            last_modified_times[feed_type] = datetime.strptime(last_modified_str, '%a, %d %b %Y %H:%M:%S %Z')

        # データベース挿入処理
        # 1. feed_meta テーブルへの挿入/更新 (INSERT ... ON CONFLICT)
        feed_updated_dt = datetime.strptime(feed_updated, '%Y-%m-%dT%H:%M:%S%z') if feed_updated else None

        feed_id = execute_sql("""
            INSERT INTO feed_meta (feed_url, feed_title, feed_subtitle, feed_updated, feed_id_in_atom, rights, category, frequency_type, last_fetched)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (feed_url) DO UPDATE
            SET feed_title = EXCLUDED.feed_title,
                feed_subtitle = EXCLUDED.feed_subtitle,
                feed_updated = EXCLUDED.feed_updated,
                feed_id_in_atom = EXCLUDED.feed_id_in_atom,
                rights = EXCLUDED.rights,
                category = EXCLUDED.category,
                frequency_type = EXCLUDED.frequency_type,
                last_fetched = EXCLUDED.last_fetched
            RETURNING id
        """, (url, feed_title, feed_subtitle, feed_updated_dt, feed_id_in_atom, rights, category, feed_info[feed_type]["frequency_type"], datetime.now()), fetchone=True)['id']


        # 2. feed_entries テーブルへの挿入 (都道府県ごとに分割)
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
                execute_sql("""
                    INSERT INTO feed_entries (feed_id, entry_id_in_atom, entry_title, entry_updated, publishing_office, entry_link, entry_content, prefecture)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (feed_id, entry_id_in_atom, publishing_office) DO NOTHING
                """, (feed_id, entry['id'], entry['title'], entry_updated_dt, entry['publishing_office'], entry['link'], entry['content'], prefecture_item))

        # 3. フィルタリング (データベースから取得)
        query = "SELECT * FROM feed_entries WHERE feed_id = %s"  # 最初に feed_id で絞り込む
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
                raise HTTPException(status_code=404, detail=f"No data found for region: {region}")

        if prefecture:
            query += " AND prefecture = %s"
            params.append(prefecture)

        query += " ORDER BY entry_updated DESC LIMIT 10" # 新しい順に取得
        filtered_entries = execute_sql(query, tuple(params), fetchall=True)

        context = {
            "request": request,
            "feed_title": feed_title,
            "entries": filtered_entries,
            "username": current_user.username if current_user else None,
        }
        return templates.TemplateResponse("feed_data.html", context)

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

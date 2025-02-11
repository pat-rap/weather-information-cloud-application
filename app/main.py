from fastapi import FastAPI, Depends, Response, Request, BackgroundTasks, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from typing import List, Optional
import logging
from urllib.parse import unquote_plus
from .auth import get_current_user, set_auth_cookie, remove_auth_cookie, TokenData
from . import rss_reader
from .database import execute_sql, delete_old_entries
from .config import REGIONS, PREFECTURES

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

# スロットリング間隔 (例: 高頻度フィードは1分、それ以外は10分)
THROTTLE_INTERVALS = {
    "extra": 60,
    "eqvol": 60,
    "other": 60,
    #"regular": 60,  # regular は一旦コメントアウト
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
        raise HTTPException(status_code=400, detail="Invalid feed type") # エラーレスポンスを返す

    url = feed_info[feed_type]["url"]
    category = feed_info[feed_type]["category"]
    frequency_type = feed_info[feed_type]["frequency_type"]

    # スロットリング処理
    if rss_reader.should_throttle(url, THROTTLE_INTERVALS.get(feed_type, 60)):
        logger.info(f"Throttling request for feed type: {feed_type}, url: {url}")
        # DBからデータ取得: rss_reader の関数を呼び出す
        filtered_entries = rss_reader.get_filtered_entries_from_db(url, region, prefecture)
        context = {
            "request": request,
            "feed_title": category,
            "entries": filtered_entries,
            "username": current_user.username if current_user else None,
        }
        return templates.TemplateResponse("feed_data.html", context)

    # RSSフィード取得
    response = rss_reader.fetch_rss_feed(url, last_modified_times.get(feed_type))

    # --- RSS フィードが取得できなかった場合 (更新がない、またはエラー) ---
    if response is None:
        logger.info(f"No update for feed type: {feed_type}, retrieving from DB")
        # DBからデータ取得: rss_reader の関数を呼び出す
        filtered_entries = rss_reader.get_filtered_entries_from_db(url, region, prefecture)
        context = {
            "request": request,
            "feed_title": category,
            "entries": filtered_entries,
            "username": current_user.username if current_user else None,
        }
        return templates.TemplateResponse("feed_data.html", context)

    # --- RSS フィードが取得できた場合 ---
    if response:
        # パース処理
        parsed_feed_data = rss_reader.parse_rss_feed(response)

        # Last-Modified ヘッダーをパースして保存
        last_modified_str = response.headers.get('Last-Modified')
        if last_modified_str:
            last_modified_times[feed_type] = datetime.strptime(last_modified_str, '%a, %d %b %Y %H:%M:%S %Z')

        # データベース挿入/更新処理: rss_reader の関数を呼び出す
        feed_id = rss_reader.insert_or_update_feed_data(parsed_feed_data, feed_type, url, category, frequency_type)

        # 3. フィルタリング (データベースから取得): rss_reader の関数を使う
        filtered_entries = rss_reader.get_filtered_entries(feed_id, region, prefecture)

        context = {
            "request": request,
            "feed_title": parsed_feed_data[1],  # feed_title
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

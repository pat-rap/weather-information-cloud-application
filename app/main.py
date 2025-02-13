from fastapi import FastAPI, Depends, Response, Request, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Optional
import asyncio
from .auth import get_current_user, set_auth_cookie, remove_auth_cookie, TokenData
from . import rss_reader
from .database import delete_old_entries
from .config import REGIONS_DATA, FEED_INFO, PERIODIC_FETCH_INTERVAL
import logging

# ルートロガーの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

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

    # データベースからデータを取得 (選択された feed_type, region, prefecture に基づいてフィルタリング)
    if context_feed_type not in FEED_INFO:
        # 不正な feed_type が指定された場合は、空のリストを渡す
        entries = []
        feed_title = ""
    else:
        entries = rss_reader.get_filtered_entries_from_db(
            FEED_INFO[context_feed_type]["url"], context_region, context_prefecture
        )
        feed_title = FEED_INFO[context_feed_type]["category"]

    context = {
        "request": request,
        "regions": list(REGIONS_DATA.keys()),
        "prefectures": [pref for data in REGIONS_DATA.values() for pref in data.get("prefectures", [])],
        "selected_region": context_region,
        "selected_prefecture": context_prefecture,
        "selected_feed_type": context_feed_type,
        "username": current_user.username if current_user else None,
        "entries": entries,
        "feed_title": feed_title,
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

@app.get("/get_prefectures")
async def get_prefectures(region: str = Query(...)) -> list[str]:
    """
    指定された地域に対応する都道府県のリストを返す。
    """
    return REGIONS_DATA.get(region, {}).get("prefectures", [])

async def periodic_fetch(background_tasks: BackgroundTasks):
    """
    定期的にフィードを取得・更新する関数。
    """
    while True:
        for feed_type, info in FEED_INFO.items():
            background_tasks.add_task(
                rss_reader.fetch_and_store_feed_data,
                feed_type,
                info["url"],
                info["category"],
                info["frequency_type"]
            )
        await asyncio.sleep(PERIODIC_FETCH_INTERVAL)

@app.on_event("startup")
async def startup_event(background_tasks: BackgroundTasks = BackgroundTasks()):
    """
    アプリケーション起動時のイベントハンドラ。
    バックグラウンドタスクを開始する。
    """
    background_tasks.add_task(periodic_fetch, background_tasks)

@app.get("/delete_old_entries")
async def delete_old_entries_endpoint(background_tasks: BackgroundTasks):
    background_tasks.add_task(delete_old_entries, days=7)
    return {"message": "Scheduled deletion of old entries."}

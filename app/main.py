from fastapi import FastAPI, Depends, Response, Request, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Optional
import asyncio
from contextlib import asynccontextmanager
from .auth import get_current_user, set_auth_cookie, remove_auth_cookie, TokenData
from . import rss_reader
from .database import delete_old_entries
from .config import REGIONS_DATA, FEED_INFO, PERIODIC_FETCH_INTERVAL
import logging

# ルートロガーの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app_mount_path = "app/static"
template_directory = "app/templates"

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(periodic_fetch())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory=app_mount_path), name="static")
templates = Jinja2Templates(directory=template_directory)

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
        # feed_type に対応する高頻度・低頻度両方のURLを取得
        feed_urls = [
            FEED_INFO[context_feed_type]["url"],
            FEED_INFO[context_feed_type + "_l"]["url"]
        ] if context_feed_type + "_l" in FEED_INFO else [FEED_INFO[context_feed_type]["url"]]

        entries = []
        try:
            for url in feed_urls:
                entries.extend(rss_reader.get_filtered_entries_from_db(
                    url, context_region, context_prefecture
                ))
        except Exception as e:
            logger.exception(f"Error getting entries from database: {e}")
            entries = []  # エラーが発生した場合は空のリストにする
            feed_title = ""
            context["error_message"] = "データの取得中にエラーが発生しました。" # エラーメッセージ

        # entry_updated でソート (降順)
        entries.sort(key=lambda x: x['entry_updated'], reverse=True)

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

async def periodic_fetch():
    """
    定期的にフィードを取得・更新する関数。
    """
    while True:
        logger.info("periodic_fetch started - outer loop")
        for feed_type, info in FEED_INFO.items():
            logger.info(f"Adding task for feed_type: {feed_type}")  # ログ追加
            try:
                result = await rss_reader.fetch_and_store_feed_data(
                    feed_type,
                    info["url"],
                    info["category"],
                    info["frequency_type"]
                )
            except Exception as e:
                logger.error(f"Error in periodic_fetch for {feed_type}: {e}")
                continue
            if result:
                logger.info(f"fetch_and_store_feed_data succeeded for {feed_type}")
            else:
                logger.info(f"fetch_and_store_feed_data failed for {feed_type}")
        await asyncio.sleep(PERIODIC_FETCH_INTERVAL)
        logger.info(f"periodic_fetch sleeping for {PERIODIC_FETCH_INTERVAL} seconds")  # ログ追加

@app.get("/delete_old_entries")
async def delete_old_entries_endpoint(background_tasks: BackgroundTasks):
    background_tasks.add_task(delete_old_entries, days=7)
    return {"message": "Scheduled deletion of old entries."}

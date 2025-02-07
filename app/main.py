from fastapi import FastAPI, Depends, Response, Request
from auth import get_current_user, set_auth_cookie, remove_auth_cookie, TokenData
from rss_reader import fetch_rss_feed, parse_rss_feed

app = FastAPI()

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
    if feed_type == "regular":
        url = "https://www.data.jma.go.jp/developer/xml/feed/regular.xml"
    elif feed_type == "extra":
        url = "https://www.data.jma.go.jp/developer/xml/feed/extra.xml"
    elif feed_type == "eqvol":
        url = "https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml"
    elif feed_type == "other":
        url = "https://www.data.jma.go.jp/developer/xml/feed/other.xml"
    else:
        return {"error": "Invalid feed type"}

    response = fetch_rss_feed(url)
    if response:
        entries, feed_title, feed_subtitle, feed_updated, feed_id_in_atom, rights = parse_rss_feed(response)
        return {"feed_title": feed_title, "entries": entries, "feed_subtitle":feed_subtitle, "feed_updated":feed_updated, "feed_id_in_atom":feed_id_in_atom, "rights":rights}
    else:
        return {"message": "No update or error fetching feed"}


import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
import xml.etree.ElementTree as ET

def fetch_rss_feed(url: str, last_modified: Optional[datetime] = None) -> Optional[requests.Response]:
    """
    指定されたURLからRSSフィードを取得する。
    If-Modified-Since ヘッダーを活用し、更新がない場合は None を返す。
    """
    headers = {}
    if last_modified:
        headers['If-Modified-Since'] = last_modified.strftime('%a, %d %b %Y %H:%M:%S GMT')

    try:
        response = requests.get(url, headers=headers, timeout=10)  # 10秒でタイムアウト
        response.raise_for_status()  # ステータスコードが200番台以外なら例外を発生

        if response.status_code == 304:
            return None  # 更新なし

        return response

    except requests.exceptions.RequestException as e:
        print(f"Error fetching RSS feed: {e}")  # エラーログ
        return None


def parse_rss_feed(response: requests.Response) -> List[Dict]:
    """
    RSSフィードのレスポンスをパースし、必要な情報を抽出する。
    """
    try:
        soup = BeautifulSoup(response.content, 'xml')
        entries = []

        for item in soup.find_all('item'):  # Atom形式の場合は 'entry'
            print(item) # 追加: item の内容を確認
            entry = {
                'title': item.title.text if item.title else None,
                'link': item.link.text if item.link else None,
                'updated': item.updated.text if item.updated else (item.pubDate.text if item.pubDate else None), # 'updated' がなければ 'pubDate'
                'author': item.find('author').find('name').text if item.find('author') and item.find('author').find('name') else None,
                'content': item.find('content').text if item.find('content') else None, #contentタグ
                'id': item.id.text if item.id else None,
            }
            print(entry)  # 追加: entry の内容を確認
            entries.append(entry)
        #find_allの結果が空の場合を考慮し、findで処理を行う。
        feed_title = soup.find('title').text if soup.find('title') else None
        feed_subtitle = soup.find('subtitle').text if soup.find('subtitle') else None
        feed_updated = soup.find('updated').text if soup.find('updated') else None
        feed_id_in_atom = soup.find('id').text if soup.find('id') else None
        rights = soup.find('rights').text if soup.find('rights') else None

        return entries, feed_title, feed_subtitle, feed_updated, feed_id_in_atom, rights

    except Exception as e:
        print(f"Error parsing RSS feed: {e}")
        return [], None, None, None, None, None


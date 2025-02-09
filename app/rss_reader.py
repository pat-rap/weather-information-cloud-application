import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
from .config import PUBLISHING_OFFICE_MAPPING, PREFECTURES, get_prefecture_from_kishodai  # config.py からインポート

import logging
# ルートロガーの設定
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# グローバル変数として、ダウンロード量を追跡 (簡易的な実装)
downloaded_bytes = 0
DOWNLOAD_LIMIT = 10 * 1024 * 1024 * 1024  # 10GB


def fetch_rss_feed(url: str, last_modified: Optional[datetime] = None) -> Optional[requests.Response]:
    """
    指定されたURLからRSSフィードを取得する。
    If-Modified-Since ヘッダーを活用し、更新がない場合は None を返す。
    """
    global downloaded_bytes
    headers = {}
    if last_modified:
        headers['If-Modified-Since'] = last_modified.strftime('%a, %d %b %Y %H:%M:%S GMT')

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        if response.status_code == 304:
            return None

        # ダウンロード量の加算 (厳密な計算ではない)
        downloaded_bytes += len(response.content)
        logger.info(f"Downloaded: {len(response.content)} bytes, Total: {downloaded_bytes} bytes")

        return response

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching RSS feed: {e}")
        return None

def extract_prefecture_from_content(content: str) -> List[str]:
    """<content> から都道府県名を抽出 (複数対応)"""
    prefectures_found = []
    if not content:
        return prefectures_found

    for pref in PREFECTURES:
        if pref in content:
            prefectures_found.append(pref)
    return prefectures_found

def parse_detail_xml(url:str) -> tuple[List[str],Optional[str]]:
    """詳細XMLをパースして都道府県情報と発表官署を取得(都道府県は複数)"""
    global downloaded_bytes
    if downloaded_bytes > DOWNLOAD_LIMIT * 0.8: # 80%を超えたら詳細XMLのダウンロードを控える
        logger.warning("Approaching download limit. Skipping detail XML parsing.")
        return [], None

    response = fetch_rss_feed(url) # ここでダウンロード
    prefectures = []
    publishing_office = None

    if response:
        try:
            soup = BeautifulSoup(response.content, 'xml')

            # 都道府県情報を抽出 (XPath)
            prefecture_elements = soup.select('Report > Head > Area > Name')
            if prefecture_elements:
                for element in prefecture_elements:
                    if '都' in element.text or '道' in element.text or '府' in element.text or '県' in element.text:
                        prefectures.append(element.text)

            publishing_office_elements = soup.select('Report > Control > PublishingOffice')
            if publishing_office_elements:
                publishing_office = publishing_office_elements[0].text

            return prefectures, publishing_office
        except Exception as e:
            logger.error(f"Error parsing detail XML: {e}")
            return [], None
    else:
        return [], None

def parse_rss_feed(response: requests.Response) -> List[Dict]:
    """
    RSSフィードのレスポンスをパースし、必要な情報を抽出する。
    """
    try:
        soup = BeautifulSoup(response.content, 'xml')
        entries = []

        for item in soup.find_all('entry'):
            #logger.debug(f"parse_rss_feed item: {item}")

            author_name = item.find('author').find('name').text if item.find('author') and item.find('author').find('name') else None

            # content から都道府県を抽出
            prefectures = extract_prefecture_from_content(item.find('content').text if item.find('content') else None)

            # content から抽出できない場合、author から都道府県を特定
            if not prefectures and author_name:
                prefectures = get_prefecture_from_kishodai(author_name)

            # contentからもauthorからも特定できない場合のみ、詳細XMLをパース
            detail_prefectures = []
            if not prefectures:
                detail_prefectures, detail_publishing_office = parse_detail_xml(item.id.text) if item.id else ([], None)
                if detail_prefectures: #詳細XMLで取得成功
                    prefectures = detail_prefectures
                #else: #詳細XMLからも取得できなかった場合は、author_nameをpublishing_officeとして利用
                    #publishing_office = author_name #詳細XMLをダウンロードしない場合

            publishing_office = author_name if author_name else (detail_publishing_office if 'detail_publishing_office' in locals() else None)


            entry = {
                'title': item.title.text if item.title else None,
                'link': item.link.text if item.link else None,
                'updated': item.updated.text if item.updated else (item.pubDate.text if item.pubDate else None),
                'publishing_office': publishing_office,
                'content': item.find('content').text if item.find('content') else None,
                'id': item.id.text if item.id else None,
                'prefectures': prefectures # 都道府県 (複数)
            }
            #logger.debug(f"parse_rss_feed entry: {entry}")
            entries.append(entry)

        feed_title = soup.find('title').text if soup.find('title') else None
        feed_subtitle = soup.find('subtitle').text if soup.find('subtitle') else None
        feed_updated = soup.find('updated').text if soup.find('updated') else None
        feed_id_in_atom = soup.find('id').text if soup.find('id') else None
        rights = soup.find('rights').text if soup.find('rights') else None

        return entries, feed_title, feed_subtitle, feed_updated, feed_id_in_atom, rights

    except Exception as e:
        print(f"Error parsing RSS feed: {e}")
        return [], None, None, None, None, None

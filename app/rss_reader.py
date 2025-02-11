import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime, timezone
from .config import PREFECTURES, get_prefecture_from_kishodai, REGIONS
from .database import execute_sql

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
            # content から都道府県を抽出
            prefectures = extract_prefecture_from_content(item.find('content').text if item.find('content') else None)

            # content から抽出できない場合、author から都道府県を特定
            author_name = item.find('author').find('name').text if item.find('author') and item.find('author').find('name') else None
            if not prefectures and author_name:
                prefectures = get_prefecture_from_kishodai(author_name)

            # contentからもauthorからも特定できない場合のみ、詳細XMLをパース
            detail_prefectures = []
            if not prefectures:
                detail_prefectures, detail_publishing_office = parse_detail_xml(item.id.text) if item.id else ([], None)
                if detail_prefectures: #詳細XMLで取得成功
                    prefectures = detail_prefectures

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

def get_feed_data(feed_type: str, url: str, category: str, frequency_type: str, last_modified: Optional[datetime] = None) -> Optional[int]:
    """RSSフィードを取得、パース、DB保存し、feed_idを返す"""
    response = fetch_rss_feed(url, last_modified)
    if response is None:
        return None

    entries, feed_title, feed_subtitle, feed_updated, feed_id_in_atom, rights = parse_rss_feed(response)

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
    """, (url, feed_title, feed_subtitle, feed_updated_dt, feed_id_in_atom, rights, category, frequency_type, datetime.now()), fetchone=True)['id']

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

    return feed_id

def get_filtered_entries(feed_id: int, region: Optional[str] = None, prefecture: Optional[str] = None) -> List[Dict]:
    """DBから指定条件でエントリをフィルタリング"""
    query = "SELECT * FROM feed_entries WHERE feed_id = %s"
    params = [feed_id]

    if region:
        prefectures_in_region = REGIONS.get(region, [])
        if prefectures_in_region:
            placeholders = ', '.join(['%s'] * len(prefectures_in_region))
            query += f" AND prefecture IN ({placeholders})"
            params.extend(prefectures_in_region)
        else:
            return []

    if prefecture:
        query += " AND prefecture = %s"
        params.append(prefecture)

    query += " ORDER BY entry_updated DESC LIMIT 10"
    filtered_entries = execute_sql(query, tuple(params), fetchall=True)
    return filtered_entries

def should_throttle(url: str, interval: int) -> bool:
    """指定されたURLに対するリクエストをスロットリングすべきかどうかを判定する"""
    last_fetched = execute_sql("SELECT last_fetched FROM feed_meta WHERE feed_url = %s", (url,), fetchone=True)

    if last_fetched and last_fetched['last_fetched']:
        time_since_last_fetch = datetime.now(timezone.utc) - last_fetched['last_fetched']
        return time_since_last_fetch.total_seconds() < interval
    else:
        return False  # 初回取得時はスロットリングしない

def get_filtered_entries_from_db(feed_url: str, region: Optional[str] = None, prefecture: Optional[str] = None) -> List[Dict]:
    """DBから指定条件でエントリをフィルタリング(feed_url使用)"""

    # feed_metaテーブルからfeed_idを取得
    feed_meta = execute_sql("SELECT id FROM feed_meta WHERE feed_url = %s", (feed_url,), fetchone=True)
    if not feed_meta:
        return []  # 該当するフィードがない場合は空のリストを返す
    feed_id = feed_meta['id']

    query = "SELECT * FROM feed_entries WHERE feed_id = %s"
    params = [feed_id]

    if region:
        prefectures_in_region = REGIONS.get(region, [])
        if prefectures_in_region:
            placeholders = ', '.join(['%s'] * len(prefectures_in_region))
            query += f" AND prefecture IN ({placeholders})"
            params.extend(prefectures_in_region)
        else:
            return []

    if prefecture:
        query += " AND prefecture = %s"
        params.append(prefecture)

    query += " ORDER BY entry_updated DESC LIMIT 10"
    filtered_entries = execute_sql(query, tuple(params), fetchall=True)
    return filtered_entries

def insert_or_update_feed_data(parsed_feed_data, feed_type, url, category, frequency_type):
    """パースされたフィードデータとその他の情報を受け取り、DBに挿入/更新する"""
    entries, feed_title, feed_subtitle, feed_updated, feed_id_in_atom, rights = parsed_feed_data

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
    """, (url, feed_title, feed_subtitle, feed_updated_dt, feed_id_in_atom, rights, category, frequency_type, datetime.now()), fetchone=True)['id']

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

    return feed_id


def get_feed_data(feed_type: str, url: str, category: str, frequency_type: str, last_modified: Optional[datetime] = None) -> Optional[int]:
    """RSSフィードを取得、パース、DB保存し、feed_idを返す"""
    response = fetch_rss_feed(url, last_modified)
    if response is None:
        return None

    parsed_feed_data = parse_rss_feed(response) #パース結果をタプルで受け取る
    feed_id = insert_or_update_feed_data(parsed_feed_data, feed_type, url, category, frequency_type) #パース結果を渡す

    return feed_id

def get_filtered_entries(feed_id: int, region: Optional[str] = None, prefecture: Optional[str] = None) -> List[Dict]:
    """DBから指定条件でエントリをフィルタリング"""
    query = "SELECT * FROM feed_entries WHERE feed_id = %s"
    params = [feed_id]

    if region:
        prefectures_in_region = REGIONS.get(region, [])
        if prefectures_in_region:
            placeholders = ', '.join(['%s'] * len(prefectures_in_region))
            query += f" AND prefecture IN ({placeholders})"
            params.extend(prefectures_in_region)
        else:
            return [] #regionに該当する都道府県がない場合

    if prefecture:
        query += " AND prefecture = %s"
        params.append(prefecture)

    query += " ORDER BY entry_updated DESC LIMIT 10"
    filtered_entries = execute_sql(query, tuple(params), fetchall=True)
    return filtered_entries

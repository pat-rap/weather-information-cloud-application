import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone, timedelta
from .config import REGIONS_DATA, get_prefecture_from_kishodai, LAST_MODIFIED_TIMES, HIGH_FREQUENCY_INTERVAL, LONG_FREQUENCY_INTERVAL, DOWNLOAD_LIMIT_THRESHOLD
from .database import execute_sql
import logging
import os
import feedparser

# ルートロガーの設定
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

ALL_PREFECTURES = [pref for data in REGIONS_DATA.values() for pref in data.get("prefectures", [])]

# ダウンロード制限値（10GB）
DOWNLOAD_LIMIT = 10 * 1024 * 1024 * 1024  # 10GB
# 現在の消費量（グローバルで管理。実際は永続ストレージやRedisなどの外部キャッシュにするのが望ましい）
downloaded_bytes = 0
# 最後にバケットをリセットした時刻。毎日リセットできる仕組みを別途実装する
bucket_reset_time = datetime.now(timezone.utc)

def reset_bucket_if_needed():
    global downloaded_bytes, bucket_reset_time
    now = datetime.now(timezone.utc)
    # 例として、毎日0時にリセットするとする。ここでは簡易的に24時間経過したか判断
    if now - bucket_reset_time >= timedelta(days=1):
        downloaded_bytes = 0
        bucket_reset_time = now
        logger.info("Download bucket reset.")

def can_download(additional: int) -> bool:
    reset_bucket_if_needed()
    return (downloaded_bytes + additional) <= DOWNLOAD_LIMIT

def fetch_rss_feed(url: str, last_modified: Optional[datetime] = None) -> Optional[requests.Response]:
    """
    指定されたURLからRSSフィードを取得する。
    If-Modified-Since ヘッダーを活用し、更新がない場合は None を返す。
    また、漏れバケツアルゴリズムを用いて1日10GBの制限を超えないようにする。
    """
    global downloaded_bytes
    headers = {}
    if last_modified:
        headers['If-Modified-Since'] = last_modified.strftime('%a, %d %b %Y %H:%M:%S GMT')

    try:
        # まず、試しにヘッドリクエストでContent-Lengthを見て
        head_response = requests.head(url, headers=headers, timeout=10)
        content_length = int(head_response.headers.get('Content-Length', 0))
        if not can_download(content_length):
            logger.error("Download limit exceeded. Skipping request.")
            return None

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        if response.status_code == 304:
            return None

        # レスポンスのバイトサイズを確認し、ダウンロード可能か再チェック
        response_size = len(response.content)
        if not can_download(response_size):
            logger.error("Download limit exceeded after fetching response. Discarding response.")
            return None

        downloaded_bytes += response_size
        logger.info(f"Downloaded: {response_size} bytes, Total: {downloaded_bytes} bytes")

        # レスポンスのエンコーディングが None の場合、'utf-8' を仮定
        if response.encoding is None:
            response.encoding = 'utf-8'

        return response

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching RSS feed: {e}")
        return None

def extract_prefecture_from_content(content: str) -> List[str]:
    """<content> から都道府県名を抽出 (複数対応)"""
    prefectures_found = []
    if not content:
        return prefectures_found

    for pref in ALL_PREFECTURES:
        if pref in content:
            prefectures_found.append(pref)
    return prefectures_found

def parse_detail_xml(url:str) -> tuple[List[str],Optional[str]]:
    """詳細XMLをパースして都道府県情報と発表官署を取得(都道府県は複数)"""
    global downloaded_bytes
    if downloaded_bytes > DOWNLOAD_LIMIT * DOWNLOAD_LIMIT_THRESHOLD: # 80%を超えたら詳細XMLのダウンロードを控える
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

def parse_rss_feed(response: requests.Response) -> Tuple[List[Dict], Optional[str], Optional[str], Optional[str], Optional[str],Optional[str]]:
    """
    RSSフィードのレスポンスをパースし、必要な情報を抽出する。
    """
    try:
        # feedparser を使ってパース
        feed = feedparser.parse(response.text)

        if feed.bozo:
            logger.warning(f"Feed parsing error: {feed.bozo_exception}")

        entries = []

        for item in feed.entries:
            # content から都道府県を抽出
            prefectures = extract_prefecture_from_content(item.get('content', [{}])[0].get('value', ''))

            # content から抽出できない場合、author から都道府県を特定
            author_name = item.get('author_detail', {}).get('name')
            if not prefectures and author_name:
                prefectures = get_prefecture_from_kishodai(author_name)

            # contentからもauthorからも特定できない場合のみ、詳細XMLをパース
            detail_prefectures = []
            detail_publishing_office = None # 初期化
            if not prefectures:
                detail_prefectures, detail_publishing_office = parse_detail_xml(item.get('id')) if item.get('id') else ([], None)
                if detail_prefectures: #詳細XMLで取得成功
                    prefectures = detail_prefectures

            publishing_office = author_name if author_name else detail_publishing_office

            entry = {
                'title': item.get('title'),
                'link': item.get('link'),
                'updated': item.get('updated'),
                'publishing_office': publishing_office,
                'content': item.get('content', [{}])[0].get('value', ''),
                'id': item.get('id'),
                'prefectures': prefectures
            }
            entries.append(entry)

        feed_title = feed.feed.get('title')
        feed_subtitle = feed.feed.get('subtitle')
        feed_updated = feed.feed.get('updated')
        feed_id_in_atom = feed.feed.get('id')
        rights = feed.feed.get('rights')

        return entries, feed_title, feed_subtitle, feed_updated, feed_id_in_atom, rights

    except Exception as e:
        logger.exception(f"Error parsing RSS feed: {e}")
        return [], None, None, None, None, None

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
        prefectures_in_region =  REGIONS_DATA.get(region, {}).get("prefectures", [])
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

def insert_or_update_feed_data(parsed_feed_data: Tuple[List[Dict], Optional[str], Optional[str], Optional[str], Optional[str],Optional[str]], feed_type: str, url: str, category: str, frequency_type: str):
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
    """, (url, feed_title, feed_subtitle, feed_updated_dt, feed_id_in_atom, rights, category, frequency_type, datetime.now(timezone.utc)), fetchone=True)['id']

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

def fetch_and_store_feed_data(feed_type: str, url: str, category: str, frequency_type: str):
    """
    指定されたフィードを取得し、DBに保存する。
    スロットリングも考慮する。
    """
    logger.info(f"Fetching feed: {url}")

    # ダウンロード制限に近づいている場合は、低頻度のフィードをスキップ
    if downloaded_bytes > DOWNLOAD_LIMIT * DOWNLOAD_LIMIT_THRESHOLD and frequency_type == "低頻度":
        logger.info(f"Skipping low frequency feed due to download limit: {feed_type}")
        return False

    interval = HIGH_FREQUENCY_INTERVAL if frequency_type == "高頻度" else LONG_FREQUENCY_INTERVAL

    if should_throttle(url, interval):
        logger.info(f"Throttling request for feed type: {feed_type}, url: {url}")
        return False

    response = fetch_rss_feed(url, LAST_MODIFIED_TIMES.get(feed_type))

    if response is None:
        logger.info(f"No update for feed type: {feed_type}")
        return False

    parsed_feed_data = parse_rss_feed(response)

    last_modified_str = response.headers.get('Last-Modified')
    if last_modified_str:
        try:
            LAST_MODIFIED_TIMES[feed_type] = datetime.strptime(last_modified_str, '%a, %d %b %Y %H:%M:%S %Z')
        except ValueError:
             logger.warning(f"Invalid date format in Last-Modified header: {last_modified_str}")


    if parsed_feed_data:
      insert_or_update_feed_data(parsed_feed_data, feed_type, url, category, frequency_type)
      logger.info(f"Successfully fetched and stored data for feed type: {feed_type}, url: {url}")
      return True
    else:
        logger.error(f"Failed to parse feed data for feed type: {feed_type}, url:{url}")
        return False

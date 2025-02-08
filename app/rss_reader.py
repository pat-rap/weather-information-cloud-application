import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
import xml.etree.ElementTree as ET
import re

import logging
# ルートロガーの設定
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def fetch_rss_feed(url: str, last_modified: Optional[datetime] = None) -> Optional[requests.Response]:
    """
    指定されたURLからRSSフィードを取得する。
    If-Modified-Since ヘッダーを活用し、更新がない場合は None を返す。
    """
    headers = {}
    if last_modified:
        headers['If-Modified-Since'] = last_modified.strftime('%a, %d %b %Y %H:%M:%S GMT')

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        if response.status_code == 304:
            return None

        return response

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching RSS feed: {e}")
        return None

def extract_prefecture_from_content(content: str) -> List[str]:
    """<content> から都道府県名を抽出 (複数対応)"""
    prefectures_found = []
    if not content:
        return prefectures_found

    prefectures = ["北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県", "茨城県", "栃木県", "群馬県",
                   "埼玉県", "千葉県", "東京都", "神奈川県", "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
                   "岐阜県", "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
                   "鳥取県", "島根県", "岡山県", "広島県", "山口県", "徳島県", "香川県", "愛媛県", "高知県", "福岡県",
                   "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"]
    for pref in prefectures:
        if pref in content:
            prefectures_found.append(pref)
    return prefectures_found

def parse_detail_xml(url:str) -> tuple[List[str],Optional[str]]:
    """詳細XMLをパースして都道府県情報と発表官署を取得(都道府県は複数)"""
    response = fetch_rss_feed(url)
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

def get_prefecture_from_kishodai(kishodai_name: str) -> List[str]:
    """気象台名から都道府県名を推測(複数県対応)"""
    prefectures = []
    if not kishodai_name:
        return prefectures

    mapping = {
        "稚内地方気象台": ["北海道"],
        "旭川地方気象台": ["北海道"],
        "札幌管区気象台": ["北海道"],
        "網走地方気象台": ["北海道"],
        "釧路地方気象台": ["北海道"],
        "帯広測候所": ["北海道"],
        "室蘭地方気象台": ["北海道"],
        "函館地方気象台": ["北海道"],
        "青森地方気象台": ["青森県"],
        "秋田地方気象台": ["秋田県"],
        "盛岡地方気象台": ["岩手県"],
        "仙台管区気象台": ["宮城県"],
        "山形地方気象台": ["山形県"],
        "福島地方気象台": ["福島県"],
        "水戸地方気象台": ["茨城県"],
        "宇都宮地方気象台": ["栃木県"],
        "前橋地方気象台": ["群馬県"],
        "熊谷地方気象台": ["埼玉県"],
        "東京管区気象台": ["東京都"],
        "銚子地方気象台": ["千葉県"],
        "横浜地方気象台": ["神奈川県"],
        "長野地方気象台": ["長野県"],
        "甲府地方気象台": ["山梨県"],
        "静岡地方気象台": ["静岡県"],
        "名古屋地方気象台": ["愛知県"],
        "岐阜地方気象台": ["岐阜県"],
        "津地方気象台": ["三重県"],
        "新潟地方気象台": ["新潟県"],
        "富山地方気象台": ["富山県"],
        "金沢地方気象台": ["石川県"],
        "福井地方気象台": ["福井県"],
        "彦根地方気象台": ["滋賀県"],
        "京都地方気象台": ["京都府"],
        "大阪管区気象台": ["大阪府"],
        "神戸地方気象台": ["兵庫県"],
        "奈良地方気象台": ["奈良県"],
        "和歌山地方気象台": ["和歌山県"],
        "岡山地方気象台": ["岡山県"],
        "広島地方気象台": ["広島県"],
        "松江地方気象台": ["島根県"],
        "鳥取地方気象台": ["鳥取県"],
        "徳島地方気象台": ["徳島県"],
        "高松地方気象台": ["香川県"],
        "松山地方気象台": ["愛媛県"],
        "高知地方気象台": ["高知県"],
        "下関地方気象台": ["山口県"],
        "福岡管区気象台": ["福岡県", "山口県"], #複数県
        "大分地方気象台": ["大分県"],
        "長崎地方気象台": ["長崎県"],
        "佐賀地方気象台": ["佐賀県"],
        "熊本地方気象台": ["熊本県"],
        "宮崎地方気象台": ["宮崎県"],
        "鹿児島地方気象台": ["鹿児島県"],
        "名瀬測候所": ["鹿児島県"],
        "沖縄気象台": ["沖縄県"],
        "南大東島地方気象台": ["沖縄県"],
        "宮古島地方気象台": ["沖縄県"],
        "石垣島地方気象台": ["沖縄県"],
        "新千歳航空測候所": ["北海道"],
        "成田航空地方気象台": ["千葉県"],
        "東京航空地方気象台": ["東京都"],
        "中部航空地方気象台": ["愛知県"],
        "関西航空地方気象台": ["大阪府"],
        "福岡航空地方気象台": ["福岡県"],
        "那覇航空測候所": ["沖縄県"],
    }
    return mapping.get(kishodai_name, []) # 見つからない場合は空リスト

def parse_rss_feed(response: requests.Response) -> List[Dict]:
    """
    RSSフィードのレスポンスをパースし、必要な情報を抽出する。
    """
    try:
        soup = BeautifulSoup(response.content, 'xml')
        entries = []

        for item in soup.find_all('entry'):
            logger.debug(f"parse_rss_feed item: {item}")

            author_name = item.find('author').find('name').text if item.find('author') and item.find('author').find('name') else None

            detail_prefectures, detail_publishing_office = parse_detail_xml(item.id.text) if item.id else ([], None)

            # 都道府県情報の取得 (優先順位: 詳細XML > content > author)
            prefectures = detail_prefectures
            if not prefectures:
                prefectures = extract_prefecture_from_content(item.find('content').text if item.find('content') else None)
            if not prefectures and author_name:
                prefectures = get_prefecture_from_kishodai(author_name)

            publishing_office = author_name
            if publishing_office is None:
                publishing_office = detail_publishing_office

            entry = {
                'title': item.title.text if item.title else None,
                'link': item.link.text if item.link else None,
                'updated': item.updated.text if item.updated else (item.pubDate.text if item.pubDate else None),
                'publishing_office': publishing_office,
                'content': item.find('content').text if item.find('content') else None,
                'id': item.id.text if item.id else None,
                'prefectures': prefectures # 都道府県 (複数)
            }
            logger.debug(f"parse_rss_feed entry: {entry}")
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

# config.py (新規作成)

import os

LAST_MODIFIED_TIMES = { "extra": None, "eqvol": None, "other": None, }

# ダウンロード制限値（10GB）
DOWNLOAD_LIMIT = 10 * 1024 * 1024 * 1024  # 10GB

# 定期取得の基本間隔（秒）
PERIODIC_FETCH_INTERVAL = int(os.environ.get("PERIODIC_FETCH_INTERVAL", "300").split()[0])

# 高頻度フィードと長期フィードの間隔（PERIODIC_FETCH_INTERVAL に対する倍率）
HIGH_FREQUENCY_MULTIPLIER = 1
LONG_FREQUENCY_MULTIPLIER = 60

# 環境変数からの読み込みを削除し、計算値を使用
HIGH_FREQUENCY_INTERVAL = int(PERIODIC_FETCH_INTERVAL * HIGH_FREQUENCY_MULTIPLIER)
LONG_FREQUENCY_INTERVAL = int(PERIODIC_FETCH_INTERVAL * LONG_FREQUENCY_MULTIPLIER)

# ダウンロード制限の閾値（環境変数から取得、デフォルトは80%）
DOWNLOAD_LIMIT_THRESHOLD = float(os.environ.get("DOWNLOAD_LIMIT_THRESHOLD", "0.8"))

FEED_INFO = {
    "extra": {"url": "https://www.data.jma.go.jp/developer/xml/feed/extra.xml", "category": "警報・注意報", "frequency_type": "高頻度"},
    "eqvol": {"url": "https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml", "category": "地震・火山", "frequency_type": "高頻度"},
    "other": {"url": "https://www.data.jma.go.jp/developer/xml/feed/other.xml", "category": "その他", "frequency_type": "高頻度"},
    "extra_l": {"url": "https://www.data.jma.go.jp/developer/xml/feed/extra_l.xml", "category": "警報・注意報", "frequency_type": "低頻度"},
    "eqvol_l": {"url": "https://www.data.jma.go.jp/developer/xml/feed/eqvol_l.xml", "category": "地震・火山", "frequency_type": "低頻度"},
    "other_l": {"url": "https://www.data.jma.go.jp/developer/xml/feed/other_l.xml", "category": "その他", "frequency_type": "低頻度"},}

REGIONS_DATA = {
    "北海道": {
        "prefectures": ["宗谷地方", "上川・留萌地方", "石狩・空知・後志地方", "網走・北見・紋別地方", "釧路・根室地方", "十勝地方", "胆振・日高地方", "渡島・檜山地方"],
        "offices": {
            "稚内地方気象台": ["宗谷地方"],
            "旭川地方気象台": ["上川・留萌地方"],
            "札幌管区気象台": ["石狩・空知・後志地方"],
            "網走地方気象台": ["網走・北見・紋別地方"],
            "釧路地方気象台": ["釧路・根室地方"],
            "帯広測候所": ["十勝地方"],
            "室蘭地方気象台": ["胆振・日高地方"],
            "函館地方気象台": ["渡島・檜山地方"],
        }
    }, 
    "東北": {
        "prefectures": ["青森県", "秋田県", "岩手県", "宮城県", "山形県", "福島県"],
        "offices": {
            "青森地方気象台": ["青森県"],
            "秋田地方気象台": ["秋田県"],
            "盛岡地方気象台": ["岩手県"],
            "仙台管区気象台": ["宮城県"],
            "山形地方気象台": ["山形県"],
            "福島地方気象台": ["福島県"],
        }
    },
    "関東甲信": {
        "prefectures": ["茨城県", "栃木県", "群馬県", "埼玉県", "東京都", "千葉県", "神奈川県", "長野県", "山梨県"],
        "offices": {
            "水戸地方気象台": ["茨城県"],
            "宇都宮地方気象台": ["栃木県"],
            "前橋地方気象台": ["群馬県"],
            "熊谷地方気象台": ["埼玉県"],
            "東京管区気象台": ["東京都"],
            "銚子地方気象台": ["千葉県"],
            "横浜地方気象台": ["神奈川県"],
            "長野地方気象台": ["長野県"],
            "甲府地方気象台": ["山梨県"],
        }
    },
    "東海": {
        "prefectures": ["静岡県", "愛知県", "岐阜県", "三重県"],
        "offices": {
            "静岡地方気象台": ["静岡県"],
            "名古屋地方気象台": ["愛知県"],
            "岐阜地方気象台": ["岐阜県"],
            "津地方気象台": ["三重県"],
        }
    },
    "北陸": {
        "prefectures": ["新潟県", "富山県", "石川県", "福井県"],
        "offices": {
            "新潟地方気象台": ["新潟県"],
            "富山地方気象台": ["富山県"],
            "金沢地方気象台": ["石川県"],
            "福井地方気象台": ["福井県"],
        }
    },
    "近畿": {
        "prefectures": ["滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県"],
        "offices": {
            "彦根地方気象台": ["滋賀県"],
            "京都地方気象台": ["京都府"],
            "大阪管区気象台": ["大阪府"],
            "神戸地方気象台": ["兵庫県"],
            "奈良地方気象台": ["奈良県"],
            "和歌山地方気象台": ["和歌山県"],
        }
    },
    "中国": {
        "prefectures": ["岡山県", "広島県", "島根県", "鳥取県", "山口県"],
        "offices": {
            "岡山地方気象台": ["岡山県"],
            "広島地方気象台": ["広島県"],
            "松江地方気象台": ["島根県"],
            "鳥取地方気象台": ["鳥取県"],
            "下関地方気象台": ["山口県"],
        }
    },
    "四国": {
        "prefectures": ["徳島県", "香川県", "愛媛県", "高知県"],
        "offices": {
            "徳島地方気象台": ["徳島県"],
            "高松地方気象台": ["香川県"],
            "松山地方気象台": ["愛媛県"],
            "高知地方気象台": ["高知県"],
        }
    },
    "九州": {
        "prefectures": ["福岡県", "大分県", "長崎県", "佐賀県", "熊本県", "宮崎県", "鹿児島県", "奄美地方"],
        "offices": {
            "福岡管区気象台": ["福岡県"],
            "大分地方気象台": ["大分県"],
            "長崎地方気象台": ["長崎県"],
            "佐賀地方気象台": ["佐賀県"],
            "熊本地方気象台": ["熊本県"],
            "宮崎地方気象台": ["宮崎県"],
            "鹿児島地方気象台": ["鹿児島県"],
            "名瀬測候所": ["奄美地方"],
        }
    },
    "沖縄": {
        "prefectures": ["沖縄本島地方", "大東島地方", "宮古島地方", "八重山地方"],
        "offices": {
            "沖縄気象台": ["沖縄本島"],
            "南大東島地方気象台": ["大東島地方"],
            "宮古島地方気象台": ["宮古島地方"],
            "石垣島地方気象台": ["八重山地方"],
        }
    }
}

def get_prefecture_from_kishodai(kishodai_name: str) -> list[str]:
    """気象台名から都道府県名を推測(複数県対応)"""
    for region in REGIONS_DATA.values():
        offices = region.get("offices", {})
        if kishodai_name in offices:
            return offices[kishodai_name]
    return []

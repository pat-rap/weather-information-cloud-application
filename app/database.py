import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
import os, logging
from datetime import datetime, timedelta # 追加

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

def get_db_connection():
    # 環境変数 DATABASE_URL が設定されている場合 (ローカル開発時) はそれを使用
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        conn = psycopg.connect(database_url)
        return conn

    # 環境変数 DATABASE_URL が設定されていない場合 (Cloud Run) は、Cloud Run 組み込みの Cloud SQL 接続を使用
    DB_USER = os.environ.get("DB_USER")
    DB_PASS = os.environ.get("DB_PASS")
    DB_NAME = os.environ.get("DB_NAME")
    # INSTANCE_CONNECTION_NAME は環境変数から取得しない
    # Cloud Run 組み込みの Cloud SQL 接続を使用する場合の接続文字列
    conn_string = f"postgresql://{DB_USER}:{DB_PASS}@{DB_NAME}?host=/cloudsql/{os.environ.get('CLOUD_SQL_CONNECTION_NAME')}"
    conn = psycopg.connect(conn_string)
    return conn
    
def execute_sql(sql: str, params=None, fetchone=False, fetchall=False):
    conn = None  # 初期化
    try:
        conn = get_db_connection()
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            if fetchone:
                result = cur.fetchone()
            elif fetchall:
                result = cur.fetchall()
            else:
                result = None
            conn.commit()
        return result
    except psycopg.OperationalError as e:
        logger.error(f"Database connection error: {e}")
        raise
    except psycopg.Error as e:
        logger.error(f"Database query error: {e}")
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        logger.exception(f"Unexpected database error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

def init_db():
    """db.sqlを実行してテーブルを初期化する"""
    try:
        with open("db.sql", "r", encoding="utf-8") as f:
            sql = f.read()
        execute_sql(sql)
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}")

def delete_old_entries(days: int = 7): # 追加
    """指定された日数以上前のエントリを削除する"""
    try:
        cutoff_date = datetime.now() - timedelta(days=days)
        execute_sql("DELETE FROM feed_entries WHERE inserted_at < %s", (cutoff_date,))
        print(f"{days}日以上前のエントリを削除しました。")
    except Exception as e:
        print(f"Error deleting old entries: {e}")

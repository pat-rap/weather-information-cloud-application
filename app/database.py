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

    # Cloud Run + Cloud SQL用
    cloud_sql_connection_name = os.environ["CLOUD_SQL_CONNECTION_NAME"]
    db_socket_dir = "/cloudsql"
    db_host = f"{db_socket_dir}/{cloud_sql_connection_name}"  # Unixソケットを指定
    db_user = os.environ["DB_USER"]
    db_pass = os.environ["DB_PASS"]
    db_name = os.environ["DB_NAME"]

    conn = psycopg.connect(
        host=db_host,
        user=db_user,
        password=db_pass,
        dbname=db_name
    )
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

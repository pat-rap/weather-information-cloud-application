import psycopg2
from psycopg2.extras import DictCursor
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def execute_sql(sql: str, params=None, fetchone=False, fetchall=False):
    conn = None  # 初期化
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(sql, params)
            if fetchone:
                result = cur.fetchone()
            elif fetchall:
                result = cur.fetchall()
            else:
                result = None
            conn.commit()
        return result
    except Exception as e:
        print(f"Database error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def init_db():
    """db.sqlを実行してテーブルを初期化する"""
    try:
        with open("db.sql", "r", encoding="utf-8") as f:  # encoding="utf-8" を追加
            sql = f.read()
        execute_sql(sql)
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}")


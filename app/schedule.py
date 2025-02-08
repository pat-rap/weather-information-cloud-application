import schedule
import time
import requests

def job():
    # FastAPIのエンドポイントを叩く
    try:
        response = requests.get("http://localhost:8000/delete_old_entries") # FastAPI が起動している URL
        response.raise_for_status()
        print("Successfully triggered /delete_old_entries")
    except requests.exceptions.RequestException as e:
        print(f"Error triggering /delete_old_entries: {e}")

# 毎日午前3時に実行
schedule.every().day.at("03:00").do(job)

while True:
    schedule.run_pending()
    time.sleep(60) # 60秒ごとに確認

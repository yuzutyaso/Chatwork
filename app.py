import os
import json
import logging
from flask import Flask, request, jsonify
from handlers import handle_webhook_event
from services import (
    post_all_room_ranking_daily,
    get_supabase_client,
    send_message
)
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta, timezone

# Initialize Flask app
app = Flask(__name__)
# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 環境変数から設定を取得 ---
CHATWORK_WEBHOOK_TOKEN = os.environ.get("CHATWORK_WEBHOOK_TOKEN")
MY_ACCOUNT_ID = os.environ.get("MY_ACCOUNT_ID")

# --- 定期実行スケジューラの初期化 ---
scheduler = BackgroundScheduler(daemon=True, timezone='Asia/Tokyo')

# --- SupabaseクライアントとSchedulerの起動 ---
def initialize_services():
    """Initializes Supabase client and schedules jobs."""
    get_supabase_client()
    
    # スケジュールされたジョブをここに追加
    scheduler.add_job(
        post_all_room_ranking_daily,
        CronTrigger(hour=8, minute=0, timezone='Asia/Tokyo'),
        id="daily_ranking_job"
    )
    
    scheduler.start()

# --- ウェブフックエンドポイント ---
@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Handles incoming Chatwork webhook events.
    Verifies the webhook token and processes the event.
    """
    try:
        data = request.json
        event_type = data.get("webhook_event_type")
        token = request.headers.get("X-ChatWorkWebhookToken")
        
        # ウェブフックトークンの検証
        if token != CHATWORK_WEBHOOK_TOKEN:
            logger.warning("Invalid webhook token received.")
            return jsonify({"status": "error", "message": "Invalid token"}), 403

        # 送信元がボット自身ではないか確認
        if str(data.get("webhook_event", {}).get("account_id")) == str(MY_ACCOUNT_ID):
            logger.info("Ignoring webhook event from bot's own account.")
            return jsonify({"status": "ok", "message": "Ignored self-event"}), 200

        # メッセージイベントの処理
        if event_type == "message_created":
            handle_webhook_event(data)
            return jsonify({"status": "ok"})
        else:
            logger.info(f"Received unknown webhook event type: {event_type}")
            return jsonify({"status": "ok", "message": "Unknown event type"}), 200

    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ルートパスの定義（ヘルスチェック用）---
@app.route('/')
def home():
    """
    A simple home route to check if the application is running.
    """
    return "Chatwork Bot is running!"

# --- アプリケーション起動時の処理 ---
if __name__ == '__main__':
    initialize_services()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

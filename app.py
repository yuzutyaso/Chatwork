import os
import logging
from flask import Flask, request
from handlers import handle_webhook_event
from utils import send_message, mark_room_as_read

# --- ロガー設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- 設定と初期化 ---
CHATWORK_API_TOKEN = os.environ.get("CHATWORK_API_TOKEN")
MY_ACCOUNT_ID = os.environ.get("MY_ACCOUNT_ID")

if not CHATWORK_API_TOKEN:
    logger.error("CHATWORK_API_TOKEN is not set.")
if not MY_ACCOUNT_ID:
    logger.error("MY_ACCOUNT_ID is not set.")

@app.route("/", methods=["POST"])
def chatwork_webhook():
    """Main webhook handler."""
    try:
        data = request.json
        webhook_event = data.get("webhook_event")
        
        if not webhook_event:
            logger.info("Received a non-webhook event. Ignoring.")
            return "", 200

        room_id = webhook_event.get("room_id")
        account_id = webhook_event.get("account_id")
        
        # Ignore messages from the bot itself.
        if str(account_id) == str(MY_ACCOUNT_ID):
            logger.info("Ignoring webhook event from myself.")
            return "", 200

        # Mark all messages in the room as read.
        mark_room_as_read(room_id)
        
        # Handle the webhook event.
        handle_webhook_event(webhook_event)

    except Exception as e:
        logger.error(f"An unexpected error occurred in app.py: {e}")
        # In case of an error, send a message to the room if possible.
        if 'room_id' in locals() and 'account_id' in locals() and 'message_id' in locals():
            send_message(room_id, "処理中にエラーが発生しました。", reply_to_id=account_id, reply_message_id=message_id)

    return "", 200

if __name__ == "__main__":
    app.run()

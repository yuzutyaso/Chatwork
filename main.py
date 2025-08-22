import os
import json
import logging
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from commands.main_commands import test_command, sorry_command, roominfo_command, say_command, weather_command, whoami_command, echo_command, timer_command, time_report_command, delete_command, omikuji_command, ranking_command, quote_command, news_command, info_command
from commands.utility_commands import wiki_command, coin_command, translate_command, reminder_command
from commands.admin_commands import log_command, stats_command, recount_command

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

COMMANDS = {
    "/test": test_command,
    "/sorry": sorry_command,
    "/roominfo": roominfo_command,
    "/say": say_command,
    "/weather": weather_command,
    "/whoami": whoami_command,
    "/echo": echo_command,
    "/timer": timer_command,
    "/時報": time_report_command,
    "/削除": delete_command,
    "/quote": quote_command,
    "おみくじ": omikuji_command,
    "/ranking": ranking_command,
    "/recount": recount_command,
    "/news": news_command,
    "/info": info_command,
    "/wiki": wiki_command,
    "/coin": coin_command,
    "/translate": translate_command,
    "/reminder": reminder_command,
    "/log": log_command,
    "/stats": stats_command,
}

@app.route("/", methods=["POST"])
@app.route("/callback", methods=["POST"])
def event_handler():
    """
    ChatWork WebhookからのPOSTリクエストを処理するエンドポイント
    """
    try:
        data = request.json
        if not data:
            return jsonify({"status": "no data"}), 400

        event_type = data.get("webhook_event_type")
        
        # message_created イベントのみを処理
        if event_type != "message_created":
            logging.info(f"Ignoring event type: {event_type}")
            return jsonify({"status": "ignored"}), 200

        message_body = data.get("body")
        room_id = data.get("room_id")
        message_id = data.get("chatwork_message_id")
        account_id = data.get("from_account_id")
        
        # message_body が存在しない場合は処理を終了
        if not message_body:
            logging.warning("Received a message_created event with no message body.")
            return jsonify({"status": "no message body"}), 200

        logging.info(f"Received message: {message_body} from room: {room_id}")

        first_word = message_body.strip().split()[0].lower() if message_body.strip() else ""

        if first_word in COMMANDS:
            COMMANDS[first_word](room_id, message_id, account_id, message_body)
            logging.info(f"Command '{first_word}' executed.")
        else:
            logging.info(f"No command found for: {message_body}")

        return jsonify({"status": "success"}), 200

    except Exception as e:
        logging.error(f"Error processing webhook event: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

import os
import json
import logging
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# 新しいファイル構造から各コマンドをインポート
# 「.commands.main_commands」のようにドットで始まる相対インポートを使用します。
from commands.main_commands import COMMANDS as main_commands
from commands.utility_commands import COMMANDS as utility_commands
from commands.admin_commands import COMMANDS as admin_commands

# 環境変数をロード
load_dotenv()

# ロガー設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Flaskアプリケーションの初期化
app = Flask(__name__)

# 全てのコマンドを一つの辞書にまとめる
COMMANDS = {}
COMMANDS.update(main_commands)
COMMANDS.update(utility_commands)
COMMANDS.update(admin_commands)


@app.route("/", methods=["POST"])
def event_handler():
    """
    ChatWork WebhookからのPOSTリクエストを処理するエンドポイント
    """
    try:
        data = request.json
        if not data:
            return jsonify({"status": "no data"}), 400

        # ChatWork Webhookのデータ構造から必要な情報を抽出
        event_type = data.get("webhook_event_type")
        message_id = data.get("chatwork_message_id")
        room_id = data.get("room_id")
        account_id = data.get("from_account_id")
        message_body = data.get("body")

        # Webhookの種類を検証
        if event_type != "message_created":
            return jsonify({"status": "not message_created event"}), 200

        logging.info(f"Received message: {message_body} from room: {room_id}")

        # メッセージがコマンドかどうかをチェック
        # 大文字小文字を区別せず、先頭のスペースを無視してコマンドを識別
        command = message_body.split()[0].lower()
        
        # コマンドの実行
        if command in COMMANDS:
            COMMANDS[command](room_id, message_id, account_id, message_body)
            logging.info(f"Command '{command}' executed.")
        else:
            logging.info(f"No command found for: {message_body}")

        return jsonify({"status": "success"}), 200

    except Exception as e:
        logging.error(f"Error processing webhook event: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

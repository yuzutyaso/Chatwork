import os
import json
from datetime import datetime
from flask import Flask, request
import requests

app = Flask(__name__)

# Chatwork APIトークンと自分のアカウントIDを環境変数から取得
CHATWORK_API_TOKEN = os.environ.get("CHATWORK_API_TOKEN")
MY_ACCOUNT_ID = os.environ.get("MY_ACCOUNT_ID") # Chatworkの自分のID

@app.route("/", methods=["POST"])
def chatwork_webhook():
    try:
        data = request.jsonimport os
import json
from datetime import datetime
from flask import Flask, request
import requests

app = Flask(__name__)

# Chatwork APIトークンと自分のアカウントIDを環境変数から取得
CHATWORK_API_TOKEN = os.environ.get("CHATWORK_API_TOKEN")
MY_ACCOUNT_ID = os.environ.get("MY_ACCOUNT_ID")

# --- 起動時のログ ---
print("Bot service is starting...")

@app.route("/", methods=["POST"])
def chatwork_webhook():
    # --- リクエスト受信時のログ ---
    print(f"[{datetime.now().isoformat()}] Received a new webhook request.")
    try:
        data = request.json
        webhook_data = data.get("webhook_event")
        message_body = webhook_data.get("body")
        account_id = webhook_data.get("account_id")
        room_id = webhook_data.get("room_id")
        
        # --- 受信メッセージの詳細ログ ---
        print(f"Message received from Account ID: {account_id}, Room ID: {room_id}")
        print(f"Message body: '{message_body}'")
        
        # メッセージが "test" で、自分宛てではないことを確認
        if "test" in message_body and str(account_id) != MY_ACCOUNT_ID:
            now = datetime.now()
            current_time = now.strftime("%Y/%m/%d %H:%M:%S")
            
            # 返信メッセージを送信
            headers = {
                "X-ChatWorkToken": CHATWORK_API_TOKEN,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            payload = {
                "body": f"現在の時刻は {current_time} です。"
            }
            requests.post(f"https://api.chatwork.com/v2/rooms/{room_id}/messages", headers=headers, data=payload)
            
            # --- 返信メッセージ送信時のログ ---
            print("Response sent successfully.")

    except Exception as e:
        # --- エラー発生時の詳細ログ ---
        print(f"[{datetime.now().isoformat()}] An error occurred: {e}")
        # リクエストデータ全体をログに出力するとデバッグに役立つ
        print(f"Received data was: {request.data}")

    # --- リクエスト処理完了時のログ ---
    print(f"[{datetime.now().isoformat()}] Request processing finished.")
    return "", 200

if __name__ == "__main__":
    app.run()
        webhook_data = data.get("webhook_event")
        message_body = webhook_data.get("body")
        room_id = webhook_data.get("room_id")
        
        # メッセージが "test" で、自分宛てではないことを確認
        if "test" in message_body and str(webhook_data.get("account_id")) != MY_ACCOUNT_ID:
            now = datetime.now()
            current_time = now.strftime("%Y/%m/%d %H:%M:%S")
            
            # 返信メッセージを送信
            headers = {
                "X-ChatWorkToken": CHATWORK_API_TOKEN,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            payload = {
                "body": f"現在の時刻は {current_time} です。"
            }
            requests.post(f"https://api.chatwork.com/v2/rooms/{room_id}/messages", headers=headers, data=payload)

    except Exception as e:
        print(f"Error: {e}")

    return "", 200

if __name__ == "__main__":
    app.run()

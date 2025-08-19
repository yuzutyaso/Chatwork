import os
import json
from datetime import datetime, timezone, timedelta
from flask import Flask, request
import requests

app = Flask(__name__)

# Chatwork APIトークンと自分のアカウントIDを環境変数から取得
CHATWORK_API_TOKEN = os.environ.get("CHATWORK_API_TOKEN")
MY_ACCOUNT_ID = os.environ.get("MY_ACCOUNT_ID")

# Bot service is starting...
print("Bot service is starting...")

@app.route("/", methods=["POST"])
def chatwork_webhook():
    print(f"[{datetime.now().isoformat()}] Received a new webhook request.")
    try:
        data = request.json
        webhook_data = data.get("webhook_event")
        message_body = webhook_data.get("body")
        account_id = webhook_data.get("account_id")
        room_id = webhook_data.get("room_id")
        
        print(f"Message received from Account ID: {account_id}, Room ID: {room_id}")
        print(f"Message body: '{message_body}'")
        
        # メッセージが "test" で、自分宛てではないことを確認
        if "test" in message_body and str(account_id) != MY_ACCOUNT_ID:
            # JST (UTC+9) のタイムゾーンを設定
            jst = timezone(timedelta(hours=9), 'JST')
            now_jst = datetime.now(jst)
            current_time = now_jst.strftime("%Y/%m/%d %H:%M:%S")
            
            # 返信メッセージを送信
            headers = {
                "X-ChatWorkToken": CHATWORK_API_TOKEN,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            payload = {
                "body": f"現在の時刻は {current_time} です。"
            }
            requests.post(f"https://api.chatwork.com/v2/rooms/{room_id}/messages", headers=headers, data=payload)
            
            print("Response sent successfully.")

    except Exception as e:
        print(f"[{datetime.now().isoformat()}] An error occurred: {e}")
        print(f"Received data was: {request.data}")

    print(f"[{datetime.now().isoformat()}] Request processing finished.")
    return "", 200

if __name__ == "__main__":
    app.run()

import os
import json
from datetime import datetime, timezone, timedelta
from flask import Flask, request
import requests
import random

app = Flask(__name__)

# Chatwork APIトークンと自分のアカウントIDを環境変数から取得
CHATWORK_API_TOKEN = os.environ.get("CHATWORK_API_TOKEN")
MY_ACCOUNT_ID = os.environ.get("MY_ACCOUNT_ID")

# Bot service is starting...
print("Bot service is starting...")

def send_message(room_id, message_body):
    """Chatworkにメッセージを送信する共通関数"""
    headers = {
        "X-ChatWorkToken": CHATWORK_API_TOKEN,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = {
        "body": message_body
    }
    requests.post(f"https://api.chatwork.com/v2/rooms/{room_id}/messages", headers=headers, data=payload)

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
        
        # 自分宛てではないことを確認
        if str(account_id) != MY_ACCOUNT_ID:
            # "test" が含まれていたら時刻を返す
            if "test" in message_body:
                jst = timezone(timedelta(hours=9), 'JST')
                now_jst = datetime.now(jst)
                current_time = now_jst.strftime("%Y/%m/%d %H:%M:%S")
                send_message(room_id, f"現在の時刻は {current_time} です。")
            
            # "omikuji" が含まれていたらおみくじを引く
            elif "omikuji" in message_body:
                omikuji_results = ["大吉🎉", "吉😊", "中吉🙂", "小吉😅", "末吉🤔", "凶😭"]
                # 各結果の確率（重み）を設定。合計が1になる必要はないが、相対的な比率が重要。
                # 例: 大吉の重みは5、凶は1。つまり大吉は凶の5倍出やすい
                omikuji_weights = [5, 4, 3, 2, 2, 1]
                
                # choices()メソッドを使って重み付きで選択
                result = random.choices(omikuji_results, weights=omikuji_weights, k=1)[0]
                send_message(room_id, f"おみくじの結果は **{result}** です。")

    except Exception as e:
        print(f"[{datetime.now().isoformat()}] An error occurred: {e}")
        print(f"Received data was: {request.data}")

    print(f"[{datetime.now().isoformat()}] Request processing finished.")
    return "", 200

if __name__ == "__main__":
    app.run()

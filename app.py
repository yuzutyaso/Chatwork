import os
import json
from datetime import datetime, timezone, timedelta
from flask import Flask, request
import requests
import random
import re

app = Flask(__name__)

# Chatwork APIトークンと自分のアカウントIDを環境変数から取得
CHATWORK_API_TOKEN = os.environ.get("CHATWORK_API_TOKEN")
MY_ACCOUNT_ID = os.environ.get("MY_ACCOUNT_ID")

# Bot service is starting...
print("Bot service is starting...")

def send_message(room_id, message_body, reply_to_id=None):
    """
    Chatworkにメッセージを送信する共通関数
    返信したいメッセージのIDをreply_to_idとして渡す
    """
    headers = {
        "X-ChatWorkToken": CHATWORK_API_TOKEN,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = {
        "body": message_body
    }
    
    # 返信IDが指定されていれば、ペイロードに追加
    if reply_to_id:
        payload["body"] = f"[rp aid={reply_to_id}] \n{message_body}"

    requests.post(f"https://api.chatwork.com/v2/rooms/{room_id}/messages", headers=headers, data=payload)
    print("Response sent successfully.")

def clean_message_body(body):
    """
    メッセージ本文からすべてのタグとそれに続く名前、余計な空白を削除する
    """
    # 正規表現パターンを定義
    # 返信タグ [rp aid=... to=...] を削除
    body = re.sub(r'\[rp aid=\d+ to=\d+-\d+\]', '', body)
    # Piconnameタグとそれに続く任意の文字（名前など）を削除
    # 例: [piconname:1234567]さん
    body = re.sub(r'\[piconname:\d+\].*?さん', '', body)
    # [To:...]タグを削除
    body = re.sub(r'\[To:\d+\]', '', body)
    
    # 前後の空白と改行をすべて削除して、純粋なメッセージ本文を抽出
    return body.strip()

@app.route("/", methods=["POST"])
def chatwork_webhook():
    print(f"[{datetime.now().isoformat()}] Received a new webhook request.")
    try:
        data = request.json
        webhook_event = data.get("webhook_event")
        message_body = webhook_event.get("body")
        account_id = webhook_event.get("account_id")
        room_id = webhook_event.get("room_id")
        message_id = webhook_event.get("message_id")
        
        # タグを削除したクリーンなメッセージ本文を取得
        cleaned_body = clean_message_body(message_body)
        
        print(f"Message received from Account ID: {account_id}, Room ID: {room_id}, Message ID: {message_id}")
        print(f"Cleaned message body: '{cleaned_body}'")
        
        # 自分宛てではないことを確認
        if str(account_id) != MY_ACCOUNT_ID:
            # "test" が含まれていたら時刻を返す
            if "test" in cleaned_body:
                jst = timezone(timedelta(hours=9), 'JST')
                now_jst = datetime.now(jst)
                current_time = now_jst.strftime("%Y/%m/%d %H:%M:%S")
                
                reply_message = f"現在の時刻は {current_time} です。"
                send_message(room_id, reply_message, reply_to_id=account_id)
            
            # "omikuji" が含まれていたらおみくじを引く
            elif "omikuji" in cleaned_body:
                omikuji_results = ["大吉🎉", "吉😊", "中吉🙂", "小吉😅", "末吉🤔", "凶😭"]
                omikuji_weights = [5, 4, 3, 2, 2, 1]
                
                result = random.choices(omikuji_results, weights=omikuji_weights, k=1)[0]
                
                reply_message = f"おみくじの結果は **{result}** です。"
                send_message(room_id, reply_message, reply_to_id=account_id)

    except Exception as e:
        print(f"[{datetime.now().isoformat()}] An error occurred: {e}")
        print(f"Received data was: {request.data}")

    print(f"[{datetime.now().isoformat()}] Request processing finished.")
    return "", 200

if __name__ == "__main__":
    app.run()

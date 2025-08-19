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

# Chatwork専用の絵文字パターン
EMOJI_PATTERN = re.compile(
    r":\)|:\(|:D|8-\)|:o|;\)|;\(|:\*|:p|:\^|\(sweat\)|\(inlove\)|\(blush\)|\(nod\)|\(shake\)|\(\^\^;\)|\(whew\)|\(clap\)|\(bow\)|\(roger\)|\(flex\)|\(dance\)|\(:/\)|(ec14)|(gogo)"
)

# Bot service is starting...
print("Bot service is starting...")

def send_message(room_id, message_body, reply_to_id=None, reply_message_id=None):
    """
    Chatworkにメッセージを送信する共通関数
    """
    headers = {
        "X-ChatWorkToken": CHATWORK_API_TOKEN,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = {
        "body": message_body
    }
    
    # 返信IDとメッセージIDが指定されていれば、ペイロードに追加
    if reply_to_id and reply_message_id:
        payload["body"] = f"[rp aid={reply_to_id} to={room_id}-{reply_message_id}]\n{message_body}"

    try:
        requests.post(f"https://api.chatwork.com/v2/rooms/{room_id}/messages", headers=headers, data=payload)
        print("Response sent successfully.")
    except Exception as e:
        print(f"Failed to send message: {e}")

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

def get_room_members(room_id):
    """
    指定されたルームのメンバーリストを取得する関数
    """
    headers = {
        "X-ChatWorkToken": CHATWORK_API_TOKEN
    }
    try:
        response = requests.get(f"https://api.chatwork.com/v2/rooms/{room_id}/members", headers=headers)
        response.raise_for_status() # HTTPエラーが発生した場合、例外を発生させる
        return response.json()
    except Exception as e:
        print(f"Failed to get room members: {e}")
        return None

def change_room_permissions(room_id, admin_ids, member_ids, readonly_ids):
    """
    ルームメンバーの権限を変更する関数
    admin_ids, member_ids, readonly_idsはaccount_idのリスト
    """
    headers = {
        "X-ChatWorkToken": CHATWORK_API_TOKEN,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = {
        "members_admin": ",".join(map(str, admin_ids)),
        "members_member": ",".join(map(str, member_ids)),
        "members_readonly": ",".join(map(str, readonly_ids))
    }
    
    try:
        response = requests.put(f"https://api.chatwork.com/v2/rooms/{room_id}/members", headers=headers, data=payload)
        response.raise_for_status()
        print("Room permissions changed successfully.")
        return True
    except Exception as e:
        print(f"Failed to change room permissions: {e}")
        return False

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
        
        print(f"Message received from Account ID: {account_id}, Room ID: {room_id}")
        print(f"Cleaned message body: '{cleaned_body}'")
        
        # 絵文字の数をカウント
        emoji_count = len(EMOJI_PATTERN.findall(message_body))
        print(f"Emoji count: {emoji_count}")

        # 自分宛てではないことを確認
        if str(account_id) != MY_ACCOUNT_ID:
            # 絵文字の数が15個以上の場合、権限を変更する
            if emoji_count >= 15:
                send_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}]\nメッセージに15個以上の絵文字が検出されたため、あなたの権限を『閲覧』に変更します。")
                
                # ルームメンバーを取得
                members = get_room_members(room_id)
                if members:
                    admin_ids = []
                    member_ids = []
                    readonly_ids = []
                    
                    # ユーザーをそれぞれの権限リストに分類
                    for member in members:
                        if str(member["account_id"]) == str(account_id):
                            # 絵文字を多く投稿したユーザーは閲覧権限に変更
                            readonly_ids.append(member["account_id"])
                        else:
                            # それ以外のユーザーはメンバー権限を維持
                            member_ids.append(member["account_id"])
                    
                    # 権限変更APIを呼び出す
                    if change_room_permissions(room_id, admin_ids, member_ids, readonly_ids):
                        send_message(room_id, "権限を更新しました。")
                    else:
                        send_message(room_id, "権限の変更に失敗しました。ボットに管理者権限があるか確認してください。")
            
            # "test" が含まれていたら時刻を返す
            elif "test" in cleaned_body:
                jst = timezone(timedelta(hours=9), 'JST')
                now_jst = datetime.now(jst)
                current_time = now_jst.strftime("%Y/%m/%d %H:%M:%S")
                
                reply_message = f"現在の時刻は {current_time} です。"
                send_message(room_id, reply_message, reply_to_id=account_id, reply_message_id=message_id)
            
            # "おみくじ" が含まれていたらおみくじを引く
            elif "おみくじ" in cleaned_body:
                omikuji_results = ["大吉🎉", "吉😊", "中吉🙂", "小吉😅", "末吉🤔", "凶😭"]
                omikuji_weights = [5, 4, 3, 2, 2, 1]
                
                result = random.choices(omikuji_results, weights=omikuji_weights, k=1)[0]
                
                reply_message = f"おみくじの結果は **{result}** です。"
                send_message(room_id, reply_message, reply_to_id=account_id, reply_message_id=message_id)

            # [toall] が含まれていたら、権限を変更する
            elif "[toall]" in message_body.lower():
                send_message(room_id, "ルームメンバーの権限を更新します。")
                
                # ルームメンバーを取得
                members = get_room_members(room_id)
                if members:
                    admin_ids = []
                    member_ids = []
                    readonly_ids = []
                    
                    # ユーザーをそれぞれの権限リストに分類
                    for member in members:
                        if str(member["account_id"]) == str(account_id):
                            # [toall]を送信したユーザーはそのままメンバー権限を維持
                            member_ids.append(member["account_id"])
                        else:
                            # それ以外のユーザーは閲覧権限に変更
                            readonly_ids.append(member["account_id"])
                    
                    # 権限変更APIを呼び出す
                    if change_room_permissions(room_id, admin_ids, member_ids, readonly_ids):
                        send_message(room_id, "メンバーの権限を『閲覧』に変更しました。")
                    else:
                        send_message(room_id, "権限の変更に失敗しました。ボットに管理者権限があるか確認してください。")

    except Exception as e:
        print(f"[{datetime.now().isoformat()}] An error occurred: {e}")
        print(f"Received data was: {request.data}")

    print(f"[{datetime.now().isoformat()}] Request processing finished.")
    return "", 200

if __name__ == "__main__":
    app.run()

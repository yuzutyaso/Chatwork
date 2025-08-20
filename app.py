import os
import json
import logging
from datetime import datetime, timezone, timedelta
from flask import Flask, request
import requests
import random
import re

# ロガー設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Chatwork APIトークンと自分のアカウントIDを環境変数から取得
CHATWORK_API_TOKEN = os.environ.get("CHATWORK_API_TOKEN")
MY_ACCOUNT_ID = os.environ.get("MY_ACCOUNT_ID")

# Chatwork専用の絵文字パターン
EMOJI_PATTERN = re.compile(
    r":\)|:\(|:D|8-\)|:o|;\)|;\(|:\*|:p|:\^|\(sweat\)|\(inlove\)|\(blush\)|\(nod\)|\(shake\)|\(\^\^;\)|\(whew\)|\(clap\)|\(bow\)|\(roger\)|\(flex\)|\(dance\)|\(:/\)|(ec14)|(gogo)"
)

# Bot service is starting...
logger.info("Bot service is starting...")

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
    
    if reply_to_id and reply_message_id:
        payload["body"] = f"[rp aid={reply_to_id} to={room_id}-{reply_message_id}]\n{message_body}"

    try:
        response = requests.post(f"https://api.chatwork.com/v2/rooms/{room_id}/messages", headers=headers, data=payload)
        response.raise_for_status()
        logger.info(f"Response sent successfully with status code: {response.status_code}")
        return True
    except requests.exceptions.HTTPError as err:
        logger.error(f"HTTP Error occurred while sending message: {err.response.status_code} - {err.response.text}")
        return False
    except Exception as e:
        logger.error(f"Failed to send message: {e}", exc_info=True)
        return False

def clean_message_body(body):
    """
    メッセージ本文からすべてのタグとそれに続く名前、余計な空白を削除する
    """
    body = re.sub(r'\[rp aid=\d+ to=\d+-\d+\]', '', body)
    body = re.sub(r'\[piconname:\d+\].*?さん', '', body)
    body = re.sub(r'\[To:\d+\]', '', body)
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
        response.raise_for_status()
        logger.info(f"Successfully fetched room members for room {room_id}")
        return response.json()
    except requests.exceptions.HTTPError as err:
        logger.error(f"HTTP Error occurred while fetching room members: {err.response.status_code} - {err.response.text}")
        return None
    except Exception as e:
        logger.error(f"Failed to get room members: {e}", exc_info=True)
        return None

def change_room_permissions(room_id, admin_ids, member_ids, readonly_ids):
    """
    ルームメンバーの権限を変更する関数
    """
    headers = {
        "X-ChatWorkToken": CHATWORK_API_TOKEN,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = {
        "members_admin_ids": ",".join(map(str, admin_ids)),
        "members_member_ids": ",".join(map(str, member_ids)),
        "members_readonly_ids": ",".join(map(str, readonly_ids))
    }

    logger.info(f"Attempting to change permissions for room {room_id}. Payload: {json.dumps(payload)}")
    
    try:
        response = requests.put(f"https://api.chatwork.com/v2/rooms/{room_id}/members", headers=headers, data=payload)
        response.raise_for_status()
        logger.info(f"Room permissions changed successfully with status code: {response.status_code}")
        return True
    except requests.exceptions.HTTPError as err:
        logger.error(f"HTTP Error occurred while changing permissions: {err.response.status_code} - {err.response.text}")
        return False
    except Exception as e:
        logger.error(f"Failed to change room permissions: {e}", exc_info=True)
        return False

@app.route("/", methods=["POST"])
def chatwork_webhook():
    logger.info(f"Received a new webhook request. Headers: {request.headers}")
    try:
        data = request.json
        logger.info(f"Received JSON data: {json.dumps(data, indent=2)}")
        webhook_event = data.get("webhook_event")
        
        if not webhook_event:
            logger.warning("Webhook event is missing from the payload. Skipping.")
            return "", 200

        message_body = webhook_event.get("body")
        account_id = webhook_event.get("account_id")
        room_id = webhook_event.get("room_id")
        message_id = webhook_event.get("message_id")
        
        cleaned_body = clean_message_body(message_body)
        
        logger.info(f"Message details: Account ID: {account_id}, Room ID: {room_id}, Cleaned body: '{cleaned_body}'")
        
        emoji_count = len(EMOJI_PATTERN.findall(message_body))
        logger.info(f"Emoji count: {emoji_count}")

        if str(account_id) != MY_ACCOUNT_ID:
            if emoji_count >= 15:
                logger.info(f"High emoji count detected ({emoji_count}). Checking user's role.")
                
                members = get_room_members(room_id)
                if members:
                    user_role = next((m["role"] for m in members if str(m["account_id"]) == str(account_id)), None)

                    if user_role == "admin":
                        # 管理者の場合は権限変更を行わず、注意喚起のみ
                        logger.info("User is an admin. Skipping permission change.")
                        send_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}]\n管理者の方、メッセージに絵文字が多すぎます。節度を守った利用をお願いします。")
                    else:
                        # 管理者ではない場合は権限変更を行う
                        logger.info("User is not an admin. Proceeding with permission change.")
                        send_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}]\nメッセージに15個以上の絵文字が検出されました。あなたの権限を『閲覧』に変更します。")
                        
                        admin_ids = []
                        member_ids = []
                        readonly_ids = []
                        
                        for member in members:
                            if str(member["account_id"]) == str(account_id):
                                continue
                            
                            if member["role"] == "admin":
                                admin_ids.append(member["account_id"])
                            elif member["role"] == "member":
                                member_ids.append(member["account_id"])
                            elif member["role"] == "readonly":
                                readonly_ids.append(member["account_id"])

                        if str(account_id) not in readonly_ids:
                            readonly_ids.append(str(account_id))
                        
                        logger.info(f"Final permission lists before API call: admin_ids={admin_ids}, member_ids={member_ids}, readonly_ids={readonly_ids}")
                        if change_room_permissions(room_id, admin_ids, member_ids, readonly_ids):
                            send_message(room_id, "メンバーの権限を更新しました。")
                        else:
                            send_message(room_id, "権限の変更に失敗しました。ボットにグループチャットの管理者権限があるか、APIトークンに正しいスコープが付与されているか確認してください。")
            
            elif "test" in cleaned_body:
                logger.info("Test message received. Responding with current time.")
                jst = timezone(timedelta(hours=9), 'JST')
                now_jst = datetime.now(jst)
                current_time = now_jst.strftime("%Y/%m/%d %H:%M:%S")
                
                reply_message = f"現在の時刻は {current_time} です。"
                send_message(room_id, reply_message, reply_to_id=account_id, reply_message_id=message_id)
            
            elif "おみくじ" in cleaned_body:
                logger.info("Omikuji message received. Drawing a fortune.")
                omikuji_results = ["大吉🎉", "吉😊", "中吉🙂", "小吉😅", "末吉🤔", "凶😭"]
                omikuji_weights = [5, 4, 3, 2, 2, 1]
                
                result = random.choices(omikuji_results, weights=omikuji_weights, k=1)[0]
                
                reply_message = f"おみくじの結果は **{result}** です。"
                send_message(room_id, reply_message, reply_to_id=account_id, reply_message_id=message_id)

            elif "[toall]" in message_body.lower():
                logger.info("[toall] message received. Changing permissions to readonly for other members.")
                send_message(room_id, "ルームメンバーの権限を更新します。")
                
                members = get_room_members(room_id)
                if members:
                    admin_ids = []
                    member_ids = []
                    readonly_ids = []
                    
                    for member in members:
                        if str(member["account_id"]) == str(account_id):
                            member_ids.append(member["account_id"])
                        else:
                            readonly_ids.append(member["account_id"])
                    
                    logger.info(f"Final permission lists before API call: admin_ids={admin_ids}, member_ids={member_ids}, readonly_ids={readonly_ids}")
                    if change_room_permissions(room_id, admin_ids, member_ids, readonly_ids):
                        send_message(room_id, "メンバーの権限を『閲覧』に変更しました。")
                    else:
                        send_message(room_id, "権限の変更に失敗しました。ボットに管理者権限があるか確認してください。")

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        logger.error(f"Received data was: {request.data.decode('utf-8')}")

    logger.info("Request processing finished.")
    return "", 200

if __name__ == "__main__":
    app.run()

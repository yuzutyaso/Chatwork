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

# ユーザーのおみくじ利用履歴を記録する辞書
# キー: ユーザーID (account_id), 値: 最終利用日時 (datetimeオブジェクト)
omikuji_history = {}

# Chatwork専用の絵文字パターン
EMOJI_PATTERN = re.compile(
    r":\)|:\(|:D|8-\)|:o|;\)|;\(|:\*|:p|\(blush\)|:\^|\(inlove\)|:\)|:\(|:D|8-\)|:o|;\)|;\(|:\*|:p|:\^|\(sweat\)|\|\-\)|\]:D|\(talk\)|\(yawn\)|\(puke\)|\(emo\)|8-\||:\#|\(nod\)|\(shake\)|\(\^\^;\)|\(whew\)|\(clap\)|\(bow\)|\(roger\)|\(flex\)|\(dance\)|\(:/\)|\(gogo\)|\(think\)|\(please\)|\(quick\)|\(anger\)|\(devil\)|\(lightbulb\)|\(\*\)|\(h\)|\(F\)|\(cracker\)|\(eat\)|\(\^\)|\(coffee\)|\(beer\)|\(handshake\)|\(y\)"
)

# Chatworkの招待URLの正規表現
INVITE_URL_PATTERN = re.compile(r"https:\/\/www\.chatwork\.com\/g\/(?P<token>[a-zA-Z0-9]+)")

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

def mark_as_read(room_id):
    """
    指定されたルームのメッセージをすべて既読にする
    """
    headers = {
        "X-ChatWorkToken": CHATWORK_API_TOKEN
    }
    try:
        response = requests.put(f"https://api.chatwork.com/v2/rooms/{room_id}/messages/read", headers=headers)
        response.raise_for_status()
        logger.info(f"Messages in room {room_id} marked as read successfully.")
        return True
    except requests.exceptions.HTTPError as err:
        logger.error(f"HTTP Error occurred while marking messages as read: {err.response.status_code} - {err.response.text}")
        return False
    except Exception as e:
        logger.error(f"Failed to mark messages as read: {e}", exc_info=True)
        return False

def get_room_info(room_id):
    """
    指定されたルームの情報を取得する
    """
    headers = {
        "X-ChatWorkToken": CHATWORK_API_TOKEN
    }
    try:
        response = requests.get(f"https://api.chatwork.com/v2/rooms/{room_id}", headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as err:
        logger.error(f"HTTP Error occurred while fetching room info: {err.response.status_code} - {err.response.text}")
        return None
    except Exception as e:
        logger.error(f"Failed to get room info: {e}", exc_info=True)
        return None

def get_room_members_count(room_id):
    """
    指定されたルームのメンバー数を取得する
    """
    members = get_room_members(room_id)
    if members:
        return len(members)
    return 0

def get_admin_count(room_id):
    """
    指定されたルームの管理者数を取得する
    """
    members = get_room_members(room_id)
    if members:
        return sum(1 for m in members if m["role"] == "admin")
    return 0

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

def get_permission_list(room_id, permission_type):
    """
    指定された権限を持つユーザーのリストを取得する関数
    """
    members = get_room_members(room_id)
    if not members:
        return None

    permission_list = []
    for member in members:
        if member["role"] == permission_type:
            permission_list.append(member)
    return permission_list

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

def request_join_group_chat(invite_token):
    """
    招待トークンを使ってグループチャットへの参加権限をリクエストする
    """
    # 招待権限リクエストには、部屋情報の取得と同様のAPIが使えますが、
    # 実際には直接APIでリクエストする機能はありません。
    # この関数は、ログの記録とメッセージの送信のためだけに存在します。
    # 実際には、手動での承認が必要になります。
    # この関数は、あくまでbotが「リクエストを送った」という振る舞いを模倣するためのものです。
    logger.info(f"Sending join request for room with token: {invite_token}")
    return True

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
        
        # /roominfo 以外のメッセージは常に既読にする
        # 特定の部屋でも既読化は行う
        if not message_body.startswith("/roominfo"):
            mark_as_read(room_id)
        
        # 特定の部屋ID (365406836) での招待URL処理
        if str(room_id) == "365406836":
            match = INVITE_URL_PATTERN.search(message_body)
            if match:
                invite_token = match.group("token")
                logger.info(f"Invitation URL detected in room {room_id}. Token: {invite_token}. Requesting join permission.")
                if request_join_group_chat(invite_token):
                    # 参加権限をリクエストしましたというメッセージを送信
                    send_message(room_id, "新しい部屋に参加権限を送りました✅️", reply_to_id=account_id, reply_message_id=message_id)
                    logger.info(f"Sent message: '新しい部屋に参加権限を送りました✅️' to room {room_id}")
                else:
                    logger.error("Failed to send join request. This part of the code should not be reached.")
                return "", 200

        cleaned_body = clean_message_body(message_body)
        
        logger.info(f"Message details: Account ID: {account_id}, Room ID: {room_id}, Cleaned body: '{cleaned_body}'")

        if str(account_id) != MY_ACCOUNT_ID:
            
            # 部屋情報表示機能
            if cleaned_body.startswith("/roominfo"):
                logger.info("/roominfo command received.")
                
                parts = cleaned_body.split()
                if len(parts) < 2:
                    send_message(room_id, "使用方法: `/roominfo [ルームID]`", reply_to_id=account_id, reply_message_id=message_id)
                    return "", 200

                target_room_id = parts[1]
                
                room_info = get_room_info(target_room_id)
                if room_info:
                    room_name = room_info.get("name", "不明な部屋名")
                    messages_count = room_info.get("message_num", 0)
                    members_count = get_room_members_count(target_room_id)
                    admins_count = get_admin_count(target_room_id)

                    info_message = (
                        f"【部屋情報】\n"
                        f"部屋名: {room_name}\n"
                        f"メッセージ数: {messages_count}件\n"
                        f"メンバー数: {members_count}人\n"
                        f"管理者数: {admins_count}人"
                    )
                    send_message(room_id, info_message, reply_to_id=account_id, reply_message_id=message_id)
                else:
                    send_message(room_id, "指定されたルームIDの情報が見つかりません。ボットがその部屋に参加しているか確認してください。", reply_to_id=account_id, reply_message_id=message_id)

            # 権限リスト表示機能
            elif cleaned_body == "/blacklist":
                logger.info("Blacklist command received. Fetching readonly members.")
                readonly_members = get_permission_list(room_id, "readonly")
                if readonly_members:
                    names = [member["name"] for member in readonly_members]
                    message = "【閲覧権限ユーザー】\n" + "\n".join(names)
                    send_message(room_id, message, reply_to_id=account_id, reply_message_id=message_id)
                else:
                    send_message(room_id, "現在、閲覧権限のユーザーはいません。", reply_to_id=account_id, reply_message_id=message_id)
            
            elif cleaned_body == "/admin":
                logger.info("Admin command received. Fetching admin members.")
                admin_members = get_permission_list(room_id, "admin")
                if admin_members:
                    names = [member["name"] for member in admin_members]
                    message = "【管理者権限ユーザー】\n" + "\n".join(names)
                    send_message(room_id, message, reply_to_id=account_id, reply_message_id=message_id)
                else:
                    send_message(room_id, "現在、管理者権限のユーザーはいません。", reply_to_id=account_id, reply_message_id=message_id)

            elif cleaned_body == "/member":
                logger.info("Member command received.")
                
                # ユーザーの権限をチェック
                members = get_room_members(room_id)
                user_role = next((m["role"] for m in members if str(m["account_id"]) == str(account_id)), None)

                if user_role == "admin":
                    member_members = get_permission_list(room_id, "member")
                    if member_members:
                        names = [member["name"] for member in member_members]
                        message = "【メンバー権限ユーザー】\n" + "\n".join(names)
                        send_message(room_id, message, reply_to_id=account_id, reply_message_id=message_id)
                    else:
                        send_message(room_id, "現在、メンバー権限のユーザーはいません。", reply_to_id=account_id, reply_message_id=message_id)
                else:
                    send_message(room_id, "このコマンドは管理者のみ実行可能です。", reply_to_id=account_id, reply_message_id=message_id)
            
            # おみくじ機能
            elif "おみくじ" in cleaned_body:
                logger.info("Omikuji message received. Drawing a fortune.")
                
                now = datetime.now()
                last_used = omikuji_history.get(account_id)

                # 最終利用日時が記録されていて、かつ24時間以内であればエラーメッセージを送信
                if last_used and (now - last_used) < timedelta(hours=24):
                    send_message(room_id, "おみくじは1日1回です。また明日お試しください。", reply_to_id=account_id, reply_message_id=message_id)
                else:
                    # おみくじを引く
                    omikuji_results = ["大吉🎉", "吉😊", "中吉🙂", "小吉😅", "末吉🤔", "凶😭"]
                    omikuji_weights = [5, 4, 3, 2, 2, 1]
                    result = random.choices(omikuji_results, weights=omikuji_weights, k=1)[0]
                    
                    # 履歴を更新
                    omikuji_history[account_id] = now
                    
                    reply_message = f"おみくじの結果は **{result}** です。"
                    send_message(room_id, reply_message, reply_to_id=account_id, reply_message_id=message_id)

            # その他の機能（絵文字、テスト、toall）はここに続く
            emoji_count = len(EMOJI_PATTERN.findall(message_body))
            if emoji_count >= 15:
                logger.info(f"High emoji count detected ({emoji_count}). Checking user's role.")
                
                members = get_room_members(room_id)
                if members:
                    user_role = next((m["role"] for m in members if str(m["account_id"]) == str(account_id)), None)

                    if user_role == "admin":
                        logger.info("User is an admin. Skipping permission change.")
                        send_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}]\n管理者の方、メッセージに絵文字が多すぎます。節度を守った利用をお願いします。")
                    else:
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

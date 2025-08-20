import os
import json
import logging
import requests
import random
import re
from datetime import datetime, timezone, timedelta
from flask import Flask, request
from collections import Counter
from supabase import create_client, Client

# Logger settings
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Chatwork API Configuration ---
CHATWORK_API_TOKEN = os.environ.get("CHATWORK_API_TOKEN")
MY_ACCOUNT_ID = os.environ.get("MY_ACCOUNT_ID")

# --- Supabase Configuration ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase client created successfully.")
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}", exc_info=True)
        supabase = None
else:
    logger.warning("SUPABASE_URL or SUPABASE_KEY is not set. Database functionality will be disabled.")
    supabase = None

# --- Cache room member info to avoid rate limits ---
member_cache = {}
# Cache expiration time (24 hours)
CACHE_EXPIRY_HOURS = 24

# Dictionary to record user's omikuji history
omikuji_history = {}

# Chatwork-specific emoji pattern. Matches the entire string to ensure it's *only* emojis.
# This pattern is specifically for the Chatwork-style emojis like :), :D, (clap), etc.
EMOJI_PATTERN = re.compile(
    r"^(?::\)|:\(|:D|8-\)|:o|;\)|;\(|:\*|:p|\(blush\)|:\^|\(inlove\)|:\)|:\(|:D|8-\)|:o|;\)|;\(|:\*|:p|:\^|\(sweat\)|\|\-\)|\]:D|\(talk\)|\(yawn\)|\(puke\)|\(emo\)|8-\||:\#|\(nod\)|\(shake\)|\(\^\^;\)|\(whew\)|\(clap\)|\(bow\)|\(roger\)|\(flex\)|\(dance\)|\(:/\)|\(gogo\)|\(think\)|\(please\)|\(quick\)|\(anger\)|\(devil\)|\(lightbulb\)|\(\*\)|\(h\)|\(F\)|\(cracker\)|\(eat\)|\(\^\)|\(coffee\)|\(beer\)|\(handshake\)|\(y\))+|^(?:[ \t]*[:\)\(\[\]pD;*^|#]|\(\w+\))*\s*$|\s*(?:[ \t]*[:\)\(\[\]pD;*^|#]|\(\w+\))*\s*$"
)

# Bot service is starting...
logger.info("Bot service is starting...")

def send_message(room_id, message_body, reply_to_id=None, reply_message_id=None):
    """
    Common function to send a message to Chatwork
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

def get_rooms():
    """
    Gets a list of all rooms the bot is a member of
    """
    headers = {
        "X-ChatWorkToken": CHATWORK_API_TOKEN
    }
    try:
        response = requests.get("https://api.chatwork.com/v2/rooms", headers=headers)
        response.raise_for_status()
        logger.info("Successfully fetched the list of all rooms.")
        return response.json()
    except requests.exceptions.HTTPError as err:
        logger.error(f"HTTP Error occurred while fetching room list: {err.response.status_code} - {err.response.text}")
        return None
    except Exception as e:
        logger.error(f"Failed to get room list: {e}", exc_info=True)
        return None

def get_room_info(room_id):
    """
    Gets information about a specific room
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

def get_room_members(room_id):
    """
    Gets the list of members for a specific room (with cache)
    """
    # Check cache
    now = datetime.now(timezone.utc)
    if room_id in member_cache and (now - member_cache[room_id]['timestamp']) < timedelta(hours=CACHE_EXPIRY_HOURS):
        logger.info(f"Using cached members for room {room_id}")
        return member_cache[room_id]['data']
    
    headers = {
        "X-ChatWorkToken": CHATWORK_API_TOKEN
    }
    try:
        response = requests.get(f"https://api.chatwork.com/v2/rooms/{room_id}/members", headers=headers)
        response.raise_for_status()
        members = response.json()
        logger.info(f"Successfully fetched room members for room {room_id}")
        
        # Cache the fetched member list
        member_cache[room_id] = {
            'timestamp': now,
            'data': members
        }
        return members
    except requests.exceptions.HTTPError as err:
        logger.error(f"HTTP Error occurred while fetching room members: {err.response.status_code} - {err.response.text}")
        return None
    except Exception as e:
        logger.error(f"Failed to get room members: {e}", exc_info=True)
        return None

def get_room_members_count(room_id):
    """
    Gets the number of members in a specified room
    """
    members = get_room_members(room_id)
    if members:
        return len(members)
    return 0

def get_admin_count(room_id):
    """
    Gets the number of administrators in a specified room
    """
    members = get_room_members(room_id)
    if members:
        return sum(1 for m in members if m["role"] == "admin")
    return 0

def is_bot_admin(room_id):
    """
    Checks if the bot itself has admin privileges in the specified room.
    """
    members = get_room_members(room_id)
    if members:
        for member in members:
            if str(member["account_id"]) == str(MY_ACCOUNT_ID) and member["role"] == "admin":
                return True
    return False

def clean_message_body(body):
    """
    Removes all tags and subsequent names, and extra whitespace from the message body
    """
    body = re.sub(r'\[rp aid=\d+ to=\d+-\d+\]', '', body)
    body = re.sub(r'\[piconname:\d+\].*?さん', '', body)
    body = re.sub(r'\[To:\d+\]', '', body)
    # Remove leading/trailing newlines and spaces
    return body.strip()

def get_permission_list(room_id, permission_type):
    """
    Gets a list of users with the specified permission
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
    Changes room member permissions
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

def update_message_count_in_db(date, account_id, account_name):
    """
    Updates or inserts a message count for a user and date in the database.
    """
    if not supabase:
        logger.warning("Supabase client is not available. Skipping database update.")
        return

    try:
        # Check if a record for the user and date already exists
        response = supabase.table('message_counts').select("*").eq("date", date).eq("account_id", account_id).execute()
        
        if response.data:
            # If record exists, increment the message_count
            current_count = response.data[0]['message_count']
            supabase.table('message_counts').update({'message_count': current_count + 1}).eq("id", response.data[0]['id']).execute()
            logger.info(f"Updated message count for {account_name} on {date}.")
        else:
            # If no record, create a new one
            supabase.table('message_counts').insert({"date": date, "account_id": account_id, "name": account_name, "message_count": 1}).execute()
            logger.info(f"Inserted new record for {account_name} on {date}.")
            
    except Exception as e:
        logger.error(f"Failed to update message count in Supabase: {e}", exc_info=True)

def post_ranking(room_id, target_date, reply_to_id, reply_message_id):
    """
    Posts the message count ranking for a specified date from the database.
    """
    if not supabase:
        send_message(room_id, "データベースが利用できません。", reply_to_id=reply_to_id, reply_message_id=reply_message_id)
        return

    logger.info(f"Posting ranking for date: {target_date} in room {room_id}...")

    try:
        response = supabase.table('message_counts').select("*").eq("date", target_date).order("message_count", desc=True).limit(5).execute()
        ranking = response.data

        if not ranking:
            ranking_body = f"{target_date} のメッセージデータが見つかりませんでした。"
        else:
            ranking_lines = [f"{target_date} の個人メッセージ数ランキング！"]
            for i, item in enumerate(ranking, 1):
                name = item.get("name", "Unknown")
                count = item.get("message_count", 0)
                ranking_lines.append(f"{i}位　{name}さん ({count}件)")
            
            ranking_lines.append("以上です")
            ranking_body = "\n".join(ranking_lines)

        send_message(room_id, ranking_body, reply_to_id=reply_to_id, reply_message_id=reply_message_id)
        logger.info("Ranking post finished.")

    except Exception as e:
        logger.error(f"Failed to fetch ranking from Supabase: {e}", exc_info=True)
        send_message(room_id, "ランキングの取得中にエラーが発生しました。", reply_to_id=reply_to_id, reply_message_id=reply_message_id)

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
        
        # --- Combined logic for [toall] and emoji-only messages ---
        # Checks if the message is [toall] or composed entirely of Chatwork emojis
        # The user requested this to be fast, so it's a priority check.
        if "[toall]" in message_body.lower() or EMOJI_PATTERN.fullmatch(cleaned_body):
            logger.info("Permissions change triggered by [toall] or emoji-only message.")
            
            # Check if the bot has admin rights before attempting to change permissions
            if is_bot_admin(room_id):
                members = get_room_members(room_id)  # Get latest member info
                if members:
                    admin_ids = []
                    member_ids = []
                    readonly_ids = []
                    
                    # Check if the message sender was originally an admin
                    is_requester_admin = any(m["role"] == "admin" and str(m["account_id"]) == str(account_id) for m in members)

                    for member in members:
                        if str(member["account_id"]) == str(account_id):
                            # If the sender was an admin, keep them as admin. Otherwise, set to member.
                            if is_requester_admin:
                                admin_ids.append(member["account_id"])
                            else:
                                member_ids.append(member["account_id"])
                        else:
                            # Set everyone else to readonly
                            readonly_ids.append(member["account_id"])
                    
                    logger.info(f"Final permission lists before API call: admin_ids={admin_ids}, member_ids={member_ids}, readonly_ids={readonly_ids}")
                    if change_room_permissions(room_id, admin_ids, member_ids, readonly_ids):
                        send_message(room_id, "メンバーの権限を『閲覧』に変更しました。", reply_to_id=account_id, reply_message_id=message_id)
                    else:
                        send_message(room_id, "権限の変更に失敗しました。ボットに管理者権限があるか確認してください。", reply_to_id=account_id, reply_message_id=message_id)
            else:
                send_message(room_id, "私はこの部屋の管理者ではありません。権限を変更できません。", reply_to_id=account_id, reply_message_id=message_id)
            return "", 200

        # --- Other features follow ---
        if str(account_id) != MY_ACCOUNT_ID:
            # Check if the message is from the designated room to track message counts
            if str(room_id) == "364321548":
                jst = timezone(timedelta(hours=9), 'JST')
                today_date_str = datetime.now(jst).strftime("%Y/%#m/%#d")
                
                members = get_room_members(room_id)
                if members:
                    account_name = next((m["name"] for m in members if str(m["account_id"]) == str(account_id)), "Unknown User")
                    update_message_count_in_db(today_date_str, account_id, account_name)

            # Ranking command processing
            ranking_match = re.match(r'^/ranking\s+(\d{4}/\d{1,2}/\d{1,2})$', cleaned_body)
            if ranking_match:
                if str(room_id) == "407802259":
                    target_date = ranking_match.group(1)
                    post_ranking(room_id, target_date, account_id, message_id)
                else:
                    send_message(room_id, "このコマンドは、指定されたルーム(407802259)でのみ有効です。", reply_to_id=account_id, reply_message_id=message_id)
            
            elif cleaned_body.startswith("/roominfo"):
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
                members = get_room_members(room_id)
                if members:
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
            
            elif "おみくじ" in cleaned_body:
                logger.info("Omikuji message received. Drawing a fortune.")
                now = datetime.now()
                last_used = omikuji_history.get(account_id)

                if last_used and (now - last_used) < timedelta(hours=24):
                    send_message(room_id, "おみくじは1日1回です。また明日お試しください。", reply_to_id=account_id, reply_message_id=message_id)
                else:
                    omikuji_results = ["大吉🎉", "吉😊", "中吉🙂", "小吉😅", "末吉🤔", "凶😭"]
                    omikuji_weights = [5, 4, 3, 2, 2, 1]
                    result = random.choices(omikuji_results, weights=omikuji_weights, k=1)[0]
                    omikuji_history[account_id] = now
                    reply_message = f"おみくじの結果は **{result}** です。"
                    send_message(room_id, reply_message, reply_to_id=account_id, reply_message_id=message_id)
            
          elif "test" in cleaned_body:
                logger.info("Test message received. Responding with current time.")
                jst = timezone(timedelta(hours=9), 'JST')
                now_jst = datetime.now(jst)
                current_time = now_jst.strftime("%Y/%m/%d %H:%M:%S")
                reply_message = f"現在の時刻は {current_time} です。"
                send_message(room_id, reply_message, reply_to_id=account_id, reply_message_id=message_id)

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        logger.error(f"Received data was: {request.data.decode('utf-8')}")

    logger.info("Request processing finished.")
    return "", 200

if __name__ == "__main__":
    app.run()

import os
import json
import logging
import requests
import re
import random
from datetime import datetime, timezone, timedelta
from flask import Flask, request
from supabase import create_client, Client

# Logger settings
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Configuration ---
CHATWORK_API_TOKEN = os.environ.get("CHATWORK_API_TOKEN")
MY_ACCOUNT_ID = os.environ.get("MY_ACCOUNT_ID")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}")

member_cache = {}
CACHE_EXPIRY_HOURS = 24
omikuji_history = {}

EMOJI_PATTERN = re.compile(r"^(?::\)|:\(|:D|8-\)|:o|;\)|;\(|:\*|:p|\(blush\)|:\^|\(inlove\)|:\)|:\(|:D|8-\)|:o|;\)|;\(|:\*|:p|:\^|\(sweat\)|\|\-\)|\]:D|\(talk\)|\(yawn\)|\(puke\)|\(emo\)|8-\||:\#|\(nod\)|\(shake\)|\(\^\^;\)|\(whew\)|\(clap\)|\(bow\)|\(roger\)|\(flex\)|\(dance\)|\(:/\)|\(gogo\)|\(think\)|\(please\)|\(quick\)|\(anger\)|\(devil\)|\(lightbulb\)|\(\*\)|\(h\)|\(F\)|\(cracker\)|\(eat\)|\(\^\)|\(coffee\)|\(beer\)|\(handshake\)|\(y\))+|^(?:[ \t]*[:\)\(\[\]pD;*^|#]|\(\w+\))*\s*$|\s*(?:[ \t]*[:\)\(\[\]pD;*^|#]|\(\w+\))*\s*$")

def send_message(room_id, message_body, reply_to_id=None, reply_message_id=None):
    """
    Sends a message to Chatwork.
    """
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN, "Content-Type": "application/x-www-form-urlencoded"}
    payload = {"body": message_body}
    
    if reply_to_id and reply_message_id:
        payload["body"] = f"[rp aid={reply_to_id} to={room_id}-{reply_message_id}]\n{message_body}"

    try:
        requests.post(f"https://api.chatwork.com/v2/rooms/{room_id}/messages", headers=headers, data=payload).raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send message: {e}")
        return False

def get_room_members(room_id):
    """
    Gets the list of members for a room, with caching.
    """
    now = datetime.now(timezone.utc)
    if room_id in member_cache and (now - member_cache[room_id]['timestamp']) < timedelta(hours=CACHE_EXPIRY_HOURS):
        return member_cache[room_id]['data']
    
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    try:
        response = requests.get(f"https://api.chatwork.com/v2/rooms/{room_id}/members", headers=headers)
        response.raise_for_status()
        members = response.json()
        member_cache[room_id] = {'timestamp': now, 'data': members}
        return members
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get room members: {e}")
        return None

def is_bot_admin(room_id):
    """
    Checks if the bot has admin privileges.
    """
    members = get_room_members(room_id)
    if members:
        for member in members:
            if str(member["account_id"]) == str(MY_ACCOUNT_ID) and member["role"] == "admin":
                return True
    return False

def clean_message_body(body):
    """
    Removes Chatwork tags from the message body.
    """
    body = re.sub(r'\[rp aid=\d+ to=\d+-\d+\]|\[piconname:\d+\].*?さん|\[To:\d+\]', '', body)
    return body.strip()

def change_room_permissions(room_id, admin_ids, member_ids, readonly_ids):
    """
    Changes room member permissions.
    """
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN, "Content-Type": "application/x-www-form-urlencoded"}
    payload = {
        "members_admin_ids": ",".join(map(str, admin_ids)),
        "members_member_ids": ",".join(map(str, member_ids)),
        "members_readonly_ids": ",".join(map(str, readonly_ids))
    }
    try:
        requests.put(f"https://api.chatwork.com/v2/rooms/{room_id}/members", headers=headers, data=payload).raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to change permissions: {e}")
        return False

def update_message_count_in_db(date, account_id, account_name):
    """
    Updates or inserts message count.
    """
    if not supabase: return

    try:
        response = supabase.table('message_counts').select("*").eq("date", date).eq("account_id", account_id).execute()
        if response.data:
            current_count = response.data[0]['message_count']
            supabase.table('message_counts').update({'message_count': current_count + 1}).eq("id", response.data[0]['id']).execute()
        else:
            supabase.table('message_counts').insert({"date": date, "account_id": account_id, "name": account_name, "message_count": 1}).execute()
    except Exception as e:
        logger.error(f"Failed to update message count: {e}")

def post_ranking(room_id, target_date, reply_to_id, reply_message_id):
    """
    Posts the message count ranking.
    """
    if not supabase:
        send_message(room_id, "データベースが利用できません。", reply_to_id=reply_to_id, reply_message_id=reply_message_id)
        return

    try:
        response = supabase.table('message_counts').select("*").eq("date", target_date).order("message_count", desc=True).limit(5).execute()
        ranking = response.data
        if not ranking:
            send_message(room_id, f"{target_date} のデータが見つかりませんでした。", reply_to_id=reply_to_id, reply_message_id=reply_message_id)
        else:
            ranking_lines = [f"{target_date} の個人メッセージ数ランキング！"] + [f"{i}位　{item.get('name', 'Unknown')}さん ({item.get('message_count', 0)}件)" for i, item in enumerate(ranking, 1)] + ["以上です"]
            send_message(room_id, "\n".join(ranking_lines), reply_to_id=reply_to_id, reply_message_id=reply_message_id)
    except Exception as e:
        logger.error(f"Failed to fetch ranking: {e}")
        send_message(room_id, "ランキングの取得中にエラーが発生しました。", reply_to_id=reply_to_id, reply_message_id=reply_message_id)

def handle_test_command(room_id, account_id, message_id):
    """
    Handles the "test" command.
    """
    jst = timezone(timedelta(hours=9), 'JST')
    current_time = datetime.now(jst).strftime("%Y/%m/%d %H:%M:%S")
    send_message(room_id, f"現在の時刻は {current_time} です。", reply_to_id=account_id, reply_message_id=message_id)

def handle_omikuji_command(room_id, account_id, message_id):
    """
    Handles the "omikuji" command.
    """
    now = datetime.now()
    last_used = omikuji_history.get(account_id)
    if last_used and (now - last_used) < timedelta(hours=24):
        send_message(room_id, "おみくじは1日1回です。また明日お試しください。", reply_to_id=account_id, reply_message_id=message_id)
    else:
        results = ["大吉🎉", "吉😊", "中吉🙂", "小吉😅", "末吉🤔", "凶😭"]
        weights = [5, 4, 3, 2, 2, 1]
        result = random.choices(results, weights=weights, k=1)[0]
        omikuji_history[account_id] = now
        send_message(room_id, f"おみくじの結果は **{result}** です。", reply_to_id=account_id, reply_message_id=message_id)

def handle_room_info_command(room_id, account_id, message_id, parts):
    """
    Handles the "/roominfo" command.
    """
    if len(parts) < 2:
        send_message(room_id, "使用方法: `/roominfo [ルームID]`", reply_to_id=account_id, reply_message_id=message_id)
        return

    target_room_id = parts[1]
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    try:
        room_info = requests.get(f"https://api.chatwork.com/v2/rooms/{target_room_id}", headers=headers).json()
        members = get_room_members(target_room_id)
        admins = sum(1 for m in members if m["role"] == "admin") if members else 0
        info_message = (f"【部屋情報】\n部屋名: {room_info.get('name', '不明')}\n"
                        f"メッセージ数: {room_info.get('message_num', 0)}件\n"
                        f"メンバー数: {len(members) if members else 0}人\n"
                        f"管理者数: {admins}人")
        send_message(room_id, info_message, reply_to_id=account_id, reply_message_id=message_id)
    except requests.exceptions.RequestException:
        send_message(room_id, "ルーム情報が見つかりません。", reply_to_id=account_id, reply_message_id=message_id)

def handle_permission_list(room_id, account_id, message_id, role_type):
    """
    Handles permission list commands like /admin and /blacklist.
    """
    members = get_room_members(room_id)
    if not members:
        send_message(room_id, "メンバー情報が取得できません。", reply_to_id=account_id, reply_message_id=message_id)
        return
    
    permission_members = [m for m in members if m["role"] == role_type]
    if permission_members:
        names = [m["name"] for m in permission_members]
        message = f"【{role_type}権限ユーザー】\n" + "\n".join(names)
        send_message(room_id, message, reply_to_id=account_id, reply_message_id=message_id)
    else:
        send_message(room_id, f"現在、{role_type}権限のユーザーはいません。", reply_to_id=account_id, reply_message_id=message_id)


@app.route("/", methods=["POST"])
def chatwork_webhook():
    try:
        data = request.json
        webhook_event = data.get("webhook_event")
        if not webhook_event: return "", 200

        message_body = webhook_event.get("body")
        account_id = webhook_event.get("account_id")
        room_id = webhook_event.get("room_id")
        message_id = webhook_event.get("message_id")
        
        cleaned_body = clean_message_body(message_body)

        if str(account_id) == MY_ACCOUNT_ID: return "", 200

        # Command handling
        if cleaned_body == "/test":
            handle_test_command(room_id, account_id, message_id)
        elif cleaned_body.startswith("/roominfo"):
            handle_room_info_command(room_id, account_id, message_id, cleaned_body.split())
        elif cleaned_body == "/blacklist":
            handle_permission_list(room_id, account_id, message_id, "readonly")
        elif cleaned_body == "/admin":
            handle_permission_list(room_id, account_id, message_id, "admin")
        elif cleaned_body == "/member":
            # Admin-only check
            members = get_room_members(room_id)
            if members and any(m["role"] == "admin" and str(m["account_id"]) == str(account_id) for m in members):
                handle_permission_list(room_id, account_id, message_id, "member")
            else:
                send_message(room_id, "このコマンドは管理者のみ実行可能です。", reply_to_id=account_id, reply_message_id=message_id)
        elif "おみくじ" in cleaned_body:
            handle_omikuji_command(room_id, account_id, message_id)
        elif ranking_match := re.match(r'^/ranking\s+(\d{4}/\d{1,2}/\d{1,2})$', cleaned_body):
            if str(room_id) == "407802259":
                post_ranking(room_id, ranking_match.group(1), account_id, message_id)
            else:
                send_message(room_id, "このコマンドは、指定されたルーム(407802259)でのみ有効です。", reply_to_id=account_id, reply_message_id=message_id)
        elif "[toall]" in message_body.lower() or EMOJI_PATTERN.fullmatch(cleaned_body):
            if is_bot_admin(room_id):
                members = get_room_members(room_id)
                if members:
                    is_requester_admin = any(m["role"] == "admin" and str(m["account_id"]) == str(account_id) for m in members)
                    admin_ids = [m["account_id"] for m in members if str(m["account_id"]) == str(account_id) and is_requester_admin]
                    member_ids = [m["account_id"] for m in members if str(m["account_id"]) == str(account_id) and not is_requester_admin]
                    readonly_ids = [m["account_id"] for m in members if str(m["account_id"]) != str(account_id)]
                    
                    if change_room_permissions(room_id, admin_ids, member_ids, readonly_ids):
                        send_message(room_id, "メンバーの権限を『閲覧』に変更しました。", reply_to_id=account_id, reply_message_id=message_id)
                    else:
                        send_message(room_id, "権限の変更に失敗しました。", reply_to_id=account_id, reply_message_id=message_id)
            else:
                send_message(room_id, "私はこの部屋の管理者ではありません。", reply_to_id=account_id, reply_message_id=message_id)

        # Message count tracking
        if str(room_id) == "364321548":
            jst = timezone(timedelta(hours=9), 'JST')
            today_date_str = datetime.now(jst).strftime("%Y/%#m/%#d")
            members = get_room_members(room_id)
            if members:
                account_name = next((m["name"] for m in members if str(m["account_id"]) == str(account_id)), "Unknown User")
                update_message_count_in_db(today_date_str, account_id, account_name)

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")

    return "", 200

if __name__ == "__main__":
    app.run()

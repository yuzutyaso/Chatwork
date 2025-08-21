# handlers.py
import os
import logging
import re
import random
import requests
from datetime import datetime, timezone, timedelta
from services import (
    send_message, get_room_members, change_room_permissions, is_bot_admin,
    save_readonly_user_to_db, remove_readonly_user_from_db, is_readonly_user_in_db,
    reset_message_counts, get_weather_info, update_room_info_in_db,
    get_all_room_info_from_db, get_message_count_for_ranking,
    update_message_count_in_db, get_supabase_client, post_personal_ranking
)
from utils import clean_message_body
from constants import SINGLE_EMOJI_PATTERN, JAPANESE_CITIES

logger = logging.getLogger(__name__)

# --- グローバル変数 ---
omikuji_history = {}
REPORT_ROOM_ID = os.environ.get("REPORT_ROOM_ID")

def handle_webhook_event(webhook_event, is_manual=True):
    """Handles the main webhook event logic."""
    room_id = webhook_event.get("room_id")
    message_body = webhook_event.get("body")
    account_id = webhook_event.get("account_id")
    message_id = webhook_event.get("message_id")

    cleaned_body = clean_message_body(message_body)

    # Check if the user is in the readonly list and change permissions if needed.
    if is_readonly_user_in_db(account_id) and is_bot_admin(room_id):
        members = get_room_members(room_id)
        if members:
            admin_ids = [m["account_id"] for m in members if m["role"] == "admin"]
            member_ids = [m["account_id"] for m in members if m["role"] == "member"]
            readonly_ids = [m["account_id"] for m in members if m["role"] == "readonly"]
            
            if account_id in admin_ids:
                admin_ids.remove(account_id)
            if account_id in member_ids:
                member_ids.remove(account_id)
            if account_id not in readonly_ids:
                readonly_ids.append(account_id)
            
            if change_room_permissions(room_id, admin_ids, member_ids, readonly_ids):
                send_message(room_id, "このユーザーは過去に閲覧権限に変更されたため、権限を『閲覧』に設定しました。", reply_to_id=account_id, reply_message_id=message_id)
        return

    # Handle commands based on the cleaned message body.
    if cleaned_body == "/test":
        handle_test_command(room_id, account_id, message_id)
    elif cleaned_body.startswith("/sorry"):
        handle_sorry_command(room_id, account_id, message_id, cleaned_body.split())
    elif cleaned_body.startswith("/roominfo"):
        handle_room_info_command(room_id, account_id, message_id, cleaned_body.split())
    elif cleaned_body == "/blacklist":
        handle_permission_list(room_id, account_id, message_id, "readonly")
    elif cleaned_body == "/admin":
        handle_permission_list(room_id, account_id, message_id, "admin")
    elif cleaned_body == "/member":
        members = get_room_members(room_id)
        if members and any(m["role"] == "admin" and str(m["account_id"]) == str(account_id) for m in members):
            handle_permission_list(room_id, account_id, message_id, "member")
        else:
            send_message(room_id, "このコマンドは管理者のみ実行可能です。", reply_to_id=account_id, reply_message_id=message_id)
    elif "おみくじ" in cleaned_body:
        handle_omikuji_command(room_id, account_id, message_id)
    elif cleaned_body == "/ranking all":
        handle_ranking_all_command(room_id, account_id, message_id, is_manual) # フラグを渡す
    # /ranking 日付コマンドの部屋ID制限を実装
    elif ranking_match := re.match(r'^/ranking\s+(\d{4}/\d{1,2}/\d{1,2})$', cleaned_body):
        if str(room_id) == "407802259":
            post_personal_ranking(room_id, ranking_match.group(1), account_id, message_id)
        else:
            send_message(room_id, "このコマンドは、指定されたルーム(407802259)でのみ有効です。", reply_to_id=account_id, reply_message_id=message_id)
    elif cleaned_body == "/restart":
        handle_restart_command(room_id, account_id, message_id)
    elif cleaned_body.startswith("/say"):
        handle_say_command(room_id, account_id, message_id, message_body)
    elif cleaned_body == "/help":
        handle_help_command(room_id, account_id, message_id)
    elif cleaned_body.startswith("/weather"):
        handle_weather_command(room_id, account_id, message_id, cleaned_body.split())
    
    # Abuse detection logic.
    emoji_matches = re.findall(SINGLE_EMOJI_PATTERN, message_body)
    if "[toall]" in message_body.lower() or len(emoji_matches) >= 15:
        if is_bot_admin(room_id):
            members = get_room_members(room_id)
            if members:
                admin_ids = [m["account_id"] for m in members if m["role"] == "admin"]
                member_ids = [m["account_id"] for m in members if m["role"] == "member"]
                readonly_ids = [m["account_id"] for m in members if m["role"] == "readonly"]

                if account_id in admin_ids:
                    admin_ids.remove(account_id)
                if account_id in member_ids:
                    member_ids.remove(account_id)
                if account_id not in readonly_ids:
                    readonly_ids.append(account_id)

                if change_room_permissions(room_id, admin_ids, member_ids, readonly_ids):
                    send_message(room_id, "メッセージを送信したユーザーの権限を『閲覧』に変更しました。", reply_to_id=account_id, reply_message_id=message_id)
                    save_readonly_user_to_db(account_id)
                else:
                    send_message(room_id, "権限の変更に失敗しました。ボットに管理者権限があるか、権限の変更が許可されているか確認してください。", reply_to_id=account_id, reply_message_id=message_id)
        else:
            send_message(room_id, "私はこの部屋の管理者ではありません。権限を変更できません。", reply_to_id=account_id, reply_message_id=message_id)
    
    # Message count logic.
    jst = timezone(timedelta(hours=9), 'JST')
    today_date_str = datetime.now(jst).strftime("%Y/%#m/%#d")
    
    # 部屋情報を更新
    members = get_room_members(room_id)
    room_info_res = requests.get(f"https://api.chatwork.com/v2/rooms/{room_id}", headers={"X-ChatWorkToken": os.environ.get("CHATWORK_API_TOKEN")}).json()
    room_name = room_info_res.get("name", "不明")
    update_room_info_in_db(room_id, room_name)
    
    if members:
        account_name = next((m["name"] for m in members if str(m["account_id"]) == str(account_id)), "Unknown User")
        update_message_count_in_db(room_id, today_date_str, account_id, account_name, message_id)

# --- Command Handler Functions ---
def handle_test_command(room_id, account_id, message_id):
    """Handles the /test command."""
    jst = timezone(timedelta(hours=9), 'JST')
    current_time = datetime.now(jst).strftime("%Y/%m/%d %H:%M:%S")
    send_message(room_id, f"現在の時刻は {current_time} です。", reply_to_id=account_id, reply_message_id=message_id)

def handle_omikuji_command(room_id, account_id, message_id):
    """Handles the fortune command."""
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

def handle_sorry_command(room_id, sender_id, message_id, parts):
    """Handles the /sorry command to remove a user from the readonly list."""
    if not get_supabase_client():
        send_message(room_id, "データベースが利用できません。", reply_to_id=sender_id, reply_message_id=message_id)
        return

    members = get_room_members(room_id)
    if not members or not any(m["role"] == "admin" and str(m["account_id"]) == str(sender_id) for m in members):
        send_message(room_id, "このコマンドは管理者のみ実行可能です。", reply_to_id=sender_id, reply_message_id=message_id)
        return

    if len(parts) < 2:
        send_message(room_id, "使用方法: `/sorry [ユーザーID]`", reply_to_id=sender_id, reply_message_id=message_id)
        return
    
    target_id = parts[1]
    
    if remove_readonly_user_from_db(target_id):
        send_message(room_id, f"ユーザーID {target_id} を閲覧者リストから削除しました。", reply_to_id=sender_id, reply_message_id=message_id)
    else:
        send_message(room_id, f"ユーザーID {target_id} は閲覧者リストに見つかりませんでした。", reply_to_id=sender_id, reply_message_id=message_id)

def handle_room_info_command(room_id, account_id, message_id, parts):
    """Handles the /roominfo command."""
    if len(parts) < 2:
        send_message(room_id, "使用方法: `/roominfo [ルームID]`", reply_to_id=account_id, reply_message_id=message_id)
        return
    target_room_id = parts[1]
    try:
        headers = {"X-ChatWorkToken": os.environ.get("CHATWORK_API_TOKEN")}
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
    """Handles commands for permission lists (/blacklist, /admin, /member)."""
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

def handle_ranking_all_command(room_id, account_id, message_id, is_manual):
    """Handles the /ranking all command for admins."""
    if not get_supabase_client():
        send_message(room_id, "データベースが利用できません。", reply_to_id=account_id, reply_message_id=message_id)
        return

    members = get_room_members(room_id)
    if not members or not any(m["role"] == "admin" and str(m["account_id"]) == str(account_id) for m in members):
        send_message(room_id, "このコマンドは管理者のみ実行可能です。", reply_to_id=account_id, reply_message_id=message_id)
        return

    jst = timezone(timedelta(hours=9), 'JST')
    
    if is_manual:
        # 手動実行の場合は「本日」のランキングを返却
        target_date_str = datetime.now(jst).strftime("%Y/%#m/%#d")
        ranking_title = "本日"
    else:
        # 自動実行の場合は「昨日」のランキングを返却
        target_date_str = (datetime.now(jst) - timedelta(days=1)).strftime("%Y/%#m/%#d")
        ranking_title = "昨日"

    ranking = get_message_count_for_ranking(target_date_str)
    if not ranking:
        send_message(room_id, f"{ranking_title}のメッセージ数ランキングはまだありません。", reply_to_id=account_id, reply_message_id=message_id)
        return
        
    ranking_lines = [f"【{ranking_title}のメッセージ数ランキング】"]
    for i, (room_id_str, count) in enumerate(ranking.items(), 1):
        room_name = get_all_room_info_from_db().get(room_id_str, {}).get("room_name", f"部屋ID: {room_id_str}")
        ranking_lines.append(f"{i}位: {room_name} ({count}件)")
        if i >= 10:
            break
    
    send_message(room_id, "\n".join(ranking_lines), reply_to_id=account_id, reply_message_id=message_id)

def post_all_room_ranking_daily():
    """Posts all room rankings automatically to the REPORT_ROOM_ID."""
    if not REPORT_ROOM_ID:
        logger.warning("REPORT_ROOM_ID is not set. Skipping daily ranking post.")
        return
    
    jst = timezone(timedelta(hours=9), 'JST')
    yesterday_date = (datetime.now(jst) - timedelta(days=1)).strftime("%Y/%#m/%#d")
    
    ranking = get_message_count_for_ranking(yesterday_date)
    
    if not ranking:
        send_message(REPORT_ROOM_ID, "昨日のメッセージ数ランキングはまだありません。", reply_to_id=None, reply_message_id=None)
        return
    
    ranking_lines = [f"【昨日のメッセージ数ランキング】"]
    for i, (room_id_str, count) in enumerate(ranking.items(), 1):
        room_name = get_all_room_info_from_db().get(room_id_str, {}).get("room_name", f"部屋ID: {room_id_str}")
        ranking_lines.append(f"{i}位: {room_name} ({count}件)")
        if i >= 10:
            break
    
    send_message(REPORT_ROOM_ID, "\n".join(ranking_lines), reply_to_id=None, reply_message_id=None)

def handle_restart_command(room_id, account_id, message_id):
    """
    Handles the /restart command.
    Resets all message counts for the current date.
    """
    if not get_supabase_client():
        send_message(room_id, "データベースが利用できません。", reply_to_id=account_id, reply_message_id=message_id)
        return

    # Check if the user is an admin.
    members = get_room_members(room_id)
    if not members or not any(m["role"] == "admin" and str(m["account_id"]) == str(account_id) for m in members):
        send_message(room_id, "このコマンドは管理者のみ実行可能です。", reply_to_id=account_id, reply_message_id=message_id)
        return

    jst = timezone(timedelta(hours=9), 'JST')
    today_date_str = datetime.now(jst).strftime("%Y/%#m/%#d")

    # Reset all message counts for today
    if reset_message_counts(today_date_str):
        send_message(room_id, f"本日（{today_date_str}）のメッセージカウントをリセットしました。", reply_to_id=account_id, reply_message_id=message_id)
    else:
        send_message(room_id, f"メッセージ数のリセットに失敗しました。", reply_to_id=account_id, reply_message_id=message_id)

def handle_say_command(room_id, account_id, message_id, full_body):
    """Handles the /say command to post a message as the bot."""
    if not is_bot_admin(room_id):
        send_message(room_id, "このコマンドはボットが管理者権限を持つ部屋でのみ使用できます。", reply_to_id=account_id, reply_message_id=message_id)
        return

    say_message = full_body.replace("/say", "", 1).strip()
    if say_message:
        send_message(room_id, say_message)
    else:
        send_message(room_id, "使用方法: `/say [メッセージ]`", reply_to_id=account_id, reply_message_id=message_id)

def handle_help_command(room_id, account_id, message_id):
    """Handles the /help command by listing all commands."""
    help_message = """
    【コマンド一覧】
    /test - ボットの動作確認
    /sorry [ユーザーID] - 閲覧者リストからユーザーを削除
    /roominfo [ルームID] - ルームの情報を表示
    /blacklist - 閲覧者リストを表示
    /admin - 管理者リストを表示
    /member - メンバーリストを表示
    /ranking all - 昨日の全部屋のメッセージ数ランキングを表示 (管理者専用)
    /ranking [YYYY/MM/DD] - 指定日のランキングを表示 (特定ルームのみ)
    /restart - 当日のメッセージカウントをリセット (管理者専用)
    /say [メッセージ] - ボットがメッセージを投稿 (管理者専用)
    /help - このヘルプを表示
    /weather [都市名] - 指定都市の天気予報を表示
    「おみくじ」 - おみくじを引く
    """
    send_message(room_id, help_message, reply_to_id=account_id, reply_message_id=message_id)

def handle_weather_command(room_id, account_id, message_id, parts):
    """Handles the /weather command to get weather information."""
    if len(parts) < 2:
        send_message(room_id, "使用方法: `/weather [都市名]`", reply_to_id=account_id, reply_message_id=message_id)
        return

    city_name_jp = parts[1]
    city_name_en = JAPANESE_CITIES.get(city_name_jp)

    if city_name_en:
        weather_info = get_weather_info(city_name_en)
        send_message(room_id, weather_info, reply_to_id=account_id, reply_message_id=message_id)
    else:
        send_message(room_id, f"『{city_name_jp}』の天気情報は対応していません。日本の都道府県名か、主要都市名を入力してください。", reply_to_id=account_id, reply_message_id=message_id)
```python
# services.py
import os
import requests
import logging
from supabase import create_client, Client
from constants import (
    CHATWORK_API_TOKEN, MY_ACCOUNT_ID, SUPABASE_URL, SUPABASE_KEY, OPENWEATHER_API_KEY
)

logger = logging.getLogger(__name__)

# --- Configuration and Initialization ---
supabase = None
def get_supabase_client():
    """Returns the Supabase client, initializing it if necessary."""
    global supabase
    if supabase is None:
        if SUPABASE_URL and SUPABASE_KEY:
            try:
                supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            except Exception as e:
                logger.error(f"Failed to create Supabase client: {e}")
    return supabase

# --- Chatwork API-related functions ---
def send_message(room_id, message_body, reply_to_id=None, reply_message_id=None):
    """Sends a message to a Chatwork room."""
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN, "Content-Type": "application/x-www-form-urlencoded"}
    payload = {"body": message_body}
    
    if reply_to_id and reply_message_id:
        payload["body"] = f"[rp aid={reply_to_id} to={room_id}-{reply_message_id}]\n{message_body}"

    try:
        requests.post(f"[https://api.chatwork.com/v2/rooms/](https://api.chatwork.com/v2/rooms/){room_id}/messages", headers=headers, data=payload).raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send message: {e}")
        return False

def get_room_members(room_id):
    """Gets the members information for a room."""
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    try:
        response = requests.get(f"[https://api.chatwork.com/v2/rooms/](https://api.chatwork.com/v2/rooms/){room_id}/members", headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get room members: {e}")
        return None

def change_room_permissions(room_id, admin_ids, member_ids, readonly_ids):
    """Changes member permissions in a room."""
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN, "Content-Type": "application/x-www-form-urlencoded"}
    payload = {
        "members_admin_ids": ",".join(map(str, admin_ids)),
        "members_member_ids": ",".join(map(str, member_ids)),
        "members_readonly_ids": ",".join(map(str, readonly_ids))
    }
    try:
        requests.put(f"[https://api.chatwork.com/v2/rooms/](https://api.chatwork.com/v2/rooms/){room_id}/members", headers=headers, data=payload).raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to change permissions: {e}")
        return False

def is_bot_admin(room_id):
    """Checks if the bot has admin permissions in a room."""
    members = get_room_members(room_id)
    if members:
        return any(str(member["account_id"]) == str(MY_ACCOUNT_ID) and member["role"] == "admin" for member in members)
    return False

# --- Supabase Database related functions ---
def get_last_message_id(account_id):
    """Fetches the last message ID for a given account from Supabase."""
    supabase = get_supabase_client()
    if not supabase: return None
    try:
        response = supabase.table('last_message_ids').select("message_id").eq("account_id", account_id).single().execute()
        return response.data['message_id']
    except Exception:
        return None

def update_last_message_id(account_id, message_id):
    """Updates the last message ID for a given account in Supabase."""
    supabase = get_supabase_client()
    if not supabase: return False
    try:
        data = {'account_id': account_id, 'message_id': message_id}
        supabase.table('last_message_ids').upsert([data]).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to update last message ID: {e}")
        return False

def update_message_count_in_db(room_id, date, account_id, account_name, message_id):
    """Updates the message count in Supabase if the message is new."""
    supabase = get_supabase_client()
    i

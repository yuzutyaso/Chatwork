import os
import logging
import re
import random
import requests
from datetime import datetime, timezone, timedelta
from utils import send_message, get_room_members, change_room_permissions, is_bot_admin, clean_message_body, \
    update_message_count_in_db, post_ranking, save_readonly_user_to_db, remove_readonly_user_from_db, \
    is_readonly_user_in_db, get_supabase_client

logger = logging.getLogger(__name__)

# --- グローバル変数 ---
omikuji_history = {}
# Chatwork絵文字の正規表現パターン
SINGLE_EMOJI_PATTERN = r"(?::\)|:\(|:D|8-\)|:o|;\)|;\(|:\*|:p|\(blush\)|:\^|\(inlove\)|\(sweat\)|\|\-\)|\]:D|\(talk\)|\(yawn\)|\(puke\)|\(emo\)|8-\||:\#|\(nod\)|\(shake\)|\(\^\^;\)|\(whew\)|\(clap\)|\(bow\)|\(roger\)|\(flex\)|\(dance\)|\(:/\)|\(gogo\)|\(think\)|\(please\)|\(quick\)|\(anger\)|\(devil\)|\(lightbulb\)|\(\*\)|\(h\)|\(F\)|\(cracker\)|\(eat\)|\(\^\)|\(coffee\)|\(beer\)|\(handshake\)|\(y\))"
MY_ACCOUNT_ID = os.environ.get("MY_ACCOUNT_ID")

def handle_webhook_event(webhook_event):
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
    elif ranking_match := re.match(r'^/ranking\s+(\d{4}/\d{1,2}/\d{1,2})$', cleaned_body):
        if str(room_id) == "407802259":
            post_ranking(room_id, ranking_match.group(1), account_id, message_id)
        else:
            send_message(room_id, "このコマンドは、指定されたルーム(407802259)でのみ有効です。", reply_to_id=account_id, reply_message_id=message_id)

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
    if str(room_id) == "364321548":
        jst = timezone(timedelta(hours=9), 'JST')
        today_date_str = datetime.now(jst).strftime("%Y/%#m/%#d")
        members = get_room_members(room_id)
        if members:
            account_name = next((m["name"] for m in members if str(m["account_id"]) == str(account_id)), "Unknown User")
            update_message_count_in_db(today_date_str, account_id, account_name)


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

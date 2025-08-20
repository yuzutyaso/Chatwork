import os
import json
import logging
import requests
import re
import random
from datetime import datetime, timezone, timedelta
from flask import Flask, request
from supabase import create_client, Client

# --- ロガー設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- 設定と初期化 ---
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

omikuji_history = {}
# Chatwork絵文字の正規表現パターン
SINGLE_EMOJI_PATTERN = r"(?::\)|:\(|:D|8-\)|:o|;\)|;\(|:\*|:p|\(blush\)|:\^|\(inlove\)|\(sweat\)|\|\-\)|\]:D|\(talk\)|\(yawn\)|\(puke\)|\(emo\)|8-\||:\#|\(nod\)|\(shake\)|\(\^\^;\)|\(whew\)|\(clap\)|\(bow\)|\(roger\)|\(flex\)|\(dance\)|\(:/\)|\(gogo\)|\(think\)|\(please\)|\(quick\)|\(anger\)|\(devil\)|\(lightbulb\)|\(\*\)|\(h\)|\(F\)|\(cracker\)|\(eat\)|\(\^\)|\(coffee\)|\(beer\)|\(handshake\)|\(y\))"

# --- Chatwork API関連の関数 ---
def send_message(room_id, message_body, reply_to_id=None, reply_message_id=None):
    """Chatworkの部屋にメッセージを送信する。"""
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
    """部屋のメンバー情報を取得する。"""
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    try:
        response = requests.get(f"https://api.chatwork.com/v2/rooms/{room_id}/members", headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get room members: {e}")
        return None

def change_room_permissions(room_id, admin_ids, member_ids, readonly_ids):
    """部屋のメンバー権限を変更する。"""
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

def mark_room_as_read(room_id):
    """指定された部屋の全てのメッセージを既読にする。"""
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    try:
        response = requests.put(f"https://api.chatwork.com/v2/rooms/{room_id}/messages/read", headers=headers)
        response.raise_for_status()
        logger.info(f"Successfully marked room {room_id} as read.")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to mark room {room_id} as read: {e}")
        return False

# --- Supabaseデータベース関連の関数 ---
def update_message_count_in_db(date, account_id, account_name):
    """Supabaseでメッセージ数を更新する。"""
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
    """メッセージ数ランキングを取得して投稿する。"""
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

def save_readonly_user_to_db(account_id):
    """閲覧者になったユーザーをデータベースに保存する。"""
    if not supabase: return
    try:
        supabase.table('readonly_users').insert({
            "account_id": account_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }).execute()
        logger.info(f"User {account_id} saved to readonly_users.")
    except Exception as e:
        logger.error(f"Failed to save user to readonly_users: {e}")

def remove_readonly_user_from_db(account_id):
    """閲覧者リストからユーザーを削除する。"""
    if not supabase: return
    try:
        response = supabase.table('readonly_users').delete().eq('account_id', account_id).execute()
        return bool(response.data)
    except Exception as e:
        logger.error(f"Failed to delete from readonly_users: {e}")
        return False

def is_readonly_user_in_db(account_id):
    """ユーザーが閲覧者リストに存在するか確認する。"""
    if not supabase: return False
    try:
        response = supabase.table('readonly_users').select("account_id").eq("account_id", account_id).execute()
        return bool(response.data)
    except Exception as e:
        logger.error(f"Supabase check for readonly_users failed: {e}")
        return False

# --- コマンドハンドリング関数 ---
def handle_test_command(room_id, account_id, message_id):
    """/testコマンドを処理する。"""
    jst = timezone(timedelta(hours=9), 'JST')
    current_time = datetime.now(jst).strftime("%Y/%m/%d %H:%M:%S")
    send_message(room_id, f"現在の時刻は {current_time} です。", reply_to_id=account_id, reply_message_id=message_id)

def handle_omikuji_command(room_id, account_id, message_id):
    """おみくじコマンドを処理する。"""
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
    """/sorryコマンドを処理して、閲覧者リストからユーザーを削除する。"""
    if not supabase:
        send_message(room_id, "データベースが利用できません。", reply_to_id=sender_id, reply_message_id=message_id)
        return

    # 管理者権限の確認
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
    """/roominfoコマンドを処理する。"""
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
    """権限リストコマンドを処理する（/blacklist, /admin, /member）。"""
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

# --- Webhookハンドラー ---
@app.route("/", methods=["POST"])
def chatwork_webhook():
    """メインのWebhookハンドラー。"""
    try:
        data = request.json
        webhook_event = data.get("webhook_event")
        room_id = webhook_event.get("room_id")
        
        # Webhookイベントにroom_idが含まれていない場合は無視
        if not room_id:
            logger.info("Received a non-webhook event. Ignoring.")
            return "", 200

        mark_room_as_read(room_id)

        message_body = webhook_event.get("body")
        account_id = webhook_event.get("account_id")
        message_id = webhook_event.get("message_id")
        cleaned_body = clean_message_body(message_body)

        if str(account_id) == str(MY_ACCOUNT_ID): return "", 200

        # Supabaseの閲覧者リストにユーザーがいるか確認し、いれば即座に閲覧者に変更
        if is_readonly_user_in_db(account_id) and is_bot_admin(room_id):
            members = get_room_members(room_id)
            if members:
                admin_ids = [m["account_id"] for m in members if m["role"] == "admin" and str(m["account_id"]) != str(account_id)]
                member_ids = [m["account_id"] for m in members if m["role"] == "member" and str(m["account_id"]) != str(account_id)]
                readonly_ids = [m["account_id"] for m in members if str(m["account_id"]) != str(account_id)]
                readonly_ids.append(account_id)
                
                if change_room_permissions(room_id, admin_ids, member_ids, readonly_ids):
                    send_message(room_id, "このユーザーは過去に閲覧権限に変更されたため、権限を『閲覧』に設定しました。", reply_to_id=account_id, reply_message_id=message_id)
            return "", 200

        # 各コマンドのハンドリング
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
        
        # 荒らし判定ロジック
        emoji_matches = re.findall(SINGLE_EMOJI_PATTERN, message_body)
        if "[toall]" in message_body.lower() or len(emoji_matches) >= 15:
            if is_bot_admin(room_id):
                members = get_room_members(room_id)
                if members:
                    admin_ids = [m["account_id"] for m in members if m["role"] == "admin" and str(m["account_id"]) != str(account_id)]
                    member_ids = [m["account_id"] for m in members if m["role"] == "member" and str(m["account_id"]) != str(account_id)]
                    readonly_ids = [m["account_id"] for m in members if str(m["account_id"]) != str(account_id)]
                    readonly_ids.append(account_id)
                    
                    if change_room_permissions(room_id, admin_ids, member_ids, readonly_ids):
                        send_message(room_id, "メッセージを送信したユーザーの権限を『閲覧』に変更しました。", reply_to_id=account_id, reply_message_id=message_id)
                        save_readonly_user_to_db(account_id)
                    else:
                        send_message(room_id, "権限の変更に失敗しました。ボットに管理者権限があるか、権限の変更が許可されているか確認してください。", reply_to_id=account_id, reply_message_id=message_id)
            else:
                send_message(room_id, "私はこの部屋の管理者ではありません。権限を変更できません。", reply_to_id=account_id, reply_message_id=message_id)

        # メッセージ数カウント
        if str(room_id) == "364321548":
            jst = timezone(timedelta(hours=9), 'JST')
            today_date_str = datetime.now(jst).strftime("%Y/%#m/%#d")
            members = get_room_members(room_id)
            if members:
                account_name = next((m["name"] for m in members if str(m["account_id"]) == str(account_id)), "Unknown User")
                update_message_count_in_db(today_date_str, account_id, account_name)

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        # エラーメッセージを送信
        if 'room_id' in locals() and 'account_id' in locals() and 'message_id' in locals():
            send_message(room_id, "処理中にエラーが発生しました。", reply_to_id=account_id, reply_message_id=message_id)

    return "", 200

if __name__ == "__main__":
    app.run()

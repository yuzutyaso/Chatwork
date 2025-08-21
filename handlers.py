# handlers.py
import json
import logging
from datetime import datetime, date, timedelta
from services import (
    send_message,
    is_bot_admin,
    change_room_permissions,
    post_personal_ranking,
    get_message_count_for_ranking,
    reset_message_counts,
    get_weather_info,
    update_room_info_in_db,
    is_readonly_user_in_db,
    save_readonly_user_to_db,
    remove_readonly_user_from_db,
    get_all_room_info_from_db,
    update_message_count_in_db
)
from apscheduler.schedulers.background import BackgroundScheduler
from constants import MY_ACCOUNT_ID, CHATWORK_API_TOKEN

logger = logging.getLogger(__name__)

# スケジューラーの初期化
scheduler = BackgroundScheduler(daemon=True, timezone='Asia/Tokyo')

# --- APschedulerのジョブ ---

def post_ranking_job():
    """
    ランキング集計のメッセージをすべてのルームに投稿するジョブ。
    """
    yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
    room_ranking_data = get_message_count_for_ranking(yesterday)
    
    if not room_ranking_data:
        logger.info(f"No message count data found for {yesterday}. Skipping ranking post.")
        return

    # 全ての部屋にランキングを投稿
    message_body = f"【{yesterday} の部屋別メッセージ数ランキング】"
    rank_list = [f"{rank}位: {room_id} ({count}件)" for rank, (room_id, count) in enumerate(room_ranking_data.items(), 1)]
    
    room_info_data = get_all_room_info_from_db()

    formatted_message = f"【{yesterday} の部屋別メッセージ数ランキング】\n"
    for rank, (room_id, count) in enumerate(room_ranking_data.items(), 1):
        room_name = room_info_data.get(room_id, {}).get("room_name", "Unknown Room")
        formatted_message += f"{rank}位: {room_name} ({count}件)\n"

    for room_id in room_ranking_data.keys():
        send_message(room_id, formatted_message)
        
    # 前日のデータを削除
    reset_message_counts(yesterday)


# スケジュール設定
if not scheduler.running:
    scheduler.add_job(post_ranking_job, 'cron', hour=16, minute=1)
    scheduler.start()

# --- コマンドハンドラー ---

def handle_help_command(room_id, reply_to_id, reply_message_id):
    """
    ヘルプメッセージを送信します。
    """
    help_text = (
        "【Chatbotコマンド一覧】\n"
        "[rp aid={}] ランキング: 前日の部屋別メッセージ数ランキングを表示します。\n"
        "[rp aid={}] 個人ランキング: 前日の個人メッセージ数ランキングを表示します。\n"
        "[rp aid={}] 天気 [都市名]: 指定された都市の天気情報を表示します。\n"
        "[rp aid={}] bot管理者設定: botの管理者を設定します。\n"
        "[rp aid={}] 読み取り専用ユーザー設定: 読み取り専用ユーザーを設定します。\n"
    )
    # The reply_to_id needs to be included dynamically in the message, so we format it
    send_message(
        room_id,
        help_text.format(reply_to_id, reply_to_id, reply_to_id, reply_to_id, reply_to_id),
        reply_to_id=reply_to_id,
        reply_message_id=reply_message_id
    )

def handle_ranking_command(room_id, reply_to_id, reply_message_id):
    """
    前日の部屋別メッセージ数ランキングを投稿します。
    """
    yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
    room_ranking_data = get_message_count_for_ranking(yesterday)
    
    if not room_ranking_data:
        send_message(room_id, f"昨日のデータが見つかりませんでした。", reply_to_id=reply_to_id, reply_message_id=reply_message_id)
        return
        
    room_info_data = get_all_room_info_from_db()
    formatted_message = f"【{yesterday} の部屋別メッセージ数ランキング】\n"
    for rank, (room_id_rank, count) in enumerate(room_ranking_data.items(), 1):
        room_name = room_info_data.get(room_id_rank, {}).get("room_name", "Unknown Room")
        formatted_message += f"{rank}位: {room_name} ({count}件)\n"
    
    send_message(room_id, formatted_message, reply_to_id=reply_to_id, reply_message_id=reply_message_id)


def handle_weather_command(room_id, content, reply_to_id, reply_message_id):
    """
    天気情報を取得して送信します。
    """
    city_name = content.replace("天気", "").strip()
    if city_name:
        weather_info = get_weather_info(city_name)
        send_message(room_id, weather_info, reply_to_id=reply_to_id, reply_message_id=reply_message_id)
    else:
        send_message(room_id, "都市名を指定してください。例: 天気 東京", reply_to_id=reply_to_id, reply_message_id=reply_message_id)

def handle_admin_permission_command(room_id, reply_to_id, reply_message_id):
    """
    ボットに管理者権限を付与するように促すメッセージを送信します。
    """
    if not is_bot_admin(room_id):
        send_message(
            room_id,
            f"[To:{reply_to_id}] 管理者設定にはbotがこの部屋の管理者である必要があります。管理者アカウントでbotのロールを「管理者」に変更してください。",
            reply_to_id=reply_to_id,
            reply_message_id=reply_message_id
        )
    else:
        send_message(
            room_id,
            f"[To:{reply_to_id}] botはすでにこの部屋の管理者です。",
            reply_to_id=reply_to_id,
            reply_message_id=reply_message_id
        )

def handle_readonly_user_command(room_id, content, reply_to_id, reply_message_id, mentioned_account_id):
    """
    読み取り専用ユーザーを設定または解除します。
    """
    if not is_bot_admin(room_id):
        send_message(
            room_id,
            f"読み取り専用ユーザーの設定にはbotがこの部屋の管理者である必要があります。",
            reply_to_id=reply_to_id,
            reply_message_id=reply_message_id
        )
        return

    command_parts = content.strip().split()
    if len(command_parts) < 2:
        send_message(
            room_id,
            "コマンドの形式が正しくありません。[rp aid=xxxx] 読み取り専用ユーザー設定 [追加/削除] [To:アカウントID] の形式で入力してください。",
            reply_to_id=reply_to_id,
            reply_message_id=reply_message_id
        )
        return

    action = command_parts[1]
    
    if action == "追加":
        if is_readonly_user_in_db(mentioned_account_id):
            send_message(room_id, f"ユーザー [To:{mentioned_account_id}] はすでに読み取り専用ユーザーです。", reply_to_id=reply_to_id, reply_message_id=reply_message_id)
        else:
            save_readonly_user_to_db(mentioned_account_id)
            send_message(room_id, f"ユーザー [To:{mentioned_account_id}] を読み取り専用ユーザーに追加しました。", reply_to_id=reply_to_id, reply_message_id=reply_message_id)
    elif action == "削除":
        if remove_readonly_user_from_db(mentioned_account_id):
            send_message(room_id, f"ユーザー [To:{mentioned_account_id}] を読み取り専用ユーザーから削除しました。", reply_to_id=reply_to_id, reply_message_id=reply_message_id)
        else:
            send_message(room_id, f"ユーザー [To:{mentioned_account_id}] は読み取り専用ユーザーではありません。", reply_to_id=reply_to_id, reply_message_id=reply_message_id)
    else:
        send_message(
            room_id,
            "アクションは「追加」または「削除」のいずれかを指定してください。",
            reply_to_id=reply_to_id,
            reply_message_id=reply_message_id
        )


# --- メインハンドラー ---

def handle_webhook_event(event):
    """
    ChatworkのWebhookイベントを処理します。
    """
    try:
        # メッセージデータの抽出
        room_id = event["webhook_event"]["room_id"]
        message_id = event["webhook_event"]["message_id"]
        body = event["webhook_event"]["body"]
        account_id = event["webhook_event"]["account_id"]
        account_name = event["webhook_event"]["account"]["name"]
        
        # Room情報をデータベースに保存
        room_name = event["webhook_event"]["room"]["name"]
        update_room_info_in_db(room_id, room_name)

        # 読み取り専用ユーザーかチェック
        if is_readonly_user_in_db(account_id):
            return {"status": "User is readonly"}

        # メッセージ数をカウント
        today = date.today().isoformat()
        update_message_count_in_db(room_id, today, account_id, account_name, message_id)
        
        # 返信情報の抽出
        reply_to_id = event["webhook_event"]["account_id"]
        reply_message_id = event["webhook_event"]["message_id"]

        # メンションされたアカウントIDの抽出
        mentioned_account_id = None
        mention_match = json.loads(event["webhook_event"]["body"]).get("mention_match")
        if mention_match:
            mentioned_account_id = mention_match.get("account_id")

        # コマンドの判定
        if "help" in body.lower():
            handle_help_command(room_id, reply_to_id, reply_message_id)
        elif "ランキング" in body:
            handle_ranking_command(room_id, reply_to_id, reply_message_id)
        elif "個人ランキング" in body:
            target_date = date.today().isoformat()
            post_personal_ranking(room_id, target_date, reply_to_id, reply_message_id)
        elif "天気" in body:
            handle_weather_command(room_id, body, reply_to_id, reply_message_id)
        elif "bot管理者設定" in body:
            handle_admin_permission_command(room_id, reply_to_id, reply_message_id)
        elif "読み取り専用ユーザー設定" in body and mentioned_account_id:
            handle_readonly_user_command(room_id, body, reply_to_id, reply_message_id, mentioned_account_id)
        
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error handling webhook event: {e}")
        return {"status": "error", "message": str(e)}

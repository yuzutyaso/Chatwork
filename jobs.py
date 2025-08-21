import os
import time
import requests
import schedule
import threading
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pytz import timezone

from db import supabase
from commands import COMMANDS
from utils import is_admin, send_message_to_chatwork, change_user_role
from jobs import time_report_job, ranking_post_job

# 環境変数の読み込み
load_dotenv()

# --- 環境変数の設定 ---
BOT_ACCOUNT_ID = os.getenv("BOT_ACCOUNT_ID")
EMOJIS = [
    ':)', ':(', ':D', '8-)', ':o', ';)', '((sweat))', ':|', ':*', ':p', '(blush)',
    ':^)', '|-)', '(inlove)', ':]', '(talk)', '(yawn)', '(puke)', '(emo)', '8-|',
    ':#', '(nod)', '(shake)', '(^^;)', '(whew)', '(clap)', '(bow)', '(roger)',
    '(flex)', '(dance)', '(:/)', '(gogo)', '(think)', '(please)', '(quick)',
    '(anger)', '(devil)', '(lightbulb)', '(*)', '(h)', '(F)', '(cracker)',
    '(eat)', '(^)', '(coffee)', '(beer)', '(handshake)', '(y)'
]

# Flaskアプリケーションの初期化
app = Flask(__name__)

# 管理者権限が必要なコマンドリスト
ADMIN_COMMANDS = ["/say", "/echo", "/削除", "/時報", "/recount"]

# --- メッセージ処理を関数に分離 ---
def handle_message(room_id, message_id, account_id, message_body):
    """
    受信したメッセージを処理し、コマンド実行や権限チェックを行う関数。
    """
    # ユーザーごとのメッセージ数カウント
    today = datetime.now().date().isoformat()
    response_user = supabase.table('user_message_counts').select('message_count', 'last_message_id').eq('user_id', account_id).eq('room_id', room_id).eq('message_date', today).execute()

    if response_user.data:
        current_count = response_user.data[0]['message_count']
        last_message_id_str = response_user.data[0].get('last_message_id')
        last_message_id = int(last_message_id_str) if last_message_id_str is not None else None

        if last_message_id is None or int(message_id) > last_message_id:
            supabase.table('user_message_counts').update({"message_count": current_count + 1, "last_message_id": message_id}).eq('user_id', account_id).eq('room_id', room_id).eq('message_date', today).execute()
    else:
        supabase.table('user_message_counts').insert({"user_id": account_id, "room_id": room_id, "message_date": today, "message_count": 1, "last_message_id": message_id}).execute()

    # コマンドの判定
    parts = message_body.split()
    command_name = parts[0] if parts else ""

    # コマンドの実行
    if command_name in COMMANDS:
        # 管理者権限が必要なコマンドかチェック
        if command_name in ADMIN_COMMANDS and not is_admin(room_id, account_id):
            send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nこのコマンドは管理者のみが実行できます。")
            return

        # timerコマンドはスレッドで実行
        if command_name == "/timer":
            thread = threading.Thread(target=COMMANDS[command_name], args=(room_id, message_id, account_id, message_body))
            thread.start()
        else:
            COMMANDS[command_name](room_id, message_id, account_id, message_body)

    # 特殊なメッセージの処理
    else:
        is_admin_user = is_admin(room_id, account_id)
        if "[toall]" in message_body:
            if is_admin_user:
                send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n[toall]タグの使用は控えてください。")
            else:
                change_user_role(room_id, account_id, 'readonly')
                send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n[toall]タグが検出されたため、権限を閲覧に変更しました。")

        emoji_count = sum(message_body.count(emoji) for emoji in EMOJIS)
        if emoji_count >= 15:
            if is_admin_user:
                send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n絵文字が多すぎます。ご注意ください。")
            else:
                change_user_role(room_id, account_id, 'readonly')
                send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n絵文字が多すぎるため、権限を閲覧に変更しました。")


# --- Webhookのコールバック関数 ---
@app.route('/callback', methods=['POST'])
def chatwork_callback():
    data = request.json
    if data and data['webhook_event_type'] == 'message_created':
        room_id = data['webhook_event']['room_id']
        message_id = data['webhook_event']['message_id']
        account_id = data['webhook_event']['account_id']
        message_body = data['webhook_event']['body']

        if str(account_id) == str(BOT_ACCOUNT_ID):
            return jsonify({'status': 'ok'})

        handle_message(room_id, message_id, account_id, message_body)

    return jsonify({'status': 'ok'})

# --- スケジューラースレッド ---
def run_scheduler():
    """
    スケジュールされたジョブを実行するための専用スレッド。
    """
    while True:
        schedule.run_pending()
        time.sleep(1)

# --- Flaskアプリケーションの実行 ---
if __name__ == '__main__':
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.start()

    jst_tz = timezone('Asia/Tokyo')
    schedule.every().day.at("00:00", tz=jst_tz).do(ranking_post_job)
    schedule.every(1).minutes.do(time_report_job)

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

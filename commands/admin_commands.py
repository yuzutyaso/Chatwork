import os
import re
import psutil
import requests
from datetime import datetime

# 修正: 相対インポートを絶対インポートに
from db import supabase
from utils import send_reply, send_message_to_chatwork, get_chatwork_members

CHATWORK_API_TOKEN = os.getenv("CHATWORK_API_TOKEN")

def log_command(room_id, message_id, account_id, message_body):
    """
    /log [行数] コマンドの処理 (管理者のみ)
    最新のログを表示する
    """
    send_reply(room_id, message_id, account_id, "⚠️ このコマンドは現在開発中です。ログはRenderのダッシュボードからご確認ください。")

def stats_command(room_id, message_id, account_id, message_body):
    """
    /stats コマンドの処理 (管理者のみ)
    サーバーとデータベースの統計情報を表示する
    """
    try:
        cpu_usage = psutil.cpu_percent(interval=1)
        mem_info = psutil.virtual_memory()
        
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        hours, remainder = divmod(uptime.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        message_count_res = supabase.table('user_message_counts').select('id', count='exact').execute()
        total_messages = message_count_res.count if message_count_res.count else 0
        
        info_message = f"""
        🤖 **ボットシステム統計**
        ---
        **CPU使用率**: {cpu_usage}%
        **メモリ使用率**: {mem_info.percent}%
        **稼働時間**: {int(hours)}h {int(minutes)}m {int(seconds)}s
        **データベース統計**:
        - メッセージ総数: {total_messages}件
        """
        
        send_reply(room_id, message_id, account_id, info_message)
        
    except Exception as e:
        send_reply(room_id, message_id, account_id, f"システム統計情報取得中にエラーが発生しました: {e}")

def recount_command(room_id, message_id, account_id, message_body):
    """
    /recount コマンドの処理 (管理者のみ)
    指定された部屋のメッセージ数を再集計する
    """
    match = re.search(r'/recount\s+(\d+)?', message_body)
    target_room_id = int(match.group(1)) if match and match.group(1) else room_id
    try:
        supabase.table('user_message_counts').delete().eq('room_id', target_room_id).execute()
        send_reply(room_id, message_id, account_id, f"ルームID {target_room_id} のメッセージ数カウントデータをリセットします。過去100件のメッセージを再集計しています...")
        messages_response = requests.get(
            f"https://api.chatwork.com/v2/rooms/{target_room_id}/messages",
            headers={"X-ChatWorkToken": CHATWORK_API_TOKEN},
            params={"count": 100}
        )
        messages_response.raise_for_status()
        messages = messages_response.json()
        if not messages:
            send_reply(room_id, message_id, account_id, f"ルームID {target_room_id} には過去100件のメッセージがありませんでした。")
            return
        messages.reverse()
        counts = {}
        for msg in messages:
            msg_date = datetime.fromtimestamp(msg['send_time']).date().isoformat()
            user_id = msg['account']['account_id']
            key = (user_id, msg_date)
            if key not in counts:
                counts[key] = {'count': 0, 'last_message_id': msg['message_id']}
            counts[key]['count'] += 1
        insert_data = []
        for (user_id, msg_date), data in counts.items():
            insert_data.append({
                "user_id": user_id,
                "room_id": target_room_id,
                "message_date": msg_date,
                "message_count": data['count'],
                "last_message_id": data['last_message_id']
            })
        if insert_data:
            supabase.table('user_message_counts').insert(insert_data).execute()
        send_reply(room_id, message_id, account_id, f"ルームID {target_room_id} の過去100件のメッセージの再集計が完了しました。")
    except requests.exceptions.RequestException as e:
        send_reply(room_id, message_id, account_id, f"再集計中にAPIエラーが発生しました: {e}")
    except Exception as e:
        send_reply(room_id, message_id, account_id, f"再集計中に予期せぬエラーが発生しました: {e}")

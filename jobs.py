import requests
import os
from datetime import datetime
from pytz import timezone

from utils import send_chatwork_message
from db import supabase

# ChatWork APIトークンを環境変数から取得
CHATWORK_API_TOKEN = os.getenv("CHATWORK_API_TOKEN")

def time_report_job():
    """時報を分単位で投稿するジョブ"""
    try:
        # pytzを使用して日本時間（JST）を取得
        jst_tz = timezone('Asia/Tokyo')
        now_jst = datetime.now(jst_tz)
        current_minute = now_jst.minute
        
        # データベースからレポート対象のルームIDと設定間隔を取得
        response = supabase.table('hourly_report_rooms').select('room_id', 'interval_minutes').execute()
        
        for room in response.data:
            room_id = room['room_id']
            # interval_minutesが存在しない場合は60分をデフォルトとする
            interval = room.get('interval_minutes', 60)
            
            # 現在の分が設定間隔の倍数である場合にメッセージを投稿
            if current_minute % interval == 0:
                message = f"現在時刻は {now_jst.strftime('%H:%M')} です。今日も一日頑張りましょう！"
                send_chatwork_message(room_id, message)

    except Exception as e:
        print(f"時報ジョブの実行中にエラーが発生しました: {e}")

def ranking_post_job():
    """日次のメッセージ数ランキングを投稿するジョブ"""
    try:
        today = datetime.now().date().isoformat()
        
        # すべてのルームのランキングを取得
        all_rooms_response = supabase.table('user_message_counts').select('room_id').order('room_id').execute()
        room_ids = list(set([item['room_id'] for item in all_rooms_response.data]))

        # 日付変更のメッセージを投稿
        new_day_message = "日付が変わりました。新しい日を頑張りましょう！"
        for room_id in room_ids:
            send_chatwork_message(room_id, new_day_message)

        # ランキングを投稿
        for room_id in room_ids:
            response = supabase.table('user_message_counts').select('*').eq('message_date', today).eq('room_id', room_id).order('message_count', desc=True).limit(10).execute()
            
            if response.data:
                # 部屋の情報を取得
                room_info = requests.get(f"https://api.chatwork.com/v2/rooms/{room_id}", headers={"X-ChatWorkToken": CHATWORK_API_TOKEN}).json()
                room_name = room_info['name']
                
                # ユーザー情報を取得
                members_response = requests.get(f"https://api.chatwork.com/v2/rooms/{room_id}/members", headers={"X-ChatWorkToken": CHATWORK_API_TOKEN})
                members = members_response.json()
                user_names = {member['account_id']: member['name'] for member in members}

                message_title = f"{room_name}の{today}個人メッセージ数ランキング\n---\n"
                message_list = ""
                
                for i, item in enumerate(response.data):
                    user_name = user_names.get(item['user_id'], f"ユーザーID {item['user_id']}")
                    message_list += f"{i+1}位: {user_name}さん - {item['message_count']}メッセージ\n"
                
                send_chatwork_message(room_id, f"{message_title}{message_list}")

    except Exception as e:
        print(f"日次ランキングジョブの実行中にエラーが発生しました: {e}")

import requests
import os
from datetime import datetime
from pytz import timezone

from utils import send_chatwork_message
from db import supabase

# ChatWork APIトークンを環境変数から取得
CHATWORK_API_TOKEN = os.getenv("CHATWORK_API_TOKEN")

def hourly_report_job():
    """毎時のメッセージ数レポートを投稿するジョブ"""
    try:
        # pytzを使用して日本時間（JST）を取得
        jst_tz = timezone('Asia/Tokyo')
        now_jst = datetime.now(jst_tz)
        current_hour = now_jst.hour
        
        # データベースからレポート対象のルームIDを取得
        response = supabase.table('hourly_report_rooms').select('room_id').execute()
        room_ids = [room['room_id'] for room in response.data]

        for room_id in room_ids:
            message = f"現在時刻は {current_hour}:00 です。今日も一日頑張りましょう！"
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

import os
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

from db import supabase
from utils import send_chatwork_message, get_chatwork_members

# 環境変数の読み込み
load_dotenv()
CHATWORK_API_TOKEN = os.getenv("CHATWORK_API_TOKEN")

def hourly_report_job():
    """毎時00分に時報を投稿するジョブ"""
    try:
        response = supabase.table('hourly_report_rooms').select('room_id').execute()
        room_ids_to_notify = [item['room_id'] for item in response.data]
        current_time = datetime.now().strftime("%H時%M分")
        message = f"現在の時刻は {current_time} です。"
        for room_id in room_ids_to_notify:
            send_chatwork_message(room_id, message)
    except Exception as e:
        print(f"時報の定期実行中にエラーが発生しました: {e}")

def ranking_post_job():
    """毎日00:00にランキングを投稿するジョブ"""
    yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
    room_id_renren = 364321548 
    room_id_ranking_post = 407802259

    # 昨日の個人ランキングを投稿
    try:
        response = supabase.table('user_message_counts').select('*').eq('message_date', yesterday).eq('room_id', room_id_renren).order('message_count', desc=True).limit(10).execute()
        if response.data:
            members = get_chatwork_members(room_id_renren)
            user_names = {member['account_id']: member['name'] for member in members}
            message = f"昨日のれんれんの部屋の個人メッセージ数ランキング\n---\n"
            for i, item in enumerate(response.data):
                user_name = user_names.get(item['user_id'], f"ユーザーID {item['user_id']}")
                message += f"{i+1}位: {user_name}さん - {item['message_count']}メッセージ\n"
            send_chatwork_message(room_id_ranking_post, message)
    except Exception as e:
        print(f"個人ランキングの定期投稿中にエラーが発生しました: {e}")

    # 本日の全ルームランキングを投稿
    try:
        response = supabase.table('room_message_counts').select('*').order('message_count', desc=True).limit(10).execute()
        if response.data:
            message = f"本日の全ルームメッセージ数ランキング\n---\n"
            for i, item in enumerate(response.data):
                try:
                    room_info = requests.get(f"https://api.chatwork.com/v2/rooms/{item['room_id']}", headers={"X-ChatWorkToken": CHATWORK_API_TOKEN}).json()
                    room_name = room_info.get('name', '取得失敗')
                    message += f"{i+1}位: {room_name} - {item['message_count']}メッセージ\n"
                except Exception:
                    message += f"{i+1}位: ルームID {item['room_id']} (部屋名取得失敗) - {item['message_count']}メッセージ\n"
            send_chatwork_message(room_id_ranking_post, message)
            supabase.table('room_message_counts').delete().neq('id', 0).execute()
    except Exception as e:
        print(f"全ルームランキングの定期投稿中にエラーが発生しました: {e}")

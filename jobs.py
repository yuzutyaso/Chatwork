import os
import time
from datetime import datetime, timedelta
from utils import send_chatwork_message
from main import supabase

def hourly_report_job():
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
    yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
    room_id_renren = 364321548 
    room_id_ranking_post = 407802259
    try:
        response = supabase.table('user_message_counts').select('*').eq('message_date', yesterday).eq('room_id', room_id_renren).order('message_count', desc=True).limit(10).execute()
        if response.data:
            message = f"昨日のれんれんの部屋の個人メッセージ数ランキング\n---\n"
            for i, item in enumerate(response.data):
                message += f"{i+1}位: ユーザーID {item['user_id']}さん - {item['message_count']}メッセージ\n"
            send_chatwork_message(room_id_ranking_post, message)
    except Exception as e:
        print(f"個人ランキングの定期投稿中にエラーが発生しました: {e}")

    try:
        response = supabase.table('room_message_counts').select('*').order('message_count', desc=True).limit(10).execute()
        if response.data:
            message = f"昨日の全ルームメッセージ数ランキング\n---\n"
            for i, item in enumerate(response.data):
                message += f"{i+1}位: ルームID {item['room_id']} - {item['message_count']}メッセージ\n"
            send_chatwork_message(room_id_ranking_post, message)
            supabase.table('room_message_counts').delete().neq('id', 0).execute()
    except Exception as e:
        print(f"全ルームランキングの定期投稿中にエラーが発生しました: {e}")

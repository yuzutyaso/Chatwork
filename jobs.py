import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pytz import timezone

from db import supabase
from utils import send_message_to_chatwork, get_chatwork_members

# 環境変数の読み込み
load_dotenv()
CHATWORK_API_TOKEN = os.getenv("CHATWORK_API_TOKEN")

def time_report_job():
    """設定されたルームに時報を投稿するジョブ"""
    try:
        response = supabase.table('hourly_report_rooms').select('room_id', 'interval_minutes').execute()
        rooms_to_report = response.data

        if not rooms_to_report:
            return

        for room in rooms_to_report:
            room_id = room['room_id']
            interval = room['interval_minutes']
            now_jst = datetime.now(timezone('Asia/Tokyo'))
            
            # 分が設定された間隔の倍数であるかを確認
            if now_jst.minute % interval == 0:
                message = f"現在の時刻をお知らせします。{now_jst.strftime('%Y/%m/%d %H:%M')}"
                send_message_to_chatwork(room_id, message)

    except Exception as e:
        print(f"時報ジョブの実行中にエラーが発生しました: {e}")

def ranking_post_job():
    """メッセージ数ランキングを毎日投稿するジョブ"""
    try:
        yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
        
        response = supabase.table('ranking_rooms').select('room_id').execute()
        ranking_rooms = response.data
        
        if not ranking_rooms:
            print("ランキングを投稿する設定の部屋がありません。")
            return

        for room in ranking_rooms:
            room_id = room['room_id']
            
            ranking_data_response = supabase.table('user_message_counts').select('user_id', 'message_count').eq('room_id', room_id).eq('message_date', yesterday).order('message_count', desc=True).limit(5).execute()
            ranking_data = ranking_data_response.data
            
            if not ranking_data:
                send_message_to_chatwork(room_id, f"{yesterday}のメッセージ数ランキングはまだありませんでした。")
                continue
                
            members = get_chatwork_members(room_id)
            user_names = {member['account_id']: member['name'] for member in members}
            
            ranking_message = f"{yesterday}のメッセージ数ランキング🎉\n"
            ranking_message += "---\n"
            
            for i, data in enumerate(ranking_data):
                user_id = data['user_id']
                count = data['message_count']
                user_name = user_names.get(user_id, f"ユーザーID:{user_id}")
                ranking_message += f"{i+1}位: {user_name}さん ({count}件)\n"
            
            send_message_to_chatwork(room_id, ranking_message)

    except Exception as e:
        print(f"ランキング投稿ジョブの実行中にエラーが発生しました: {e}")

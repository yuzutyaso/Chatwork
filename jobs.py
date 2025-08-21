import os
import requests
from datetime import datetime, timedelta
from db import supabase
from utils import get_chatwork_members, send_chatwork_message

# ChatWork APIトークンを環境変数から取得
CHATWORK_API_TOKEN = os.getenv("CHATWORK_API_TOKEN")

# ランキングを投稿する特定のルームID
RANKING_ROOM_ID = "407802259"

def hourly_report_job():
    """毎時の時報を投稿するジョブ"""
    try:
        response = supabase.table('hourly_report_rooms').select('room_id').execute()
        rooms = response.data
        
        jst = datetime.now()

        for room in rooms:
            room_id = room['room_id']
            message = f"現在時刻は {jst.strftime('%H:%M')} です。今日も一日頑張りましょう！"
            
            headers = { "X-ChatWorkToken": CHATWORK_API_TOKEN }
            payload = { "body": message }
            
            requests.post(
                f"https://api.chatwork.com/v2/rooms/{room_id}/messages",
                headers=headers,
                data=payload
            )
            print(f"時報をルーム {room_id} に投稿しました。")
            
    except Exception as e:
        print(f"時報の投稿中にエラーが発生しました: {e}")

def ranking_post_job():
    """メッセージ数ランキングを指定されたルームに投稿するジョブ"""
    
    # 前日の日付を取得
    yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
    
    try:
        # --- 個人メッセージ数ランキングを投稿 ---
        response_user = supabase.table('user_message_counts').select('*').eq('room_id', RANKING_ROOM_ID).eq('message_date', yesterday).order('message_count', desc=True).limit(10).execute()
        user_ranks = response_user.data
        
        if user_ranks:
            members = get_chatwork_members(RANKING_ROOM_ID)
            user_names = {member['account_id']: member['name'] for member in members}
            
            message = f"【{yesterday}】メッセージ数ランキング\n---\n"
            
            for i, item in enumerate(user_ranks):
                user_name = user_names.get(item['user_id'], f"ユーザーID {item['user_id']}")
                message_count = item['message_count']
                message += f"{i+1}位: {user_name}さん - {message_count}メッセージ\n"
            
            send_chatwork_message(RANKING_ROOM_ID, message)
            print(f"ルーム {RANKING_ROOM_ID} に個人メッセージ数ランキングを投稿しました。")
        else:
            print(f"ルーム {RANKING_ROOM_ID} の前日メッセージデータがありません。")

        # --- 全ルームのメッセージ数ランキングを投稿 ---
        response_room = supabase.table('room_message_counts').select('*').order('message_count', desc=True).limit(10).execute()
        room_ranks = response_room.data

        if room_ranks:
            message = "【全期間】ルーム別メッセージ数ランキング\n---\n"
            for i, item in enumerate(room_ranks):
                try:
                    room_info = requests.get(f"https://api.chatwork.com/v2/rooms/{item['room_id']}", headers={"X-ChatWorkToken": CHATWORK_API_TOKEN}).json()
                    room_name = room_info.get('name', '取得失敗')
                    message += f"{i+1}位: {room_name} - {item['message_count']}メッセージ\n"
                except Exception:
                    message += f"{i+1}位: ルームID {item['room_id']} (部屋名取得失敗) - {item['message_count']}メッセージ\n"
            
            send_chatwork_message(RANKING_ROOM_ID, message)
            print(f"ルーム {RANKING_ROOM_ID} に全ルームメッセージ数ランキングを投稿しました。")
        else:
            print("全ルームのメッセージデータがありません。")

    except Exception as e:
        print(f"ランキングの投稿中にエラーが発生しました: {e}")

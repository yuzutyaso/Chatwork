import os
import requests
import json
import logging
import pytz
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from collections import defaultdict
from functools import lru_cache
from dateutil.parser import parse

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 環境変数から設定を取得 ---
CHATWORK_API_TOKEN = os.environ.get("CHATWORK_API_TOKEN")
MY_ACCOUNT_ID = os.environ.get("MY_ACCOUNT_ID")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
REPORT_ROOM_ID = os.environ.get("REPORT_ROOM_ID")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")

# --- Supabaseクライアントの初期化 ---
@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Initializes and returns a Supabase client."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Supabase URL or Key is not set.")
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Chatwork API関数 ---
def send_message(room_id: str, message: str, reply_to_id: str = None, reply_message_id: str = None):
    """Sends a message to a Chatwork room."""
    if not CHATWORK_API_TOKEN:
        logger.error("CHATWORK_API_TOKEN is not set.")
        return
    url = f"https://api.chatwork.com/v2/rooms/{room_id}/messages"
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    body = message
    if reply_to_id:
        body = f"[rp aid={reply_to_id}] {body}"
    if reply_message_id:
        # Chatworkの正しい引用形式に修正
        body = f"[qt ref={reply_message_id}]\n{body}\n[/qt]"
    payload = {"body": body}
    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending message: {e}")
        return None

def get_room_members(room_id: str):
    """Gets the members of a Chatwork room."""
    if not CHATWORK_API_TOKEN:
        logger.error("CHATWORK_API_TOKEN is not set.")
        return None
    url = f"https://api.chatwork.com/v2/rooms/{room_id}/members"
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error getting room members: {e}")
        return None

def change_room_permissions(room_id: str, admin_ids: list, member_ids: list, readonly_ids: list):
    """Changes the permissions of a Chatwork room."""
    if not CHATWORK_API_TOKEN:
        logger.error("CHATWORK_API_TOKEN is not set.")
        return False
    url = f"https://api.chatwork.com/v2/rooms/{room_id}/members"
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    payload = {
        "members_admin": ",".join(map(str, admin_ids)),
        "members_member": ",".join(map(str, member_ids)),
        "members_readonly": ",".join(map(str, readonly_ids))
    }
    try:
        response = requests.put(url, headers=headers, data=payload)
        response.raise_for_status()
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        logger.error(f"Error changing room permissions: {e}")
        return False

def is_bot_admin(room_id: str) -> bool:
    """Checks if the bot has admin privileges in the specified room."""
    if not CHATWORK_API_TOKEN or not MY_ACCOUNT_ID:
        logger.error("CHATWORK_API_TOKEN or MY_ACCOUNT_ID is not set.")
        return False
    members = get_room_members(room_id)
    if members:
        return any(str(member['account_id']) == str(MY_ACCOUNT_ID) and member['role'] == 'admin' for member in members)
    return False

# --- データベース操作関数 ---
def save_readonly_user_to_db(user_id: str):
    """Saves a user ID to the 'readonly_users' table in Supabase."""
    supabase = get_supabase_client()
    if not supabase:
        return False
    try:
        data, count = supabase.from_("readonly_users").insert({"user_id": user_id}).execute()
        return True
    except Exception as e:
        logger.error(f"Error saving readonly user: {e}")
        return False

def remove_readonly_user_from_db(user_id: str):
    """Removes a user ID from the 'readonly_users' table."""
    supabase = get_supabase_client()
    if not supabase:
        return False
    try:
        data, count = supabase.from_("readonly_users").delete().eq("user_id", user_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error removing readonly user: {e}")
        return False

def is_readonly_user_in_db(user_id: str):
    """Checks if a user is in the 'readonly_users' table."""
    supabase = get_supabase_client()
    if not supabase:
        return False
    try:
        response = supabase.from_("readonly_users").select("*").eq("user_id", user_id).execute()
        return len(response.data) > 0
    except Exception as e:
        logger.error(f"Error checking readonly user: {e}")
        return False

def reset_message_counts(date_str: str):
    """Resets message counts for a specific date."""
    supabase = get_supabase_client()
    if not supabase:
        return False
    try:
        data, count = supabase.from_("daily_message_counts").delete().eq("date", date_str).execute()
        return True
    except Exception as e:
        logger.error(f"Error resetting message counts: {e}")
        return False

def update_room_info_in_db(room_id: str, room_name: str):
    """Updates or inserts room info into the 'rooms' table."""
    supabase = get_supabase_client()
    if not supabase:
        return False
    try:
        data, count = supabase.from_("rooms").upsert({"room_id": room_id, "room_name": room_name}).execute()
        return True
    except Exception as e:
        logger.error(f"Error updating room info: {e}")
        return False

def update_message_count_in_db(room_id: str, date_str: str, account_id: str, account_name: str, message_id: str):
    """Updates or inserts a message count for a user in a room for a specific date."""
    supabase = get_supabase_client()
    if not supabase:
        return False
    try:
        # Check if a record already exists for the message ID
        existing_record, _ = supabase.from_("daily_message_counts").select("*").eq("message_id", message_id).execute()
        if existing_record:
            return True # Message already processed

        # Get existing message count
        existing_count_res = supabase.from_("daily_message_counts").select("count").eq("room_id", room_id).eq("account_id", account_id).eq("date", date_str).limit(1).execute()
        existing_count = existing_count_res.data[0]['count'] if existing_count_res.data else 0

        # Increment count
        new_count = existing_count + 1

        # Upsert the new record
        data_to_upsert = {
            "date": date_str,
            "room_id": room_id,
            "account_id": account_id,
            "account_name": account_name,
            "count": new_count,
            "message_id": message_id
        }
        
        upsert_result = supabase.from_("daily_message_counts").upsert(data_to_upsert, on_conflict='date, room_id, account_id').execute()

        return True
    except Exception as e:
        logger.error(f"Error updating message count: {e}")
        return False

def get_message_count_for_ranking(date_str: str):
    """Retrieves and aggregates message counts for a given date, ordered by count."""
    supabase = get_supabase_client()
    if not supabase:
        return None
    try:
        response = supabase.from_("daily_message_counts").select("room_id, count").eq("date", date_str).execute()
        
        # Aggregate counts by room_id
        room_counts = defaultdict(int)
        for record in response.data:
            room_counts[record['room_id']] += record['count']
        
        # Sort rooms by total message count in descending order
        sorted_ranking = sorted(room_counts.items(), key=lambda item: item[1], reverse=True)
        return sorted_ranking
    except Exception as e:
        logger.error(f"Error getting message count for ranking: {e}")
        return None

def get_all_room_info_from_db():
    """Retrieves all room information from the 'rooms' table."""
    supabase = get_supabase_client()
    if not supabase:
        return {}
    try:
        response = supabase.from_("rooms").select("*").execute()
        return {room['room_id']: room for room in response.data}
    except Exception as e:
        logger.error(f"Error getting all room info: {e}")
        return {}

def get_messages_by_room_and_date(room_id: str, date_str: str):
    """Retrieves all messages for a specific room and date."""
    supabase = get_supabase_client()
    if not supabase:
        return []
    try:
        response = supabase.from_("daily_message_counts").select("*").eq("room_id", room_id).eq("date", date_str).execute()
        return response.data
    except Exception as e:
        logger.error(f"Error retrieving messages from database: {e}")
        return []

def get_weather_info(city_name_en: str):
    """Fetches weather information from OpenWeatherMap API."""
    if not OPENWEATHER_API_KEY:
        return "OpenWeather APIキーが設定されていません。"

    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name_en}&appid={OPENWEATHER_API_KEY}&units=metric&lang=ja"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        weather_description = data['weather'][0]['description']
        temp = data['main']['temp']
        humidity = data['main']['humidity']
        
        return f"【{city_name_en}の天気】\n天気: {weather_description}\n気温: {temp}°C\n湿度: {humidity}%"
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching weather info: {e}")
        return "天気情報の取得に失敗しました。"

# --- 定期実行ジョブ関数 ---
def post_all_room_ranking_daily():
    """
    Scheduled job to post the ranking of all rooms to the report room daily.
    This job runs at 08:00 AM JST.
    """
    logger.info("Starting scheduled job: post_all_room_ranking_daily")
    jst = timezone(timedelta(hours=9), 'JST')
    
    # Get the date for yesterday in JST
    target_date = datetime.now(jst) - timedelta(days=1)
    target_date_str = target_date.strftime("%Y/%#m/%#d")
    
    ranking = get_message_count_for_ranking(target_date_str)
    
    if not ranking:
        logger.info(f"No ranking data found for {target_date_str}. Skipping.")
        return
        
    ranking_lines = [f"【{target_date_str}のメッセージ数ランキング】"]
    all_room_info = get_all_room_info_from_db()

    for i, (room_id_str, count) in enumerate(ranking):
        room_name = all_room_info.get(room_id_str, {}).get("room_name", f"部屋ID: {room_id_str}")
        ranking_lines.append(f"{i+1}位: {room_name} ({count}件)")
        if i >= 9: # Only show top 10
            break
    
    if REPORT_ROOM_ID:
        send_message(REPORT_ROOM_ID, "\n".join(ranking_lines))
        logger.info(f"Successfully posted daily ranking to room {REPORT_ROOM_ID}")
    else:
        logger.error("REPORT_ROOM_ID is not set. Cannot post daily ranking.")

def post_personal_ranking(room_id, date_str, account_id, message_id):
    """
    Posts the personal ranking of a room for a specific date.
    """
    supabase = get_supabase_client()
    if not supabase:
        send_message(room_id, "データベースが利用できません。", reply_to_id=account_id, reply_message_id=message_id)
        return

    try:
        # Retrieve all message counts for the specified room and date
        response = supabase.from_("daily_message_counts").select("account_id, account_name, count").eq("room_id", room_id).eq("date", date_str).execute()

        # Check if data exists
        if not response.data:
            send_message(room_id, f"指定された日付（{date_str}）のデータが見つかりませんでした。", reply_to_id=account_id, reply_message_id=message_id)
            return

        # Aggregate counts by user
        user_counts = defaultdict(int)
        user_names = {}
        for record in response.data:
            user_counts[record['account_id']] += record['count']
            user_names[record['account_id']] = record['account_name']

        # Sort users by total message count in descending order
        sorted_ranking = sorted(user_counts.items(), key=lambda item: item[1], reverse=True)

        ranking_lines = [f"【{date_str}のユーザー別メッセージ数ランキング】"]
        for i, (user_id, count) in enumerate(sorted_ranking):
            user_name = user_names.get(user_id, "Unknown User")
            ranking_lines.append(f"{i+1}位: {user_name} ({count}件)")

        send_message(room_id, "\n".join(ranking_lines), reply_to_id=account_id, reply_message_id=message_id)

    except Exception as e:
        logger.error(f"Error posting personal ranking: {e}")
        send_message(room_id, "ランキングの取得中にエラーが発生しました。", reply_to_id=account_id, reply_message_id=message_id)

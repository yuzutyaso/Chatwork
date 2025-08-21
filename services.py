# services.py
import os
import requests
import logging
from supabase import create_client, Client
from constants import (
    CHATWORK_API_TOKEN, MY_ACCOUNT_ID, SUPABASE_URL, SUPABASE_KEY, OPENWEATHER_API_KEY
)

logger = logging.getLogger(__name__)

# --- Configuration and Initialization ---
supabase = None
def get_supabase_client():
    """Returns the Supabase client, initializing it if necessary."""
    global supabase
    if supabase is None:
        if SUPABASE_URL and SUPABASE_KEY:
            try:
                supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            except Exception as e:
                logger.error(f"Failed to create Supabase client: {e}")
    return supabase

# --- Chatwork API-related functions ---
def send_message(room_id, message_body, reply_to_id=None, reply_message_id=None):
    """Sends a message to a Chatwork room."""
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN, "Content-Type": "application/x-www-form-urlencoded"}
    payload = {"body": message_body}
    
    if reply_to_id and reply_message_id:
        payload["body"] = f"[rp aid={reply_to_id} to={room_id}-{reply_message_id}]\n{message_body}"

    try:
        requests.post(f"https://api.chatwork.com/v2/rooms/{room_id}/messages", headers=headers, data=payload).raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send message: {e}")
        return False

def get_room_members(room_id):
    """Gets the members information for a room."""
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    try:
        response = requests.get(f"https://api.chatwork.com/v2/rooms/{room_id}/members", headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get room members: {e}")
        return None

def change_room_permissions(room_id, admin_ids, member_ids, readonly_ids):
    """Changes member permissions in a room."""
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN, "Content-Type": "application/x-www-form-urlencoded"}
    payload = {
        "members_admin_ids": ",".join(map(str, admin_ids)),
        "members_member_ids": ",".join(map(str, member_ids)),
        "members_readonly_ids": ",".join(map(str, readonly_ids))
    }
    try:
        requests.put(f"https://api.chatwork.com/v2/rooms/{room_id}/members", headers=headers, data=payload).raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to change permissions: {e}")
        return False

def is_bot_admin(room_id):
    """Checks if the bot has admin permissions in a room."""
    members = get_room_members(room_id)
    if members:
        return any(str(member["account_id"]) == str(MY_ACCOUNT_ID) and member["role"] == "admin" for member in members)
    return False

# --- Supabase Database related functions ---
def get_last_message_id(account_id):
    """Fetches the last message ID for a given account from Supabase."""
    supabase = get_supabase_client()
    if not supabase: return None
    try:
        response = supabase.table('last_message_ids').select("message_id").eq("account_id", account_id).single().execute()
        return response.data['message_id']
    except Exception:
        return None

def update_last_message_id(account_id, message_id):
    """Updates the last message ID for a given account in Supabase."""
    supabase = get_supabase_client()
    if not supabase: return False
    try:
        data = {'account_id': account_id, 'message_id': message_id}
        supabase.table('last_message_ids').upsert([data]).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to update last message ID: {e}")
        return False

def update_message_count_in_db(room_id, date, account_id, account_name, message_id):
    """Updates the message count in Supabase if the message is new."""
    supabase = get_supabase_client()
    if not supabase: return
    
    last_id = get_last_message_id(account_id)
    if last_id and int(message_id) <= int(last_id):
        logger.info(f"Ignoring duplicate message for account {account_id}, message_id {message_id}")
        return

    try:
        response = supabase.table('message_counts').select("*").eq("room_id", room_id).eq("date", date).eq("account_id", account_id).execute()
        if response.data:
            current_count = response.data[0]['message_count']
            supabase.table('message_counts').update({'message_count': current_count + 1}).eq("id", response.data[0]['id']).execute()
        else:
            supabase.table('message_counts').insert({"room_id": room_id, "date": date, "account_id": account_id, "name": account_name, "message_count": 1}).execute()
        
        # Update the last message ID after a successful count update
        update_last_message_id(account_id, message_id)

    except Exception as e:
        logger.error(f"Failed to update message count or last message ID: {e}")

def get_message_count_for_ranking(date_str):
    """Gets message counts for all rooms for a specific date and returns a dictionary."""
    supabase = get_supabase_client()
    if not supabase: return {}
    try:
        response = supabase.table('message_counts').select("room_id, message_count").eq("date", date_str).execute()
        
        # Aggregate counts by room_id
        room_counts = {}
        for row in response.data:
            room_id = str(row['room_id'])
            count = row['message_count']
            room_counts[room_id] = room_counts.get(room_id, 0) + count
        
        # Sort the dictionary by value (message count) in descending order
        sorted_counts = dict(sorted(room_counts.items(), key=lambda item: item[1], reverse=True))
        return sorted_counts
    except Exception as e:
        logger.error(f"Failed to fetch ranking: {e}")
        return {}


def reset_message_counts(date_str):
    """Deletes all message counts for a specific date."""
    supabase = get_supabase_client()
    if not supabase: return False
    try:
        supabase.table('message_counts').delete().eq('date', date_str).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to reset message counts for date {date_str}: {e}")
        return False

def post_personal_ranking(room_id, target_date, reply_to_id, reply_message_id):
    """Fetches and posts the message count ranking for a specific room."""
    supabase = get_supabase_client()
    if not supabase:
        send_message(room_id, "データベースが利用できません。", reply_to_id=reply_to_id, reply_message_id=reply_message_id)
        return
    try:
        response = supabase.table('message_counts').select("*").eq("date", target_date).eq("room_id", room_id).order("message_count", desc=True).execute()
        ranking = response.data
        if not ranking:
            send_message(room_id, f"{target_date} のデータが見つかりませんでした。", reply_to_id=reply_to_id, reply_message_id=reply_message_id)
        else:
            total_count = sum(item.get('message_count', 0) for item in ranking)
            ranking_lines = [f"【{target_date} の個人メッセージ数ランキング】"]
            for i, item in enumerate(ranking, 1):
                ranking_lines.append(f"{i}位　{item.get('name', 'Unknown')}さん ({item.get('message_count', 0)}件)")
            ranking_lines.append("\n")
            ranking_lines.append(f"合計コメント数: {total_count}件")
            send_message(room_id, "\n".join(ranking_lines), reply_to_id=reply_to_id, reply_message_id=reply_message_id)
    except Exception as e:
        logger.error(f"Failed to fetch ranking: {e}")
        send_message(room_id, "ランキングの取得中にエラーが発生しました。", reply_to_id=reply_to_id, reply_message_id=reply_message_id)

def save_readonly_user_to_db(account_id):
    """Saves a user to the readonly list in the database."""
    from datetime import datetime, timezone
    supabase = get_supabase_client()
    if not supabase: return
    try:
        supabase.table('readonly_users').insert({
            "account_id": account_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }).execute()
        logger.info(f"User {account_id} saved to readonly_users.")
    except Exception as e:
        logger.error(f"Failed to save user to readonly_users: {e}")

def remove_readonly_user_from_db(account_id):
    """Removes a user from the readonly list."""
    supabase = get_supabase_client()
    if not supabase: return False
    try:
        response = supabase.table('readonly_users').delete().eq('account_id', account_id).execute()
        return bool(response.data)
    except Exception as e:
        logger.error(f"Failed to delete from readonly_users: {e}")
        return False

def is_readonly_user_in_db(account_id):
    """Checks if a user exists in the readonly list."""
    supabase = get_supabase_client()
    if not supabase: return False
    try:
        response = supabase.table('readonly_users').select("account_id").eq("account_id", account_id).execute()
        return bool(response.data)
    except Exception as e:
        logger.error(f"Supabase check for readonly_users failed: {e}")
        return False

def get_weather_info(city_name):
    """Gets weather information from OpenWeatherMap."""
    base_url = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city_name,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
        "lang": "ja"  # Added to get Japanese descriptions
    }
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()
        main_info = data["main"]
        weather_info = data["weather"][0]
        
        weather_description = weather_info["description"]
        temp = main_info["temp"]
        humidity = main_info["humidity"]
        
        return f"【{city_name}の天気】\n天気: {weather_description}\n気温: {temp}°C\n湿度: {humidity}%"
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get weather data: {e}")
        return f"天気情報が取得できませんでした。都市名を確認してください。"
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        return "天気情報の取得中にエラーが発生しました。"
    
def update_room_info_in_db(room_id, room_name):
    """Updates or inserts room information in the database."""
    supabase = get_supabase_client()
    if not supabase: return False
    try:
        data = {
            "room_id": str(room_id),
            "room_name": room_name,
        }
        supabase.table('room_info').upsert([data]).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to update room info: {e}")
        return False

def get_all_room_info_from_db():
    """Gets all room information from the database."""
    supabase = get_supabase_client()
    if not supabase: return {}
    try:
        response = supabase.table('room_info').select("*").execute()
        room_info = {str(item["room_id"]): item for item in response.data}
        return room_info
    except Exception as e:
        logger.error(f"Failed to get all room info: {e}")
        return {}

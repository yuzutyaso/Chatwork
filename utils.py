import os
import re
import requests
import logging
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# --- Configuration and Initialization ---
CHATWORK_API_TOKEN = os.environ.get("CHATWORK_API_TOKEN")
MY_ACCOUNT_ID = os.environ.get("MY_ACCOUNT_ID")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")

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

def mark_room_as_read(room_id):
    """Marks all messages in the specified room as read."""
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    try:
        response = requests.put(f"https://api.chatwork.com/v2/rooms/{room_id}/messages/read", headers=headers)
        response.raise_for_status()
        logger.info(f"Successfully marked room {room_id} as read.")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to mark room {room_id} as read: {e}")
        return False

def is_bot_admin(room_id):
    """Checks if the bot has admin permissions in a room."""
    members = get_room_members(room_id)
    if members:
        return any(str(member["account_id"]) == str(MY_ACCOUNT_ID) and member["role"] == "admin" for member in members)
    return False

def clean_message_body(body):
    """Removes Chatwork-specific tags from the message body."""
    body = re.sub(r'\[rp aid=\d+ to=\d+-\d+\]|\[piconname:\d+\].*?さん|\[To:\d+\]', '', body)
    return body.strip()

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

def update_message_count_in_db(date, account_id, account_name, message_id):
    """Updates the message count in Supabase if the message is new."""
    supabase = get_supabase_client()
    if not supabase: return
    
    last_id = get_last_message_id(account_id)
    if last_id and int(message_id) <= int(last_id):
        logger.info(f"Ignoring duplicate message for account {account_id}, message_id {message_id}")
        return

    try:
        response = supabase.table('message_counts').select("*").eq("date", date).eq("account_id", account_id).execute()
        if response.data:
            current_count = response.data[0]['message_count']
            supabase.table('message_counts').update({'message_count': current_count + 1}).eq("id", response.data[0]['id']).execute()
        else:
            supabase.table('message_counts').insert({"date": date, "account_id": account_id, "name": account_name, "message_count": 1}).execute()
        
        # Update the last message ID after a successful count update
        update_last_message_id(account_id, message_id)

    except Exception as e:
        logger.error(f"Failed to update message count or last message ID: {e}")

def reset_message_counts(date_str):
    """Deletes all message counts for a specific date."""
    supabase = get_supabase_client()
    if not supabase: return False
    try:
        # Delete from message_counts table
        supabase.table('message_counts').delete().eq('date', date_str).execute()
        
        # Optionally, clear last_message_ids for this date, though webhook logic will overwrite it anyway.
        # This is commented out to avoid unnecessary DB calls.
        # supabase.table('last_message_ids').delete().eq('date', date_str).execute()

        return True
    except Exception as e:
        logger.error(f"Failed to reset message counts for date {date_str}: {e}")
        return False

def post_ranking(room_id, target_date, reply_to_id, reply_message_id):
    """Fetches and posts the message count ranking."""
    supabase = get_supabase_client()
    if not supabase:
        send_message(room_id, "データベースが利用できません。", reply_to_id=reply_to_id, reply_message_id=reply_message_id)
        return
    try:
        response = supabase.table('message_counts').select("*").eq("date", target_date).order("message_count", desc=True).execute()
        ranking = response.data
        if not ranking:
            send_message(room_id, f"{target_date} のデータが見つかりませんでした。", reply_to_id=reply_to_id, reply_message_id=reply_message_id)
        else:
            total_count = sum(item.get('message_count', 0) for item in ranking)
            ranking_lines = [f"{target_date} の個人メッセージ数ランキング！"]
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
    supabase = get_supabase_client()
    if not supabase: return
    try:
        from datetime import datetime, timezone
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
        "units": "metric", # Celsius
        "lang": "ja"
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

def get_user_info(target_user_id):
    """Gets user information from the Chatwork API."""
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    try:
        response = requests.get(f"https://api.chatwork.com/v2/my/account", headers=headers)
        response.raise_for_status()
        my_account_info = response.json()
        
        # Simplified for now, as direct user lookup is not possible without advanced permissions.
        # This will only return info if the target is the bot itself.
        if str(my_account_info["account_id"]) == str(target_user_id):
            return f"【ユーザー情報】\n名前: {my_account_info['name']}\nアカウントID: {my_account_info['account_id']}"
        else:
            return f"ユーザーID {target_user_id} の情報を取得できませんでした。権限を確認してください。"
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get user info: {e}")
        return "ユーザー情報の取得中にエラーが発生しました。"

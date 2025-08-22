import os
import re
import time
import requests
import random
from datetime import datetime
from dotenv import load_dotenv

from db import supabase
from utils import send_message_to_chatwork, get_chatwork_members, is_admin, change_user_role, send_reply, get_weather_info

# ChatWork APIトークンを環境変数から取得
CHATWORK_API_TOKEN = os.getenv("CHATWORK_API_TOKEN")

# --- 各コマンドの関数を定義 ---

def test_command(room_id, message_id, account_id, message_body):
    """/test コマンドの処理"""
    send_reply(room_id, message_id, account_id, "Botは正常に動作しています。成功です。")

def sorry_command(room_id, message_id, account_id, message_body):
    """/sorry (ユーザーid) コマンドの処理"""
    match = re.search(r'/sorry\s+(\d+)', message_body)
    if not match:
        send_reply(room_id, message_id, account_id, "コマンド形式が正しくありません。例: /sorry 12345")
        return
    
    user_id_to_delete = int(match.group(1))
    
    try:
        response = supabase.table('viewer_list').delete().eq('user_id', user_id_to_delete).execute()
        if response.data:
            send_reply(room_id, message_id, account_id, f"{user_id_to_delete}さんを閲覧者リストから削除しました。")
        else:
            send_reply(room_id, message_id, account_id, "指定されたユーザーIDが見つからないか、処理に失敗しました。")
    except Exception as e:
        send_reply(room_id, message_id, account_id, f"データベース処理中にエラーが発生しました: {e}")

def roominfo_command(room_id, message_id, account_id, message_body):
    """/roominfo (roomid) コマンドの処理"""
    match = re.search(r'/roominfo\s+(\d+)', message_body)
    target_room_id = match.group(1) if match else room_id

    try:
        members = get_chatwork_members(target_room_id)
        if not members:
            send_reply(room_id, message_id, account_id, f"ルームID {target_room_id} のメンバー情報を取得できませんでした。ボットがその部屋に参加しているか確認してください。")
            return

        room_info_res = requests.get(f"https://api.chatwork.com/v2/rooms/{target_room_id}", headers={"X-ChatWorkToken": CHATWORK_API_TOKEN})
        room_info_res.raise_for_status()
        room_info = room_info_res.json()
        
        member_count = len(members)
        admin_count = sum(1 for m in members if m['role'] == 'admin')
        room_name = room_info.get('name', '取得失敗')
        
        response_message = f"""
        ルーム名: {room_name}
        メンバー数: {member_count}人
        管理者数: {admin_count}人
        """
        send_reply(room_id, message_id, account_id, response_message)
    except requests.exceptions.RequestException as e:
        send_reply(room_id, message_id, account_id, f"ルーム情報の取得に失敗しました。エラー: {e}")

def say_command(room_id, message_id, account_id, message_body):
    """/say メッセージ コマンドの処理"""
    message_to_post = message_body.replace("/say ", "", 1)
    if not message_to_post.strip():
        send_reply(room_id, message_id, account_id, "メッセージを入力してください。例: /say こんにちは")
        return
    send_message_to_chatwork(room_id, message_to_post)

def weather_command(room_id, message_id, account_id, message_body):
    """/weather 都市名 コマンドの処理"""
    city_name = message_body.replace("/weather ", "", 1).strip()
    
    weather_result = get_weather_info(city_name)
    
    if weather_result.get("error"):
        send_reply(room_id, message_id, account_id, weather_result["error"])
        return
        
    data = weather_result["data"]
    city = weather_result["city"]
    
    weather = data['weather'][0]['description']
    temp = data['main']['temp']
    humidity = data['main']['humidity']
    wind_speed = data['wind']['speed']
    
    response_message = f"""
    **{city}**の天気予報
    ---
    天気: {weather}
    気温: {temp}℃
    湿度: {humidity}%
    風速: {wind_speed}m/s
    """
    send_reply(room_id, message_id, account_id, response_message)

def whoami_command(room_id, message_id, account_id, message_body):
    """/whoami コマンドの処理"""
    try:
        members = get_chatwork_members(room_id)
        my_info = next((m for m in members if m['account_id'] == account_id), None)
        
        if not my_info:
            send_reply(room_id, message_id, account_id, "あなたの情報が見つかりませんでした。")
            return
            
        response_message = f"""
        あなたの情報です。
        ---
        アカウントID: {my_info['account_id']}
        名前: {my_info['name']}
        権限: {my_info['role']}
        """
        send_reply(room_id, message_id, account_id, response_message)
    except Exception as e:
        send_reply(room_id, message_id, account_id, f"エラーが発生しました: {e}")

def echo_command(room_id, message_id, account_id, message_body):
    """/echo コマンドの処理"""
    message_to_echo = message_body.replace("/echo ", "", 1).strip()
    if not message_to_echo:
        send_reply(room_id, message_id, account_id, "エコーするメッセージを入力してください。例: /echo こんにちは")
        return
        
    send_reply(room_id, message_id, account_id, message_to_echo)
    
def timer_command(room_id, message_id, account_id, message_body):
    """/timer コマンドの処理"""
    match = re.search(r'/timer\s+(\d+m)?\s*(\d+s)?\s*"(.*)"', message_body)
    if not match:
        send_reply(room_id, message_id, account_id, "コマンド形式が正しくありません。例: /timer 5m 30s \"休憩終了\"")
        return

    minutes = int(match.group(1)[:-1]) if match.group(1) else 0
    seconds = int(match.group(2)[:-1]) if match.group(2) else 0
    message_to_post = match.group(3)
    
    total_seconds = minutes * 60 + seconds
    
    if total_seconds <= 0:
        send_reply(room_id, message_id, account_id, "タイマー時間は1秒以上にしてください。")
        return
        
    send_reply(room_id, message_id, account_id, f"{minutes}分{seconds}秒のタイマーを設定しました。")
    time.sleep(total_seconds)
    send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n{message_to_post}")

def time_report_command(room_id, message_id, account_id, message_body):
    """時報コマンドの処理（管理者のみ）"""
    match_h = re.search(r'(\d+)\s*h', message_body)
    match_m = re.search(r'(\d+)\s*m', message_body)
    
    if "/時報 OK" in message_body:
        try:
            # 既に存在するかチェック
            response = supabase.table('hourly_report_rooms').select('room_id').eq('room_id', room_id).execute()
            if not response.data:
                supabase.table('hourly_report_rooms').insert({"room_id": room_id, "interval_minutes": 60}).execute()
                send_reply(room_id, message_id, account_id, "このルームに毎時お知らせを投稿するように設定しました。")
            else:
                send_reply(room_id, message_id, account_id, "このルームは既に時報が設定されています。")
        except Exception as e:
            send_reply(room_id, message_id, account_id, f"設定中にエラーが発生しました: {e}")
            
    elif "/時報 NO" in message_body:
        try:
            supabase.table('hourly_report_rooms').delete().eq('room_id', room_id).execute()
            send_reply(room_id, message_id, account_id, "このルームの毎時お知らせを解除しました。")
        except Exception as e:
            send_reply(room_id, message_id, account_id, f"解除中にエラーが発生しました: {e}")
            
    elif match_h or match_m:
        hours = int(match_h.group(1)) if match_h else 0
        minutes = int(match_m.group(1)) if match_m else 0
        
        total_minutes = hours * 60 + minutes
        
        if total_minutes <= 0:
            send_reply(room_id, message_id, account_id, "時間または分は1以上で指定してください。")
            return
            
        try:
            response = supabase.table('hourly_report_rooms').update({"interval_minutes": total_minutes}).eq('room_id', room_id).execute()
            if not response.data:
                supabase.table('hourly_report_rooms').insert({"room_id": room_id, "interval_minutes": total_minutes}).execute()
            send_reply(room_id, message_id, account_id, f"このルームに毎 {hours}時間 {minutes}分ごとのお知らせを投稿するように設定しました。")
        except Exception as e:
            send_reply(room_id, message_id, account_id, f"設定中にエラーが発生しました: {e}")
            
    else:
        send_reply(room_id, message_id, account_id, "コマンド形式が正しくありません。例: /時報 OK, /時報 NO, /時報 1h, /時報 30m, /時報 1h 30m")

def delete_command(room_id, message_id, account_id, message_body):
    """/削除 コマンドの処理（返信されたメッセージを削除）"""
    match = re.search(r'\[rp aid=\d+ to=\d+-(\d+)\]', message_body)
    if not match:
        send_reply(room_id, message_id, account_id, "このコマンドは返信として使用してください。")
        return

    target_message_id = match.group(1)
    
    try:
        response = requests.post(
            f"https://api.chatwork.com/v2/rooms/{room_id}/messages/{target_message_id}/deletion",
            headers={"X-ChatWorkToken": CHATWORK_API_TOKEN}
        )
        if response.status_code == 204:
            send_reply(room_id, message_id, account_id, "メッセージを削除しました。")
        else:
            send_reply(room_id, message_id, account_id, f"メッセージの削除に失敗しました。ステータスコード: {response.status_code}")
    except requests.exceptions.RequestException as e:
        send_reply(room_id, message_id, account_id, f"メッセージ削除中にエラーが発生しました: {e}")

def omikuji_command(room_id, message_id, account_id, message_body):
    """おみくじ コマンドの処理"""
    today = datetime.now().date()
    
    try:
        response = supabase.table('omikuji_history').select('last_drawn_date').eq('user_id', account_id).execute()
        data = response.data
    except Exception as e:
        send_reply(room_id, message_id, account_id, f"データベースエラーが発生しました: {e}")
        return
    
    if data and datetime.strptime(data[0]['last_drawn_date'], '%Y-%m-%d').date() == today:
        send_reply(room_id, message_id, account_id, "今日のおみくじはすでに引きました。また明日試してくださいね！")
        return
        
    results = ["大吉"] * 10 + ["中吉"] * 20 + ["小吉"] * 30 + ["吉"] * 20 + ["末吉"] * 10 + ["凶"] * 5 + ["大凶"] * 5
    result = random.choice(results)
    
    try:
        if data:
            supabase.table('omikuji_history').update({"last_drawn_date": today.isoformat()}).eq('user_id', account_id).execute()
        else:
            supabase.table('omikuji_history').insert({"user_id": account_id, "last_drawn_date": today.isoformat()}).execute()
        
        send_reply(room_id, message_id, account_id, f"あなたのおみくじは... **{result}** です！")
    except Exception as e:
        send_reply(room_id, message_id, account_id, f"データベース更新中にエラーが発生しました: {e}")

def ranking_command(room_id, message_id, account_id, message_body):
    """/ranking yyyy/mm/dd (room_id) コマンドの処理"""
    parts = message_body.split()
    target_room_id = room_id
    date_str = None
    
    if len(parts) > 1:
        date_pattern = r'\d{4}/\d{2}/\d{2}'
        room_id_pattern = r'\d+'
        
        date_match = re.search(date_pattern, message_body)
        if date_match:
            date_str = date_match.group(0)
        
        room_id_match = re.search(room_id_pattern, message_body)
        if room_id_match:
            target_room_id_candidate = room_id_match.group(0)
            if not date_match or target_room_id_candidate != date_match.group(0).replace('/', ''):
                target_room_id = int(target_room_id_candidate)

    try:
        if date_str:
            ranking_date = datetime.strptime(date_str, '%Y/%m/%d').date().isoformat()
        else:
            ranking_date = datetime.now().date().isoformat()
    except ValueError:
        send_reply(room_id, message_id, account_id, "日付の形式が正しくありません。例: /ranking 2025/08/21")
        return
        
    response = supabase.table('user_message_counts').select('*').eq('message_date', ranking_date).eq('room_id', target_room_id).order('message_count', desc=True).limit(10).execute()
    
    if not response.data:
        send_reply(room_id, message_id, account_id, f"指定された部屋({target_room_id})の{ranking_date}にはまだメッセージがありません。")
        return
        
    try:
        members = get_chatwork_members(target_room_id)
        room_info_res = requests.get(f"https://api.chatwork.com/v2/rooms/{target_room_id}", headers={"X-ChatWorkToken": CHATWORK_API_TOKEN})
        room_info_res.raise_for_status()
        room_info = room_info_res.json()
        
        user_names = {member['account_id']: member['name'] for member in members}
        room_name = room_info.get('name', '取得失敗')
        
        total_messages_res = supabase.table('user_message_counts').select('message_count').eq('room_id', target_room_id).execute()
        total_room_messages = sum(item['message_count'] for item in total_messages_res.data)

        message_title = f"{room_name}の{ranking_date}個人メッセージ数ランキング\n---\n"
        message_list = ""
        
        for i, item in enumerate(response.data):
            user_name = user_names.get(item['user_id'], f"ユーザーID {item['user_id']}")
            total_count_res = supabase.table('user_message_counts').select('message_count').eq('user_id', item['user_id']).eq('room_id', target_room_id).execute()
            total_user_messages = sum(row['message_count'] for row in total_count_res.data)

            message_list += f"{i+1}位: {user_name}さん\n"
            message_list += f"  - 当日メッセージ数: {item['message_count']}\n"
            message_list += f"  - 累計メッセージ数: {total_user_messages}\n"
        
        message_list += f"\n部屋全体の累計メッセージ数: {total_room_messages}"
        
        send_reply(room_id, message_id, account_id, f"{message_title}{message_list}")
    except requests.exceptions.RequestException as e:
        send_reply(room_id, message_id, account_id, f"指定された部屋({target_room_id})の情報を取得できませんでした。エラー: {e}")

def quote_command(room_id, message_id, account_id, message_body):
    """/quote コマンドの処理（返信されたメッセージを引用）"""
    match = re.search(r'\[rp aid=(\d+) to=\d+-(\d+)\]', message_body)
    if not match:
        send_reply(room_id, message_id, account_id, "このコマンドは返信として使用してください。")
        return

    quoted_user_id = match.group(1)
    quoted_message_id = match.group(2)
    
    try:
        message_response = requests.get(
            f"https://api.chatwork.com/v2/rooms/{room_id}/messages/{quoted_message_id}",
            headers={"X-ChatWorkToken": CHATWORK_API_TOKEN}
        )
        message_response.raise_for_status()
        message_data = message_response.json()
        
        members_response = get_chatwork_members(room_id)
        if not members_response:
            raise requests.exceptions.RequestException("メンバー情報が取得できませんでした。")
        
        quoted_user_name = next((member['name'] for member in members_response if member['account_id'] == int(quoted_user_id)), f"ユーザーID:{quoted_user_id}")
        
        quoted_message_body = message_data.get("body", "メッセージ本文の取得に失敗しました。")
        quoted_date = datetime.fromtimestamp(message_data["send_time"]).strftime("%Y/%m/%d %H:%M")
        
        quote_text = f"[qt][qtmsg aid={quoted_user_id} file=0 time={message_data['send_time']}]"
        quote_text += f"**{quoted_user_name}**さん\n"
        quote_text += f"{quoted_message_body}"
        quote_text += f"[/qt]\n"
        quote_text += f"（{quoted_date}の投稿を引用）"
        
        send_message_to_chatwork(room_id, quote_text)
        
    except requests.exceptions.RequestException as e:
        send_reply(room_id, message_id, account_id, f"引用の処理中にAPIエラーが発生しました: {e}")
    except Exception as e:
        send_reply(room_id, message_id, account_id, f"引用の処理中に予期せぬエラーが発生しました: {e}")

def recount_command(room_id, message_id, account_id, message_body):
    """
    /recount コマンドの処理
    指定ルームのメッセージ数データをリセットし、過去100件を再集計する
    """
    # 正規表現を修正し、room_idがなくても動作するようにする
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


# 全コマンドを辞書にまとめる
COMMANDS = {
    "/test": test_command,
    "/sorry": sorry_command,
    "/roominfo": roominfo_command,
    "/say": say_command,
    "/weather": weather_command,
    "/whoami": whoami_command,
    "/echo": echo_command,
    "/timer": timer_command,
    "/時報": time_report_command,
    "/削除": delete_command,
    "/quote": quote_command,
    "おみくじ": omikuji_command,
    "/ranking": ranking_command,
    "/recount": recount_command,
            }

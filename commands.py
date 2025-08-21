import os
import re
import time
import requests
import random
from datetime import datetime
from dotenv import load_dotenv

from db import supabase
from utils import send_message_to_chatwork, get_chatwork_members, is_admin, change_user_role

# 環境変数の読み込み
load_dotenv()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

# ChatWork APIトークンを環境変数から取得
CHATWORK_API_TOKEN = os.getenv("CHATWORK_API_TOKEN")

# --- 都道府県と県庁所在地のマッピング ---
JAPAN_PREFECTURES = {
    "北海道": "札幌", "青森県": "青森", "岩手県": "盛岡", "宮城県": "仙台", "秋田県": "秋田",
    "山形県": "山形", "福島県": "福島", "茨城県": "水戸", "栃木県": "宇都宮", "群馬県": "前橋",
    "埼玉県": "さいたま", "千葉県": "千葉", "東京都": "東京", "神奈川県": "横浜", "新潟県": "新潟",
    "富山県": "富山", "石川県": "金沢", "福井県": "福井", "山梨県": "甲府", "長野県": "長野",
    "岐阜県": "岐阜", "静岡県": "静岡", "愛知県": "名古屋", "三重県": "津", "滋賀県": "大津",
    "京都府": "京都", "大阪府": "大阪", "兵庫県": "神戸", "奈良県": "奈良", "和歌山県": "和歌山",
    "鳥取県": "鳥取", "島根県": "松江", "岡山県": "岡山", "広島県": "広島", "山口県": "山口",
    "徳島県": "徳島", "香川県": "高松", "愛媛県": "松山", "高知県": "高知", "福岡県": "福岡",
    "佐賀県": "佐賀", "長崎県": "長崎", "熊本県": "熊本", "大分県": "大分", "宮崎県": "宮崎",
    "鹿児島県": "鹿児島", "沖縄県": "那覇",
}

# --- 各コマンドの関数を定義 ---

def test_command(room_id, message_id, account_id, message_body):
    """/test コマンドの処理"""
    response_message = "Botは正常に動作しています。成功です。"
    send_message_to_chatwork(room_id, response_message)

def sorry_command(room_id, message_id, account_id, message_body):
    """/sorry (ユーザーid) コマンドの処理"""
    match = re.search(r'/sorry\s+(\d+)', message_body)
    if not match:
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nコマンド形式が正しくありません。例: /sorry 12345")
        return
    
    user_id_to_delete = int(match.group(1))
    
    try:
        response = supabase.table('viewer_list').delete().eq('user_id', user_id_to_delete).execute()
        if response.data:
            send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n{user_id_to_delete}さんを閲覧者リストから削除しました。")
        else:
            send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n指定されたユーザーIDが見つからないか、処理に失敗しました。")
    except Exception as e:
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nデータベース処理中にエラーが発生しました: {e}")

def roominfo_command(room_id, message_id, account_id, message_body):
    """/roominfo (roomid) コマンドの処理"""
    match = re.search(r'/roominfo\s+(\d+)', message_body)
    target_room_id = match.group(1) if match else room_id

    try:
        members = get_chatwork_members(target_room_id)
        room_info = requests.get(f"https://api.chatwork.com/v2/rooms/{target_room_id}", headers={"X-ChatWorkToken": CHATWORK_API_TOKEN}).json()
        
        member_count = len(members)
        admin_count = sum(1 for m in members if m['role'] == 'admin')
        room_name = room_info['name']
        
        response_message = f"""
        [rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん
        ルーム名: {room_name}
        メンバー数: {member_count}人
        管理者数: {admin_count}人
        """
        send_message_to_chatwork(room_id, response_message)
    except Exception as e:
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nルーム情報の取得に失敗しました。Botがその部屋に入っていない可能性があります。")

def say_command(room_id, message_id, account_id, message_body):
    """/say メッセージ コマンドの処理"""
    message_to_post = message_body.replace("/say ", "", 1)
    send_message_to_chatwork(room_id, message_to_post)

def weather_command(room_id, message_id, account_id, message_body):
    """/weather 都市名 コマンドの処理"""
    city_name = message_body.replace("/weather ", "", 1)
    if not city_name:
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n都市名を入力してください。例: /weather 東京 または /weather 東京都")
        return
    
    if city_name in JAPAN_PREFECTURES:
        city_name = JAPAN_PREFECTURES[city_name]

    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name},jp&appid={OPENWEATHER_API_KEY}&units=metric&lang=ja"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        weather = data['weather'][0]['description']
        temp = data['main']['temp']
        humidity = data['main']['humidity']
        wind_speed = data['wind']['speed']
        
        response_message = f"""
        [rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん
        **{city_name}**の天気予報
        ---
        天気: {weather}
        気温: {temp}℃
        湿度: {humidity}%
        風速: {wind_speed}m/s
        """
        send_message_to_chatwork(room_id, response_message)
    else:
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n指定された都市または都道府県が見つかりません。")

def whoami_command(room_id, message_id, account_id, message_body):
    """/whoami コマンドの処理"""
    try:
        members = get_chatwork_members(room_id)
        my_info = next((m for m in members if m['account_id'] == account_id), None)
        
        if my_info:
            response_message = f"""
            [rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん
            あなたの情報です。
            ---
            アカウントID: {my_info['account_id']}
            名前: {my_info['name']}
            権限: {my_info['role']}
            """
            send_message_to_chatwork(room_id, response_message)
        else:
            send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nあなたの情報が見つかりませんでした。")
    except Exception as e:
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nエラーが発生しました: {e}")

def echo_command(room_id, message_id, account_id, message_body):
    """/echo コマンドの処理"""
    message_to_echo = message_body.replace("/echo ", "", 1)
    response_message = f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n{message_to_echo}"
    send_message_to_chatwork(room_id, response_message)
    
def timer_command(room_id, message_id, account_id, message_body):
    """/timer コマンドの処理"""
    match = re.search(r'/timer\s+(\d+m)?\s*(\d+s)?\s*"(.*)"', message_body)
    if not match:
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nコマンド形式が正しくありません。例: /timer 5m 30s \"休憩終了\"")
        return

    minutes = int(match.group(1)[:-1]) if match.group(1) else 0
    seconds = int(match.group(2)[:-1]) if match.group(2) else 0
    message_to_post = match.group(3)
    
    total_seconds = minutes * 60 + seconds
    
    if total_seconds > 0:
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n{minutes}分{seconds}秒のタイマーを設定しました。")
        time.sleep(total_seconds)
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n{message_to_post}")
    else:
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nタイマー時間は1秒以上にしてください。")

def time_report_command(room_id, message_id, account_id, message_body):
    """時報コマンドの処理（管理者のみ）"""
    
    # ユーザーが管理者であるかを確認
    if not is_admin(room_id, account_id):
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nこのコマンドは管理者のみが実行できます。")
        return

    # 時間と分を正規表現で抽出
    match_h = re.search(r'(\d+)\s*h', message_body)
    match_m = re.search(r'(\d+)\s*m', message_body)
    
    if "/時報 OK" in message_body:
        try:
            supabase.table('hourly_report_rooms').insert({"room_id": room_id, "interval_minutes": 60}).execute()
            send_message_to_chatwork(room_id, "このルームに毎時お知らせを投稿するように設定しました。")
        except Exception as e:
            send_message_to_chatwork(room_id, f"設定中にエラーが発生しました: {e}")
    elif "/時報 NO" in message_body:
        try:
            supabase.table('hourly_report_rooms').delete().eq('room_id', room_id).execute()
            send_message_to_chatwork(room_id, "このルームの毎時お知らせを解除しました。")
        except Exception as e:
            send_message_to_chatwork(room_id, f"解除中にエラーが発生しました: {e}")
    elif match_h or match_m:
        hours = int(match_h.group(1)) if match_h else 0
        minutes = int(match_m.group(1)) if match_m else 0
        
        total_minutes = hours * 60 + minutes
        
        if total_minutes > 0:
            try:
                response = supabase.table('hourly_report_rooms').update({"interval_minutes": total_minutes}).eq('room_id', room_id).execute()
                if not response.data:
                    supabase.table('hourly_report_rooms').insert({"room_id": room_id, "interval_minutes": total_minutes}).execute()
                send_message_to_chatwork(room_id, f"このルームに毎 {hours}時間 {minutes}分ごとのお知らせを投稿するように設定しました。")
            except Exception as e:
                send_message_to_chatwork(room_id, f"設定中にエラーが発生しました: {e}")
        else:
            send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n時間または分は1以上で指定してください。")
    else:
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nコマンド形式が正しくありません。例: /時報 OK, /時報 NO, /時報 1h, /時報 30m, /時報 1h 30m")

def delete_command(room_id, message_id, account_id, message_body):
    """/削除 コマンドの処理（返信されたメッセージを削除）"""
    match = re.search(r'\[rp aid=\d+ to=\d+-(\d+)\]', message_body)
    if not match:
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nこのコマンドは返信として使用してください。")
        return

    target_message_id = match.group(1)
    
    try:
        response = requests.post(
            f"https://api.chatwork.com/v2/rooms/{room_id}/messages/{target_message_id}/deletion",
            headers={"X-ChatWorkToken": CHATWORK_API_TOKEN}
        )
        if response.status_code == 204:
            send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nメッセージを削除しました。")
        else:
            send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nメッセージの削除に失敗しました。ステータスコード: {response.status_code}")
    except Exception as e:
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nメッセージ削除中にエラーが発生しました: {e}")

def omikuji_command(room_id, message_id, account_id, message_body):
    """おみくじ コマンドの処理"""
    today = datetime.now().date()
    
    # Supabaseのuser_idカラムがinteger型であることを前提に、整数型として扱う
    user_id_int = int(account_id)
    
    try:
        response = supabase.table('omikuji_history').select('last_drawn_date').eq('user_id', user_id_int).execute()
        data = response.data
    except Exception as e:
        send_message_to_chatwork(room_id, f"データベースエラーが発生しました: {e}")
        return
    
    if data and datetime.strptime(data[0]['last_drawn_date'], '%Y-%m-%d').date() == today:
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n今日のおみくじはすでに引きました。また明日試してくださいね！")
    else:
        results = ["大吉"] * 10 + ["中吉"] * 20 + ["小吉"] * 30 + ["吉"] * 20 + ["末吉"] * 10 + ["凶"] * 5 + ["大凶"] * 5
        result = random.choice(results)
        
        if data:
            supabase.table('omikuji_history').update({"last_drawn_date": today.isoformat()}).eq('user_id', user_id_int).execute()
        else:
            supabase.table('omikuji_history').insert({"user_id": user_id_int, "last_drawn_date": today.isoformat()}).execute()
        
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nあなたのおみくじは... **{result}** です！")

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

    if date_str:
        try:
            ranking_date = datetime.strptime(date_str, '%Y/%m/%d').date().isoformat()
        except ValueError:
            send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n日付の形式が正しくありません。例: /ranking 2025/08/21")
            return
    else:
        ranking_date = datetime.now().date().isoformat()

    # 1. 指定された日付と部屋のメッセージ数ランキングを取得
    response = supabase.table('user_message_counts').select('*').eq('message_date', ranking_date).eq('room_id', target_room_id).order('message_count', desc=True).limit(10).execute()
    
    if response.data:
        try:
            members = get_chatwork_members(target_room_id)
            room_info = requests.get(f"https://api.chatwork.com/v2/rooms/{target_room_id}", headers={"X-ChatWorkToken": CHATWORK_API_TOKEN}).json()
            user_names = {member['account_id']: member['name'] for member in members}
            room_name = room_info['name']
            
            # 部屋の合計メッセージ数を計算
            total_messages_response = supabase.table('user_message_counts').select('message_count').eq('room_id', target_room_id).execute()
            total_room_messages = sum(item['message_count'] for item in total_messages_response.data)

        except Exception as e:
            send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n指定された部屋({target_room_id})の情報を取得できませんでした。ボットがその部屋に参加しているか確認してください。")
            return

        message_title = f"{room_name}の{ranking_date}個人メッセージ数ランキング\n---\n"
        message_list = ""
        
        # 2. 各ユーザーの合計メッセージ数を取得し、ランキングに加える
        for i, item in enumerate(response.data):
            user_name = user_names.get(item['user_id'], f"ユーザーID {item['user_id']}")
            
            # 個人の累計メッセージ数を取得
            total_count_response = supabase.table('user_message_counts').select('message_count').eq('user_id', item['user_id']).eq('room_id', target_room_id).execute()
            total_user_messages = sum(row['message_count'] for row in total_count_response.data)

            message_list += f"{i+1}位: {user_name}さん\n"
            message_list += f"  - 当日メッセージ数: {item['message_count']}\n"
            message_list += f"  - 累計メッセージ数: {total_user_messages}\n"
        
        message_list += f"\n部屋全体の累計メッセージ数: {total_room_messages}"
        
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n{message_title}{message_list}")

    else:
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n指定された部屋({target_room_id})の{ranking_date}にはまだメッセージがありません。")

def quote_command(room_id, message_id, account_id, message_body):
    """/quote コマンドの処理（返信されたメッセージを引用）"""
    match = re.search(r'\[rp aid=(\d+) to=\d+-(\d+)\]', message_body)
    if not match:
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nこのコマンドは返信として使用してください。")
        return

    quoted_user_id = match.group(1)
    quoted_message_id = match.group(2)
    
    try:
        # 返信先のメッセージ情報を取得
        message_response = requests.get(
            f"https://api.chatwork.com/v2/rooms/{room_id}/messages/{quoted_message_id}",
            headers={"X-ChatWorkToken": CHATWORK_API_TOKEN}
        ).json()
        
        # ユーザー情報を取得
        user_response = requests.get(
            f"https://api.chatwork.com/v2/rooms/{room_id}/members",
            headers={"X-ChatWorkToken": CHATWORK_API_TOKEN}
        ).json()
        
        # ユーザーIDから名前を検索
        quoted_user_name = next((member['name'] for member in user_response if member['account_id'] == int(quoted_user_id)), f"ユーザーID:{quoted_user_id}")
        
        # メッセージ内容を抽出
        quoted_message_body = message_response.get("body", "メッセージ本文の取得に失敗しました。")
        quoted_date = datetime.fromtimestamp(message_response["send_time"]).strftime("%Y/%m/%d %H:%M")
        
        # 引用形式に整形
        quote_text = f"[qt][qtmsg aid={quoted_user_id} file=0 time={message_response['send_time']}]"
        quote_text += f"**{quoted_user_name}**さん\n"
        quote_text += f"{quoted_message_body}"
        quote_text += f"[/qt]\n"
        quote_text += f"（{quoted_date}の投稿を引用）"
        
        send_message_to_chatwork(room_id, quote_text)
        
    except Exception as e:
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n引用の処理中にエラーが発生しました: {e}")

def recount_command(room_id, message_id, account_id, message_body):
    """
    /recount コマンドの処理
    指定ルームのメッセージ数データをリセットし、過去100件を再集計する
    """
    is_admin_user = is_admin(room_id, account_id)
    if not is_admin_user:
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nこのコマンドは管理者のみが実行できます。")
        return

    # コマンドからルームIDを抽出
    match = re.search(r'/recount\s+(\d+)', message_body)
    target_room_id = int(match.group(1)) if match else room_id
    
    try:
        # 1. 指定されたルームのメッセージ数データをすべて削除
        supabase.table('user_message_counts').delete().eq('room_id', target_room_id).execute()
        
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nルームID {target_room_id} のメッセージ数カウントデータをリセットします。過去100件のメッセージを再集計しています...")

        # 2. ChatWork APIから直近100件のメッセージを取得
        messages_response = requests.get(
            f"https://api.chatwork.com/v2/rooms/{target_room_id}/messages",
            headers={"X-ChatWorkToken": CHATWORK_API_TOKEN},
            params={"count": 100}
        )
        messages_response.raise_for_status()
        messages = messages_response.json()
        
        # 3. 取得したメッセージを日時順にソート（ChatWork APIの仕様では新しい順に返されるので、リバースする）
        messages.reverse()

        # 4. 各メッセージの投稿者と日付を抽出して集計
        counts = {}
        for msg in messages:
            msg_date = datetime.fromtimestamp(msg['send_time']).date().isoformat()
            user_id = msg['account']['account_id']
            
            key = (user_id, msg_date)
            if key not in counts:
                counts[key] = {'count': 0, 'last_message_id': msg['message_id']}
            counts[key]['count'] += 1
            
        # 5. 集計結果をデータベースに一括挿入
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
            
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nルームID {target_room_id} の過去100件のメッセージの再集計が完了しました。")

    except Exception as e:
        send_message_to_chatwork(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n再集計中にエラーが発生しました: {e}")


# 全コマンドを辞書にまとめる
COMMANDS = {
    "/test": test_command, "/sorry": sorry_command, "/roominfo": roominfo_command,
    "/say": say_command, "/weather": weather_command, "/whoami": whoami_command,
    "/echo": echo_command, "/timer": timer_command, "/時報": time_report_command,
    "/削除": delete_command, "/quote": quote_command,
    "おみくじ": omikuji_command, "/ranking": ranking_command,
    "/recount": recount_command, # 新しいコマンド
}

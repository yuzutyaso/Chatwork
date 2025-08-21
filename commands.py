import os
import re
import time
import requests
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

from db import supabase
from utils import send_chatwork_message, get_chatwork_members, is_admin

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
    send_chatwork_message(room_id, response_message)

def sorry_command(room_id, message_id, account_id, message_body):
    """/sorry (ユーザーid) コマンドの処理"""
    match = re.search(r'/sorry\s+(\d+)', message_body)
    if not match:
        send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nコマンド形式が正しくありません。例: /sorry 12345")
        return
    
    user_id_to_delete = int(match.group(1))
    
    try:
        response = supabase.table('viewer_list').delete().eq('user_id', user_id_to_delete).execute()
        if response.data:
            send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n{user_id_to_delete}さんを閲覧者リストから削除しました。")
        else:
            send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n指定されたユーザーIDが見つからないか、処理に失敗しました。")
    except Exception as e:
        send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nデータベース処理中にエラーが発生しました: {e}")

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
        send_chatwork_message(room_id, response_message)
    except Exception as e:
        send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nルーム情報の取得に失敗しました。Botがその部屋に入っていない可能性があります。")

def say_command(room_id, message_id, account_id, message_body):
    """/say メッセージ コマンドの処理"""
    message_to_post = message_body.replace("/say ", "", 1)
    send_chatwork_message(room_id, message_to_post)

def weather_command(room_id, message_id, account_id, message_body):
    """/weather 都市名 コマンドの処理"""
    city_name = message_body.replace("/weather ", "", 1)
    if not city_name:
        send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n都市名を入力してください。例: /weather 東京 または /weather 東京都")
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
        send_chatwork_message(room_id, response_message)
    else:
        send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n指定された都市または都道府県が見つかりません。")

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
            send_chatwork_message(room_id, response_message)
        else:
            send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nあなたの情報が見つかりませんでした。")
    except Exception as e:
        send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nエラーが発生しました: {e}")

def echo_command(room_id, message_id, account_id, message_body):
    """/echo コマンドの処理"""
    message_to_echo = message_body.replace("/echo ", "", 1)
    response_message = f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n{message_to_echo}"
    send_chatwork_message(room_id, response_message)
    
def timer_command(room_id, message_id, account_id, message_body):
    """/timer コマンドの処理"""
    match = re.search(r'/timer\s+(\d+m)?\s*(\d+s)?\s*"(.*)"', message_body)
    if not match:
        send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nコマンド形式が正しくありません。例: /timer 5m 30s \"休憩終了\"")
        return

    minutes = int(match.group(1)[:-1]) if match.group(1) else 0
    seconds = int(match.group(2)[:-1]) if match.group(2) else 0
    message_to_post = match.group(3)
    
    total_seconds = minutes * 60 + seconds
    
    if total_seconds > 0:
        send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n{minutes}分{seconds}秒のタイマーを設定しました。")
        time.sleep(total_seconds)
        send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n{message_to_post}")
    else:
        send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nタイマー時間は1秒以上にしてください。")

def time_report_command(room_id, message_id, account_id, message_body):
    """時報コマンドの処理（管理者のみ）"""
    
    # ユーザーが管理者であるかを確認
    if not is_admin(room_id, account_id):
        send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nこのコマンドは管理者のみが実行できます。")
        return

    if "/時報 OK" in message_body:
        try:
            supabase.table('hourly_report_rooms').insert({"room_id": room_id}).execute()
            send_chatwork_message(room_id, "このルームに毎時お知らせを投稿するように設定しました。")
        except Exception as e:
            send_chatwork_message(room_id, f"設定中にエラーが発生しました: {e}")
    elif "/時報 NO" in message_body:
        try:
            supabase.table('hourly_report_rooms').delete().eq('room_id', room_id).execute()
            send_chatwork_message(room_id, "このルームの毎時お知らせを解除しました。")
        except Exception as e:
            send_chatwork_message(room_id, f"解除中にエラーが発生しました: {e}")
    else:
        send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nコマンド形式が正しくありません。例: /時報 OK または /時報 NO")

def omikuji_command(room_id, message_id, account_id, message_body):
    """おみくじ コマンドの処理"""
    today = datetime.now().date()
    
    response = supabase.table('omikuji_history').select('last_drawn_date').eq('user_id', account_id).execute()
    data = response.data
    
    if data and datetime.strptime(data[0]['last_drawn_date'], '%Y-%m-%d').date() == today:
        send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n今日のおみくじはすでに引きました。また明日試してくださいね！")
    else:
        # 確率でおみくじの結果を決定
        results = [
            "大吉"] * 10 + ["中吉"] * 20 + ["小吉"] * 30 + ["吉"] * 20 + ["末吉"] * 10 + ["凶"] * 5 + ["大凶"] * 5
        result = random.choice(results)
        
        if data:
            supabase.table('omikuji_history').update({"last_drawn_date": today.isoformat()}).eq('user_id', account_id).execute()
        else:
            supabase.table('omikuji_history').insert({"user_id": account_id, "last_drawn_date": today.isoformat()}).execute()
        
        send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nあなたのおみくじは... **{result}** です！")

def ranking_command(room_id, message_id, account_id, message_body):
    """/ranking all または /ranking yyyy/mm/dd コマンドの処理"""
    parts = message_body.split()
    command_type = parts[1] if len(parts) > 1 else None

    if command_type == "all":
        response = supabase.table('room_message_counts').select('*').order('message_count', desc=True).limit(10).execute()
        if response.data:
            message = "本日のメッセージ数ランキング (全ルーム)\n---\n"
            for i, item in enumerate(response.data):
                try:
                    # ルームIDから部屋名を取得
                    room_info = requests.get(f"https://api.chatwork.com/v2/rooms/{item['room_id']}", headers={"X-ChatWorkToken": CHATWORK_API_TOKEN}).json()
                    room_name = room_info.get('name', '取得失敗')
                    message += f"{i+1}位: {room_name} - {item['message_count']}メッセージ\n"
                except Exception:
                    message += f"{i+1}位: ルームID {item['room_id']} (部屋名取得失敗) - {item['message_count']}メッセージ\n"
            send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n{message}")
        else:
            send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nまだメッセージがありません。")

    else:
        date_str = command_type if command_type else datetime.now().date().strftime('%Y/%m/%d')
        try:
            ranking_date = datetime.strptime(date_str, '%Y/%m/%d').date().isoformat()
        except ValueError:
            send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n日付の形式が正しくありません。例: /ranking 2025/08/21")
            return

        response = supabase.table('user_message_counts').select('*').eq('message_date', ranking_date).eq('room_id', room_id).order('message_count', desc=True).limit(10).execute()
        
        if response.data:
            # ルームメンバーリストを取得してユーザーIDと名前をマッピング
            members = get_chatwork_members(room_id)
            user_names = {member['account_id']: member['name'] for member in members}
            
            message = f"{date_str}の個人メッセージ数ランキング\n---\n"
            for i, item in enumerate(response.data):
                user_name = user_names.get(item['user_id'], f"ユーザーID {item['user_id']}")
                message += f"{i+1}位: {user_name}さん - {item['message_count']}メッセージ\n"
            send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n{message}")
        else:
            send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n{date_str}にはまだメッセージがありません。")

# 全コマンドを辞書にまとめる
commands = {
    "/test": test_command, "/sorry": sorry_command, "/roominfo": roominfo_command,
    "/say": say_command, "/weather": weather_command, "/whoami": whoami_command,
    "/echo": echo_command, "/timer": timer_command, "/時報": time_report_command,
    "おみくじ": omikuji_command, "/ranking": ranking_command,
            }

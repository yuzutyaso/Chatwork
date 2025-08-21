import os
import re
import time
import requests
import schedule
from flask import Flask, request, jsonify
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client

# 環境変数の読み込み
load_dotenv()

# --- 環境変数の設定 ---
CHATWORK_API_TOKEN = os.getenv("CHATWORK_API_TOKEN")
SUPABASE_URL: str = os.getenv("SUPABASE_URL")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY")
OPENWEATHER_API_KEY: str = os.getenv("OPENWEATHER_API_KEY")
BOT_ACCOUNT_ID = os.getenv("BOT_ACCOUNT_ID")

# --- Supabaseクライアントの初期化 ---
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Flaskアプリの初期化 ---
app = Flask(__name__)

# --- 絵文字リストの定義 ---
EMOJIS = [
    ':)', ':(', ':D', '8-)', ':o', ';)', '((sweat))', ':|', ':*', ':p', '(blush)',
    ':^)', '|-)', '(inlove)', ':]', '(talk)', '(yawn)', '(puke)', '(emo)', '8-|',
    ':#', '(nod)', '(shake)', '(^^;)', '(whew)', '(clap)', '(bow)', '(roger)',
    '(flex)', '(dance)', '(:/)', '(gogo)', '(think)', '(please)', '(quick)',
    '(anger)', '(devil)', '(lightbulb)', '(*)', '(h)', '(F)', '(cracker)',
    '(eat)', '(^)', '(coffee)', '(beer)', '(handshake)', '(y)'
]

# --- 共通のユーティリティ関数 ---
def send_chatwork_message(room_id, message_body):
    """Chatworkにメッセージを送信する関数"""
    url = f"https://api.chatwork.com/v2/rooms/{room_id}/messages"
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    payload = {"body": message_body}
    requests.post(url, headers=headers, data=payload)
    # レート制限回避のための一時停止
    time.sleep(1)

def get_chatwork_members(room_id):
    """ルームのメンバー情報を取得する関数"""
    url = f"https://api.chatwork.com/v2/rooms/{room_id}/members"
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    response = requests.get(url, headers=headers)
    return response.json()

def change_user_role(room_id, user_id, role="readonly"):
    """ユーザーの権限を変更する関数"""
    url = f"https://api.chatwork.com/v2/rooms/{room_id}/members"
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    payload = {
        "members_admin_ids": ",".join([str(m['account_id']) for m in get_chatwork_members(room_id) if m['role'] == 'admin']),
        "members_member_ids": ",".join([str(m['account_id']) for m in get_chatwork_members(room_id) if m['role'] == 'member' and m['account_id'] != user_id]),
        "members_readonly_ids": ",".join([str(m['account_id']) for m in get_chatwork_members(room_id) if m['role'] == 'readonly' or m['account_id'] == user_id])
    }
    requests.put(url, headers=headers, data=payload)

def is_admin(room_id, account_id):
    """ユーザーが管理者かどうかを判定する関数"""
    members = get_chatwork_members(room_id)
    for member in members:
        if member['account_id'] == account_id:
            return member['role'] == 'admin'
    return False

# --- ここに各コマンドの関数を定義 ---

def test_command(room_id, message_id, account_id, message_body):
    """/test コマンドの処理"""
    response_message = "Botは正常に動作しています。成功です。"
    send_chatwork_message(room_id, response_message)

def sorry_command(room_id, message_id, account_id, message_body):
    """/sorry (ユーザーid) コマンドの処理"""
    match = re.search(r'/sorry\s+(\d+)', message_body)
    if not match:
        send_chatwork_message(room_id, "[rp aid={} to={}-{}][pname:{}]さん\nコマンド形式が正しくありません。例: /sorry 12345".format(account_id, room_id, message_id, account_id))
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
        members_url = f"https://api.chatwork.com/v2/rooms/{target_room_id}/members"
        room_url = f"https://api.chatwork.com/v2/rooms/{target_room_id}"
        headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
        
        members_res = requests.get(members_url, headers=headers)
        room_res = requests.get(room_url, headers=headers)

        if members_res.status_code == 200 and room_res.status_code == 200:
            members = members_res.json()
            room_info = room_res.json()
            
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
        else:
            send_chatwork_message(room_id, "[rp aid={} to={}-{}][pname:{}]さん\nルーム情報の取得に失敗しました。Botがその部屋に入っていない可能性があります。".format(account_id, room_id, message_id, account_id))
    except Exception as e:
        send_chatwork_message(room_id, f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nエラーが発生しました: {e}")

def say_command(room_id, message_id, account_id, message_body):
    """/say メッセージ コマンドの処理"""
    message_to_post = message_body.replace("/say ", "", 1)
    send_chatwork_message(room_id, message_to_post)

def weather_command(room_id, message_id, account_id, message_body):
    """/weather 都市名 コマンドの処理"""
    city_name = message_body.replace("/weather ", "", 1)
    if not city_name:
        send_chatwork_message(room_id, "[rp aid={} to={}-{}][pname:{}]さん\n都市名を入力してください。例: /weather 東京".format(account_id, room_id, message_id, account_id))
        return
    
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={OPENWEATHER_API_KEY}&units=metric&lang=ja"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        weather = data['weather'][0]['description']
        temp = data['main']['temp']
        humidity = data['main']['humidity']
        wind_speed = data['wind']['speed']
        
        response_message = f"""
        [rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん
        {city_name}の天気予報
        ---
        天気: {weather}
        気温: {temp}℃
        湿度: {humidity}%
        風速: {wind_speed}m/s
        """
        send_chatwork_message(room_id, response_message)
    else:
        send_chatwork_message(room_id, "[rp aid={} to={}-{}][pname:{}]さん\n指定された都市が見つかりません。".format(account_id, room_id, message_id, account_id))

def whoami_command(room_id, message_id, account_id, message_body):
    """/whoami コマンドの処理"""
    # 実際にはChatwork APIを叩いてユーザー情報を取得する
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
            send_chatwork_message(room_id, "[rp aid={} to={}-{}][pname:{}]さん\nあなたの情報が見つかりませんでした。".format(account_id, room_id, message_id, account_id))
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
        send_chatwork_message(room_id, "[rp aid={} to={}-{}][pname:{}]さん\nコマンド形式が正しくありません。例: /timer 5m 30s \"休憩終了\"".format(account_id, room_id, message_id, account_id))
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
        send_chatwork_message(room_id, "[rp aid={} to={}-{}][pname:{}]さん\nタイマー時間は1秒以上にしてください。".format(account_id, room_id, message_id, account_id))

def time_report_command(room_id, message_id, account_id, message_body):
    """/時報 コマンドの処理"""
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
        send_chatwork_message(room_id, "[rp aid={} to={}-{}][pname:{}]さん\nコマンド形式が正しくありません。例: /時報 OK または /時報 NO".format(account_id, room_id, message_id, account_id))

# --- コマンド実行関数の登録 ---
# 新しいコマンドを追加する際は、ここに `コマンド名: 実行関数` の形式で追加
commands = {
    "/test": test_command,
    "/sorry": sorry_command,
    "/roominfo": roominfo_command,
    "/say": say_command,
    "/weather": weather_command,
    "/whoami": whoami_command,
    "/echo": echo_command,
    "/timer": timer_command,
    "/時報": time_report_command,
    # /ranking コマンドはロジックが複雑なため、別途実装が必要
}

# --- メッセージ受信時のメイン処理 ---
@app.route('/callback', methods=['POST'])
def chatwork_callback():
    """ChatworkのWebhookからメッセージを受信した際の処理"""
    data = request.json
    if data and data['webhook_event_type'] == 'message_created':
        room_id = data['webhook_event']['room_id']
        message_id = data['webhook_event']['message_id']
        account_id = data['webhook_event']['account_id']
        message_body = data['webhook_event']['body']
        
        # Bot自身のメッセージは無視
        if str(account_id) == str(BOT_ACCOUNT_ID):
            return jsonify({'status': 'ok'})

        # コマンドの判定と実行
        for command_name, command_func in commands.items():
            if message_body.startswith(command_name):
                # /timerのように時間のかかる処理は非同期で実行する
                if command_name == "/timer":
                    import threading
                    thread = threading.Thread(target=command_func, args=(room_id, message_id, account_id, message_body))
                    thread.start()
                else:
                    command_func(room_id, message_id, account_id, message_body)
                return jsonify({'status': 'ok'})

        # [toall]と絵文字の判定
        is_admin_user = is_admin(room_id, account_id)
        
        if "[toall]" in message_body:
            if is_admin_user:
                send_chatwork_message(room_id, "[rp aid={} to={}-{}][pname:{}]さん\n[toall]タグの使用は控えてください。".format(account_id, room_id, message_id, account_id))
            else:
                change_user_role(room_id, account_id)
                send_chatwork_message(room_id, "[rp aid={} to={}-{}][pname:{}]さん\n[toall]タグが検出されたため、{user_name}さんの権限を閲覧に変更しました。".format(account_id, room_id, message_id, account_id, user_name="ユーザー名")) # ユーザー名は別途取得

        emoji_count = sum(message_body.count(emoji) for emoji in EMOJIS)
        if emoji_count >= 15:
            if is_admin_user:
                send_chatwork_message(room_id, "[rp aid={} to={}-{}][pname:{}]さん\n絵文字が多すぎます。ご注意ください。".format(account_id, room_id, message_id, account_id))
            else:
                change_user_role(room_id, account_id)
                send_chatwork_message(room_id, "[rp aid={} to={}-{}][pname:{}]さん\n絵文字が多すぎるため、{user_name}さんの権限を閲覧に変更しました。".format(account_id, room_id, message_id, account_id, user_name="ユーザー名")) # ユーザー名は別途取得
        
    return jsonify({'status': 'ok'})

# --- 定期実行ジョブの設定 (時報) ---
def hourly_report_job():
    """時報を投稿する定期実行処理"""
    try:
        response = supabase.table('hourly_report_rooms').select('room_id').execute()
        room_ids_to_notify = [item['room_id'] for item in response.data]
        
        current_time = datetime.now().strftime("%H時%M分")
        message = f"現在の時刻は {current_time} です。"
        
        for room_id in room_ids_to_notify:
            send_chatwork_message(room_id, message)
    except Exception as e:
        print(f"時報の定期実行中にエラーが発生しました: {e}")

# スケジューラーの起動
schedule.every().hour.at(":00").do(hourly_report_job)
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

# スケジューラースレッドの開始
import threading
scheduler_thread = threading.Thread(target=run_scheduler)
scheduler_thread.start()

# --- アプリケーションの起動 ---
if __name__ == '__main__':
    # RenderはPORT環境変数を使用
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

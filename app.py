import os
import random
import requests
import google.generativeai as genai
import chatwork
from datetime import date
import wikipedia
from flask import Flask, request

# --- 環境変数からAPIキーとボットIDを取得 ---
try:
    CHATWORK_API_TOKEN = os.environ['CHATWORK_API_TOKEN']
    BOT_ACCOUNT_ID = int(os.environ['BOT_ACCOUNT_ID'])
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    OPENWEATHERMAP_API_KEY = os.environ.get('OPENWEATHERMAP_API_KEY')

    # Gemini APIキーが設定されていれば設定
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
except KeyError as e:
    print(f"Error: 環境変数 {e} が設定されていません。")
    exit(1)

# --- グローバル変数とクライアントの初期化 ---
cw_client = chatwork.ChatworkAPI(token=CHATWORK_API_TOKEN)
app = Flask(__name__)

# チャット履歴を保持する辞書
chat_sessions = {}
# おみくじ履歴を保持する辞書
omikuji_history = {}

# 都道府県マッピング
prefectures_map = {
    "北海道": "Hokkaido", "青森": "Aomori", "岩手": "Iwate", "宮城": "Miyagi", "秋田": "Akita",
    "山形": "Yamagata", "福島": "Fukushima", "茨城": "Ibaraki", "栃木": "Tochigi", "群馬": "Gunma",
    "埼玉": "Saitama", "千葉": "Chiba", "東京": "Tokyo", "神奈川": "Kanagawa", "新潟": "Niigata",
    "富山": "Toyama", "石川": "Ishikawa", "福井": "Fukui", "山梨": "Yamanashi", "長野": "Nagano",
    "岐阜": "Gifu", "静岡": "Shizuoka", "愛知": "Aichi", "三重": "Mie", "滋賀": "Shiga",
    "京都": "Kyoto", "大阪": "Osaka", "兵庫": "Hyogo", "奈良": "Nara", "和歌山": "Wakayama",
    "鳥取": "Tottori", "島根": "Shimane", "岡山": "Okayama", "広島": "Hiroshima", "山口": "Yamaguchi",
    "徳島": "Tokushima", "香川": "Kagawa", "愛媛": "Ehime", "高知": "Kochi", "福岡": "Fukuoka",
    "佐賀": "Saga", "長崎": "Nagasaki", "熊本": "Kumamoto", "大分": "Oita", "宮崎": "Miyazaki",
    "鹿児島": "Kagoshima", "沖縄": "Okinawa"
}

# --- Webhookエンドポイント ---
@app.route('/webhook', methods=['POST'])
def handle_webhook():
    data = request.json
    room_id = data.get('room_id')
    account_id = data.get('account_id')
    message_id = data.get('message_id')
    message_body = data.get('body', '')

    # 1. ボット自身の投稿には反応しない
    if account_id == BOT_ACCOUNT_ID:
        return 'OK'

    # 2. 絵文字と[toall]の権限変更ロジック
    emoji_list = [":)", ":(", ":D", "8-)", ":o", ";)", ":sweat:", ":|", ":*", ":p", ":blush:", ":^)", "|-)", ":inlove:", ":]", ":talk:", ":yawn:", ":puke:", ":emo:", "8-|", ":#", ":nod:", ":shake:", ":^^;", ":whew:", ":clap:", ":bow:", ":roger:", ":flex:", ":dance:", ":/", ":gogo:", ":think:", ":please:", ":quick:", ":anger:", ":devil:", ":lightbulb:", ":*", ":h:", ":F:", ":cracker:", ":eat:", ":^:", ":coffee:", ":beer:", ":handshake:", ":y:"]
    emoji_count = sum(message_body.count(e) for e in emoji_list)

    is_admin = False
    try:
        members = cw_client.get_room_members(room_id)
        for member in members:
            if member['account_id'] == account_id and member['role'] == 'admin':
                is_admin = True
                break
    except chatwork.ChatworkAPIException:
        is_admin = False # APIエラーの場合も管理者と見なさない

    if not is_admin and (emoji_count >= 15 or "[toall]" in message_body):
        try:
            for member in members:
                if member['role'] != 'admin' and member['account_id'] != account_id:
                    cw_client.update_room_members(room_id, members=f"readonly:{member['account_id']}")
            
            # 返信はここではしない。権限変更のみ。
            
        except Exception as e:
            print(f"権限変更に失敗しました: {e}")
        return 'OK'


    # --- 3. 各種コマンドの処理 ---
    
    # /help
    if message_body == "/help":
        help_message = (
            "[info]対応コマンド一覧\n"
            "・おみくじ: 運勢を占います（1日1回）\n"
            "・/news: 最新のメッセージを取得します\n"
            "・/roominfo [roomid]: 部屋の情報を取得します\n"
            "・/ai [質問]: AIと話せます\n"
            "・/ai reset: AIとのチャット履歴をリセットします（管理者のみ）\n"
            "・/see all: 参加している全ての部屋のメッセージを既読にします（管理者のみ）\n"
            "・/dice [数]: サイコロを振ります\n"
            "・/whoami: 自分の情報を取得します\n"
            "・/echo [メッセージ]: メッセージをオウム返しします（管理者のみ）\n"
            "・/weather [都市名]: 天気予報を取得します\n"
            "・/wikipedia [キーワード]: Wikipediaの記事の要約を取得します\n"
            "・/random user: 部屋のメンバーをランダムに選びます\n"
            "・/help: このヘルプを表示します[/info]"
        )
        cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + help_message)
        return 'OK'

    # /ai reset
    if message_body == "/ai reset":
        if is_admin:
            if room_id in chat_sessions:
                del chat_sessions[room_id]
                reply_body = "チャット履歴をリセットしました。"
            else:
                reply_body = "リセットするチャット履歴はありませんでした。"
        else:
            reply_body = "このコマンドは管理者のみ実行できます。"
        cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        return 'OK'

    # /ai
    if message_body.startswith("/ai "):
        question = message_body.replace("/ai ", "", 1).strip()
        if not question:
            reply_body = "質問を入力してください。例: /ai 日本の首都はどこ？"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
            return 'OK'
        
        if not GEMINI_API_KEY:
            reply_body = "Gemini APIキーが設定されていません。"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
            return 'OK'

        try:
            if room_id not in chat_sessions:
                model = genai.GenerativeModel('gemini-1.5-flash')
                chat = model.start_chat(history=[])
                chat_sessions[room_id] = chat
            else:
                chat = chat_sessions[room_id]
            
            response = chat.send_message(question)
            ai_response_text = response.text
            reply_body = f"質問：{question}\n\n回答：{ai_response_text}"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        except Exception as e:
            reply_body = f"AIとの対話中にエラーが発生しました。{e}"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        return 'OK'

    # /see all
    if message_body == "/see all":
        if not is_admin:
            reply_body = "このコマンドは管理者のみ実行できます。"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
            return 'OK'
        try:
            all_rooms = cw_client.get_rooms()
            read_rooms_count = 0
            for room in all_rooms:
                try:
                    cw_client.update_messages_read(room['room_id'])
                    read_rooms_count += 1
                except Exception:
                    pass
            reply_body = f"参加している全{read_rooms_count}部屋のメッセージを既読にしました。"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        except Exception as e:
            reply_body = f"メッセージの既読化に失敗しました。{e}"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        return 'OK'

    # /news
    if message_body == "/news":
        try:
            recent_messages = cw_client.get_messages(room_id)
            if recent_messages:
                latest_message = recent_messages[0]
                latest_sender_id = latest_message['account_id']
                latest_message_body = latest_message['body']
                reply_body = f"最新の情報です：\n投稿者：[picon:{latest_sender_id}]\n本文：\n{latest_message_body}"
            else:
                reply_body = "この部屋にはまだメッセージがありません。"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        except Exception as e:
            reply_body = f"最新情報の取得に失敗しました。{e}"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        return 'OK'

    # おみくじ
    if message_body == "おみくじ":
        today = date.today().isoformat()
        if account_id in omikuji_history and omikuji_history[account_id] == today:
            reply_body = "本日はすでにおみくじを引きました。また明日挑戦してください！"
        else:
            omikuji_results = ["大吉", "中吉", "小吉", "吉", "末吉", "凶", "大凶"]
            result = random.choice(omikuji_results)
            omikuji_history[account_id] = today
            reply_body = f"あなたのおみくじの結果は「{result}」です！"
        cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        return 'OK'

    # /dice
    if message_body.startswith("/dice"):
        try:
            parts = message_body.split()
            dice_sides = 6
            if len(parts) > 1:
                dice_sides = int(parts[1])
            if dice_sides > 0:
                result = random.randint(1, dice_sides)
                reply_body = f"{dice_sides}面ダイスを振りました。結果は「{result}」です。"
            else:
                reply_body = "サイコロの面数は1以上の数字で指定してください。"
        except ValueError:
            reply_body = "サイコロの面数は半角数字で指定してください。"
        except Exception as e:
            reply_body = f"コマンドの実行に失敗しました。{e}"
        cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        return 'OK'

    # /roominfo
    if message_body.startswith("/roominfo"):
        try:
            room_id_to_find = int(message_body.split()[1])
            all_rooms = cw_client.get_rooms()
            target_room_info = None
            for room in all_rooms:
                if room['room_id'] == room_id_to_find:
                    target_room_info = room
                    break
            if target_room_info:
                room_name = target_room_info['name']
                message_num = target_room_info['message_num']
                members = cw_client.get_room_members(room_id_to_find)
                admin_picons = ''.join([f"[picon:{m['account_id']}]" for m in members if m['role'] == 'admin'])
                reply_body = f"{room_name}と、message数({message_num})、管理者{admin_picons}"
            else:
                reply_body = "指定された部屋はボットが参加していません。"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        except (IndexError, ValueError):
            reply_body = "部屋IDが正しく指定されていません。例: /roominfo 1234567"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        except Exception as e:
            reply_body = f"部屋情報の取得に失敗しました。{e}"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        return 'OK'

    # /whoami
    if message_body == "/whoami":
        try:
            members = cw_client.get_room_members(room_id)
            my_info = next((m for m in members if m['account_id'] == account_id), None)
            if my_info:
                reply_body = (
                    f"あなたの情報です。\n"
                    f"アカウントID: {my_info['account_id']}\n"
                    f"名前: {my_info['name']}\n"
                    f"ロール: {my_info['role']}\n"
                    f"自己紹介: {my_info['introduction']}"
                )
            else:
                reply_body = "あなたの情報が見つかりませんでした。"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        except Exception as e:
            reply_body = f"コマンドの実行に失敗しました。{e}"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        return 'OK'

    # /echo
    if message_body.startswith("/echo"):
        if not is_admin:
            reply_body = "このコマンドは管理者のみ実行できます。"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
            return 'OK'
        echo_message = message_body[len("/echo "):].strip()
        if echo_message:
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + echo_message)
        else:
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + "オウム返しするメッセージを入力してください。")
        return 'OK'
        
    # /weather
    if message_body.startswith("/weather"):
        try:
            parts = message_body.split()
            if len(parts) < 2:
                reply_body = "都市名を指定してください。例: /weather 東京"
                cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
                return 'OK'
            city_name_ja = parts[1]
            city_name_en = prefectures_map.get(city_name_ja)
            if not city_name_en:
                reply_body = "指定された都市は天気予報の対象外です。"
                cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
                return 'OK'
            if not OPENWEATHERMAP_API_KEY:
                reply_body = "天気予報APIキーが設定されていません。"
                cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
                return 'OK'
            api_url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name_en},jp&appid={OPENWEATHERMAP_API_KEY}&units=metric&lang=ja"
            response = requests.get(api_url)
            weather_data = response.json()
            if weather_data['cod'] == 200:
                weather = weather_data['weather'][0]['description']
                temp = weather_data['main']['temp']
                humidity = weather_data['main']['humidity']
                reply_body = f"{city_name_ja}の天気\n天気: {weather}\n気温: {temp}°C\n湿度: {humidity}%"
            else:
                reply_body = f"天気情報の取得に失敗しました。エラーコード: {weather_data['cod']}"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        except Exception as e:
            reply_body = f"コマンドの実行に失敗しました。{e}"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        return 'OK'

    # /wikipedia
    if message_body.startswith("/wikipedia"):
        try:
            wikipedia.set_lang("ja")
            keyword = message_body.replace("/wikipedia", "", 1).strip()
            if not keyword:
                reply_body = "検索キーワードを入力してください。例: /wikipedia チャットワーク"
            else:
                page = wikipedia.page(keyword, auto_suggest=True)
                summary = wikipedia.summary(keyword, sentences=3)
                reply_body = f"【Wikipedia】{page.title}\n{summary}\n詳しくは[url]{page.url}[/url]"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        except wikipedia.exceptions.PageError:
            reply_body = "指定されたキーワードの記事が見つかりませんでした。"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        except wikipedia.exceptions.DisambiguationError as e:
            reply_body = f"複数の候補が見つかりました: {', '.join(e.options[:5])}..."
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        except Exception as e:
            reply_body = f"コマンドの実行に失敗しました。{e}"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        return 'OK'

    # /random user
    if message_body == "/random user":
        try:
            members = cw_client.get_room_members(room_id)
            if members:
                chosen_user = random.choice(members)
                reply_body = f"今回選ばれたのは、あなたです！ → [picon:{chosen_user['account_id']}] {chosen_user['name']}さん"
            else:
                reply_body = "この部屋にメンバーがいません。"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        except Exception as e:
            reply_body = f"コマンドの実行に失敗しました。{e}"
            cw_client.post_messages(room_id, body=f"[rp aid={account_id} to={room_id}-{message_id}]" + reply_body)
        return 'OK'

    # --- 最終的な応答 ---
    return 'OK'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

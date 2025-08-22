import os
import requests
import re
from db import supabase

# 環境変数の読み込み
CHATWORK_API_TOKEN = os.getenv("CHATWORK_API_TOKEN")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

# --- ChatWork関連の汎用関数 ---

def send_message_to_chatwork(room_id, message_body):
    """指定されたルームにメッセージを送信する汎用関数"""
    url = f"https://api.chatwork.com/v2/rooms/{room_id}/messages"
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    data = {"body": message_body}
    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as err:
        print(f"HTTPエラーが発生しました: {err}")
        print(f"レスポンスボディ: {err.response.text}")
    except requests.exceptions.RequestException as e:
        print(f"メッセージの送信中にエラーが発生しました: {e}")
    return None

def send_reply(room_id, message_id, account_id, text):
    """
    指定されたメッセージに返信する汎用関数

    Args:
        room_id (str): ChatWorkのルームID
        message_id (str): 返信元のメッセージID
        account_id (str): 返信元のユーザーアカウントID
        text (str): 送信するメッセージ本文
    """
    reply_prefix = f"[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n"
    message_to_send = reply_prefix + text
    send_message_to_chatwork(room_id, message_to_send)

def get_chatwork_members(room_id):
    """指定されたルームのメンバーリストを取得する汎用関数"""
    url = f"https://api.chatwork.com/v2/rooms/{room_id}/members"
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"メンバーリストの取得中にエラーが発生しました: {e}")
        return []

def is_admin(room_id, account_id):
    """指定されたユーザーが管理者かどうかを判定する汎用関数"""
    members = get_chatwork_members(room_id)
    for member in members:
        if member['account_id'] == account_id and member['role'] == 'admin':
            return True
    return False

def change_user_role(room_id, account_id, role):
    """
    ユーザーの権限を安全に変更する汎用関数。
    - 変更したいユーザーと、現在のメンバー全員の権限を一度にPUTで更新する
    """
    try:
        current_members = get_chatwork_members(room_id)
        if not current_members:
            return None, "メンバー情報の取得に失敗しました。"

        admin_ids = []
        member_ids = []
        readonly_ids = []

        for member in current_members:
            # 権限を変更するユーザー
            if member['account_id'] == account_id:
                if role == 'admin':
                    admin_ids.append(member['account_id'])
                elif role == 'member':
                    member_ids.append(member['account_id'])
                elif role == 'readonly':
                    readonly_ids.append(member['account_id'])
            # 他のメンバーは現在の権限を維持
            else:
                if member['role'] == 'admin':
                    admin_ids.append(member['account_id'])
                elif member['role'] == 'member':
                    member_ids.append(member['account_id'])
                elif member['role'] == 'readonly':
                    readonly_ids.append(member['account_id'])

        url = f"https://api.chatwork.com/v2/rooms/{room_id}/members"
        headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
        data = {
            "members_admin_ids": ",".join(map(str, admin_ids)),
            "members_member_ids": ",".join(map(str, member_ids)),
            "members_readonly_ids": ",".join(map(str, readonly_ids))
        }

        response = requests.put(url, headers=headers, data=data)
        response.raise_for_status()
        return response.json(), None

    except requests.exceptions.RequestException as e:
        print(f"ユーザー権限の変更中にエラーが発生しました: {e}")
        return None, f"APIエラー: {e}"

# --- 天気関連の汎用関数 ---

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

def get_weather_info(city_name):
    """
    OpenWeatherMap APIから天気情報を取得する

    Args:
        city_name (str): 取得したい都市名

    Returns:
        dict: 天気情報を含む辞書、またはエラーメッセージ
    """
    if not city_name:
        return {"error": "都市名が指定されていません。"}

    if city_name in JAPAN_PREFECTURES:
        city_name = JAPAN_PREFECTURES[city_name]

    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name},jp&appid={OPENWEATHER_API_KEY}&units=metric&lang=ja"

    try:
        response = requests.get(url)
        response.raise_for_status()
        return {"data": response.json(), "city": city_name}
    except requests.exceptions.HTTPError as err:
        if err.response.status_code == 404:
            return {"error": f"指定された都市名({city_name})が見つかりませんでした。"}
        else:
            return {"error": f"APIエラーが発生しました: {err}"}
    except requests.exceptions.RequestException as e:
        return {"error": f"天気情報の取得中にエラーが発生しました: {e}"}

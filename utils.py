import os
import requests
from db import supabase

# 環境変数の読み込み
CHATWORK_API_TOKEN = os.getenv("CHATWORK_API_TOKEN")

def send_message_to_chatwork(room_id, message_body):
    """指定されたルームにメッセージを送信する汎用関数"""
    url = f"https://api.chatwork.com/v2/rooms/{room_id}/messages"
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    data = {"body": message_body}
    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status() # 200番台以外のステータスコードで例外を発生させる
        return response.json()
    except requests.exceptions.HTTPError as err:
        print(f"HTTPエラーが発生しました: {err}")
        print(f"レスポンスボディ: {err.response.text}")
    except Exception as e:
        print(f"メッセージの送信中にエラーが発生しました: {e}")
    return None

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
    """ユーザーの権限を変更する汎用関数"""
    url = f"https://api.chatwork.com/v2/rooms/{room_id}/members"
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    data = {
        "members_admin_ids": account_id if role == 'admin' else '',
        "members_member_ids": account_id if role == 'member' else '',
        "members_readonly_ids": account_id if role == 'readonly' else ''
    }
    try:
        response = requests.put(url, headers=headers, data=data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"ユーザー権限の変更中にエラーが発生しました: {e}")
        return None

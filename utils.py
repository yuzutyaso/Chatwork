import os
import time
import requests
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()
CHATWORK_API_TOKEN = os.getenv("CHATWORK_API_TOKEN")

def send_chatwork_message(room_id, message_body):
    url = f"https://api.chatwork.com/v2/rooms/{room_id}/messages"
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    payload = {"body": message_body}
    requests.post(url, headers=headers, data=payload)
    time.sleep(1)

def get_chatwork_members(room_id):
    url = f"https://api.chatwork.com/v2/rooms/{room_id}/members"
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    response = requests.get(url, headers=headers)
    return response.json()

def change_user_role(room_id, user_id, role="readonly"):
    members = get_chatwork_members(room_id)
    admin_ids = [str(m['account_id']) for m in members if m['role'] == 'admin']
    member_ids = [str(m['account_id']) for m in members if m['role'] == 'member' and m['account_id'] != user_id]
    readonly_ids = [str(m['account_id']) for m in members if m['role'] == 'readonly' or m['account_id'] == user_id]
    url = f"https://api.chatwork.com/v2/rooms/{room_id}/members"
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    payload = {
        "members_admin_ids": ",".join(admin_ids),
        "members_member_ids": ",".join(member_ids),
        "members_readonly_ids": ",".join(readonly_ids)
    }
    requests.put(url, headers=headers, data=payload)

def is_admin(room_id, account_id):
    members = get_chatwork_members(room_id)
    for member in members:
        if member['account_id'] == account_id:
            return member['role'] == 'admin'
    return False

import os
import httpx
import asyncio
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()

# --- ChatWork APIトークンを環境変数から取得 ---
CHATWORK_API_TOKEN = os.getenv("CHATWORK_API_TOKEN")

# --- APIリクエストの共通関数 ---
async def _chatwork_api_request(method, endpoint, headers, data=None):
    """
    ChatWork APIへのリクエストを共通化する関数。
    非同期通信ライブラリhttpxを使用。
    """
    base_url = "https://api.chatwork.com/v2"
    url = f"{base_url}/{endpoint}"
    async with httpx.AsyncClient() as client:
        try:
            if method.upper() == 'GET':
                response = await client.get(url, headers=headers)
            elif method.upper() == 'POST':
                response = await client.post(url, headers=headers, data=data)
            else:
                raise ValueError("Unsupported HTTP method.")
            
            response.raise_for_status() # HTTPステータスコードが2xx以外の場合は例外を発生させる
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"HTTPエラーが発生しました: {e.response.status_code}")
            return {"error": f"HTTPStatusError: {e.response.status_code}"}
        except httpx.RequestError as e:
            print(f"リクエスト中にエラーが発生しました: {e}")
            return {"error": f"RequestError: {e}"}

# --- メッセージ送信関数 ---
def send_message_to_chatwork(room_id, message_body):
    """
    ChatWorkにメッセージを送信する関数。
    同期的に実行するため、内部でasyncio.runを使用。
    """
    asyncio.run(_chatwork_api_request('POST', f"rooms/{room_id}/messages", {"X-ChatWorkToken": CHATWORK_API_TOKEN}, data={"body": message_body}))

# --- メンバー情報取得関数 ---
def get_chatwork_members(room_id):
    """
    ルームのメンバーリストを取得する関数。
    同期的に実行するため、内部でasyncio.runを使用。
    """
    response = asyncio.run(_chatwork_api_request('GET', f"rooms/{room_id}/members", {"X-ChatWorkToken": CHATWORK_API_TOKEN}))
    return response

# --- 管理者判定関数 ---
def is_admin(room_id, account_id):
    """
    指定されたアカウントIDがルームの管理者であるかを判定する関数。
    内包表記を使い、コードを簡潔に。
    """
    members = get_chatwork_members(room_id)
    # メンバーリストからアカウントIDと'role'が'admin'のメンバーが存在するかをチェック
    return any(member['account_id'] == account_id and member['role'] == 'admin' for member in members)

# --- ユーザー権限変更関数 ---
def change_user_role(room_id, account_id, role):
    """
    指定されたアカウントIDのユーザー権限を変更する関数。
    `role`は`member`、`admin`、`readonly`から指定。
    """
    asyncio.run(_change_user_role_async(room_id, account_id, role))

async def _change_user_role_async(room_id, account_id, role):
    """
    ユーザー権限を変更する非同期ヘルパー関数。
    """
    endpoint = f"rooms/{room_id}/members"
    headers = {"X-ChatWorkToken": CHATWORK_API_TOKEN}
    data = {"members_admin_ids": "", "members_member_ids": "", "members_readonly_ids": ""}

    members = await get_chatwork_members(room_id)
    
    # 全メンバーを一旦現在の権限に分類
    admin_ids = [m['account_id'] for m in members if m['role'] == 'admin']
    member_ids = [m['account_id'] for m in members if m['role'] == 'member']
    readonly_ids = [m['account_id'] for m in members if m['role'] == 'readonly']

    # 対象ユーザーの権限を変更
    if role == 'admin':
        if account_id not in admin_ids:
            admin_ids.append(account_id)
            if account_id in member_ids: member_ids.remove(account_id)
            if account_id in readonly_ids: readonly_ids.remove(account_id)
    elif role == 'member':
        if account_id not in member_ids:
            member_ids.append(account_id)
            if account_id in admin_ids: admin_ids.remove(account_id)
            if account_id in readonly_ids: readonly_ids.remove(account_id)
    elif role == 'readonly':
        if account_id not in readonly_ids:
            readonly_ids.append(account_id)
            if account_id in admin_ids: admin_ids.remove(account_id)
            if account_id in member_ids: member_ids.remove(account_id)
    else:
        return {"error": "Invalid role specified."}

    data['members_admin_ids'] = ",".join(map(str, admin_ids))
    data['members_member_ids'] = ",".join(map(str, member_ids))
    data['members_readonly_ids'] = ",".join(map(str, readonly_ids))

    await _chatwork_api_request('POST', endpoint, headers, data=data)

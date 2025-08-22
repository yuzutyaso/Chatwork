import os
import re
import requests
from flask import Flask, request

# --- 初期設定 ---
app = Flask(__name__)

# 環境変数から機密情報を取得
# ※ Renderの環境変数に設定してください
CHATWORK_API_TOKEN = os.environ.get("CHATWORK_API_TOKEN")
ADMIN_ACCOUNT_ID = int(os.environ.get("ADMIN_ACCOUNT_ID", 0))
BOT_ACCOUNT_ID = int(os.environ.get("BOT_ACCOUNT_ID", 0))

# 監視対象の絵文字リスト
EMOJIS = [
    ":)", ":(", ":D", "8-)", ":o", ";)", ":sweat:", ":|", ":*", ":p",
    ":blush:", ":^)", ":-)", ":inlove:", ":]", "(talk)", "(yawn)",
    "(puke)", "(emo)", "8-|", ":#", "(nod)", "(shake)", "(^^;)",
    "(whew)", "(clap)", "(bow)", "(roger)", "(flex)", "(dance)",
    ":/", "(gogo)", "(think)", "(please)", "(quick)", "(anger)",
    "(devil)", "(lightbulb)", "(*)", "(h)", "(F)", "(cracker)",
    "(eat)", "(^)", "(coffee)", "(beer)", "(handshake)", "(y)"
]

# --- API通信関数 ---
def send_chatwork_message(room_id, message_body):
    """Chatwork APIを使ってメッセージを送信する"""
    url = f"https://api.chatwork.com/v2/rooms/{room_id}/messages"
    headers = {"X-Chatworktoken": CHATWORK_API_TOKEN}
    data = {"body": message_body}
    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        print("メッセージを送信しました。")
    except requests.exceptions.RequestException as e:
        print(f"メッセージ送信エラー: {e}")

def update_member_permission(room_id, target_account_id, new_role):
    """ユーザーの権限を変更する"""
    url = f"https://api.chatwork.com/v2/rooms/{room_id}/members"
    headers = {"X-Chatworktoken": CHATWORK_API_TOKEN}
    try:
        # 既存のメンバーリストを取得
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        members = response.json()
        
        # ターゲットユーザーの権限を更新
        for member in members:
            if member["account_id"] == target_account_id:
                member["role"] = new_role
                break
        
        # PUTリクエスト用のデータを準備
        data = {
            "members_admin_ids": ",".join(str(m["account_id"]) for m in members if m["role"] == "admin"),
            "members_member_ids": ",".join(str(m["account_id"]) for m in members if m["role"] == "member"),
            "members_readonly_ids": ",".join(str(m["account_id"]) for m in members if m["role"] == "readonly")
        }
        
        print(f"更新メンバーリスト: {data}")
        response = requests.put(url, headers=headers, data=data)
        response.raise_for_status()
        print("メンバー権限を更新しました。")
    except requests.exceptions.RequestException as e:
        print(f"メンバー権限更新エラー: {e}")

# --- メインロジック ---
@app.route('/webhook', methods=['POST'])
def webhook():
    """Chatworkからのウェブフックリクエストを処理する"""
    try:
        data = request.json
        room_id = data.get("room_id")
        message_body = data.get("body")
        sender_account_id = data.get("account", {}).get("account_id")
        
        # 送信者がbot自身なら処理をスキップ
        if sender_account_id == BOT_ACCOUNT_ID:
            print("送信者はbot自身です。処理をスキップします。")
            return "OK", 200

        is_administrator = (sender_account_id == ADMIN_ACCOUNT_ID)

        # 絵文字の数をカウント
        emoji_count = sum(message_body.count(emoji) for emoji in EMOJIS)

        if emoji_count >= 15:
            if is_administrator:
                warning_msg = "[info][title]⚠️ 注意：絵文字の過剰な利用[/title]管理者様、メッセージ内の絵文字数が多すぎます。メンバーの場合は閲覧権限に変更されます。[/info]"
                send_chatwork_message(room_id, warning_msg)
            else:
                update_member_permission(room_id, sender_account_id, "readonly")
        
        elif "[toall]" in message_body:
            if is_administrator:
                warning_msg = "[info][title]⚠️ 注意：全体宛の利用[/title]管理者様、全体宛の利用はメンバーの場合、閲覧権限に変更される原因になります。[/info]"
                send_chatwork_message(room_id, warning_msg)
            else:
                update_member_permission(room_id, sender_account_id, "readonly")

        return "OK", 200

    except Exception as e:
        print(f"Webhook処理エラー: {e}")
        return "Internal Server Error", 500

# --- アプリケーションの起動 ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    # Werkzeugの開発サーバー警告を非表示にする
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    app.run(host='0.0.0.0', port=port)

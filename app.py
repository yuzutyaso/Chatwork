import os
import random
import re
import time
from datetime import datetime
from flask import Flask, request, jsonify
from chatwork import Chatwork
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# 環境変数からChatwork APIトークンを取得
chatwork_token = os.environ.get('CHATWORK_API_TOKEN')
chatwork = None
bot_account_id = None

if chatwork_token:
    try:
        chatwork = Chatwork(chatwork_token)
        # ボット自身のIDを自動で取得
        my_status = chatwork.get_my_status()
        bot_account_id = my_status['account_id']
        logging.info(f"Bot's account ID is {bot_account_id}")
    except Exception as e:
        logging.error(f"Error initializing Chatwork client or getting bot's account ID: {e}")
else:
    logging.error("CHATWORK_API_TOKEN environment variable is not set.")

# 監視対象の絵文字リスト
EMOJI_LIST = [
    ':)', ':(', ':D', '8-)', ':o', ';)', ';((sweat)', ':|', ':*', ':p', '(blush)',
    ':^)', '|-)', '(inlove)', ']:)', '(talk)', '(yawn)', '(puke)', '(emo)', '8-|',
    ':#)', '(nod)', '(shake)', '(^^;)', '(whew)', '(clap)', '(bow)', '(roger)',
    '(flex)', '(dance)', ':/', '(gogo)', '(think)', '(please)', '(quick)', '(anger)',
    '(devil)', '(lightbulb)', '(*)', '(h)', '(F)', '(cracker)', '(eat)', '(^)',
    '(coffee)', '(beer)', '(handshake)', '(y)'
]

def contains_too_many_emojis(text):
    """メッセージ内の絵文字の数をカウントする"""
    count = 0
    for emoji in EMOJI_LIST:
        count += text.count(emoji)
    return count >= 15

def get_admin_account_id(room_id):
    """ルームIDから管理者のアカウントIDを取得する"""
    if not chatwork:
        return None
    try:
        members = chatwork.get_room_members(room_id=room_id)
        for member in members:
            if member['role'] == 'admin':
                return member['account_id']
    except Exception as e:
        logging.error(f"Error getting room members for room {room_id}: {e}")
    return None

def draw_omikuji():
    """確率に基づいておみくじを引く"""
    results = {
        "大吉": 1,
        "吉": 3,
        "中吉": 5,
        "小吉": 10,
        "末吉": 20,
        "凶": 30,
        "大凶": 31
    }
    
    total_weight = sum(results.values())
    rand_num = random.uniform(0, total_weight)
    current_weight = 0
    
    for result, weight in results.items():
        current_weight += weight
        if rand_num < current_weight:
            return result
    return "大凶"

@app.route('/', methods=['POST'])
def webhook():
    """ChatworkのWebhookを受け取るエンドポイント"""
    try:
        data = request.json
        event_type = data.get('webhook_event_type')

        if event_type == 'message':
            event = data['webhook_event']
            room_id = event['room_id']
            message_body = event['body']
            account_id = event['account_id']
            message_id = event['message_id']

            # ボット自身の投稿は無視
            if bot_account_id and account_id == bot_account_id:
                logging.info(f"Message from bot account {bot_account_id}. Skipping.")
                return jsonify({'status': 'ignored'}), 200

            # 削除コマンドを正規表現でチェック
            delete_pattern = re.compile(rf'\[rp aid={bot_account_id} to=(\d+)-(\d+)\]\[pname:{bot_account_id}\]さん\n削除')
            match = delete_pattern.match(message_body)

            if match:
                target_room_id = int(match.group(1))
                target_message_id = int(match.group(2))
                
                logging.info(f"Deletion command detected. Deleting message_id: {target_message_id} in room_id: {target_room_id}")
                
                try:
                    chatwork.delete_message(room_id=target_room_id, message_id=target_message_id)
                    reply_message = "メッセージを削除しました。"
                    chatwork.post_message(room_id=room_id, body=reply_message)
                    logging.info("Message deleted successfully.")
                except Exception as e:
                    logging.error(f"Failed to delete message: {e}")
                    reply_message = "メッセージの削除に失敗しました。"
                    chatwork.post_message(room_id=room_id, body=reply_message)

                return jsonify({'status': 'ok'}), 200
            
            # /info コマンド
            if message_body.strip() == '/info':
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                reply_message = (
                    f'[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n'
                    f'ボットは正常に稼働しています！✨\n'
                    f'ボットのアカウントID: {bot_account_id}\n'
                    f'現在時刻: {current_time}'
                )
                if chatwork:
                    chatwork.post_message(room_id=room_id, body=reply_message)
                return jsonify({'status': 'ok'}), 200
            
            # おみくじ機能
            if "おみくじ" in message_body:
                result = draw_omikuji()
                reply_message = f'[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nあなたの運勢は【{result}】です！'
                if chatwork:
                    chatwork.post_message(room_id=room_id, body=reply_message)
                return jsonify({'status': 'ok'}), 200

            # /roominfo/ コマンド
            if message_body.startswith('/roominfo/'):
                target_room_id = message_body.replace('/roominfo/', '').strip()
                try:
                    target_room_id = int(target_room_id)
                    
                    my_rooms = chatwork.get_my_rooms()
                    is_member = any(room['room_id'] == target_room_id for room in my_rooms)
                    
                    if not is_member:
                        reply_message = f'[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n指定された部屋には所属していません。'
                    else:
                        room_info = chatwork.get_room_info(room_id=target_room_id)
                        messages = chatwork.get_messages(room_id=target_room_id, limit=1)
                        latest_message_id = messages[0]['message_id'] if messages else 'N/A'
                        
                        reply_message = (
                            f'[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n'
                            f'部屋情報\n'
                            f'--------------------\n'
                            f'部屋名: {room_info["name"]}\n'
                            f'最新メッセージID: {latest_message_id}\n'
                            f'最新メッセージ投稿日時: {messages[0]["send_time"]} (UNIX時間)\n'
                            f'--------------------'
                        )

                except ValueError:
                    reply_message = f'[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nルームIDは数字で指定してください。例：`/roominfo/12345`'
                except Exception as e:
                    logging.error(f"Error fetching room info: {e}")
                    reply_message = f'[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n部屋情報の取得中にエラーが発生しました。'
                
                if chatwork:
                    chatwork.post_message(room_id=room_id, body=reply_message)
                return jsonify({'status': 'ok'}), 200

            # /coin コマンド (コイントス)
            if message_body.startswith('/coin'):
                coin_result = random.choice(['表', '裏'])
                reply_message = f'[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nコイントスの結果は「{coin_result}」でした。'
                if chatwork:
                    chatwork.post_message(room_id=room_id, body=reply_message)
                return jsonify({'status': 'ok'}), 200

            # /timer コマンド
            if message_body.startswith('/timer'):
                try:
                    timer_string = message_body.replace('/timer', '').strip()
                    if 'm' in timer_string:
                        minutes = int(timer_string.replace('m', ''))
                        seconds = minutes * 60
                        reply_message = f'[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n{minutes}分間のタイマーをセットしました。'
                    elif 's' in timer_string:
                        seconds = int(timer_string.replace('s', ''))
                        reply_message = f'[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\n{seconds}秒間のタイマーをセットしました。'
                    else:
                        reply_message = f'[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nタイマーの時間を指定してください（例：`/timer 5m` または `/timer 30s`）。'
                        if chatwork:
                            chatwork.post_message(room_id=room_id, body=reply_message)
                        return jsonify({'status': 'ok'}), 200

                    if chatwork:
                        chatwork.post_message(room_id=room_id, body=reply_message)
                        time.sleep(seconds)
                        finish_message = f'[To:{account_id}] タイマーが終了しました！'
                        chatwork.post_message(room_id=room_id, body=finish_message)
                except Exception as e:
                    logging.error(f"Error setting timer: {e}")
                    reply_message = f'[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nタイマー設定中にエラーが発生しました。'
                    if chatwork:
                        chatwork.post_message(room_id=room_id, body=reply_message)
                
                return jsonify({'status': 'ok'}), 200
            
            # 以下、既存の権限変更ロジック
            admin_account_id = get_admin_account_id(room_id)
            if account_id == admin_account_id:
                logging.info(f"Message from admin account {admin_account_id}. Skipping.")
                return jsonify({'status': 'ignored'}), 200

            should_change_role = False
            if '[toall]' in message_body:
                should_change_role = True
                logging.info(f"[toall] detected in message from account {account_id}.")
            elif contains_too_many_emojis(message_body):
                should_change_role = True
                logging.info(f"Too many emojis detected in message from account {account_id}.")

            if should_change_role and chatwork:
                chatwork.update_room_role(room_id=room_id, members=[account_id], role='readonly')
                reply_message = f'[rp aid={account_id} to={room_id}-{message_id}][pname:{account_id}]さん\nあなたのメッセージがルームルールに違反したため、権限が閲覧者に変更されました。'
                chatwork.post_message(room_id=room_id, body=reply_message)
                logging.info(f'Role of account {account_id} changed to readonly in room {room_id}.')
            else:
                logging.info(f"Message from account {account_id} does not require a role change.")
                
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        logging.error(f"Error processing webhook: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

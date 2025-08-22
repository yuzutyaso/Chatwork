import os
import requests
import logging

CHATWORK_API_TOKEN = os.environ.get("CHATWORK_API_TOKEN")
CHATWORK_API_URL = "https://api.chatwork.com/v2"

def send_reply(room_id, message_id, account_id, message_text):
    """
    ChatWorkにメッセージを返信する
    """
    try:
        if not CHATWORK_API_TOKEN:
            logging.error("CHATWORK_API_TOKEN is not set.")
            return

        headers = {
            "X-ChatWorkToken": CHATWORK_API_TOKEN,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        # 宛先指定（reply_message_idは元のメッセージID、toは送信者のaccount_id）
        reply_message = f"[rp aid={account_id} to={room_id}-{message_id}]{message_text}"
        
        payload = {
            "body": reply_message
        }

        url = f"{CHATWORK_API_URL}/rooms/{room_id}/messages"
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()

    except requests.exceptions.RequestException as e:
        logging.error(f"ChatWork API request failed: {e}", exc_info=True)
    except Exception as e:
        logging.error(f"An unexpected error occurred while sending a reply: {e}", exc_info=True)

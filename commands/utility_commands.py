import re
import time
import requests
import random
import threading
import wikipediaapi
from translate import Translator
from datetime import datetime
from ..utils import send_reply, send_message_to_chatwork

def wiki_command(room_id, message_id, account_id, message_body):
    """
    /wiki [キーワード] コマンドの処理
    Wikipediaから情報を取得して要約する
    """
    keyword = message_body.replace("/wiki ", "", 1).strip()
    if not keyword:
        send_reply(room_id, message_id, account_id, "検索キーワードを入力してください。例: /wiki 東京タワー")
        return
    try:
        wiki_wiki = wikipediaapi.Wikipedia('ja')
        page = wiki_wiki.page(keyword)
        if not page.exists():
            send_reply(room_id, message_id, account_id, f"「{keyword}」に関する情報が見つかりませんでした。")
            return
        summary = page.summary
        if len(summary) > 400:
            summary = summary[:400] + "..."
        message = f"📚 **Wikipedia検索: {keyword}**\n\n{summary}\n\n詳細はこちら: {page.fullurl}"
        send_reply(room_id, message_id, account_id, message)
    except Exception as e:
        send_reply(room_id, message_id, account_id, f"Wikipediaの検索中にエラーが発生しました: {e}")

def coin_command(room_id, message_id, account_id, message_body):
    """
    /coin コマンドの処理
    コイントスを行う
    """
    result = random.choice(["表", "裏"])
    send_reply(room_id, message_id, account_id, f"コイントス... 結果は「**{result}**」です！")

def translate_command(room_id, message_id, account_id, message_body):
    """
    /translate [言語コード] [テキスト] コマンドの処理
    指定された言語にテキストを翻訳する
    """
    parts = message_body.split(' ', 2)
    if len(parts) < 3:
        send_reply(room_id, message_id, account_id, "コマンド形式が正しくありません。例: /translate en 日本語の文章")
        return
    lang_code = parts[1]
    text_to_translate = parts[2]
    try:
        translator = Translator(to_lang=lang_code)
        translation = translator.translate(text_to_translate)
        send_reply(room_id, message_id, account_id, f"翻訳結果:\n{translation}")
    except Exception as e:
        send_reply(room_id, message_id, account_id, f"翻訳に失敗しました。対応言語コードか確認してください: {e}")

def reminder_command(room_id, message_id, account_id, message_body):
    """
    /reminder [時間] "[メッセージ]" コマンドの処理
    指定した時間にリマインダーを送信する
    """
    match = re.search(r'/reminder\s+(\d{1,2}:\d{2})\s*"(.*)"', message_body)
    if not match:
        send_reply(room_id, message_id, account_id, "コマンド形式が正しくありません。例: /reminder 15:30 \"今日の定例会\"")
        return
    reminder_time_str = match.group(1)
    reminder_message = match.group(2)
    try:
        now = datetime.now()
        reminder_time = datetime.strptime(reminder_time_str, "%H:%M").time()
        reminder_datetime = datetime.combine(now.date(), reminder_time)
        if reminder_datetime < now:
            reminder_datetime = reminder_datetime.replace(day=now.day + 1)
        wait_seconds = (reminder_datetime - now).total_seconds()
        send_reply(room_id, message_id, account_id, f"リマインダーを {reminder_time_str} に設定しました。")
        def send_reminder_message():
            time.sleep(wait_seconds)
            send_message_to_chatwork(room_id, f"[To:{account_id}] リマインダーです: {reminder_message}")
        threading.Thread(target=send_reminder_message).start()
    except Exception as e:
        send_reply(room_id, message_id, account_id, f"リマインダー設定中にエラーが発生しました: {e}")

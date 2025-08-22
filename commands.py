from .commands.main_commands import test_command, sorry_command, roominfo_command, say_command, weather_command, whoami_command, echo_command, timer_command, time_report_command, delete_command, omikuji_command, ranking_command, quote_command, news_command, info_command
from .commands.utility_commands import wiki_command, coin_command, translate_command, reminder_command
from .commands.admin_commands import log_command, stats_command, recount_command

# 全コマンドを辞書にまとめる
COMMANDS = {
    "/test": test_command,
    "/sorry": sorry_command,
    "/roominfo": roominfo_command,
    "/say": say_command,
    "/weather": weather_command,
    "/whoami": whoami_command,
    "/echo": echo_command,
    "/timer": timer_command,
    "/時報": time_report_command,
    "/削除": delete_command,
    "/quote": quote_command,
    "おみくじ": omikuji_command,
    "/ranking": ranking_command,
    "/recount": recount_command,
    "/news": news_command,
    "/info": info_command,
    "/wiki": wiki_command,
    "/coin": coin_command,
    "/translate": translate_command,
    "/reminder": reminder_command,
    "/log": log_command,
    "/stats": stats_command,
}

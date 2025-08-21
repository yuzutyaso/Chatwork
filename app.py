from flask import Flask
from handlers import post_all_room_ranking_daily

# Flaskアプリケーションのインスタンスを作成
app = Flask(__name__)

# ルーティング設定
@app.route('/run-ranking-update')
def run_update():
    """
    このエンドポイントは、ランキング更新関数を呼び出します。
    """
    try:
        post_all_room_ranking_daily()
        return "Ranking update initiated successfully."
    except Exception as e:
        return f"An error occurred: {e}", 500

if __name__ == '__main__':
    # 開発環境での実行
    app.run(host='0.0.0.0', port=5000)


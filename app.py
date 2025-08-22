import os
import json
from flask import Flask, request
import subprocess

app = Flask(__name__)

# Renderの環境変数を取得
CHATWORK_API_TOKEN = os.environ.get("CHATWORK_API_TOKEN")

@app.route('/webhook', methods=['POST'])
def webhook():
    # ウェブフックのJSONデータを受け取る
    data = request.json
    
    # PowerShellスクリプトを実行
    # subprocess.runでps1にJSONデータを渡し、環境変数も渡す
    process = subprocess.run(
        ["powershell.exe", "-ExecutionPolicy", "Bypass", "./bot.ps1"],
        input=json.dumps(data).encode('utf-8'),
        capture_output=True,
        text=True,
        env={
            "CHATWORK_API_TOKEN": CHATWORK_API_TOKEN,
            **os.environ  # Renderの既存の環境変数も引き継ぐ
        }
    )
    
    # 実行結果（エラーや出力）をログに表示
    print(process.stdout)
    print(process.stderr)
    
    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000))

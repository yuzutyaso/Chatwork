import os
import json
from flask import Flask, request
import subprocess
import sys

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Chatworkからのウェブフックリクエストを処理するエンドポイント
    """
    try:
        # ウェブフックのJSONデータを受け取る
        data = request.json
        
        # PowerShellスクリプトを実行し、標準入力にJSONデータを渡す
        # 実行ポリシーをBypassに設定して、スクリプトの実行を許可
        ps_process = subprocess.run(
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "./bot.ps1"],
            input=json.dumps(data).encode('utf-8'),
            capture_output=True,
            text=True,
            env={**os.environ} # Renderの環境変数をすべて引き継ぐ
        )
        
        # PowerShellスクリプトの標準出力とエラー出力をログに表示
        print(f"PowerShell stdout: {ps_process.stdout}")
        print(f"PowerShell stderr: {ps_process.stderr}", file=sys.stderr)
        
        # PowerShellスクリプトの終了コードをチェック
        if ps_process.returncode != 0:
            return "PowerShell script error", 500

        return "OK", 200

    except Exception as e:
        print(f"Webhook processing error: {e}", file=sys.stderr)
        return "Internal Server Error", 500

if __name__ == '__main__':
    # Renderのポート環境変数を使用
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

# Pythonの公式イメージをベースとして使用
FROM python:3.9-slim

# アプリケーションの作業ディレクトリを設定
WORKDIR /app

# 必要なPythonパッケージをrequirements.txtからインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションのソースコードを作業ディレクトリにコピー
COPY . .

# 環境変数CHATWORK_API_TOKENが設定されていることを確認する（Render側で設定）
ENV CHATWORK_API_TOKEN=$CHATWORK_API_TOKEN

# 5000番ポートを公開
EXPOSE 5000

# アプリケーションを起動
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]

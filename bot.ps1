# 標準入力からJSONデータを受け取る
$input_json = $Input | Out-String | ConvertFrom-Json

# ここに以前作成したボットのロジックを実装
$roomId = $input_json.room_id
$messageBody = $input_json.body
$senderAccountId = $input_json.account.account_id

# 例: メッセージ本文を表示
Write-Host "ルームID: $roomId"
Write-Host "メッセージ: $messageBody"

# ここに絵文字カウントや[toall]の判定ロジックを記述し、
# Chatwork APIを呼び出す処理を追加します。
# 例: Invoke-WebRequest ...

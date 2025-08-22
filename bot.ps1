# 標準入力からJSONデータを受け取り、PowerShellオブジェクトに変換
$input_json = $Input | Out-String | ConvertFrom-Json

# 環境変数からAPIトークンと管理者IDを取得
$chatworkApiToken = $env:CHATWORK_API_TOKEN
$adminAccountId = [int]$env:ADMIN_ACCOUNT_ID # 管理者のChatwork account_id
# 環境変数からbot自身のIDを取得
$botAccountId = [int]$env:BOT_ACCOUNT_ID

# 監視対象の絵文字リスト
$emojis = @(
    ":)", ":(", ":D", "8-)", ":o", ";)", ":sweat:", ":|", ":*", ":p",
    ":blush:", ":^)", ":-)", ":inlove:", ":]", "(talk)", "(yawn)",
    "(puke)", "(emo)", "8-|", ":#", "(nod)", "(shake)", "(^^;)",
    "(whew)", "(clap)", "(bow)", "(roger)", "(flex)", "(dance)",
    ":/", "(gogo)", "(think)", "(please)", "(quick)", "(anger)",
    "(devil)", "(lightbulb)", "(*)", "(h)", "(F)", "(cracker)",
    "(eat)", "(^)", "(coffee)", "(beer)", "(handshake)", "(y)"
)

# JSONから必要な情報を抽出
$roomId = $input_json.room_id
$messageBody = $input_json.body
$senderAccountId = $input_json.account.account_id

# --- 重要: 送信者がbot自身でないことを確認 ---
if ($senderAccountId -eq $botAccountId) {
    Write-Host "送信者はbot自身です。処理をスキップします。"
    exit
}

# APIリクエスト用ヘッダー
$headers = @{
    "X-Chatworktoken" = $chatworkApiToken
}

function Send-ChatworkMessage {
    param(
        [string]$roomId,
        [string]$messageBody,
        [hashtable]$headers
    )
    $uri = "https://api.chatwork.com/v2/rooms/$roomId/messages"
    try {
        Invoke-WebRequest -Uri $uri -Method POST -Headers $headers -Body @{ "body" = $messageBody } -ErrorAction Stop
        Write-Host "メッセージを送信しました。"
    } catch {
        Write-Error "メッセージ送信エラー: $_"
    }
}

function Update-ChatworkMemberPermission {
    param(
        [string]$roomId,
        [int]$targetAccountId,
        [string]$newRole,
        [hashtable]$headers
    )
    $membersUri = "https://api.chatwork.com/v2/rooms/$roomId/members"
    
    try {
        # 既存のメンバーリストを取得
        $response = Invoke-WebRequest -Uri $membersUri -Method GET -Headers $headers -ErrorAction Stop
        $members = $response.Content | ConvertFrom-Json
    
        # ターゲットユーザーの権限を更新
        $newMembers = @()
        foreach ($member in $members) {
            $currentMember = $member
            if ($currentMember.account_id -eq $targetAccountId) {
                $currentMember.role = $newRole
                Write-Host "アカウントID $targetAccountId の権限を $newRole に変更します。"
            }
            $newMembers += $currentMember
        }
    
        # PUTリクエスト用のbodyを準備
        $membersBody = @{
            "members_admin_ids" = (($newMembers | Where-Object { $_.role -eq "admin" }).account_id | Out-String).Trim().Replace("`r`n", ",")
            "members_member_ids" = (($newMembers | Where-Object { $_.role -eq "member" }).account_id | Out-String).Trim().Replace("`r`n", ",")
            "members_readonly_ids" = (($newMembers | Where-Object { $_.role -eq "readonly" }).account_id | Out-String).Trim().Replace("`r`n", ",")
        }

        # 空のリストを処理
        foreach ($key in $membersBody.Keys) {
            if ($membersBody[$key] -eq "") {
                $membersBody[$key] = $null
            }
        }
    
        Write-Host "更新メンバーリスト: $($membersBody | ConvertTo-Json)"

        # 権限を更新したメンバーリストでAPIを呼び出し
        Invoke-WebRequest -Uri $membersUri -Method PUT -Headers $headers -Body $membersBody -ContentType "application/x-www-form-urlencoded" -ErrorAction Stop
        Write-Host "メンバー権限を更新しました。"
        
    } catch {
        Write-Error "メンバー権限更新エラー: $_"
    }
}

# --- 条件判定ロジック ---
$isAdministrator = ($senderAccountId -eq $adminAccountId)

# 絵文字の数をカウント
$emojiCount = 0
foreach ($emoji in $emojis) {
    $emojiCount += ($messageBody | Select-String -Pattern ([regex]::Escape($emoji)) -AllMatches).Matches.Count
}

if ($emojiCount -ge 15) {
    if ($isAdministrator) {
        $warningMsg = "[info][title]⚠️ 注意：絵文字の過剰な利用[/title]管理者様、メッセージ内の絵文字数が多すぎます。メンバーの場合は閲覧権限に変更されます。[/info]"
        Send-ChatworkMessage -roomId $roomId -messageBody $warningMsg -headers $headers
    } else {
        Update-ChatworkMemberPermission -roomId $roomId -targetAccountId $senderAccountId -newRole "readonly" -headers $headers
    }
} elseif ($messageBody.Contains("[toall]")) {
    if ($isAdministrator) {
        # 修正: [toall]を削除
        $warningMsg = "[info][title]⚠️ 注意：全体宛の利用[/title]管理者様、全体宛の利用はメンバーの場合、閲覧権限に変更される原因になります。[/info]"
        Send-ChatworkMessage -roomId $roomId -messageBody $warningMsg -headers $headers
    } else {
        Update-ChatworkMemberPermission -roomId $roomId -targetAccountId $senderAccountId -newRole "readonly" -headers $headers
    }
}

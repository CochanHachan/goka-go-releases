# 碁華 HP（このフォルダ）を http://127.0.0.1:8765/ で表示する簡易サーバー
# 使い方: エクスプローラでこのファイルを右クリック → PowerShell で実行
$ErrorActionPreference = "Stop"
$port = 8765
$root = $PSScriptRoot
Set-Location $root
$url = "http://127.0.0.1:$port/"
Write-Host "Serving: $root"
Write-Host "URL:    $url"
Write-Host "終了: このウィンドウで Ctrl+C"
Start-Sleep -Milliseconds 300
Start-Process $url
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -m http.server $port
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m http.server $port
} else {
    Write-Host "Python が見つかりません。https://www.python.org/ をインストールしてください。"
    Read-Host "Enter で閉じます"
}

# 管理者 staging ZIP を取得（OneDrive 外の保存先推奨）
$ErrorActionPreference = "Stop"
$outDir = "C:\Temp"
$outFile = Join-Path $outDir "goka-admin-staging.zip"
$url = "https://github.com/CochanHachan/goka-go-releases/releases/download/staging-latest/goka-admin-staging.zip"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Invoke-WebRequest -Uri $url -OutFile $outFile -UseBasicParsing
Write-Host "Saved: $outFile"

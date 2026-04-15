param(
    [string]$SourceBranch = "main",
    [ValidateSet("true", "false")]
    [string]$AutoMergeToMain = "false"
)

$ErrorActionPreference = "Stop"

Write-Host "One Click Staging EXE を実行します..."
Write-Host "  source_branch      = $SourceBranch"
Write-Host "  auto_merge_to_main = $AutoMergeToMain"

gh workflow run "one-click-staging-exe.yml" `
  -f source_branch="$SourceBranch" `
  -f auto_merge_to_main="$AutoMergeToMain"

Write-Host ""
Write-Host "ワークフロー実行を開始しました。進捗確認:"
Write-Host "  gh run list --workflow one-click-staging-exe.yml --limit 1"
Write-Host "  gh run watch"

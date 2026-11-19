# self-hosted 러너를 이 Windows PC 에 등록한다 (TOK-62). **대표님 PC 에 프로그램을 깔고 로그인 때 자동으로
# 시작하게 한다 — 대표님이 확인한 뒤에만 돌린다.** 절차와 먼저 바꿔야 하는 저장소 설정은 ci\SELF_HOSTED_RUNNERS.md.
#
#   powershell -ExecutionPolicy Bypass -File ci\register-runner-windows.ps1            등록 + 로그인 때 시작
#   powershell -ExecutionPolicy Bypass -File ci\register-runner-windows.ps1 -Remove    등록 해제
#
# 러너는 서비스가 아니라 **로그인한 사용자의 세션**에서 돈다(로그인 때 시작하는 예약 작업). Windows 서비스는
# 세션 0 의 다른 계정으로 돌아 사용자의 자격 증명 관리자와 CLI 로그인 상태를 볼 수 없다.
param([switch]$Remove)
$ErrorActionPreference = "Stop"

$Repo = "BrilliantTiger/token-pet"
$Dir = Join-Path $env:USERPROFILE "actions-runner-token-pet"
$Task = "token-pet-actions-runner"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw "gh CLI 가 필요합니다" }

if ($Remove) {
    Stop-ScheduledTask -TaskName $Task -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $Task -Confirm:$false -ErrorAction SilentlyContinue
    Set-Location $Dir
    $token = gh api -X POST "repos/$Repo/actions/runners/remove-token" --jq .token
    .\config.cmd remove --token $token
    gh variable delete SELF_HOSTED_WINDOWS --repo $Repo
    Write-Host "해제했습니다. 폴더는 남아 있습니다: $Dir"
    exit 0
}

# 포크 PR 이 승인 없이 워크플로를 돌릴 수 있으면 등록하지 않는다 — 공개 저장소다.
$policy = gh api "repos/$Repo/actions/permissions/fork-pr-contributor-approval" --jq .approval_policy
if ($policy -ne "all_external_contributors") {
    Write-Host "포크 PR 승인 정책이 '$policy' 입니다. 먼저 all_external_contributors 로 바꾸세요:"
    Write-Host "  gh api -X PUT repos/$Repo/actions/permissions/fork-pr-contributor-approval -f approval_policy=all_external_contributors"
    exit 1
}

$ver = (gh api repos/actions/runner/releases/latest --jq .tag_name).TrimStart("v")
$pkg = "actions-runner-win-x64-$ver.zip"
$body = gh api repos/actions/runner/releases/latest --jq .body
$sha = $null
$lines = $body -split "`n"
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match [regex]::Escape($pkg)) {
        $m = [regex]::Match(($lines[$i..([Math]::Min($i + 1, $lines.Count - 1))] -join " "), "[0-9a-f]{64}")
        if ($m.Success) { $sha = $m.Value; break }
    }
}
if (-not $sha) { throw "러너 $ver 의 SHA-256 을 릴리스 노트에서 찾지 못했습니다" }

New-Item -ItemType Directory -Force -Path $Dir | Out-Null
Set-Location $Dir
Invoke-WebRequest -Uri "https://github.com/actions/runner/releases/download/v$ver/$pkg" -OutFile $pkg
if ((Get-FileHash $pkg -Algorithm SHA256).Hash.ToLower() -ne $sha) { throw "받은 파일의 SHA-256 이 다릅니다" }
Expand-Archive -Path $pkg -DestinationPath $Dir -Force

$token = gh api -X POST "repos/$Repo/actions/runners/registration-token" --jq .token
.\config.cmd --unattended --url "https://github.com/$Repo" --name $env:COMPUTERNAME --labels Windows --token $token

$action = New-ScheduledTaskAction -Execute (Join-Path $Dir "run.cmd") -WorkingDirectory $Dir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $Task -Action $action -Trigger $trigger -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $Task
gh variable set SELF_HOSTED_WINDOWS --repo $Repo --body 1
Write-Host "등록했습니다: $env:COMPUTERNAME (labels: self-hosted, Windows)"

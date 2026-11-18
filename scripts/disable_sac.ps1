# disable_sac.ps1 - 关闭智能应用控制 (Smart App Control)
# 需要管理员权限运行
$ErrorActionPreference = 'Continue'
$key = "HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy"
$log = "artifacts\sac_disable_log.txt"
$out = @()

function W($msg) {
    $script:out += $msg
    Write-Output $msg
}

W "=== 关闭智能应用控制 ==="
W "时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

# 1) 当前状态
$before = (Get-ItemProperty $key -ErrorAction SilentlyContinue).VerifiedAndReputablePolicyState
W "[1] 修改前 VerifiedAndReputablePolicyState = $before"

# 2) 检查管理员
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$pr = New-Object Security.Principal.WindowsPrincipal($id)
$isAdmin = $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
W "[2] IsAdmin = $isAdmin"
if (-not $isAdmin) {
    W "  ERROR: 需要管理员权限"
    $out | Set-Content $log -Encoding UTF8
    exit 1
}

# 3) 尝试写入
W "[3] 写入 VerifiedAndReputablePolicyState = 0"
try {
    Set-ItemProperty -Path $key -Name "VerifiedAndReputablePolicyState" -Value 0 -Type DWord -ErrorAction Stop
    W "  写入命令执行成功"
} catch {
    W "  写入失败: $($_.Exception.Message)"
}

# 4) 读回验证
$after = (Get-ItemProperty $key -ErrorAction SilentlyContinue).VerifiedAndReputablePolicyState
W "[4] 修改后 VerifiedAndReputablePolicyState = $after"

if ($after -eq 0) {
    W "  SUCCESS: 已被接受（重启后完全生效）"
} elseif ($after -eq $before) {
    W "  FAILED: 值未改变，可能被篡改保护/CI 策略锁定"
} else {
    W "  PARTIAL: 值变为 $after"
}

# 5) 完整键值留档
W ""
W "=== 当前完整键值 ==="
$props = Get-ItemProperty $key -ErrorAction SilentlyContinue
foreach ($p in $props.PSObject.Properties) {
    if ($p.Name -notlike "PS*") {
        W ("  {0,-40} = {1}" -f $p.Name, $p.Value)
    }
}

$out | Set-Content $log -Encoding UTF8
Write-Output "日志已写入: $log"

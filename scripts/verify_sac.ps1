# verify_sac.ps1 - 重启后验证智能应用控制是否已关闭
# 用法: 右键 -> 使用 PowerShell 运行；或 powershell -ExecutionPolicy Bypass -File verify_sac.ps1
$ErrorActionPreference = 'Continue'
$out = @()

function W($m) { $script:out += $m; Write-Host $m }

W "=============================================="
W " 智能应用控制 (Smart App Control) 状态检查"
W " $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
W "=============================================="

# 1) 注册表值
$key = "HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy"
$v = (Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue).VerifiedAndReputablePolicyState
W ""
W "[1] 注册表 VerifiedAndReputablePolicyState = $v"
switch ($v) {
    0 { W "    -> 已关闭" }
    1 { W "    -> 强制模式（开启）" }
    2 { W "    -> 评估模式" }
    default { W "    -> 未知值" }
}

# 2) 代码完整性策略执行状态
W ""
W "[2] 代码完整性策略执行状态"
$dg = Get-CimInstance -ClassName Win32_DeviceGuard `
      -Namespace root\Microsoft\Windows\DeviceGuard -ErrorAction SilentlyContinue
if ($dg) {
    W "    CodeIntegrityPolicyEnforcementStatus         = $($dg.CodeIntegrityPolicyEnforcementStatus)"
    W "    UsermodeCodeIntegrityPolicyEnforcementStatus = $($dg.UsermodeCodeIntegrityPolicyEnforcementStatus)"
    W "    (0=未配置/关闭, 1=审核模式, 2=强制)"
} else {
    W "    无法查询 Win32_DeviceGuard"
}

# 3) 实测：能否运行自编译 exe
W ""
W "[3] 实测：运行一个自编译 exe"
$testExe = Join-Path $env:TEMP "sac_verify_test.exe"
$csc = @(
    "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($csc) {
    $src = Join-Path $env:TEMP "sac_verify.cs"
    'public class T { public static void Main(){ System.Console.WriteLine("OK"); } }' |
        Set-Content -Path $src -Encoding UTF8
    & $csc /nologo /target:exe /out:$testExe $src 2>&1 | Out-Null
    if (Test-Path $testExe) {
        try {
            $r = & $testExe 2>&1
            W "    可以运行 -> 已关闭 ✔  (输出: $r)"
        } catch {
            W "    仍被拦截 ✘"
            W "    $($_.Exception.Message)"
        }
        Remove-Item $testExe -Force -ErrorAction SilentlyContinue
    } else {
        W "    编译失败，跳过此项"
    }
    Remove-Item $src -Force -ErrorAction SilentlyContinue
} else {
    W "    找不到 csc.exe，跳过"
}

# 4) 项目 exe
W ""
W "[4] 实测：项目自带的 山海寻灵防AFK.exe"
$projExe = Join-Path (Split-Path -Parent $PSScriptRoot) "build\山海寻灵防AFK.exe"
if (-not (Test-Path $projExe)) {
    $projExe = "build\山海寻灵防AFK.exe"
}
if (Test-Path $projExe) {
    try {
        Get-Process pythonw -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 400
        $p = Start-Process $projExe -PassThru -ErrorAction Stop
        W "    可以运行 ✔ (启动器 PID=$($p.Id))"
        Start-Sleep -Seconds 5
        $gui = Get-Process pythonw -ErrorAction SilentlyContinue
        if ($gui) {
            W "    界面已启动: $($gui[0].MainWindowTitle)"
        } else {
            W "    启动器成功但界面未起来，检查 Python 环境"
        }
    } catch {
        W "    仍被拦截 ✘"
        W "    $($_.Exception.Message)"
    }
} else {
    W "    未找到 exe（路径: $projExe）"
}

W ""
W "=============================================="
if ($v -eq 0) {
    W " 结论: 注册表已关闭。若 [3] 仍被拦截，说明策略尚未卸载，"
    W "       请再重启一次；若反复如此，说明被更深层策略锁定。"
} else {
    W " 结论: 仍未关闭，注册表值 = $v"
    W "       请确认是否已重启，或检查 Windows 安全中心。"
}
W "=============================================="

$logPath = Join-Path $env:TEMP "sac_verify_result.txt"
$out | Set-Content -Path $logPath -Encoding UTF8
Write-Host ""
Write-Host "结果已保存: $logPath"

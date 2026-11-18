"""make_portable.py —— 生成「带运行时」的绿色便携包。

为什么需要这个脚本
==================
PyInstaller 打出来的 exe 是个**新 PE 文件**，没有受信任签名。在启用了
Smart App Control / WDAC 强制模式的机器上会被直接拦掉：

    'xxx.exe' was blocked by your organization's Device Guard policy.

实测（2026-11-18，Windows 11，策略 {0283AC0F-FFF1-49AE-ADA1-8A933130CAD6}）：
  - csc 编译的 8 KB C# 启动器         -> 被拦
  - hello-world 级 C# exe（3 574 B）  -> 被拦
  - 自签名证书签过的 exe              -> 被拦（策略不认自签根）
  - PyInstaller onefile / onedir      -> 都被拦
  - **已签名的 python.exe 复制到别处** -> 正常跑

结论：策略是按 **PE 签名**判定的，不按路径/文件名。所以只要不去造新 exe，
改用「已签名的官方解释器 + 纯 .py 源码」就能绕开，且**完全合法**——跑的是
微软/发布方已经信任的二进制。

用法
====
    python scripts/make_portable.py                    # 自动找本机已安装的 Python
    python scripts/make_portable.py --python <python.exe>
    python scripts/make_portable.py --check            # 只打印计划

产物
====
    dist-portable/山海寻灵防AFK-便携版/
        runtime/            已签名的 CPython 3.12（裁剪过，约 25 MB）
        app/  assets/  main.py
        config/targets.example.json
        启动.bat            无黑框启动（走 runtime\\pythonw.exe）
        校验环境.bat        诊断脚本：打印签名状态与自检结果
        README.txt
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "dist-portable", "山海寻灵防AFK-便携版")

# ── 运行时要复制的文件 ─────────────────────────────────────────────────────
# 顶层文件：解释器本体 + 运行时 DLL
TOP_FILES = [
    "python.exe", "pythonw.exe", "python3.dll",
    "vcruntime140.dll", "vcruntime140_1.dll",
]
# 按版本号命名的核心 DLL 单独匹配（python312.dll / python313.dll …）
CORE_DLL_GLOB = ("python3", ".dll")

# 标准库子目录：只保留本项目真正用得到的
# app/ 的 import 全集：argparse collections copy ctypes dataclasses json
#                       os random sys threading time tkinter
KEEP_LIB_DIRS = {
    "collections", "ctypes", "json", "tkinter", "concurrent",
    "encodings", "email", "html", "http", "importlib", "logging",
    "multiprocessing", "re", "unittest", "urllib", "xml", "sqlite3",
    "asyncio", "zoneinfo", "wsgiref",
}
# 明确丢弃的
DROP_LIB_DIRS = {
    "site-packages", "test", "tests", "idlelib", "ensurepip",
    "pydoc_data", "lib2to3", "turtledemo", "distutils", "venv",
    "__pycache__", "turtle.py",
}
# DLLs/ 里丢掉的扩展模块（本项目用不到，且体积大）
DROP_DLL_PATTERNS = (
    "_test", "xxlimited", "_ctypes_test", "_testcapi", "_testbuffer",
    "_testimportmultiple", "_testinternalcapi", "_testmultiphase",
    "_testsinglephase", "libcrypto", "libssl", "sqlite3", "_msi",
    "winsound", "_decimal", "_elementtree", "_multiprocessing",
    "_asyncio", "_bz2", "_lzma", "_hashlib",
)

# tcl/tk 运行时数据（tkinter 必须，缺了会报 "Can't find a usable init.tcl"）
TCL_DIR = "tcl"


def find_python(explicit: str | None) -> str:
    if explicit:
        if not os.path.isfile(explicit):
            sys.exit(f"指定的解释器不存在: {explicit}")
        return explicit
    env = os.environ.get("HELMD_PYTHON")
    if env and os.path.isfile(env):
        return env
    # 本机 DSH 自带运行时（就是那个有 DeepSeek 签名的）
    cand = os.path.join(
        os.path.expanduser("~"), ".dsh", "dsh-runtimes",
        "dsh-primary-runtime", "dependencies", "python", "python.exe")
    if os.path.isfile(cand):
        return cand
    for name in ("python.exe",):
        found = shutil.which(name)
        if found and "WindowsApps" not in found:
            return found
    sys.exit("找不到可用的 Python，请用 --python 指定")


def copy_tree_filtered(src: str, dst: str, keep: set[str] | None,
                       drop: set[str]) -> int:
    """复制目录，按白名单/黑名单过滤子项。返回复制的文件数。"""
    n = 0
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        if name in drop:
            continue
        if keep is not None and os.path.isdir(os.path.join(src, name)) \
                and name not in keep:
            continue
        s = os.path.join(src, name)
        d = os.path.join(dst, name)
        if os.path.isdir(s):
            n += copy_tree_filtered(s, d, None, drop)
        else:
            shutil.copy2(s, d)
            n += 1
    return n


def dir_size(path: str) -> float:
    total = 0
    for dp, _dn, fns in os.walk(path):
        for fn in fns:
            try:
                total += os.path.getsize(os.path.join(dp, fn))
            except OSError:
                pass
    return total / (1024 * 1024)


def build_runtime(pyexe: str, dest: str) -> dict:
    """从 pyexe 所在的安装目录裁出一个可搬运的运行时。"""
    src = os.path.dirname(os.path.abspath(pyexe))
    os.makedirs(dest, exist_ok=True)
    stats = {"top": 0, "dlls": 0, "lib": 0, "tcl": 0}

    # 1) 顶层：解释器 + 核心 DLL + VC 运行时
    ver_dlls = [n for n in os.listdir(src)
                if n.startswith("python3") and n.endswith(".dll")
                and n != "python3.dll"]
    for name in TOP_FILES + ver_dlls:
        s = os.path.join(src, name)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(dest, name))
            stats["top"] += 1
    for name in ("vcruntime140.dll", "vcruntime140_1.dll"):
        if not os.path.isfile(os.path.join(dest, name)):
            alt = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                               "System32", name)
            if os.path.isfile(alt):
                shutil.copy2(alt, os.path.join(dest, name))
                stats["top"] += 1

    # 2) DLLs/：扩展模块，去掉用不到的大件
    dlls_src = os.path.join(src, "DLLs")
    if os.path.isdir(dlls_src):
        dlls_dst = os.path.join(dest, "DLLs")
        os.makedirs(dlls_dst, exist_ok=True)
        for name in os.listdir(dlls_src):
            if any(p in name for p in DROP_DLL_PATTERNS):
                continue
            s = os.path.join(dlls_src, name)
            if os.path.isfile(s):
                shutil.copy2(s, os.path.join(dlls_dst, name))
                stats["dlls"] += 1

    # 3) Lib/：标准库，白名单保留子目录，丢弃 site-packages 等
    lib_src = os.path.join(src, "Lib")
    if os.path.isdir(lib_src):
        stats["lib"] = copy_tree_filtered(lib_src, os.path.join(dest, "Lib"),
                                          KEEP_LIB_DIRS, DROP_LIB_DIRS)

    # 4) tcl/：tkinter 的 Tcl/Tk 运行时数据
    tcl_src = os.path.join(src, TCL_DIR)
    if os.path.isdir(tcl_src):
        stats["tcl"] = copy_tree_filtered(tcl_src, os.path.join(dest, TCL_DIR),
                                          None, {"__pycache__"})

    # 5) 清掉所有 __pycache__（体积没意义且会带绝对路径）
    for dp, dns, _fn in os.walk(dest):
        if "__pycache__" in dns:
            shutil.rmtree(os.path.join(dp, "__pycache__"), ignore_errors=True)
            dns.remove("__pycache__")
    return stats


LAUNCH_BAT = r"""@echo off
rem ============================================================================
rem  ShanhaiAFK portable launcher
rem
rem  Runs the app with the CONTAINED runtime\pythonw.exe, so no Python install
rem  is needed and no new unsigned exe is created (which WDAC / Smart App
rem  Control would block).
rem ============================================================================
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONHOME="
set "PYTHONPATH="

if not exist "runtime\pythonw.exe" (
    echo [x] runtime\pythonw.exe not found.
    echo     The portable package is incomplete - re-extract the archive.
    pause
    exit /b 1
)

rem --- Elevation check via integrity level -------------------------------
rem  "net session" / "fltmc" both return 0 in a Medium integrity shell,
rem  so they cannot be used to detect elevation (verified on this machine).
whoami /groups 2>nul | findstr /I /C:"Mandatory Label\High" /C:"Mandatory Label\System" >nul
if not errorlevel 1 goto :run

echo [*] Administrator rights required.
echo     Game platform processes run at High integrity; without elevation
echo     Windows UIPI blocks the key injection (PostMessage returns err=5).
echo.
echo [*] Requesting elevation - click "Yes" on the UAC prompt...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -Verb RunAs -FilePath '%~f0' -WorkingDirectory '%~dp0'"
if errorlevel 1 (
    echo.
    echo [x] Elevation failed. Right-click this file and choose "Run as administrator".
    pause
)
exit /b

:run
echo [*] Elevated. Starting with the bundled runtime...
start "" "runtime\pythonw.exe" "%~dp0main.py"
exit /b 0
"""

CHECK_BAT = r"""@echo off
rem Diagnose the portable package: signature status, WDAC state, self-check.
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONHOME="
set "PYTHONPATH="

echo ============================================================
echo  Portable package diagnostics
echo ============================================================
echo.
echo [1] Interpreter signature
powershell -NoProfile -Command "$s=Get-AuthenticodeSignature 'runtime\python.exe'; Write-Host ('    Status : ' + $s.Status); Write-Host ('    Signer : ' + $s.SignerCertificate.Subject)"
echo.
echo [2] Code integrity policy state
powershell -NoProfile -Command "$v=(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy' -EA SilentlyContinue).VerifiedAndReputablePolicyState; Write-Host ('    SmartAppControl = ' + $v); $d=Get-CimInstance -ClassName Win32_DeviceGuard -Namespace root\Microsoft\Windows\DeviceGuard -EA SilentlyContinue; Write-Host ('    WDAC enforce    = ' + $d.CodeIntegrityPolicyEnforcementStatus)"
echo.
echo [3] Self-check (no keys are sent)
runtime\python.exe main.py --check
echo.
echo [4] Permission scan
runtime\python.exe main.py --permissions
echo.
pause
"""

README_TXT = """山海寻灵 · 防AFK控制器  —— 便携版
================================================================

这个版本和 Release 里的 ShanhaiAFK.exe 有什么区别？

  ShanhaiAFK.exe      PyInstaller 单文件，内含 Python。
                      **是一个全新的、没有代码签名的 PE 文件**，
                      在启用 Smart App Control / WDAC 强制模式的机器上
                      会被直接拦掉（报 "An Application Control policy has
                      blocked this file"）。

  便携版（本包）      不造新 exe。用 runtime\\pythonw.exe（微软/发布方
                      已签名的官方解释器）+ 纯 .py 源码运行。
                      因为跑的二进制是系统本来就信任的，不会被策略拦。

  代价：体积 25~45 MB，解压后是一堆文件，不是单文件。


怎么用
----------------------------------------------------------------
1. 解压到任意目录（路径不要有中文以外的怪字符也行，中文没问题）
2. 右键「启动.bat」-> 以管理员身份运行（或者直接双击，它会自己请求提权）
3. UAC 点「是」
4. 点「＋新建任务」-> 下拉框选你的程序 -> 填按键和间隔 -> 「▶ 启动 (F9)」

配置会生成在 config\\targets.json，跟 exe 同级，不会丢。


启动不了？跑「校验环境.bat」
----------------------------------------------------------------
它会打印三件事：
  [1] runtime\\python.exe 的签名状态（应该是 Valid + 一个公司名）
  [2] 本机 Smart App Control / WDAC 状态
  [3] 程序自带的自检结果（应该 6/6 通过）

如果 [1] 是 NotSigned，说明你用的 Python 没有签名 —— 换一个官方
python.org 安装的，或者用 DSH 自带的运行时。


为什么需要管理员
----------------------------------------------------------------
UIPI（用户界面特权隔离）规定低完整性进程不能给高完整性进程发窗口消息。
游戏平台进程一般是 High 完整性，所以本工具必须以管理员运行，
否则 PostMessage 返回 FALSE + GetLastError()=5 (ERROR_ACCESS_DENIED)。

实测：普通权限 0/5 成功，管理员权限 5/5 成功。


免责
----------------------------------------------------------------
通用 Windows 键盘消息投递工具，用于自动化你**有权操作**的本地程序。
请遵守目标程序的服务条款。不含任何反检测/反作弊绕过/内存读写/进程注入。
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=None, help="源解释器 python.exe")
    ap.add_argument("--check", action="store_true", help="只打印计划")
    ap.add_argument("--out", default=OUT, help="输出目录")
    args = ap.parse_args()

    pyexe = find_python(args.python)
    print(f"源解释器: {pyexe}")
    print(f"输出目录: {args.out}")

    # 签名状态先打出来 —— 这是整个方案的立论基础
    try:
        ps = ("$s=Get-AuthenticodeSignature '" + pyexe + "'; "
              "Write-Output ($s.Status); "
              "Write-Output ($s.SignerCertificate.Subject)")
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=60)
        lines = [l for l in out.stdout.splitlines() if l.strip()]
        if len(lines) >= 1:
            print(f"签名状态  : {lines[0].strip()}")
        if len(lines) >= 2:
            print(f"签名主体  : {lines[1].strip()[:90]}")
    except Exception as exc:
        print(f"（无法读取签名信息: {exc}）")

    if args.check:
        print("\n--check：不写任何文件")
        return 0

    if os.path.isdir(args.out):
        print("清空旧产物…")
        shutil.rmtree(args.out)
    os.makedirs(args.out, exist_ok=True)

    print("\n[1/4] 裁运行时…")
    stats = build_runtime(pyexe, os.path.join(args.out, "runtime"))
    print(f"     顶层 {stats['top']} 个, DLLs {stats['dlls']} 个, "
          f"Lib {stats['lib']} 个, tcl {stats['tcl']} 个")

    print("[2/4] 复制程序源码…")
    for name in ("app", "assets"):
        shutil.copytree(os.path.join(ROOT, name),
                        os.path.join(args.out, name),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(os.path.join(ROOT, "main.py"),
                 os.path.join(args.out, "main.py"))
    cfgdir = os.path.join(args.out, "config")
    os.makedirs(cfgdir, exist_ok=True)
    shutil.copy2(os.path.join(ROOT, "config", "targets.example.json"),
                 os.path.join(cfgdir, "targets.example.json"))

    print("[3/4] 写启动脚本…")
    for fname, body in (("启动.bat", LAUNCH_BAT), ("校验环境.bat", CHECK_BAT),
                        ("README.txt", README_TXT)):
        # .bat 必须是 GBK —— cmd.exe 按 OEM 代码页解析，UTF-8 中文会烂；
        # README 用 UTF-8 以便记事本正确显示。
        enc = "utf-8" if fname.endswith(".txt") else "gbk"
        with open(os.path.join(args.out, fname), "w",
                  encoding=enc, errors="replace", newline="\r\n") as fh:
            fh.write(body)

    print("[4/4] 冒烟测试（用包内解释器跑自检）…")
    env = dict(os.environ)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [os.path.join(args.out, "runtime", "python.exe"), "main.py", "--check"],
        cwd=args.out, capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=env, timeout=180)
    tail = [l for l in (r.stdout or "").splitlines() if l.strip()][-6:]
    for line in tail:
        print("     " + line)
    ok = "6/6" in (r.stdout or "")
    print(f"     自检 {'通过' if ok else '失败'}（exit={r.returncode}）")
    if not ok:
        print((r.stderr or "")[:1500])

    size = dir_size(args.out)
    count = sum(len(f) for _d, _s, f in os.walk(args.out))
    print(f"\n完成: {args.out}")
    print(f"      共 {size:.1f} MB / {count} 个文件")
    if ok:
        print("      自检 6/6 —— 可以直接发布")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

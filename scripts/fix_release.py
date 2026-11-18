"""fix_release.py —— 重写 Release v1.0 的标题与说明（UTF-8 安全）。

为什么要单独写这个脚本：直接用 PowerShell 的 here-string 构造中文 JSON，
经 `pwsh -Command` 传参时会被系统 OEM 代码页(936) 转换一次，落到 GitHub 上
就成了 "鈥?棣栦釜鍙笅杞界増鏈?" 这种 UTF-8→GBK 双重编码乱码。
把正文写在 .py 文件里（文件以 UTF-8 保存）再用 curl --data-binary 发出去，
全程不经过 shell 的编码转换，就不会烂。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time

REPO = "Jiissoooo/shanhai-afk-guard"
RELEASE_ID = "450122751"

NAME = "v1.0 — 首个可下载版本"

BODY = """## 山海寻灵 · 防AFK控制器 v1.0

### 下载

| 文件 | 大小 | 说明 |
|---|---|---|
| **`ShanhaiAFK-portable-v1.0.zip`** | 10.4 MB | **推荐**。解压后双击 `启动.bat`。内含已签名的官方 CPython 运行时，**不会被 Smart App Control / WDAC 拦** |
| `ShanhaiAFK.exe` | 10.3 MB | 单文件绿色版，双击即用。是**未签名的新 PE 文件**，策略受限的机器上会被拦 |

### 便携版怎么用

1. 解压到任意目录
2. 双击 `启动.bat`，UAC 点「是」
3. 建任务 → 选程序 → 填按键和间隔 → `▶ 启动 (F9)`

配置生成在 `config/targets.json`，与程序同级，重装不丢。

### 单文件版怎么用

1. 下载 `ShanhaiAFK.exe`
2. **右键 → 属性 → 勾选「解除锁定」**
3. 双击运行，UAC 点「是」

### 为什么会有两个版本

`ShanhaiAFK.exe` 是 PyInstaller 产物，属于**全新的、没有代码签名的 PE 文件**。
在启用了智能应用控制或 WDAC 强制模式的 Windows 上会被直接拒绝：

```
An Application Control policy has blocked this file
```

实测（Windows 11，策略 `{0283AC0F-FFF1-49AE-ADA1-8A933130CAD6}`）：

| 实验 | 结果 |
|---|---|
| hello-world 级 C# exe（3574 B，未签名） | 被拦 |
| 自签名证书签过的 exe | 被拦 |
| PyInstaller onefile | 被拦 |
| PyInstaller onedir（941 文件 / 27 MB） | 被拦 |
| **已签名的 python.exe 复制改路径运行** | **正常跑** |

结论：策略**按 PE 签名判定**，不按路径或文件名。便携版因此不造新 exe，
改用受信任的官方解释器 + 纯 `.py` 源码。

### 校验

```
ShanhaiAFK.exe                 sha256:7047d0e4987b72852a310349e14c176321e65501c42a4027dca6c77058ed3de2
ShanhaiAFK-portable-v1.0.zip   sha256:f46f9cec4b48aba9d52ebbcf08bdea90bfcf944c27edd13cb9f1f5aea70e2594
```

`certutil -hashfile <文件名> SHA256`

### 构建环境

Windows 11 · Python 3.12.14 · PyInstaller 6.22.3 · 便携包自检 6/6 通过
"""


def token() -> str:
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    home = os.environ.get("DSH_HOME") or os.path.join(os.path.expanduser("~"), ".dsh")
    with open(os.path.join(home, ".dsh-github-connect", "auth.json"),
              encoding="utf-8") as fh:
        return json.load(fh)["token"]


def main() -> int:
    payload = json.dumps({"name": NAME, "body": BODY}, ensure_ascii=False)
    body_file = os.path.join(tempfile.gettempdir(), "_rel_body.json")
    with open(body_file, "w", encoding="utf-8", newline="") as fh:
        fh.write(payload)

    url = f"https://api.github.com/repos/{REPO}/releases/{RELEASE_ID}"
    for attempt in range(1, 11):
        proc = subprocess.run([
            "curl.exe", "-sS", "-m", "120", "-w", "%{http_code}", "-o",
            os.path.join(tempfile.gettempdir(), "_rel_out.json"),
            "-X", "PATCH",
            "-H", f"Authorization: Bearer {token()}",
            "-H", "User-Agent: shanhai-afk-guard-publisher",
            "-H", "Accept: application/vnd.github+json",
            "-H", "Content-Type: application/json; charset=utf-8",
            "--data-binary", f"@{body_file}", url,
        ], capture_output=True, text=True, encoding="utf-8", errors="replace")
        code = (proc.stdout or "").strip()
        if code == "200":
            with open(os.path.join(tempfile.gettempdir(), "_rel_out.json"),
                      encoding="utf-8") as fh:
                data = json.load(fh)
            print(f"HTTP 200")
            print(f"name     : {data['name']}")
            print(f"body len : {len(data['body'])} chars")
            print(f"assets   : {len(data['assets'])}")
            for a in data["assets"]:
                print(f"  - {a['name']}  {a['size']} bytes  {a.get('digest')}")
            print("\n--- body 前 6 行 ---")
            for line in data["body"].splitlines()[:6]:
                print("  " + line)
            return 0
        print(f"attempt {attempt} -> HTTP {code} {proc.stderr[:120]}")
        time.sleep(min(2 * attempt, 8))
    return 1


if __name__ == "__main__":
    sys.exit(main())

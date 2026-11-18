"""upload_repo.py —— 把本项目发布到 GitHub 仓库。

不依赖 git / requests / PyGithub。网络请求交给 curl.exe（Windows 10 1803+ 自带），
因为本机到 api.github.com 的 TLS 握手会被中间设备频繁打断，而 curl 走的是
系统 TLS 栈，实测 8/8 成功（python urllib 是 4/12）。

用法：
    python scripts/upload_repo.py --check     # 只列出要上传的文件，不写 GitHub
    python scripts/upload_repo.py             # 真正提交
凭据来源：环境变量 GITHUB_TOKEN，或本机 dsh-github-connect 的 auth.json。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time

OWNER = "Jiissoooo"
REPO = "shanhai-afk-guard"
BRANCH = "main"
API = "https://api.github.com"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 不发布的东西：运行时配置（含个人游戏进程名）、缓存、构建产物
SKIP_DIRS = {"__pycache__", ".git", "dist", ".venv", "venv", "node_modules"}
SKIP_REL = {"config/targets.json", "artifacts/sac_disable_log.txt"}
SKIP_EXT = {".pyc", ".pyo", ".tmp", ".log", ".reg"}
SAMPLE_EXE = "build/山海寻灵防AFK.exe"

# 已经通过 Contents API 单独管理的老文件（首次发布时要先建 commit 才能用 contents API，
# 所以第一版统一走 git tree，这里不特殊处理）
BINARY_EXT = {".exe", ".ico", ".png", ".jpg", ".zip"}


def auth_headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token == "":
        token = _read_local_token()
    if token == "":
        sys.exit("找不到 GitHub Token：请设置 GITHUB_TOKEN 环境变量")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "shanhai-afk-guard-publisher",
        "Content-Type": "application/json",
    }


def _read_local_token() -> str:
    """复用 dsh-github-connect 已经授权过的凭据，省得再粘一遍。"""
    home = os.environ.get("DSH_HOME") or os.path.join(os.path.expanduser("~"), ".dsh")
    path = os.path.join(home, ".dsh-github-connect", "auth.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            rec = json.load(fh)
        tok = rec.get("token")
        return tok if isinstance(tok, str) else ""
    except Exception:
        return ""


def api(method: str, path: str, body: dict | None = None, tries: int = 20):
    """通过 curl.exe 调 GitHub API，失败无限退避重试。

    为什么不用 urllib：本机到 api.github.com 的 TLS 握手会被中间设备频繁打断。
    实测 12 次连续 POST：
        python urllib  -> 4 成功 / 8 失败（SSLEOFError: UNEXPECTED_EOF_WHILE_READING）
        curl.exe       -> 8 成功 / 0 失败
    所以把发请求这件事整个交给 curl（Windows 10 1803+ 自带），
    Python 只负责枚举文件、编码 base64、组装 JSON。
    """
    url = f"{API}{path}"
    header_file = os.path.join(tempfile.gettempdir(), "_gh_headers.txt")
    body_file = os.path.join(tempfile.gettempdir(), "_gh_body.json")
    resp_file = os.path.join(tempfile.gettempdir(), "_gh_resp.json")

    token = auth_headers()["Authorization"].split(" ", 1)[1]
    with open(header_file, "w", encoding="utf-8") as fh:
        fh.write(f'Authorization: Bearer {token}\n')
        fh.write("Accept: application/vnd.github+json\n")
        fh.write("X-GitHub-Api-Version: 2022-11-28\n")
        fh.write("User-Agent: shanhai-afk-guard-publisher\n")
        fh.write("Content-Type: application/json\n")
    if body is not None:
        with open(body_file, "w", encoding="utf-8") as fh:
            json.dump(body, fh)

    last_error = ""
    for attempt in range(1, tries + 1):
        cmd = ["curl.exe", "-sS", "-m", "60", "-o", resp_file, "-w", "%{http_code}",
               "-X", method, "-H", f"@{header_file}", url]
        if body is not None:
            cmd[-1:-1] = ["--data-binary", f"@{body_file}"]
        # curl 在 --data-binary 之后仍需 URL，重建一次保证顺序正确
        cmd = ["curl.exe", "-sS", "-m", "60", "-o", resp_file, "-w", "%{http_code}",
               "-X", method, "-H", f"@{header_file}"]
        if body is not None:
            cmd += ["--data-binary", f"@{body_file}"]
        cmd.append(url)

        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
        code_text = (proc.stdout or "").strip()
        try:
            status = int(code_text)
        except ValueError:
            status = 0

        raw = ""
        try:
            with open(resp_file, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except Exception:
            pass
        parsed = None
        if raw.strip():
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {"message": raw[:400]}

        # 成功，或不可重试的 4xx
        if 200 <= status < 300:
            return status, parsed
        if 400 <= status < 500 and status not in (408, 409, 429):
            return status, parsed

        last_error = f"HTTP {status} {raw[:160]}" if status else f"curl: {(proc.stderr or '')[:160]}"
        wait = min(1.5 * attempt, 8)
        if attempt == 1 or attempt % 5 == 0:
            print(f"    [retry {attempt}/{tries}] {method} {path.split('/')[-1]} -> {last_error[:110]}")
        time.sleep(wait)

    return 0, {"message": f"重试 {tries} 次仍失败：{last_error}"}


def collect() -> list[dict]:
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, ROOT).replace("\\", "/")
            if rel in SKIP_REL:
                continue
            if os.path.splitext(name)[1].lower() in SKIP_EXT:
                continue
            # build/ 下的 exe 是 csc 编译的原生启动器（8 KB .NET 程序集，
            # 源码 launcher/Launcher.cs），直接可用，要发布。
            # dist/ 下的 PyInstaller 大产物才排除。
            with open(full, "rb") as fh:
                data = fh.read()
            files.append({"path": rel, "data": data, "size": len(data),
                          "binary": os.path.splitext(name)[1].lower() in BINARY_EXT})
    files.sort(key=lambda f: f["path"])
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只打印将要上传的文件，不写 GitHub")
    ap.add_argument("--message", default="feat: 首次发布 山海寻灵·防AFK控制器 v1.0")
    args = ap.parse_args()

    files = collect()
    total = sum(f["size"] for f in files)
    print(f"待上传 {len(files)} 个文件，共 {total/1024:.1f} KB")
    for f in files:
        print(f"  {'[BIN]' if f['binary'] else '     '} {f['size']:>8}  {f['path']}")
    if args.check:
        return 0

    # 0) 空仓库时 git/blobs 会返回 409 "Git Repository is empty"，
    #    必须先用 Contents API 种一个初始 commit，之后 git tree 才能用。
    status, ref0 = api("GET", f"/repos/{OWNER}/{REPO}/git/ref/heads/{BRANCH}")
    if status != 200:
        print(f"仓库尚无 {BRANCH} 分支（HTTP {status}），先种一个初始 commit…")
        seed = ("# shanhai-afk-guard\n\n"
                "初始化占位提交，真正的文件由 scripts/upload_repo.py 随后提交。\n").encode()
        status, seeded = api("PUT", f"/repos/{OWNER}/{REPO}/contents/.bootstrap",
                             {"message": "chore: 初始化仓库",
                              "content": base64.b64encode(seed).decode("ascii")})
        if status not in (200, 201):
            print(f"[FAIL] 初始 commit: HTTP {status} {seeded}")
            return 1
        print(f"初始 commit = {seeded['commit']['sha']}")
        time.sleep(2)

    # 1) 逐个大文件先建 blob（小文件也走同一路径，简单一致）
    tree_items = []
    for idx, f in enumerate(files, 1):
        status, blob = api("POST", f"/repos/{OWNER}/{REPO}/git/blobs", {
            "content": base64.b64encode(f["data"]).decode("ascii"),
            "encoding": "base64",
        })
        if status not in (200, 201) or not blob or "sha" not in blob:
            print(f"  [FAIL] blob {f['path']}: HTTP {status} {blob}")
            return 1
        tree_items.append({"path": f["path"], "mode": "100644",
                           "type": "blob", "sha": blob["sha"]})
        print(f"  [{idx}/{len(files)}] blob ok  {f['path']}")

    # 2) 建 tree
    status, tree = api("POST", f"/repos/{OWNER}/{REPO}/git/trees", {
        "tree": tree_items,
    })
    if status not in (200, 201) or not tree:
        print(f"[FAIL] tree: HTTP {status} {tree}")
        return 1
    print(f"tree sha = {tree['sha']}")

    # 3) 找父 commit（仓库刚建时为空）
    status, ref = api("GET", f"/repos/{OWNER}/{REPO}/git/ref/heads/{BRANCH}")
    parents = []
    if status == 200 and ref and ref.get("object"):
        parents = [ref["object"]["sha"]]
        print(f"父 commit = {parents[0]}")
    else:
        print("仓库为空，创建首个 commit")

    # 4) commit
    status, commit = api("POST", f"/repos/{OWNER}/{REPO}/git/commits", {
        "message": args.message,
        "tree": tree["sha"],
        "parents": parents,
    })
    if status not in (200, 201) or not commit:
        print(f"[FAIL] commit: HTTP {status} {commit}")
        return 1
    print(f"commit sha = {commit['sha']}")

    # 5) 指向分支
    if parents:
        status, out = api("PATCH", f"/repos/{OWNER}/{REPO}/git/refs/heads/{BRANCH}",
                          {"sha": commit["sha"], "force": False})
    else:
        status, out = api("POST", f"/repos/{OWNER}/{REPO}/git/refs",
                          {"ref": f"refs/heads/{BRANCH}", "sha": commit["sha"]})
    if status not in (200, 201):
        print(f"[FAIL] ref: HTTP {status} {out}")
        return 1
    print(f"分支 {BRANCH} -> {commit['sha']}")

    # 6) 确认
    time.sleep(2)
    status, info = api("GET", f"/repos/{OWNER}/{REPO}")
    if status == 200 and info:
        print(f"完成: {info['html_url']}  (default_branch={info.get('default_branch')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

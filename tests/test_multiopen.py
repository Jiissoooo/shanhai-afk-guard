"""test_multiopen.py - 同进程多开验证 + 抖动生效验证。

场景：山海寻灵这类游戏常开 3-4 个客户端。若按进程名配置，
必须给每个窗口独立计时、独立投递，不能只打第一个。
"""
from __future__ import annotations

import os
import random
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app.engine import Engine, Target  # noqa: E402
from app import winapi as W            # noqa: E402

LOGDIR = os.path.join(ROOT, "artifacts")


def count_keys(log: str) -> int:
    if not os.path.exists(log):
        return 0
    with open(log, "r", encoding="utf-8", errors="replace") as fh:
        return sum(1 for line in fh if line.startswith(tuple("0123456789")) and "VK=" in line)


def key_times(log: str) -> list[float]:
    out = []
    if not os.path.exists(log):
        return out
    with open(log, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith(tuple("0123456789")) and "VK=" in line:
                try:
                    out.append(float(line.split("\t")[0]))
                except ValueError:
                    pass
    return out


def main() -> int:
    os.makedirs(LOGDIR, exist_ok=True)
    print("=" * 68)
    print(" 同进程多开 + 抖动 验证")
    print("=" * 68)

    procs = []
    logs = {}
    try:
        # 同一个可执行文件、同一个进程族名（python.exe），标题不同
        for nm in ("K1", "K2", "K3"):
            log = os.path.join(LOGDIR, f"mo_{nm}.log")
            if os.path.exists(log):
                os.remove(log)
            p = subprocess.Popen([sys.executable,
                                  os.path.join(HERE, "probe_target.py"),
                                  f"SH_MULTI_{nm}", log, "minimize"],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            procs.append(p)
            logs[nm] = log
            time.sleep(0.5)

        deadline = time.time() + 8
        wins = []
        while time.time() < deadline:
            wins = W.find_windows(title_sub="SH_MULTI_", include_hidden=True)
            if len(wins) >= 3:
                break
            time.sleep(0.2)
        print(f"\n[1] 同名进程族窗口: {len(wins)} 个")
        for w in wins:
            print(f"    0x{w['hwnd']:X} {w['title']:<16} exe={w['exe']} "
                  f"pid={w['pid']} min={w['minimized']}")
        if len(wins) < 3:
            print("FAIL: 窗口数不足")
            return 1

        # 用「按进程名 + 标题前缀」双条件配置，等价于真实用法
        cfg = os.path.join(ROOT, "config", "test_multiopen.json")
        eng = Engine(cfg)
        eng.targets = [Target(name="山海3开", title_sub="SH_MULTI_", exe_sub="",
                              key="space", interval_sec=0.8, jitter_pct=25.0,
                              hold_ms=15, method="message", auto_discover=True,
                              max_instances=8)]
        eng._last_scan = 0.0
        eng.rescan(force=True)
        print(f"\n[2] 引擎接管: {len(eng.instances)} 个实例（应 >=3）")
        for i in eng.instances:
            print(f"    0x{i.hwnd:X} {i.title:<16} next_fire_off={i.next_fire - time.monotonic():+.2f}s")

        # 检查错峰：各实例的 next_fire 不应完全相同
        offsets = [round(i.next_fire, 3) for i in eng.instances]
        stagger = len(set(offsets))
        print(f"\n[3] 错峰检查: {stagger} 个不同起始时刻 -> "
              f"{'PASS' if stagger >= min(3, len(offsets)) else 'FAIL'}")

        eng.set_running(True)
        t0 = time.time()
        while time.time() - t0 < 8.0:
            eng.tick()
            time.sleep(0.05)
        eng.running = False
        time.sleep(0.3)

        print("\n[4] 每个窗口收到次数")
        counts = {}
        for nm, log in logs.items():
            c = count_keys(log)
            counts[nm] = c
            ts = key_times(log)
            gaps = [f"{ts[i+1]-ts[i]:.2f}" for i in range(len(ts) - 1)][:8]
            print(f"    SH_MULTI_{nm}: {c} 次   间隔序列(s)= {gaps}")

        all_hit = all(c >= 4 for c in counts.values())
        print(f"\n[5] 每个窗口均 >=4 次           : {'PASS' if all_hit else 'FAIL'}")

        # 抖动验证：间隔不应是常数
        all_gaps = []
        for log in logs.values():
            ts = key_times(log)
            all_gaps += [round(ts[i + 1] - ts[i], 3) for i in range(len(ts) - 1)]
        uniq = len(set(all_gaps))
        jitter_ok = uniq >= max(3, len(all_gaps) // 2)
        print(f"[6] 抖动生效 (间隔种类 {uniq}/{len(all_gaps)}): "
              f"{'PASS' if jitter_ok else 'FAIL'}")

        eng.save()
        done = all_hit and stagger >= 3 and jitter_ok
        print("\n" + "=" * 68)
        print(f" 结论: {'多开并发 + 独立计时 + 抖动 全部通过' if done else '存在失败项'}")
        print("=" * 68)
        return 0 if done else 1
    finally:
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())

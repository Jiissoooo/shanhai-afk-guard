"""engine.py - 调度核心。

模型：
    Target  = 一条配置（匹配规则 + 按键 + 间隔 + 抖动 + 注入方式）
    Instance= 某个 Target 命中的一个真实窗口（同一进程多开就多个 Instance）
所有 Instance 各自独立计时，因此可以同时对多个应用/多个游戏窗口控制，
彼此互不阻塞，也不会在同一毫秒齐发（自动错峰）。
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field, asdict

from . import inject
from . import integrity as INTEG
from . import winapi as W

LOG_MAX = 2000
TICK = 0.05            # 引擎节拍 20Hz
RESCAN_SEC = 3.0       # 自动重扫窗口间隔
DEAD_GRACE = 20.0      # 窗口消失后保留多久再丢弃


@dataclass
class Target:
    name: str = "新任务"
    title_sub: str = ""            # 窗口标题子串
    exe_sub: str = ""              # 进程名子串，如 Game.exe
    key: str = "space"             # 按键名 → VK
    interval_sec: float = 300.0    # 多少秒按一次
    jitter_pct: float = 5.0        # ±% 抖动，防固定节拍
    hold_ms: int = 40              # 按下保持毫秒
    method: str = "both"           # message | sendinput | focus | both
    enabled: bool = True
    auto_discover: bool = True     # 自动接管所有匹配窗口（多开）
    max_instances: int = 16
    hotkey: str = ""               # 单任务热键，如 ctrl+alt+1

    def vk(self) -> int:
        return W.vk_from_name(self.key)


@dataclass
class Instance:
    target_idx: int
    target_name: str
    hwnd: int
    pid: int
    title: str
    exe: str
    next_fire: float = 0.0
    count: int = 0
    last_via: str = "-"
    last_at: float = 0.0
    alive: bool = True
    dead_since: float = 0.0
    fail_streak: int = 0

    def key(self):
        return (self.target_idx, self.hwnd)


class Engine:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.lock = threading.RLock()
        self.targets: list[Target] = []
        self.instances: list[Instance] = []
        self.running = False                # 总开关
        self.logs: deque = deque(maxlen=LOG_MAX)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_scan = 0.0
        self._warned_admin = False
        self._hotkey_state: dict[int, bool] = {}
        self._hotkey_action: dict[int, str] = {}
        self._bind_hotkeys()
        self.load()

    # ------------------------------------------------------------ logging
    def log(self, msg: str, level: str = "info"):
        stamp = time.strftime("%H:%M:%S")
        with self.lock:
            self.logs.append((stamp, level, msg))

    def drain_logs(self) -> list[tuple[str, str, str]]:
        with self.lock:
            items = list(self.logs)
            self.logs.clear()
        return items

    # ------------------------------------------------------------ lifecycle
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="helmd-engine",
                                        daemon=True)
        self._thread.start()
        self.log("引擎线程已启动", "ok")

    def shutdown(self):
        self._stop.set()
        self.running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self.save()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:          # 引擎不允许因单点异常退出
                self.log(f"tick 异常: {exc!r}", "err")
            time.sleep(TICK)

    # ------------------------------------------------------------ hotkeys
    def _bind_hotkeys(self):
        """全局热键：轮询 GetAsyncKeyState，后台/最小化也有效。"""
        self._hotkey_action.clear()
        table = {"F9": "toggle_run", "F10": "stop_all", "F11": "rescan"}
        for name, action in table.items():
            try:
                self._hotkey_action[W.vk_from_name(name)] = action
            except ValueError:
                pass

    def _poll_hotkeys(self):
        # 单任务热键
        with self.lock:
            for idx, t in enumerate(self.targets):
                if not t.hotkey:
                    continue
                vk = self._parse_combo(t.hotkey)
                if vk:
                    self._hotkey_action[vk] = f"toggle:{idx}"

        edge = []
        for vk, action in list(self._hotkey_action.items()):
            down = W.vk_down(vk)
            was = self._hotkey_state.get(vk, False)
            if down and not was:
                edge.append(action)
            self._hotkey_state[vk] = down
        for action in edge:
            if action == "toggle_run":
                self.running = not self.running
                self.log(f"总开关 -> {'运行' if self.running else '暂停'}", "ok")
            elif action == "stop_all":
                self.running = False
                self.log("热键停止全部", "warn")
            elif action == "rescan":
                self.rescan(force=True)
                self.log("热键重扫窗口", "info")
            elif action.startswith("toggle:"):
                idx = int(action.split(":")[1])
                with self.lock:
                    if 0 <= idx < len(self.targets):
                        self.targets[idx].enabled = not self.targets[idx].enabled
                        st = "启用" if self.targets[idx].enabled else "禁用"
                        self.log(f"任务[{self.targets[idx].name}] {st}", "info")

    def _parse_combo(self, combo: str) -> int:
        """'ctrl+alt+1' 这类组合只支持单键触发部分（取最后一个键）。"""
        if not combo:
            return 0
        last = combo.lower().split("+")[-1].strip()
        try:
            return W.vk_from_name(last)
        except ValueError:
            return 0

    # ------------------------------------------------------------ scanning
    def rescan(self, force: bool = False):
        now = time.monotonic()
        if not force and now - self._last_scan < RESCAN_SEC:
            return
        self._last_scan = now
        with self.lock:
            targets = list(self.targets)
        new_inst: list[Instance] = []
        live_keys = set()
        for idx, t in enumerate(targets):
            try:
                # match_all=True：标题+进程名同时生效，避免宿主进程下
                # 把不相干的窗口一起接管（多开场景必须如此）
                hits = W.find_windows(t.title_sub, t.exe_sub,
                                      include_hidden=True,
                                      match_all=True,
                                      limit=max(1, t.max_instances))
            except Exception as exc:
                self.log(f"枚举失败 {t.name}: {exc!r}", "err")
                continue
            if not t.auto_discover and hits:
                hits = hits[:1]
            for w in hits:
                k = (idx, w["hwnd"])
                live_keys.add(k)
                new_inst.append(Instance(
                    target_idx=idx, target_name=t.name, hwnd=w["hwnd"],
                    pid=w["pid"], title=w["title"], exe=w["exe"]))
        with self.lock:
            old = {i.key(): i for i in self.instances}
            merged = []
            for inst in new_inst:
                prev = old.get(inst.key())
                if prev:
                    inst.count = prev.count
                    inst.next_fire = prev.next_fire
                    inst.last_via = prev.last_via
                    inst.last_at = prev.last_at
                    inst.title = inst.title or prev.title
                else:
                    # 错峰：新接管窗口按序号错开 0.2s，避免同帧齐发
                    inst.next_fire = now + 0.2 * (len(merged) % 8)
                    self.log(f"接管窗口 [{inst.title[:24]}] ({inst.exe} pid={inst.pid})", "ok")
                    # 权限预检：高完整性目标在普通权限下必然被 UIPI 拦截，
                    # 提前告警，避免"界面显示在线但游戏没反应"。
                    rid = INTEG.process_integrity(inst.pid)
                    ok_perm, reason = INTEG.can_target(INTEG.self_integrity(), rid)
                    if not ok_perm:
                        self.log(f"  ⚠ {inst.exe} 权限不足: {reason}", "err")
                        if not self._warned_admin:
                            self._warned_admin = True
                            self.log("  ⚠ 请以管理员身份重启本工具，否则该目标无法控制", "err")
                merged.append(inst)
            # 保留刚消失的窗口一小会儿，避免误判抖动造成频繁重挂
            n_targets = len(targets)
            for k, v in old.items():
                if k in live_keys:
                    continue
                # 任务被删除后 target_idx 会失效，这类残留必须直接丢弃，
                # 否则会带着越界索引复活，导致按错任务的按键/间隔。
                if not (0 <= v.target_idx < n_targets):
                    continue
                if not v.dead_since:
                    v.dead_since = now
                    v.alive = False
                if now - v.dead_since < DEAD_GRACE:
                    merged.append(v)
            self.instances = merged

    # ------------------------------------------------------------ tick
    def tick(self):
        self._poll_hotkeys()
        self.rescan()
        if not self.running:
            return
        now = time.monotonic()
        with self.lock:
            snapshot = [(i, self.targets[i.target_idx]) for i in self.instances
                        if i.alive and i.target_idx < len(self.targets)]
        fired = 0
        for inst, t in snapshot:
            if not t.enabled or now < inst.next_fire:
                continue
            try:
                vk = t.vk()
            except ValueError as exc:
                self.log(f"键位配置错误 {t.name}: {exc}", "err")
                t.enabled = False
                continue
            if not W.user32.IsWindow(inst.hwnd):
                inst.alive = False
                inst.dead_since = inst.dead_since or now
                continue
            res = inject.press(inst.hwnd, vk, t.method, t.hold_ms)
            inst.count += 1
            inst.last_at = now
            inst.last_via = res["via"]
            base = max(0.5, float(t.interval_sec))
            jit = base * float(t.jitter_pct) / 100.0
            inst.next_fire = now + max(0.3, base + random.uniform(-jit, jit))
            if res["ok"]:
                inst.fail_streak = 0
                if inst.count == 1 or inst.count % 10 == 0:
                    self.log(f"[{t.name}] {inst.title[:20]} 第 {inst.count} 次 ({res['via']})", "ok")
            else:
                inst.fail_streak += 1
                self.log(f"[{t.name}] {inst.title[:20]} 注入失败 ({res['via']})", "warn")
                if inst.fail_streak >= 5:
                    inst.alive = False
                    inst.dead_since = now
                    self.log(f"[{t.name}] {inst.title[:20]} 连续失败已脱管", "err")
            fired += 1
        del fired

    # ------------------------------------------------------------ api for GUI
    def set_running(self, value: bool):
        self.running = bool(value)
        self.log(f"总开关 -> {'运行' if self.running else '暂停'}", "ok")

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "running": self.running,
                "targets": [asdict(t) for t in self.targets],
                "instances": [{
                    "target": i.target_name, "title": i.title, "exe": i.exe,
                    "pid": i.pid, "count": i.count, "via": i.last_via,
                    "alive": i.alive,
                    "eta": max(0.0, i.next_fire - time.monotonic()) if i.alive else -1,
                } for i in self.instances],
            }

    # ------------------------------------------------------------ persistence
    def load(self):
        if not os.path.exists(self.config_path):
            self.targets = [Target(name="示例任务", title_sub="", exe_sub="Game.exe")]
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.targets = [Target(**t) for t in data.get("targets", [])]
            self.log(f"已载入配置 {len(self.targets)} 条", "info")
        except Exception as exc:
            self.log(f"配置损坏，使用默认: {exc!r}", "err")
            self.targets = [Target(name="示例任务", exe_sub="Game.exe")]

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with self.lock:
                data = {"version": 1, "targets": [asdict(t) for t in self.targets]}
            tmp = self.config_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.config_path)
        except Exception as exc:
            self.log(f"保存失败: {exc!r}", "err")

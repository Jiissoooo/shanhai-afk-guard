"""ui.py - tkinter 控制台。

布局：
  [顶部]  总开关 / 全部启动 / 全部停止 / 重扫窗口 / 测试按键
  [左]    任务列表 + 编辑表单（匹配标题、进程名、按键、间隔、抖动、方式、热键）
  [右]    实时窗口实例表（每个窗口一行，倒计时、次数、注入方式）
  [底]    日志
快捷键：F9 总开关 / F10 全停 / F11 重扫（引擎层轮询，最小化也生效）
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk

from . import elevate as ELEV
from . import paths as PATHS
from . import tray as TRAY
from . import winapi as W
from .engine import Engine, Target


class App:
    def __init__(self, root: tk.Tk, engine: Engine):
        self.root = root
        self.engine = engine
        self.sel = -1
        self.var_autorun = tk.BooleanVar(value=False)
        self.var_tray = tk.BooleanVar(value=True)
        self.tray: TRAY.TrayIcon | None = None
        self.hidden_to_tray = False
        self._really_quit = False
        root.title("山海寻灵 · 防AFK控制器  v1.0")
        root.geometry("1180x760")
        root.minsize(1000, 640)

        self._build_top()
        self._build_body()
        self._build_log()

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        engine.start()
        self._init_tray()
        self.refresh_tasks()
        self.refresh_instances()
        self.pump_logs()
        # 程序清单延迟到窗口映射完成后再加载，否则部分环境下枚举为空
        self.root.after(120, self._initial_app_load)
        # 程序清单定时刷新（新开的游戏能自动出现在下拉框里）
        self.root.after(5200, self._app_tick)

    def _initial_app_load(self):
        self.refresh_app_list()
        self._sync_exe_combo()
        n = len(self._app_map)
        self.engine.log(f"已载入 {n} 个正在运行的程序到下拉框", "info")
        if n == 0:
            self.engine.log("未发现可选程序，点「刷新」重试", "warn")
        else:
            self._set_app_placeholder()

    def _set_app_placeholder(self):
        """显示占位提示，让用户一眼看出这里可以下拉。"""
        n = len(self._app_map)
        if n <= 0:
            return
        self.v_app.set("")
        self.cb_app.set(f"（点击下拉选择，共 {n} 个程序）")

    # ---------------------------------------------------------------- top
    def _build_top(self):
        bar = ttk.Frame(self.root, padding=(8, 6))
        bar.pack(fill="x")
        self.btn_run = ttk.Button(bar, text="▶ 启动 (F9)", width=14,
                                  command=self.toggle_run)
        self.btn_run.pack(side="left")
        ttk.Button(bar, text="■ 全部停止 (F10)", width=16,
                   command=self.stop_all).pack(side="left", padx=4)
        ttk.Button(bar, text="⟳ 重扫窗口 (F11)", width=16,
                   command=lambda: (self.engine.rescan(force=True),
                                    self.refresh_instances())).pack(side="left", padx=4)
        ttk.Button(bar, text="＋ 新建任务", width=12,
                   command=self.new_task).pack(side="left", padx=4)
        ttk.Label(bar, text="  ").pack(side="left")
        ttk.Checkbutton(bar, text="启动后自动开跑", variable=self.var_autorun,
                        command=self._apply_autorun).pack(side="left", padx=6)
        ttk.Checkbutton(bar, text="关闭时最小化到托盘", variable=self.var_tray).pack(
            side="left", padx=6)
        self.lbl_state = ttk.Label(bar, text="● 待机", font=("Consolas", 11, "bold"))
        self.lbl_state.pack(side="right", padx=8)
        self.lbl_count = ttk.Label(bar, text="接管 0 窗口")
        self.lbl_count.pack(side="right", padx=8)
        # 权限状态：非管理员时给出可点击的提权重启
        if ELEV.is_elevated():
            self.lbl_perm = ttk.Label(bar, text="🔓 管理员", foreground="#5fd38d")
            self.lbl_perm.pack(side="right", padx=6)
        else:
            self.lbl_perm = ttk.Label(bar, text="🔒 普通权限", foreground="#e3b341")
            self.lbl_perm.pack(side="right", padx=(6, 0))
            ttk.Button(bar, text="以管理员重启", width=14,
                       command=self.restart_as_admin).pack(side="right", padx=4)

    # ---------------------------------------------------------------- body
    def _build_body(self):
        pw = ttk.PanedWindow(self.root, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=8, pady=4)
        self.pw = pw

        left = ttk.Frame(pw, width=470)
        right = ttk.Frame(pw)
        left.pack_propagate(False)
        left.grid_propagate(False)
        pw.add(left, weight=0)
        pw.add(right, weight=1)

        # --- 任务列表
        lf = ttk.LabelFrame(left, text="任务配置", padding=6)
        lf.pack(fill="x")
        cols = ("name", "rule", "key", "itv", "method", "st")
        self.tree = ttk.Treeview(lf, columns=cols, show="headings", height=7)
        heads = {"name": ("名称", 78), "rule": ("匹配(进程/标题)", 122),
                 "key": ("按键", 46), "itv": ("间隔s", 44),
                 "method": ("方式", 56), "st": ("状态", 42)}
        for c in cols:
            self.tree.heading(c, text=heads[c][0])
            self.tree.column(c, width=heads[c][1], anchor="w", minwidth=36,
                             stretch=(c == "rule"))
        self.tree.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        # --- 应用区（参与全高分配）
        formw = ttk.Frame(left)
        formw.pack(fill="both", expand=True, pady=(6, 0))
        form = ttk.LabelFrame(formw, text="编辑选中任务", padding=(8, 4))
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)

        self.v_name = tk.StringVar()
        self.v_title = tk.StringVar()
        self.v_exe = tk.StringVar()
        self.v_key = tk.StringVar(value="space")
        self.v_interval = tk.StringVar(value="300")
        self.v_jitter = tk.StringVar(value="5")
        self.v_hold = tk.StringVar(value="40")
        self.v_method = tk.StringVar(value="both")
        self.v_hotkey = tk.StringVar()
        self.v_auto = tk.BooleanVar(value=True)
        self.v_enabled = tk.BooleanVar(value=True)

        # 程序下拉框：显示文本 -> exe 的映射
        self._app_map: dict[str, str] = {}
        self._app_list: list[dict] = []
        self.v_app = tk.StringVar()

        rows = [
            ("任务名", ttk.Entry(form, textvariable=self.v_name)),
            ("选择程序", self._app_widget(form)),
            ("窗口标题含", ttk.Entry(form, textvariable=self.v_title)),
            ("进程名含", self._exe_widget(form)),
            ("按键", self._key_widget(form)),
            ("间隔(秒)", ttk.Entry(form, textvariable=self.v_interval)),
            ("抖动±%", ttk.Entry(form, textvariable=self.v_jitter)),
            ("按下保持ms", ttk.Entry(form, textvariable=self.v_hold)),
            ("注入方式", ttk.Combobox(form, textvariable=self.v_method,
                                      values=("both", "message", "sendinput", "focus"),
                                      state="readonly", width=14)),
            ("单任务热键", ttk.Entry(form, textvariable=self.v_hotkey)),
        ]
        for r, (label, widget) in enumerate(rows):
            ttk.Label(form, text=label, width=11).grid(
                row=r, column=0, sticky="w", pady=1)
            widget.grid(row=r, column=1, sticky="ew", pady=1)
        ttk.Checkbutton(form, text="自动接管全部匹配窗口(多开)",
                        variable=self.v_auto).grid(row=10, column=1, sticky="w", pady=1)
        ttk.Checkbutton(form, text="启用本任务", variable=self.v_enabled).grid(
            row=11, column=1, sticky="w", pady=1)

        # 匹配状态行：直观显示当前规则会命中几个窗口
        self.lbl_match = ttk.Label(form, text="匹配 -", anchor="w",
                                   font=("Microsoft YaHei UI", 9, "bold"))
        self.lbl_match.grid(row=12, column=0, columnspan=2, sticky="ew", pady=(4, 2))

        btns = ttk.Frame(form)
        btns.grid(row=13, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        ttk.Button(btns, text="保存", width=7, command=self.save_task).pack(side="left")
        ttk.Button(btns, text="测试", width=7, command=self.test_task).pack(side="left", padx=3)
        ttk.Button(btns, text="删除", width=7, command=self.del_task).pack(side="left")
        ttk.Button(btns, text="探测窗口", width=9,
                   command=self.probe_windows).pack(side="right")

        # --- 实例表
        rf = ttk.LabelFrame(right, text="正在控制的窗口（每个窗口独立计时）", padding=6)
        rf.pack(fill="both", expand=True)
        icols = ("target", "title", "exe", "pid", "eta", "count", "via", "alive")
        self.itree = ttk.Treeview(rf, columns=icols, show="headings", height=18)
        iheads = {"target": ("任务", 80), "title": ("窗口标题", 190),
                  "exe": ("进程", 100), "pid": ("PID", 55),
                  "eta": ("下次(秒)", 68), "count": ("已按", 48),
                  "via": ("通道", 72), "alive": ("状态", 48)}
        for c in icols:
            self.itree.heading(c, text=iheads[c][0])
            self.itree.column(c, width=iheads[c][1], anchor="w", minwidth=40,
                              stretch=(c == "title"))
        vsb = ttk.Scrollbar(rf, orient="vertical", command=self.itree.yview)
        hsb = ttk.Scrollbar(rf, orient="horizontal", command=self.itree.xview)
        self.itree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.itree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        rf.rowconfigure(0, weight=1)
        rf.columnconfigure(0, weight=1)

    def _app_widget(self, parent):
        """程序下拉框：列出当前所有正在运行的程序，选中即自动填进程名。

        可以输入过滤（输入 game 就只剩含 game 的项），也可以直接选。
        """
        fr = ttk.Frame(parent)
        self.cb_app = ttk.Combobox(fr, textvariable=self.v_app, width=30)
        self.cb_app.pack(side="left", fill="x", expand=True)
        self.cb_app.bind("<<ComboboxSelected>>", self._on_app_pick)
        # 输入时实时过滤
        self.cb_app.bind("<KeyRelease>", self._on_app_filter)
        ttk.Button(fr, text="刷新", width=6,
                   command=self.refresh_app_list).pack(side="left", padx=(3, 0))
        return fr

    def refresh_app_list(self, keep_text: bool = False):
        """重新枚举正在运行的程序，填充下拉框。"""
        try:
            apps = W.list_apps()
        except Exception as exc:
            self.engine.log(f"枚举程序失败: {exc!r}", "err")
            return
        self._app_list = apps
        self._app_map = {}
        values = []
        for a in apps:
            txt = W.display_name(a)
            # 显示文本可能重名，加序号保证可区分
            base = txt
            n = 2
            while txt in self._app_map:
                txt = f"{base} ({n})"
                n += 1
            self._app_map[txt] = a["exe"]
            values.append(txt)
        self.cb_app["values"] = values
        if not values:
            # 明确告诉用户为什么是空的，而不是给一个空下拉框
            self.cb_app["values"] = ["(未发现程序，点「刷新」)"]
        if not keep_text:
            self.cb_app.delete(0, "end")
            # 刷新后恢复占位提示，否则用户看到的是个空白框，
            # 会误以为控件坏了（真实踩过的坑）
            if self._app_map:
                self.cb_app.set(f"（点击下拉选择，共 {len(self._app_map)} 个程序）")

    def _on_app_filter(self, _e=None):
        """输入过滤：按输入串筛出匹配的程序。"""
        typed = self.v_app.get().strip().lower()
        # 忽略占位提示文本
        if typed.startswith("（"):
            typed = ""
        if not typed:
            self.cb_app["values"] = list(self._app_map.keys())
            return
        hit = [t for t in self._app_map
               if typed in t.lower() or typed in self._app_map[t].lower()]
        self.cb_app["values"] = hit
        if hit and self.cb_app.focus_get() == self.cb_app:
            self.cb_app.event_generate("<Down>")

    def _on_app_pick(self, _e=None):
        """选中某个程序 -> 自动填入进程名，并回填任务名 / 标题。"""
        txt = self.v_app.get()
        exe = self._app_map.get(txt)
        if not exe:
            return
        self.v_exe.set(exe)
        base = exe[:-4] if exe.lower().endswith(".exe") else exe
        # 任务名为空或还是默认名时，自动填成程序名
        cur = self.v_name.get().strip()
        if not cur or cur.startswith("任务") or cur.startswith("示例"):
            self.v_name.set(base)

        target = None
        for a in self._app_list:
            if a["exe"] == exe:
                target = a
                break

        if target and target["windows"] > 1:
            # 多开：按 exe 会把同进程所有窗口都接管。
            # 用全部标题（不只前 3 个）提取公共前缀来收窄。
            common = self._common_title(target.get("all_titles")
                                        or target["titles"])
            if common:
                self.v_title.set(common)
                self._hint_matched()
                hits = len(W.find_windows(common, exe, include_hidden=True))
                self.engine.log(
                    f"{exe} 有 {target['windows']} 个窗口，"
                    f"用标题关键字 {common!r} 收窄到 {hits} 个", "info")
            else:
                self.v_title.set("")
                self.engine.log(
                    f"{exe} 有 {target['windows']} 个窗口且标题无公共特征，"
                    f"将按进程名全部接管", "warn")
        elif target and target["titles"]:
            # 单窗口：清空标题，只按进程名匹配即可（更宽松、更稳）
            self.v_title.set("")
            self.engine.log(f"已选择 {exe}（{target['titles'][0][:30]}）", "info")
        else:
            self.v_title.set("")

        self._hint_matched()

    def _common_title(self, titles: list[str]) -> str:
        """从多个窗口标题里提取公共前缀，作为收窄匹配的关键字。

        例：['山海寻灵 - 主号', '山海寻灵 - 小号'] -> '山海寻灵'

        注意：像 python.exe 这种宿主进程底下会同时跑多个互不相关的程序，
        所有标题的公共前缀可能是空的。这时退化为「出现次数最多的前缀」，
        只要覆盖到 60% 的窗口就认为可用。
        """
        if not titles or len(titles) < 2:
            return ""
        # 先试全量公共前缀
        prefix = titles[0]
        for t in titles[1:]:
            i = 0
            while i < len(prefix) and i < len(t) and prefix[i] == t[i]:
                i += 1
            prefix = prefix[:i]
            if not prefix:
                break
        prefix = prefix.strip(" -_|·:：")
        if len(prefix) >= 3:
            return prefix

        # 退路：统计各标题的前缀，取覆盖 60% 以上的最长者
        need = max(2, int(len(titles) * 0.6))
        cand: dict[str, int] = {}
        for t in titles:
            t = t.strip()
            for cut in range(3, min(len(t), 20) + 1):
                p = t[:cut].strip(" -_|·:：")
                if len(p) >= 3:
                    cand[p] = cand.get(p, 0) + 1
        best = ""
        for p, c in cand.items():
            if c >= need and len(p) > len(best):
                best = p
        return best

    def _hint_matched(self):
        """在界面上直观显示当前规则会命中几个窗口（AND 语义）。"""
        try:
            hits = W.find_windows(self.v_title.get().strip(),
                                  self.v_exe.get().strip(),
                                  include_hidden=True, match_all=True)
        except Exception:
            return
        n = len(hits)
        if n == 0:
            self.lbl_match.configure(text="匹配 0 个窗口", foreground="#f26d6d")
        else:
            self.lbl_match.configure(
                text=f"匹配 {n} 个窗口", foreground="#5fd38d")

    def _exe_widget(self, parent):
        """进程名：可编辑（下拉框允许手输），与程序清单联动。"""
        fr = ttk.Frame(parent)
        cb = ttk.Combobox(fr, textvariable=self.v_exe, width=30)
        cb.pack(fill="x")
        cb.bind("<<ComboboxSelected>>", lambda e: self._hint_matched())
        cb.bind("<KeyRelease>", lambda e: self._hint_matched())
        self.cb_exe = cb
        return fr

    def _key_widget(self, parent):
        """按键输入 + 常用预设下拉。"""
        fr = ttk.Frame(parent)
        ent = ttk.Entry(fr, textvariable=self.v_key, width=14)
        ent.pack(side="left")
        cb = ttk.Combobox(fr, width=12, state="readonly",
                          values=("space", "enter", "f1", "f2", "f5",
                                  "numpad0", "numpad5", "z", "x", "tab"))
        cb.pack(side="left", padx=4)

        def _pick(_e=None):
            if cb.get():
                self.v_key.set(cb.get())
        cb.bind("<<ComboboxSelected>>", _pick)
        return fr

    # ---------------------------------------------------------------- log
    def _build_log(self):
        frame = ttk.LabelFrame(self.root, text="日志", padding=4)
        frame.pack(fill="both", padx=8, pady=(0, 8))
        self.log_txt = tk.Text(frame, height=8, wrap="none",
                               bg="#111318", fg="#c8cdd4",
                               insertbackground="#c8cdd4", font=("Consolas", 9))
        self.log_txt.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.log_txt.yview)
        sb.pack(side="right", fill="y")
        self.log_txt.configure(yscrollcommand=sb.set)
        self.log_txt.tag_configure("ok", foreground="#5fd38d")
        self.log_txt.tag_configure("warn", foreground="#e3b341")
        self.log_txt.tag_configure("err", foreground="#f26d6d")
        self.log_txt.tag_configure("info", foreground="#8ab4f8")

    def pump_logs(self):
        for stamp, level, msg in self.engine.drain_logs():
            self.log_txt.insert("end", f"[{stamp}] {msg}\n", level)
            self.log_txt.see("end")
        self.root.after(200, self.pump_logs)

    # ---------------------------------------------------------------- actions
    def _app_tick(self):
        """每 5 秒刷新一次程序下拉框，让新启动的游戏自动出现。"""
        try:
            # 只在用户没在输入时刷新，避免打断
            if self.cb_app.focus_get() != self.cb_app:
                keep = self.v_app.get()
                self.refresh_app_list(keep_text=True)
                if keep and keep in self._app_map:
                    self.v_app.set(keep)
                self._sync_exe_combo()
        except Exception:
            pass
        self.root.after(5000, self._app_tick)

    def _sync_exe_combo(self):
        """让「进程名」下拉框也列出可选程序，方便手选。"""
        try:
            vals = [a["exe"] for a in self._app_list]
            cur = self.v_exe.get()
            if cur and cur not in vals:
                vals = [cur] + vals
            self.cb_exe["values"] = vals
        except Exception:
            pass

    def restart_as_admin(self):
        """保存后以管理员身份重启自身。"""
        self.engine.save()
        code = ELEV.relaunch_as_admin()
        if code > 32:
            self.engine.log("正在以管理员身份重启...", "ok")
            self.root.after(300, self.on_close)
        else:
            messagebox.showwarning(
                "提权未完成",
                f"ShellExecuteW 返回 {code}。\n\n"
                "1223 表示你在 UAC 弹窗点了「否」。\n"
                "也可以手动右键 run.bat -> 以管理员身份运行。")

    def _apply_autorun(self):
        if self.var_autorun.get():
            self.engine.set_running(True)
            self._sync_state()

    def toggle_run(self):
        """启动/暂停总开关。

        启动前先自动应用表单里未保存的修改。
        否则用户填完信息直接点启动会「毫无反应」——引擎读的是旧配置，
        这是最容易踩的坑（已写成回归测试 test_run_flow.py）。
        """
        if not self.engine.running:
            self._auto_apply_form()
            # 没有任务或没有选中任务时，明确告诉用户该做什么
            if not self.engine.targets:
                self.engine.log("还没有任务。先点「＋ 新建任务」", "warn")
                return
            if self.sel < 0:
                self.engine.log(
                    "提示：先在左侧列表点选一条任务并填好，再启动。"
                    "已保存的任务会照常运行", "info")
        self.engine.set_running(not self.engine.running)
        self._sync_state()
        if self.engine.running:
            self.engine.rescan(force=True)
            n = sum(1 for i in self.engine.instances if i.alive)
            if n == 0:
                self.engine.log(
                    "已启动，但当前没有匹配到任何窗口。"
                    "请检查「选择程序」是否选中了正在运行的程序，"
                    "或点「重扫窗口 (F11)」", "warn")

    def _auto_apply_form(self):
        """无提示地把表单当前内容写回引擎（供启动时调用）。"""
        try:
            if self.sel < 0 or self.sel >= len(self.engine.targets):
                return
            t = self.engine.targets[self.sel]
            # 复用校验逻辑，但用静默版本避免弹窗打断启动
            import copy
            probe = copy.copy(t)
            name = self.v_name.get().strip()
            if name:
                probe.name = name
            probe.title_sub = self.v_title.get().strip()
            probe.exe_sub = self.v_exe.get().strip()
            key = self.v_key.get().strip().lower()
            if key:
                W.vk_from_name(key)          # 校验，非法则抛异常被下面捕获
                probe.key = key
            probe.interval_sec = max(0.5, float(self.v_interval.get() or 300))
            probe.jitter_pct = float(self.v_jitter.get() or 0)
            probe.hold_ms = max(0, int(float(self.v_hold.get() or 40)))
            probe.method = self.v_method.get() or "both"
            probe.hotkey = self.v_hotkey.get().strip()
            probe.auto_discover = bool(self.v_auto.get())
            probe.enabled = bool(self.v_enabled.get())
            # 校验通过才写回
            for k, v in probe.__dict__.items():
                setattr(t, k, v)
            self.engine.save()
            self.refresh_tasks()
        except Exception as exc:
            self.engine.log(f"表单内容未保存（{exc}），沿用上次配置", "warn")

    def stop_all(self):
        self.engine.set_running(False)
        self._sync_state()

    def _sync_state(self):
        on = self.engine.running
        self.btn_run.configure(text="⏸ 暂停 (F9)" if on else "▶ 启动 (F9)")
        self.lbl_state.configure(text="● 运行中" if on else "● 待机",
                                 foreground="#5fd38d" if on else "#8a8f98")

    def new_task(self):
        self.engine.targets.append(Target(name=f"任务{len(self.engine.targets)+1}"))
        self.engine.save()
        self.refresh_tasks()
        self.tree.selection_set(self.tree.get_children()[-1])

    def on_select(self, _e=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        if idx >= len(self.engine.targets):
            return
        self.sel = idx
        t = self.engine.targets[idx]
        self.v_name.set(t.name)
        self.v_title.set(t.title_sub)
        self.v_exe.set(t.exe_sub)
        self.v_key.set(t.key)
        self.v_interval.set(str(t.interval_sec))
        self.v_jitter.set(str(t.jitter_pct))
        self.v_hold.set(str(t.hold_ms))
        self.v_method.set(t.method)
        self.v_hotkey.set(t.hotkey)
        self.v_auto.set(t.auto_discover)
        self.v_enabled.set(t.enabled)
        # 同步程序下拉框：按 exe 反查显示文本，找不到就清空
        picked = ""
        for disp, exe in self._app_map.items():
            if exe == t.exe_sub:
                picked = disp
                break
        self.v_app.set(picked)
        self._hint_matched()

    def _form_to_target(self) -> Target | None:
        if self.sel < 0 or self.sel >= len(self.engine.targets):
            messagebox.showwarning("提示", "先在左侧列表选中一条任务")
            return None
        try:
            W.vk_from_name(self.v_key.get())
        except ValueError:
            messagebox.showerror("按键无效", f"无法识别按键: {self.v_key.get()!r}\n"
                                          "可用: space / enter / a-z / 0-9 / f1-f12 / numpad0-9 / 0x20")
            return None
        try:
            interval = float(self.v_interval.get())
            jitter = float(self.v_jitter.get())
            hold = int(float(self.v_hold.get()))
            if interval < 0.5:
                raise ValueError("间隔不能小于 0.5 秒")
            if not (0 <= jitter <= 90):
                raise ValueError("抖动范围 0-90")
            if not (0 <= hold <= 2000):
                raise ValueError("保持时长 0-2000ms")
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return None
        t = self.engine.targets[self.sel]
        t.name = self.v_name.get().strip() or "未命名"
        t.title_sub = self.v_title.get().strip()
        t.exe_sub = self.v_exe.get().strip()
        t.key = self.v_key.get().strip().lower()
        t.interval_sec = interval
        t.jitter_pct = jitter
        t.hold_ms = hold
        t.method = self.v_method.get()
        t.hotkey = self.v_hotkey.get().strip()
        t.auto_discover = bool(self.v_auto.get())
        t.enabled = bool(self.v_enabled.get())
        return t

    def save_task(self):
        if self._form_to_target() is None:
            return
        self.engine.save()
        self.engine.rescan(force=True)
        self.refresh_tasks()
        self.engine.log("任务已保存", "ok")

    def test_task(self):
        t = self._form_to_target()
        if not t:
            return
        hits = W.find_windows(t.title_sub, t.exe_sub, include_hidden=True)
        if not hits:
            messagebox.showinfo("测试", "没有匹配到窗口。\n请检查窗口标题关键字或进程名。")
            return
        from . import inject
        vk = t.vk()
        lines = []
        for w in hits[:8]:
            r = inject.press(w["hwnd"], vk, t.method, t.hold_ms)
            lines.append(f"{r['ok'] and '✔' or '✘'} {w['title'][:28]} ({w['exe']}) via={r['via']}")
        messagebox.showinfo("测试结果", "\n".join(lines))
        self.engine.log(f"测试按键 {t.key} 命中 {len(hits)} 窗口", "info")

    def del_task(self):
        """删除选中的任务。

        两个必须处理的点（曾经都出错）：
          1) 索引要在改动列表**之前**保存下来，否则过滤条件失效
          2) 删除后所有大于被删索引的 target_idx 都要左移 1，
             否则实例会被错配到别的任务，按错任务的按键
        """
        if self.sel < 0 or self.sel >= len(self.engine.targets):
            return
        target = self.engine.targets[self.sel]
        if not messagebox.askyesno(
                "确认删除",
                f"删除任务「{target.name}」？\n\n"
                f"匹配规则：{target.exe_sub or '-'} / {target.title_sub or '-'}\n\n"
                "该任务正在控制的窗口会立即脱管（其它任务不受影响）。"):
            return

        removed = self.sel                       # 先记住，后面 self.sel 会被重置
        del self.engine.targets[removed]

        # 清理该任务的实例，并把后面任务的索引左移
        kept = []
        for inst in self.engine.instances:
            if inst.target_idx == removed:
                continue                          # 被删任务的实例直接丢弃
            if inst.target_idx > removed:
                inst.target_idx -= 1              # 后面的整体前移
            kept.append(inst)
        self.engine.instances = kept

        self.sel = -1
        self.engine.save()
        self.refresh_tasks()
        self.engine.rescan(force=True)
        self.engine.log(f"已删除任务「{target.name}」", "ok")

    def probe_windows(self):
        """列出当前所有可见窗口，方便抄标题/进程名。"""
        ws = W.list_windows()
        top = tk.Toplevel(self.root)
        top.title("窗口探测 · 双击填入")
        top.geometry("900x520")
        t = ttk.Treeview(top, columns=("title", "exe", "pid", "cls"),
                         show="headings")
        for c, w, txt in (("title", 420, "标题"), ("exe", 160, "进程"),
                          ("pid", 70, "PID"), ("cls", 220, "窗口类")):
            t.heading(c, text=txt)
            t.column(c, width=w, anchor="w")
        for w in ws:
            t.insert("", "end", values=(w["title"][:90], w["exe"], w["pid"], w["cls"]))
        t.pack(fill="both", expand=True)

        def _fill(_e=None):
            sel = t.selection()
            if not sel:
                return
            vals = t.item(sel[0], "values")
            self.v_exe.set(vals[1])
            self.v_title.set(vals[0][:16])
            if not self.v_name.get() or self.v_name.get().startswith("任务"):
                self.v_name.set(vals[1].rsplit(".", 1)[0] or vals[0][:12])
            top.destroy()
        t.bind("<Double-1>", _fill)

    # ---------------------------------------------------------------- refresh
    def refresh_tasks(self):
        self.tree.delete(*self.tree.get_children())
        for t in self.engine.targets:
            rule = " / ".join(x for x in (t.exe_sub, t.title_sub) if x) or "未设置"
            self.tree.insert("", "end", values=(
                t.name, rule, t.key, f"{t.interval_sec:g}", t.method,
                "启用" if t.enabled else "禁用"))

    def refresh_instances(self):
        snap = self.engine.snapshot()
        self.itree.delete(*self.itree.get_children())
        for i in snap["instances"]:
            eta = "—" if i["alive"] is False else f'{i["eta"]:.1f}'
            self.itree.insert("", "end", values=(
                i["target"], i["title"][:60], i["exe"], i["pid"], eta,
                i["count"], i["via"], "在线" if i["alive"] else "掉线"))
        self.lbl_count.configure(text=f'接管 {sum(1 for i in snap["instances"] if i["alive"])} 窗口')
        self._sync_state()
        # 热键可能改了引擎状态，按钮文案要跟着变
        self.btn_run.configure(
            text="⏸ 暂停 (F9)" if self.engine.running else "▶ 启动 (F9)")
        self.root.after(500, self.refresh_instances)

    # ---------------------------------------------------------------- close
    def on_close(self):
        """点窗口 X：默认收进托盘而不是退出。

        这是用户明确要求的：关掉窗口后程序继续在后台跑，
        需要真退出时用托盘右键菜单的「退出程序」。
        """
        if self._really_quit:
            self._do_quit()
            return
        if self.var_tray.get():
            self.hide_to_tray()
        else:
            # 没勾"关闭时最小化到托盘" -> 直接退出，但先确认
            if messagebox.askyesno(
                    "确认退出",
                    "关闭后程序将停止工作。\n\n"
                    "如果想让它在后台继续运行，请勾选「关闭时最小化到托盘」。\n\n"
                    "确定退出吗？"):
                self._do_quit()

    def hide_to_tray(self):
        """隐藏主窗口，保留托盘图标，引擎继续运行。"""
        try:
            self.root.withdraw()
        except Exception:
            pass
        self.hidden_to_tray = True
        if self.tray and self.tray.is_visible():
            self.tray.notify(
                "已最小化到托盘",
                "程序仍在后台运行。双击托盘图标可恢复窗口。")
            self.tray._refresh()
        self.engine.log("窗口已收进托盘，后台继续运行", "ok")

    def show_from_tray(self):
        """从托盘恢复主窗口。"""
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            # 抢一次前台，否则窗口可能在其它窗口后面
            hwnd = int(self.root.winfo_id())
            while hwnd:
                parent = W.user32.GetParent(hwnd)
                if not parent:
                    break
                hwnd = int(parent)
            W.user32.ShowWindow(hwnd, 9)      # SW_RESTORE
            W.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass
        self.hidden_to_tray = False
        self.engine.log("已从托盘恢复窗口", "info")

    def _do_quit(self):
        """真正退出：移除托盘图标、停止引擎、销毁窗口。"""
        self._really_quit = True
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        try:
            self.engine.shutdown()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def _init_tray(self):
        """创建托盘图标并绑定回调。"""
        # 打包后 assets 在 _MEIPASS 里，源码运行时在项目根，paths 模块负责区分
        icon = PATHS.resource_path("assets", "tray.ico")
        self.tray = TRAY.TrayIcon(
            "山海寻灵 · 防AFK控制器", icon,
            {
                "on_show": lambda: self.root.after(0, self.show_from_tray),
                "on_toggle": lambda: self.root.after(0, self._tray_toggle),
                "on_stopall": lambda: self.root.after(0, self._tray_stopall),
                "on_exit": lambda: self.root.after(0, self._tray_exit),
                "get_state": self._tray_state,
            })
        if self.tray.start(timeout=4.0):
            self.engine.log("托盘图标已就绪（关闭窗口会收进托盘）", "info")
        else:
            self.engine.log("托盘图标创建失败，关闭窗口将直接退出", "warn")
            self.var_tray.set(False)

    def _tray_state(self) -> dict:
        try:
            snap = self.engine.snapshot()
            alive = sum(1 for i in snap["instances"] if i["alive"])
        except Exception:
            alive = 0
        return {"running": self.engine.running, "count": alive}

    def _tray_toggle(self):
        if not self.engine.running:
            self._auto_apply_form()
        self.engine.set_running(not self.engine.running)
        self._sync_state()
        if self.tray:
            self.tray._refresh()

    def _tray_stopall(self):
        self.engine.set_running(False)
        self._sync_state()
        if self.tray:
            self.tray._refresh()

    def _tray_exit(self):
        self._do_quit()


def run():
    root = tk.Tk()
    # config 必须落在 exe 所在目录（打包后 _MEIPASS 是临时解压目录，
    # 写进去进程退出就丢），paths.app_path 负责这个区分。
    cfg = PATHS.app_path("config", "targets.json")
    eng = Engine(cfg)
    app = App(root, eng)
    root.mainloop()

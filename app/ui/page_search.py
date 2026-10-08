# -*- coding: utf-8 -*-
"""F5 关键词检索页：双引擎 + 多关键词并发 + 树形汇总（52+ 关键词规模）。"""
import os
import subprocess
import time
import tkinter as tk

import customtkinter as ctk

from core import content_search as cs
from core import everything as ev
from core.config import save_config
from core.util import delete_to_recycle, human_size
from ui import theme
from ui.components import CheckableTree, make_tree

CATEGORIES = [
    ("文档", {"doc", "docx", "xls", "xlsx", "ppt", "pptx", "pdf", "wps", "et", "dps",
             "txt", "csv", "md", "rtf", "ofd"}),
    ("图片", {"jpg", "jpeg", "png", "gif", "bmp", "webp", "tif", "tiff"}),
    ("视频", {"mp4", "avi", "mkv", "mov", "flv", "wmv", "ts", "rmvb"}),
    ("音频", {"mp3", "wav", "flac", "m4a", "wma"}),
    ("压缩包", {"zip", "rar", "7z", "tar", "gz", "iso"}),
    ("安装包", {"exe", "msi", "apk", "bat"}),
]

COLS = [("chk", "✔"), ("cat", "分类"), ("name", "名称"), ("size", "大小"),
        ("mtime", "修改日期"), ("frag", "命中片段"), ("path", "路径")]
WIDTHS = {"chk": 44, "cat": 76, "name": 190, "size": 78,
          "mtime": 128, "frag": 300, "path": 250}

FRAG_PER_GROUP = 6    # 每个关键词组最多取回的命中片段数
FRAG_TOTAL = 150      # 片段总量上限
CHIPS_COLS = 4        # 关键词小方框每行列数


def categorize(path):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    for cat, exts in CATEGORIES:
        if ext in exts:
            return cat
    return "其他"


class SearchPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.ct = None            # 汇总树
        self.chip_vars = {}       # kw -> {"btn":, "on": bool}
        self._build()

    # ================= 布局 =================
    def _build(self):
        left = ctk.CTkFrame(self, width=330, fg_color=theme.CARD, corner_radius=10,
                            border_width=1, border_color=theme.BORDER)
        left.pack(side="left", fill="y", padx=(10, 6), pady=10)
        left.pack_propagate(False)

        ctk.CTkLabel(left, text="搜索引擎", font=(theme.FONT, 13, "bold"),
                     text_color=theme.TEXT, anchor="w").pack(
            anchor="w", padx=6, pady=(10, 4))
        eng_row = ctk.CTkFrame(left, fg_color="transparent")
        eng_row.pack(fill="x", padx=6)
        self.engine_btns = {}
        for name, key in (("Everything", "everything"), ("AnyTXT", "anytxt")):
            b = ctk.CTkButton(eng_row, text=name, height=32, corner_radius=6,
                              font=(theme.FONT, 12, "bold"),
                              command=lambda k=key: self._set_engine(k))
            b.pack(side="left", fill="x", expand=True,
                   padx=(0, 6) if key == "everything" else 0)
            self.engine_btns[key] = b
        self._paint_engine()
        ctk.CTkLabel(left, text="AnyTXT：搜文档内容（.doc/.wps/OFD/扫描件等），首次使用需安装官方组件。",
                     font=(theme.FONT, 11), text_color=theme.MUTED,
                     wraplength=300, justify="left").pack(anchor="w", padx=6, pady=(4, 6))

        ctk.CTkButton(left, text="检索全部关键词（并发）", height=38,
                      fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER,
                      font=(theme.FONT, 13, "bold"),
                      command=self.search_all).pack(fill="x", padx=6, pady=(2, 6))

        # ---- 关键词区：流式小方框（chips）----
        kwhead = ctk.CTkFrame(left, fg_color="transparent")
        kwhead.pack(fill="x", padx=6, pady=(2, 2))
        ctk.CTkLabel(kwhead, text="关键词", font=(theme.FONT, 13, "bold"),
                     text_color=theme.TEXT, anchor="w").pack(side="left")
        self.kw_count = ctk.CTkLabel(kwhead, text="", font=(theme.FONT, 11),
                                     text_color=theme.MUTED)
        self.kw_count.pack(side="left", padx=8)
        ctk.CTkButton(kwhead, text="删除所选词", width=84, height=22,
                      fg_color=theme.DANGER, hover_color=theme.DANGER_HOVER,
                      font=(theme.FONT, 11), command=self._del_selected_kw
                      ).pack(side="right")
        ctk.CTkButton(kwhead, text="全选/全不选", width=88, height=22,
                      fg_color="#eceff4", text_color=theme.TEXT,
                      hover_color="#dde3ec", font=(theme.FONT, 11),
                      command=self._toggle_all_chips).pack(side="right", padx=6)

        self.chips_box = ctk.CTkScrollableFrame(left, height=210,
                                                fg_color="#fbfcfe")
        self.chips_box.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        ctk.CTkButton(left, text="删除勾选关键词的命中文档", height=28,
                      fg_color=theme.DANGER, hover_color=theme.DANGER_HOVER,
                      font=(theme.FONT, 12, "bold"),
                      command=self._delete_kw_hits).pack(fill="x", padx=6, pady=(0, 6))

        row = ctk.CTkFrame(left, fg_color="transparent")
        row.pack(fill="x", padx=6, pady=(0, 6))
        self.kw_entry = ctk.CTkEntry(row, placeholder_text="新增关键词，回车或点添加")
        self.kw_entry.pack(side="left", fill="x", expand=True)
        self.kw_entry.bind("<Return>", lambda e: self._add_kw())
        ctk.CTkButton(row, text="添加", width=56, height=26,
                      fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER,
                      command=self._add_kw).pack(side="left", padx=(6, 0))

        self.status = ctk.CTkLabel(left, text="就绪", font=(theme.FONT, 12),
                                   text_color=theme.PRIMARY, wraplength=300,
                                   anchor="w", justify="left")
        self.status.pack(anchor="w", padx=6, pady=(0, 8))

        # ---- 右侧：树形汇总结果 ----
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, pady=10, padx=(0, 10))
        bar = ctk.CTkFrame(right, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(bar, text="检索结果（点击关键词行展开/折叠，勾选首列后批量删除）",
                     font=(theme.FONT, 12, "bold"), text_color=theme.TEXT
                     ).pack(side="left")
        ctk.CTkButton(bar, text="全选 / 全不选", width=110, fg_color="#eceff4",
                      text_color=theme.TEXT, hover_color="#dde3ec",
                      command=self._toggle_all).pack(side="right")
        ctk.CTkButton(bar, text="删除勾选项", width=110, fg_color=theme.DANGER,
                      hover_color=theme.DANGER_HOVER,
                      command=self._delete_checked).pack(side="right", padx=8)
        self.result_hint = ctk.CTkLabel(bar, text="", font=(theme.FONT, 12),
                                        text_color=theme.MUTED)
        self.result_hint.pack(side="right", padx=8)

        wrap, tree = make_tree(right, COLS, WIDTHS, height=20)
        wrap.pack(fill="both", expand=True)
        self.ct = CheckableTree(tree, on_change=self._update_checked_hint)
        tree.bind("<Double-1>", self._on_double_click)
        tree.bind("<Button-3>", self._on_right_click)
        tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._reload_chips()

    # ---- 结果行交互：双击打开 / 右键菜单 / 已删除行保持灰显 ----
    def _row_path(self, iid):
        payload = self.ct.payload.get(iid)
        return payload if isinstance(payload, str) else None

    def _on_tree_select(self, _event=None):
        """已删除行被选中时立即取消选中，保持灰显（不再高亮误导）。"""
        tree = self.ct.tree
        for iid in tree.selection():
            if tree.item(iid, "tags") == ("deleted",):
                tree.selection_remove(iid)

    def _on_double_click(self, _event=None):
        iid = self.ct.tree.focus()
        path = self._row_path(iid)
        if path and os.path.exists(path) and self.ct.tree.item(iid, "tags") != ("deleted",):
            self._open_path(path)

    def _on_right_click(self, event):
        tree = self.ct.tree
        iid = tree.identify_row(event.y)
        if not iid:
            return
        tree.selection_set(iid)
        path = self._row_path(iid)
        if not path:
            return
        import tkinter as tk
        menu = tk.Menu(self, tearoff=0)
        deleted = tree.item(iid, "tags") == ("deleted",)
        state = "disabled" if deleted else "normal"
        menu.add_command(label="打开文件", state=state,
                         command=lambda: self._open_path(path))
        menu.add_command(label="打开所在文件夹", state=state,
                         command=lambda: self._open_folder(path))
        menu.add_separator()
        menu.add_command(label="复制完整路径",
                         command=lambda: self._copy_path(path))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _open_path(self, path):
        try:
            os.startfile(path)  # noqa
            self.app.logger.log(f"已打开文件：{path}")
        except Exception as e:
            self.app.logger.log(f"打开失败：{e}")

    def _open_folder(self, path):
        try:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            self.app.logger.log(f"已在资源管理器中定位：{path}")
        except Exception as e:
            self.app.logger.log(f"打开文件夹失败：{e}")

    def _copy_path(self, path):
        self.app.clipboard_clear()
        self.app.clipboard_append(path)
        self.status.configure(text="已复制完整路径")

    # ---- 关键词 chips ----
    def _reload_chips(self):
        for w in self.chips_box.winfo_children():
            w.destroy()
        self.chip_vars = {}
        kws = [k for k in self.app.cfg.get("search_keywords", []) if k.strip()]
        for i, kw in enumerate(kws):
            self._add_chip_widget(kw, i)
        for c in range(CHIPS_COLS):
            self.chips_box.grid_columnconfigure(c, weight=1)
        self.kw_count.configure(text=f"共 {len(kws)} 个")

    def _add_chip_widget(self, kw, index):
        btn = ctk.CTkButton(
            self.chips_box, text=kw, height=24, corner_radius=6,
            font=(theme.FONT, 11), fg_color="#eceff4", text_color=theme.TEXT,
            hover_color="#cfe0f2",
            command=lambda k=kw: self._toggle_chip(k))
        btn.grid(row=index // CHIPS_COLS, column=index % CHIPS_COLS,
                 padx=3, pady=3, sticky="ew")
        self.chip_vars[kw] = {"btn": btn, "on": False}

    def _toggle_all_chips(self):
        """关键词一键全选/全不选（便于批量删除）。"""
        if not self.chip_vars:
            return
        target = not all(st["on"] for st in self.chip_vars.values())
        for st in self.chip_vars.values():
            if st["on"] != target:
                st["on"] = target
                if target:
                    st["btn"].configure(fg_color=theme.PRIMARY,
                                        text_color="#ffffff",
                                        hover_color=theme.PRIMARY_HOVER)
                else:
                    st["btn"].configure(fg_color="#eceff4",
                                        text_color=theme.TEXT,
                                        hover_color="#dde3ec")
        n = len(self.chip_vars) if target else 0
        self.status.configure(text=f"已选中 {n} 个关键词" + ("（点删除所选词批量移除）" if target else ""))

    def _toggle_chip(self, kw):
        st = self.chip_vars.get(kw)
        if not st:
            return
        st["on"] = not st["on"]
        if st["on"]:
            st["btn"].configure(fg_color=theme.PRIMARY, text_color="#ffffff",
                                hover_color=theme.PRIMARY_HOVER)
        else:
            st["btn"].configure(fg_color="#eceff4", text_color=theme.TEXT,
                                hover_color="#dde3ec")

    def _regrid_chips(self):
        """按配置顺序重排关键词方框位置（原地移动，不重建控件）。

        增量删除后只需重排，避免整区重建造成闪烁与选中态丢失。
        """
        order = [k for k in self.app.cfg.get("search_keywords", [])
                 if k in self.chip_vars]
        for c in range(CHIPS_COLS):
            self.chips_box.grid_columnconfigure(c, weight=1)
        for i, kw in enumerate(order):
            self.chip_vars[kw]["btn"].grid(
                row=i // CHIPS_COLS, column=i % CHIPS_COLS,
                padx=3, pady=3, sticky="ew")

    def _del_selected_kw(self):
        kws = self.app.cfg.get("search_keywords", [])
        picked = [k for k, st in self.chip_vars.items() if st["on"]]
        if not picked:
            self.status.configure(text="请先点击关键词小方框选中（变蓝）再删除")
            return
        # 防误删确认（两键：确认删除 / 取消）
        preview = "、".join(picked[:20]) + ("…" if len(picked) > 20 else "")
        if not self.app.confirm_danger("删除关键词确认", [
                f"将删除 {len(picked)} 个关键词：{preview}",
                "删除后这些词不再参与检索，其结果也不会再出现在结果区。",
                "删除仅影响关键词列表（不改动磁盘上的任何文件）。",
                "如需找回：同目录 config.json.bak 为上一版备份，或重启本软件按提示一键恢复。"]):
            return
        remain = [k for k in kws if k not in picked]
        self.app.cfg["search_keywords"] = remain
        save_config(self.app.cfg)
        shown = "、".join(picked[:10]) + ("…" if len(picked) > 10 else "")
        self.app.logger.log(f"已删除检索关键词 {len(picked)} 个：{shown}"
                            + (f"（剩余 {len(remain)} 个）" if remain else "（已清空）"))
        # 增量移除：只销毁被删方框，其余控件原地保留
        for kw in picked:
            st = self.chip_vars.pop(kw, None)
            if st:
                st["btn"].destroy()
        self._regrid_chips()
        self.kw_count.configure(text=f"共 {len(remain)} 个")
        self.status.configure(text=f"已删除 {len(picked)} 个关键词，剩余 {len(remain)} 个")

    def _add_kw(self):
        v = self.kw_entry.get().strip()
        kws = self.app.cfg.get("search_keywords", [])
        if v and v not in kws:
            kws.append(v)
            self.app.cfg["search_keywords"] = kws
            save_config(self.app.cfg)
            self.app.logger.log(f"已添加检索关键词：{v}")
            self._add_chip_widget(v, len(kws) - 1)   # 增量插入，不重建其余词
            self.kw_count.configure(text=f"共 {len(kws)} 个")
        self.kw_entry.delete(0, tk.END)

    # ---- 引擎 ----
    def _engine_key(self):
        return self.app.cfg.get("search_engine", "everything")

    def _paint_engine(self):
        """选中=蓝底白字，未选=灰底黑字。"""
        cur = self._engine_key()
        for key, b in self.engine_btns.items():
            if key == cur:
                b.configure(fg_color=theme.PRIMARY,
                            hover_color=theme.PRIMARY_HOVER,
                            text_color="#ffffff")
            else:
                b.configure(fg_color="#eceff4",
                            hover_color="#dde3ec",
                            text_color=theme.TEXT)

    def _set_engine(self, key):
        self.app.cfg["search_engine"] = key
        save_config(self.app.cfg)
        self._paint_engine()
        if key == "anytxt" and not cs.anytxt_installed():
            self._offer_install()

    def _offer_install(self):
        """未安装 AnyTXT：引导用单位配发安装包静默安装。"""
        pkg = cs.installer_path()
        if not pkg:
            from tkinter import filedialog
            self.status.configure(text="未找到 AnyTXT 安装包，请选择安装包文件")
            self.app.logger.log("未在本软件目录找到 Anytxt 安装包，请手动选择单位配发的安装包")
            pkg = filedialog.askopenfilename(
                title="选择单位配发的 Anytxt 安装包（Anytxt_*Windows*.exe）",
                filetypes=[("Anytxt 安装包", "Anytxt*.exe"), ("所有文件", "*.exe")],
                parent=self)
            if not pkg:
                self.status.configure(text="已取消：未选择 AnyTXT 安装包")
                self.app.cfg["search_engine"] = "everything"
                save_config(self.app.cfg)
                self._paint_engine()
                return
        detail = (f"将静默安装官方内容搜索引擎 AnyTXT（CBEWIN 出品，单位配发软件，"
                  f"安装包 {human_size(os.path.getsize(pkg))}）。\n\n"
                  "说明：\n"
                  "  · 安装完成后首次需在全盘建立内容索引（后台自动，视文件量约几分钟到更久）\n"
                  "  · 引擎作为后台服务运行，本软件界面内直接出结果\n"
                  "  · 原样安装官方组件，不做任何修改\n\n"
                  "是否现在安装？")
        if not self.app.confirm(detail):
            self.app.cfg["search_engine"] = "everything"
            save_config(self.app.cfg)
            self._paint_engine()
            return
        self.status.configure(text="AnyTXT 安装中（约1-2分钟），请稍候...")
        self.app.run_bg(lambda: cs.install_anytxt(pkg),
                        on_done=self._after_install,
                        on_error=self._install_error)

    def _after_install(self, ready):
        self.status.configure(text="AnyTXT 安装完成，引擎就绪，可开始检索" if ready
                              else "AnyTXT 已安装，索引后台建立中；检索时自动重试")

    def _install_error(self, e):
        self.status.configure(text=f"AnyTXT 安装失败：{e}")
        self.app.cfg["search_engine"] = "everything"
        save_config(self.app.cfg)
        self._paint_engine()

    # ---- 检索 ----
    def search_all(self):
        kws = [k for k in self.app.cfg.get("search_keywords", []) if k.strip()]
        if not kws:
            self.status.configure(text="请先添加关键词")
            return
        engine = self._engine_key()
        if engine == "anytxt":
            if not cs.anytxt_installed():
                self._offer_install()
                if not cs.anytxt_installed():
                    return
            self.status.configure(text="AnyTXT 并发检索中（含引擎启动）...")
        else:
            n = len(kws)
            self.status.configure(text=f"并发检索中 0/{n} 个关键词（引擎就绪检测中）...")

        def progress(done, total):
            self.app.post(lambda d=done, t=total: self.status.configure(
                text=f"并发检索中 {d}/{t} 个关键词..."))

        if engine == "anytxt":
            def progress_ui(msg):
                self.app.post(lambda m=msg: self.status.configure(text=m))

            def fn():
                if not cs.ensure_running(timeout=300, log=self.app.logger.log,
                                         progress=progress_ui):
                    self.app.logger.log("AnyTXT 引擎未就绪（等待超时），请稍后重试检索")
                    return {}
                return cs.search_all(kws, self.app.cfg.get("search_max_results", 3000),
                                     progress=progress, log=self.app.logger.log)
        else:
            fn = lambda: ev.search_all(kws, self.app.cfg.get("search_max_results", 3000),
                                       progress=progress, log=self.app.logger.log)
        self.app.run_bg(fn, lambda res: self._after_search(engine, res),
                        on_error=self._search_error)

    def _search_error(self, e):
        self.status.configure(text=f"检索失败：{e}", text_color=theme.DANGER)
        self.app.logger.log(f"[检索失败] {e}")

    def _after_search(self, engine, res_map):
        ct = self.ct
        ct.clear()
        self._group_of_kw = {}   # kw -> 组头 iid（按关键词批量删除用）
        frag_jobs = []           # (kw, iid, path, fid)
        frag_group_count = {}    # kw -> 已入队片段数（每组上限 FRAG_PER_GROUP）
        total_files = 0
        for kw in self.app.cfg.get("search_keywords", []):
            rows = res_map.get(kw, [])
            entries, seen = [], set()
            for p, size, mt, fid in [(r if isinstance(r, tuple) else (r, None, None, None))
                                     for r in rows]:
                if not p or p in seen or not os.path.exists(p):
                    continue
                seen.add(p)
                if not size or not mt:
                    try:
                        st = os.stat(p)
                        size, mt = st.st_size, st.st_mtime
                    except OSError:
                        size, mt = size or 0, mt or 0
                entries.append((p, size, mt, fid))
            entries.sort(key=lambda e: -e[1])
            gsize = sum(e[1] for e in entries)
            head = ct.add_group(
                ("组", kw, human_size(gsize), "", f"{len(entries)} 项", ""),
                tags=() if entries else ("empty",))
            self._group_of_kw[kw] = head
            for ridx, (p, size, mt, fid) in enumerate(entries):
                cat = "文档内容" if engine == "anytxt" else categorize(p)
                if p in self.app.deleted_paths:
                    tag = ("deleted",)
                else:
                    tag = ("odd",) if ridx % 2 else ()
                iid = ct.add_child(
                    head,
                    (cat, os.path.basename(p), human_size(size),
                     time.strftime("%Y-%m-%d %H:%M", time.localtime(mt)) if mt else "-",
                     "", p),
                    payload=p, tags=tag)
                total_files += 1
                if engine == "anytxt" and fid and len(frag_jobs) < FRAG_TOTAL:
                    gcount = frag_group_count.get(kw, 0)
                    if gcount < FRAG_PER_GROUP:      # 每组限流，防单组占满配额
                        frag_group_count[kw] = gcount + 1
                        frag_jobs.append((kw, iid, p, fid))
        for iid in ct.children:
            ct.tree.item(iid, open=False)
        scope = ""
        if engine == "anytxt":
            try:
                from core.util import drive_scope
                scope = "、".join(drive_scope()[0])
            except Exception:
                scope = ""
        self.result_hint.configure(
            text=f"{len(res_map)} 个关键词 / 命中 {total_files} 项 / 引擎:"
                 f"{'AnyTXT 文档内容' if engine=='anytxt' else 'Everything 文件名'}"
                 + (f" / 检索范围 {scope}" if scope else ""))
        self.status.configure(
            text=f"检索完成：{len(res_map)} 个关键词，共命中 {total_files} 项"
                 + ("（点击关键词行展开明细）" if total_files else ""))
        if frag_jobs:
            self.app.run_bg(lambda: self._fetch_frags(frag_jobs), None)

    def _fetch_frags(self, jobs):
        done = 0
        for kw, iid, path, fid in jobs:
            if done >= FRAG_TOTAL:
                break
            frag = cs.anytxt_fragment(fid, kw)
            done += 1
            if frag:
                self.app.post(lambda i=iid, f=frag: self._set_frag(i, f))

    def _set_frag(self, iid, frag):
        if not self.ct.tree.exists(iid):
            return
        frag = frag.replace("\r", " ").replace("\n", " ").strip()
        vals = list(self.ct.tree.item(iid, "values"))
        if len(vals) >= 6:
            vals[5] = frag[:120]
            self.ct.tree.item(iid, values=vals)

    # ---- 删除 ----
    def _toggle_all(self):
        self.ct.check_all(not self.ct.all_checked())

    def _delete_kw_hits(self):
        """按关键词批量删除：勾选（变蓝）的关键词方框 → 自动全选其命中文件 →
        走统一的确认弹窗批量删除。"""
        picked = [k for k, st in self.chip_vars.items() if st["on"]]
        if not picked:
            self.status.configure(text="请先点击关键词方框选中（变蓝）")
            return
        if not getattr(self, "_group_of_kw", None):
            self.status.configure(text="请先执行检索，再按关键词批量删除命中文档")
            return
        heads = [self._group_of_kw[k] for k in picked if k in self._group_of_kw]
        if not heads:
            self.status.configure(text="选中的关键词本次检索没有命中结果")
            return
        total = 0
        for h in heads:
            for c in self.ct.children.get(h, []):
                if self.ct.tree.item(c, "tags") != ("deleted",):
                    self.ct.checked[c] = True
                    self.ct._paint(c)
                    total += 1
            self.ct._paint_group(h)
        self.ct._notify()
        if not total:
            self.status.configure(text="选中的关键词当前没有可删除的命中文件")
            return
        self.status.configure(
            text=f"已按 {len(heads)} 个关键词选中 {total} 个命中文件，请确认删除")
        self._delete_checked()

    def _update_checked_hint(self):
        items = self.ct.checked_payloads()
        if not items:
            self.result_hint.configure(text="", text_color=theme.MUTED)
        else:
            size = 0
            for p in items:
                try:
                    size += os.path.getsize(p)
                except OSError:
                    pass
            self.result_hint.configure(
                text=f"已勾选 {len(items)} 项 / {human_size(size)}",
                text_color=theme.TEXT)

    def _delete_checked(self):
        paths = self.ct.checked_payloads()
        if not paths:
            self.status.configure(text="请先在列表首列勾选要删除的项")
            return
        size = 0
        shown = []
        for p in paths:
            try:
                size += os.path.getsize(p)
            except OSError:
                pass
        shown = [os.path.basename(p) for p in paths[:15]]
        lines = [f"将删除以下 {len(paths)} 项（合计 {human_size(size)}），送入回收站：", ""]
        lines += [f"  · {n}" for n in shown]
        if len(paths) > len(shown):
            lines.append(f"  · …… 其余 {len(paths) - len(shown)} 项")
        lines += ["",
                  "可能导致：",
                  "  · 这些文件从原位置消失（回收站可恢复，但若清空回收站则不可找回）",
                  "  · 若为项目过程文件/台账，删除后可能影响后续追溯",
                  "",
                  "请确认这些文件确实不再需要。"]
        if not self.app.confirm_danger("文件删除确认", lines):
            return
        self.status.configure(text="删除中...")
        self.app.run_bg(lambda: delete_to_recycle(paths, self.app.logger.log),
                        lambda res: self._after_delete(paths, res))

    def _after_delete(self, paths, res):
        ok, fail = res
        failed_paths = {f[0] for f in fail} if fail else set()
        ok_paths = [p for p in paths if p not in failed_paths]
        self.app.deleted_paths.update(ok_paths)   # 只标记成功项，失败项保留可重试
        self.app.logger.log(f"删除完成：成功 {ok}/{len(paths)}，失败 {len(fail)}")
        if failed_paths:
            for fp in failed_paths:
                self.app.logger.log(f"  ✗ 删除失败（仍保留在列表中）：{fp}")
        for iid, p in self.ct.payload.items():
            if p in self.app.deleted_paths and iid in self.ct.checked:
                self.ct.mark_deleted(iid)
        tail = f"，失败 {len(fail)} 项已保留可重试" if fail else ""
        self.status.configure(text=f"删除完成（{ok} 项已入回收站{tail}）")
        self._update_checked_hint()

    def _delete_checked_failed_hint(self):
        pass

# -*- coding: utf-8 -*-
"""F4 下载目录管理页（复选框多选 + 批量删除）。"""
import os
import time

import customtkinter as ctk

from core import downloads
from core.config import save_config
from core.util import delete_to_recycle, expand, human_size
from ui import theme
from ui.components import CheckableTree, make_tree

COLS = [("chk", "✔"), ("name", "名称"), ("size", "大小"),
        ("mtime", "修改时间"), ("path", "路径")]
WIDTHS = {"chk": 44, "name": 250, "size": 90, "mtime": 150, "path": 460}


class DownloadsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.entries = []
        self._build()

    def _build(self):
        box, c = theme.card(self, "下载目录管理", subtitle="首列点☑勾选后批量删除，统一送回收站")
        box.pack(fill="both", expand=True)
        top = ctk.CTkFrame(c, fg_color="transparent")
        top.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(top, text="目录：", font=(theme.FONT, 12),
                     text_color=theme.TEXT).pack(side="left")
        self.dirs = self.app.cfg.get("download_dirs", ["%USERPROFILE%\\Downloads"])
        self.combo = ctk.CTkComboBox(top, values=self.dirs, width=380)
        self.combo.set(self.dirs[0] if self.dirs else "")
        self.combo.pack(side="left", padx=6)
        ctk.CTkButton(top, text="新增目录", width=90,
                      fg_color="#eceff4", text_color=theme.TEXT,
                      hover_color="#dde3ec", command=self.add_dir).pack(side="left")
        ctk.CTkButton(top, text="加载列表", width=100,
                      fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER,
                      command=self.load).pack(side="left", padx=8)
        self.rec_var = ctk.StringVar(value="off")
        ctk.CTkCheckBox(top, text="含子目录", variable=self.rec_var,
                        onvalue="on", offvalue="off",
                        font=(theme.FONT, 12)).pack(side="left", padx=4)
        ctk.CTkButton(top, text="打开目录", width=90,
                      fg_color="#eceff4", text_color=theme.TEXT,
                      hover_color="#dde3ec", command=self.open_dir).pack(side="left", padx=4)
        self.summary = ctk.CTkLabel(top, text="", font=(theme.FONT, 12),
                                    text_color=theme.TEXT)
        self.summary.pack(side="right")

        bar = ctk.CTkFrame(c, fg_color="transparent")
        bar.pack(fill="x", pady=2)
        ctk.CTkButton(bar, text="全选 / 全不选", width=110,
                      fg_color="#eceff4", text_color=theme.TEXT,
                      hover_color="#dde3ec", command=self.toggle_all).pack(side="left")
        ctk.CTkButton(bar, text="删除勾选项", width=120, fg_color=theme.DANGER,
                      hover_color=theme.DANGER_HOVER,
                      command=self.delete_checked).pack(side="left", padx=8)
        self.checked_label = ctk.CTkLabel(bar, text="未勾选", font=(theme.FONT, 12),
                                          text_color=theme.MUTED)
        self.checked_label.pack(side="left", padx=8)
        ctk.CTkLabel(bar, text="删除统一送入回收站，可恢复。", font=(theme.FONT, 12),
                     text_color="#8d6e63").pack(side="left")

        wrap, self.tree = make_tree(c, COLS, WIDTHS, height=16)
        wrap.pack(fill="both", expand=True, pady=(4, 0))
        self.ct = CheckableTree(self.tree, on_change=self._update_checked_label)

    def _update_checked_label(self):
        items = self.ct.checked_payloads()
        if not items:
            self.checked_label.configure(text="未勾选", text_color=theme.MUTED)
        else:
            size = sum(e["size"] for e in items if not e["is_dir"])
            self.checked_label.configure(
                text=f"已勾选 {len(items)} 项 / {human_size(size)}",
                text_color=theme.TEXT)

    def add_dir(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(title="选择要管理的目录")
        if d:
            self.combo.set(d)
            if d not in self.dirs:
                self.dirs.append(d)
                self.combo.configure(values=self.dirs)
                self.app.cfg["download_dirs"] = self.dirs
                save_config(self.app.cfg)

    def load(self):
        d = self.combo.get().strip()
        if not d:
            return
        self.summary.configure(text="加载中...")
        rec = self.rec_var.get() == "on"
        self.app.run_bg(lambda: downloads.list_files(d, rec), self._after_load)

    def _after_load(self, entries):
        self.entries = sorted(entries, key=lambda e: -e["size"])
        self.ct.clear()
        for idx, e in enumerate(self.entries):
            tags = ("flag",) if e["is_dir"] else (("odd",) if idx % 2 else ())
            self.ct.insert(
                (e["name"], human_size(e["size"]),
                 time.strftime("%Y-%m-%d %H:%M", time.localtime(e["mtime"])) if e["mtime"] else "-",
                 e["path"]),
                payload=e, tags=tags)
        self.summary.configure(text=downloads.summary(self.entries))
        self._update_checked_label()

    def toggle_all(self):
        self.ct.check_all(not self.ct.all_checked())

    def delete_checked(self):
        items = self.ct.checked_payloads()
        if not items:
            self.app.logger.log("下载目录：请先在列表首列勾选要删除的项")
            return
        paths = [e["path"] for e in items]
        size = sum(e["size"] for e in items if not e["is_dir"])
        lines = [f"将删除以下 {len(paths)} 项（合计 {human_size(size)}），送入回收站：", ""]
        shown = [e["name"] for e in items[:15]]
        lines += [f"  · {n}" for n in shown]
        if len(items) > len(shown):
            lines.append(f"  · …… 其余 {len(items) - len(shown)} 项")
        lines += ["",
                  "可能导致：这些文件从原位置消失（回收站可恢复）。",
                  "请确认不再需要后再执行。"]
        if not self.app.confirm_danger("下载目录删除确认", lines):
            return
        self.app.run_bg(lambda: delete_to_recycle(paths, self.app.logger.log),
                        lambda res: self._after_delete(len(paths), res))

    def _after_delete(self, n, res):
        ok, fail = res
        self.app.logger.log(f"下载目录删除完成：成功 {ok}/{n}，失败 {len(fail)}")
        self.load()

    def open_dir(self):
        d = expand(self.combo.get().strip())
        if os.path.isdir(d):
            os.startfile(d)  # noqa
        else:
            self.app.logger.log(f"目录不存在：{d}")

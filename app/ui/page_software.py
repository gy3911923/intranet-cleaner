# -*- coding: utf-8 -*-
"""F1 软件扫描清理页。"""
import os

import customtkinter as ctk

from core import registry
from core.config import save_config
from core.util import human_size
from ui import theme
from ui.components import KeywordEditor, make_tree

def _safe_kb(v):
    """注册表体积值安全转换（可能是 '1,234' 或非数字）。"""
    try:
        return int(str(v).replace(",", "").strip()) * 1024
    except (TypeError, ValueError):
        return 0


COLS = [("name", "软件名称"), ("version", "版本"), ("publisher", "发布者"),
        ("size", "大小"), ("status", "状态")]
WIDTHS = {"name": 300, "version": 100, "publisher": 190, "size": 90, "status": 110}


class SoftwarePage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.items = []
        self._build()

    def _build(self):
        box, c = theme.card(self, "已安装软件与磁盘概览",
                            subtitle="黑名单命中的软件标红显示")
        box.pack(fill="both", expand=True)
        top = ctk.CTkFrame(c, fg_color="transparent")
        top.pack(fill="x", pady=(0, 6))
        ctk.CTkButton(top, text="扫描全部硬盘与已安装软件", width=210,
                      fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER,
                      command=self.scan).pack(side="left")
        ctk.CTkButton(top, text="卸载选中软件", width=130, fg_color=theme.DANGER,
                      hover_color=theme.DANGER_HOVER,
                      command=self.uninstall).pack(side="left", padx=8)
        ctk.CTkButton(top, text="打开安装目录", width=130,
                      fg_color="#eceff4", text_color=theme.TEXT,
                      hover_color="#dde3ec", command=self.open_dir).pack(side="left")
        self.drives_label = ctk.CTkLabel(top, text="", font=(theme.FONT, 12),
                                         text_color=theme.MUTED)
        self.drives_label.pack(side="left", padx=12)
        self.summary = ctk.CTkLabel(top, text="未扫描", font=(theme.FONT, 12),
                                    text_color=theme.TEXT)
        self.summary.pack(side="right")

        self.kw = KeywordEditor(
            c, "需移除软件关键词（黑名单，软件名包含即标记；config.json 可直接编辑）",
            self.app.cfg.get("remove_keywords", []),
            persist=self._save_kw, placeholder="如：XX游戏  视频软件，待补充")
        self.kw.pack(fill="x", pady=4)

        wrap, self.tree = make_tree(c, COLS, WIDTHS, height=16)
        wrap.pack(fill="both", expand=True, pady=(4, 0))

    def _save_kw(self, kws):
        self.app.cfg["remove_keywords"] = kws
        save_config(self.app.cfg)
        self.app.logger.log(f"黑名单关键词已保存：{kws}")

    def scan(self):
        self.summary.configure(text="扫描中...")
        self.app.run_bg(self._do_scan, self._after_scan)

    def _do_scan(self):
        drives = registry.list_drives_usage()
        items = registry.list_installed(self.app.cfg.get("remove_keywords", []))
        return drives, items

    def _after_scan(self, res):
        drives, items = res
        self.items = items   # 注意：不能写成 "drives, items = self.items = res"——
                             # 链式赋值会把整个元组存进 self.items，导致卸载/打开目录崩溃
        dtxt = "  |  ".join(
            f"{d['drive']} 总 {human_size(d['total'])} 余 {human_size(d['free'])}"
            for d in drives)
        self.drives_label.configure(text=dtxt)
        self.tree.delete(*self.tree.get_children())
        flagged = 0
        for idx, it in enumerate(items):
            flag = "需移除" if it["flagged"] else ""
            flagged += it["flagged"]
            tags = ("flag",) if it["flagged"] else (("odd",) if idx % 2 else ())
            self.tree.insert("", "end", values=(
                it["name"], it["version"], it["publisher"],
                human_size(_safe_kb(it["size_kb"])), flag), tags=tags)
        self.summary.configure(text=f"共 {len(items)} 款软件，标记需移除 {flagged} 款")

    def _selected_item(self):
        sel = self.tree.selection()
        if not sel:
            return None
        name = self.tree.item(sel[0], "values")[0]
        for it in self.items:
            if it["name"] == name:
                return it
        return None

    def uninstall(self):
        it = self._selected_item()
        if not it:
            return
        if not self.app.confirm(f"调起卸载程序？\n\n{it['name']}\n（卸载界面由该软件提供，请按其向导完成）"):
            return
        try:
            registry.launch_uninstall(it)
            self.app.logger.log(f"已调起卸载：{it['name']}")
        except Exception as e:
            self.app.logger.log(f"卸载调起失败：{it['name']} -> {e}")

    def open_dir(self):
        it = self._selected_item()
        if not it or not it["install_loc"]:
            return
        p = it["install_loc"].strip('"')
        if os.path.isdir(p):
            os.startfile(p)  # noqa

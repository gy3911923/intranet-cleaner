# -*- coding: utf-8 -*-
"""UI 复用组件：表格、关键词编辑器。"""
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from ui import theme


def make_tree(parent, columns, widths, height=14):
    """带双向滚动条的 ttk.Treeview。

    columns: [(key, title)]。列宽固定（stretch=False）：拖某列表头时不影响其他列；
    勾选列 minwidth 锁定为 44，无法再缩小；横向滚动条支持右拖查看长路径。
    """
    wrap = tk.Frame(parent, background=theme.CARD)
    tree = ttk.Treeview(wrap, columns=[c for c, _ in columns], show="headings",
                        height=height)
    for key, title in columns:
        w = widths.get(key, 120)
        minw = 44 if key == "chk" else 60
        tree.heading(key, text=title)
        tree.column(key, width=w, minwidth=minw, anchor="w", stretch=False)
    vsb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(wrap, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    wrap.grid_rowconfigure(0, weight=1)
    wrap.grid_columnconfigure(0, weight=1)
    tree.tag_configure("flag", background=theme.FLAG_BG, foreground=theme.FLAG_FG)
    tree.tag_configure("deleted", foreground="#9e9e9e")
    tree.tag_configure("empty", foreground="#b0b8c4")
    tree.tag_configure("odd", background=theme.ZEBRA)
    return wrap, tree


# 勾选框字符必须用中文字体自带字形：☐/☑（U+2610/2611）在微软雅黑中缺字形，
# 部分系统渲染为空白（用户"能勾但看不见"的根因）；□/√ 为 GBK 字符，全平台可靠。
CHK_OFF, CHK_ON = "□", "√"


class CheckableTree:
    """给 ttk.Treeview 加首列复选框（☐/☑ 点击切换），支持批量勾选删除。

    列定义需以 ("chk", "✔") 为第一列。insert() 自动在 values 前补勾选格。
    payload 存原始业务数据（如整行 dict 或路径），checked_payloads() 取勾选行。
    add_group()/add_child() 支持分组头模式：点分组头勾选格=全选/取消该组子行。
    """

    def __init__(self, tree, on_change=None):
        self.tree = tree
        self.checked = {}    # iid -> bool（仅子行）
        self.payload = {}    # iid -> 原始业务数据（子行）
        self.children = {}   # 组头 iid -> [子行 iid]
        self.on_change = on_change
        tree.bind("<Button-1>", self._on_click, add="+")

    def insert(self, values, payload=None, tags=()):
        iid = self.tree.insert("", "end",
                               values=(CHK_OFF,) + tuple(values), tags=tags)
        self.checked[iid] = False
        self.payload[iid] = payload if payload is not None else values
        return iid

    def add_group(self, values, tags=()):
        """插入分组头（关键词行），返回头 iid。头行带组状态框（□/■ 全选指示）。"""
        iid = self.tree.insert("", "end", values=(CHK_OFF,) + tuple(values), tags=tags)
        self.children[iid] = []
        return iid

    def add_child(self, group_iid, values, payload=None, tags=()):
        iid = self.tree.insert(group_iid, "end",
                               values=(CHK_OFF,) + tuple(values), tags=tags)
        self.checked[iid] = False
        self.payload[iid] = payload if payload is not None else values
        self.children[group_iid].append(iid)
        return iid

    def clear(self):
        self.checked.clear()
        self.payload.clear()
        self.children.clear()
        self.tree.delete(*self.tree.get_children())

    def _on_click(self, event):
        if self.tree.identify_column(event.x) == "#1":
            iid = self.tree.identify_row(event.y)
            if iid:
                if iid in self.children:       # 分组头：全选/取消该组
                    target = not self._group_all_on(iid)
                    for c in self.children[iid]:
                        self.checked[c] = target
                        self._paint(c)
                    self._paint_group(iid)
                    self._notify()
                else:
                    self.toggle(iid)
            return "break"

    def _group_all_on(self, group_iid):
        kids = self.children.get(group_iid, [])
        return bool(kids) and all(self.checked.get(c) for c in kids)

    def _paint_group(self, group_iid):
        """分组头状态框：全组勾选=√，否则=□。"""
        if group_iid not in self.children:
            return
        box = CHK_ON if self._group_all_on(group_iid) else CHK_OFF
        vals = tuple(self.tree.item(group_iid, "values"))
        if vals and vals[0] in (CHK_ON, CHK_OFF):
            self.tree.item(group_iid, values=(box,) + vals[1:])

    def toggle(self, iid):
        tags = self.tree.item(iid, "tags")
        if tags == ("deleted",):     # 已删除行不可勾选
            return
        self.checked[iid] = not self.checked[iid]
        self._paint(iid)
        gid = self.tree.parent(iid)
        if gid:
            self._paint_group(gid)
        self._notify()

    def check_all(self, on):
        for iid in self.checked:
            self.checked[iid] = on
            self._paint(iid)
        for gid in self.children:
            self._paint_group(gid)
        self._notify()

    def all_checked(self):
        return bool(self.checked) and all(self.checked.values())

    def checked_payloads(self):
        return [self.payload[i] for i, v in self.checked.items() if v]

    def mark_deleted(self, iid):
        """标记为已删除：灰显+取消勾选。"""
        self.checked[iid] = False
        self.tree.item(iid, values=(CHK_OFF,) + tuple(self.tree.item(iid, "values")[1:]),
                       tags=("deleted",))
        gid = self.tree.parent(iid)
        if gid:
            self._paint_group(gid)

    def _paint(self, iid):
        box = CHK_ON if self.checked[iid] else CHK_OFF
        self.tree.item(iid, values=(box,) + tuple(self.tree.item(iid, "values")[1:]))

    def _notify(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass


class KeywordEditor(ctk.CTkFrame):
    """关键词增删编辑器（persist 回调保存 config）。两行布局防溢出。"""

    def __init__(self, master, title, keywords, persist, placeholder="输入关键词后回车或点添加"):
        super().__init__(master, fg_color="transparent")
        self.persist = persist
        self.keywords = list(keywords)
        ctk.CTkLabel(self, text=title, font=(theme.FONT, 13, "bold"),
                     text_color=theme.TEXT, wraplength=280,
                     justify="left").pack(anchor="w", padx=4, pady=(2, 4))
        self.entry = ctk.CTkEntry(self, placeholder_text=placeholder)
        self.entry.pack(fill="x", padx=4)
        self.entry.bind("<Return>", lambda e: self._add())
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=(6, 0))
        ctk.CTkButton(row, text="添加", command=self._add,
                      fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER
                      ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(row, text="删除所选", fg_color=theme.DANGER,
                      hover_color=theme.DANGER_HOVER,
                      command=self._del).pack(side="left", fill="x", expand=True)
        self.listbox = tk.Listbox(self, height=5, activestyle="dotbox",
                                  exportselection=False,
                                  font=(theme.FONT, 10),
                                  selectbackground=theme.PRIMARY,
                                  selectforeground="#ffffff")
        self.listbox.pack(fill="x", padx=4, pady=6)
        self._reload()

    def _reload(self):
        self.listbox.delete(0, tk.END)
        for k in self.keywords:
            self.listbox.insert(tk.END, k)

    def _add(self):
        v = self.entry.get().strip()
        if v and v not in self.keywords:
            self.keywords.append(v)
            self._reload()
            self.persist(self.keywords)
        self.entry.delete(0, tk.END)

    def _del(self):
        sel = list(self.listbox.curselection())
        for i in reversed(sel):
            del self.keywords[i]
        self._reload()
        self.persist(self.keywords)

# -*- coding: utf-8 -*-
"""清爽浅蓝主题（企业淡蓝色调）：色彩 token、ttk 样式、卡片工厂。"""
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

# ---- 色彩 token（浅色清爽版）----
PRIMARY = "#2e7cd6"        # 主按钮：柔和蓝
PRIMARY_HOVER = "#1f63b3"
PRIMARY_DARK = "#174a7c"   # 标题深蓝
SIDEBAR_BG = "#f7fafd"     # 侧栏：近白淡蓝
SIDEBAR_SEL = "#dcecfa"    # 导航选中：淡蓝底
SIDEBAR_SEL_TEXT = "#1f5fb0"
DANGER = "#d64541"         # 危险按钮：柔和红
DANGER_HOVER = "#a8322e"
BG = "#eef3f9"             # 主窗背景
CARD = "#ffffff"           # 卡片
BORDER = "#d5e2ef"         # 卡片描边
TEXT = "#1f2d3d"
MUTED = "#6b7a90"
ZEBRA = "#f4f8fc"          # 表格斑马纹
FLAG_BG = "#fdecea"        # 黑名单行
FLAG_FG = "#b71c1c"
HEADER_BG = "#e6f0fa"      # 表头：淡蓝底
HEADER_FG = "#1f4e79"      # 表头字：深蓝

FONT = "Microsoft YaHei UI"


def apply_theme():
    """全局一次性设置：CTk 外观 + ttk.Treeview 样式。"""
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("Treeview",
                    rowheight=26,
                    font=(FONT, 10),
                    background="#ffffff",
                    fieldbackground="#ffffff",
                    foreground=TEXT)
    style.configure("Treeview.Heading",
                    font=(FONT, 10, "bold"),
                    background=HEADER_BG,
                    foreground=HEADER_FG,
                    relief="flat",
                    padding=(6, 4))
    style.map("Treeview.Heading", background=[("active", "#d8e8f7")])
    style.map("Treeview",
              background=[("selected", "#dcecfa")],
              foreground=[("selected", TEXT)])
    style.configure("Vertical.TScrollbar", background="#dfe7f0")
    _style = style  # 保持引用


def card(master, title=None, subtitle=None):
    """圆角描边白色卡片，可选标题。返回 (卡片frame, 内容frame)。"""
    box = ctk.CTkFrame(master, fg_color=CARD, corner_radius=10,
                       border_width=1, border_color=BORDER)
    inner = ctk.CTkFrame(box, fg_color="transparent")
    inner.pack(fill="both", expand=True, padx=14, pady=(10, 12))
    if title:
        head = ctk.CTkFrame(inner, fg_color="transparent")
        head.pack(fill="x", pady=(0, 8))
        ctk.CTkFrame(head, width=4, height=18, fg_color=PRIMARY,
                     corner_radius=2).pack(side="left", padx=(0, 8))
        t = ctk.CTkLabel(head, text=title, font=(FONT, 14, "bold"),
                         text_color=TEXT, anchor="w")
        t.pack(side="left")
        if subtitle:
            ctk.CTkLabel(head, text=subtitle, font=(FONT, 11),
                         text_color=MUTED, anchor="w").pack(side="left", padx=10)
    return box, inner

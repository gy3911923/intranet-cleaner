# -*- coding: utf-8 -*-
"""F3 WPS/Office 缓存与最近打开记录清理页。"""
import os
import customtkinter as ctk

from core import wps_office
from core.util import human_size, run_hidden
from ui import theme

WPS_PROCS = ("wps.exe", "et.exe", "wpp.exe", "wpspdf.exe")


class WpsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.items = []
        self.vars = {}
        self._build()

    def _build(self):
        box1, c1 = theme.card(self, "本地文件缓存清理")
        box1.pack(fill="both", expand=True, padx=2, pady=(0, 8))
        bar = ctk.CTkFrame(c1, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 6))
        ctk.CTkButton(bar, text="扫描缓存", width=110,
                      fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER,
                      command=self.scan).pack(side="left")
        ctk.CTkButton(bar, text="全选", width=70,
                      fg_color="#eceff4", text_color=theme.TEXT,
                      hover_color="#dde3ec", command=self.select_all).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="清理所选项", width=120, fg_color=theme.DANGER,
                      hover_color=theme.DANGER_HOVER, command=self.clean).pack(side="left")
        self.hint = ctk.CTkLabel(bar, text="未扫描", font=(theme.FONT, 12),
                                 text_color=theme.MUTED)
        self.hint.pack(side="right")
        self.note = ctk.CTkLabel(
            c1, text="⚠ “备份/草稿”类删除后本次的自动备份不可恢复（回收站捞回也难保证可用）。",
            font=(theme.FONT, 12), text_color="#8d6e63", anchor="w")
        self.note.pack(anchor="w", pady=(0, 6))
        self.clean_result = ctk.CTkLabel(c1, text="", font=(theme.FONT, 12),
                                         text_color=theme.TEXT, wraplength=900,
                                         justify="left", anchor="w")
        self.clean_result.pack(anchor="w", pady=(2, 4))
        self.list_frame = ctk.CTkFrame(c1, fg_color="transparent")
        self.list_frame.pack(fill="both", expand=True)

        box2, c2 = theme.card(self, "最近打开记录（注册表 MRU）")
        box2.pack(fill="x", padx=2, pady=(0, 8))
        bar2 = ctk.CTkFrame(c2, fg_color="transparent")
        bar2.pack(fill="x")
        ctk.CTkButton(bar2, text="一键清除 Office + WPS 最近记录", width=230,
                      fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER,
                      command=self.clean_recent).pack(side="left")
        self.recent_label = ctk.CTkLabel(bar2, text="", font=(theme.FONT, 12),
                                         text_color=theme.MUTED)
        self.recent_label.pack(side="left", padx=12)

    def scan(self):
        self.hint.configure(text="扫描中...")
        self.app.run_bg(wps_office.collect_items, self._after_scan)

    def _after_scan(self, items):
        self.items = items
        for w in self.list_frame.winfo_children():
            w.destroy()
        self.vars = {}
        total = 0
        for it in items:
            v = ctk.StringVar(value="on")
            self.vars[it["path"]] = v
            total += it["size"]
            txt = f'[{it["group"]}] {it["label"]}  —  {human_size(it["size"])}'
            if it["group"] in ("备份", "草稿"):
                txt += "   ⚠ 含自动备份/草稿"
            ctk.CTkCheckBox(self.list_frame, text=txt, variable=v,
                            onvalue="on", offvalue="off",
                            font=(theme.FONT, 12)).pack(anchor="w", pady=2)
        self.hint.configure(text=f"{len(items)} 项 / 合计 {human_size(total)}",
                            text_color=theme.TEXT)

    def select_all(self):
        on = all(v.get() == "off" for v in self.vars.values())
        for v in self.vars.values():
            v.set("on" if on else "off")

    def _wps_procs(self):
        """运行中的 WPS 组件进程名列表。"""
        try:
            r = run_hidden(["tasklist", "/NH"], timeout=10)
            out = r.stdout.decode("gbk", errors="replace").lower()
            return [im for im in WPS_PROCS if im in out]
        except Exception:
            return []

    def clean(self):
        sel = [it for it in self.items if self.vars.get(it["path"]) and
               self.vars[it["path"]].get() == "on"]
        if not sel:
            self.app.logger.log("WPS/Office 缓存：未勾选任何项")
            return
        # WPS 占用预警：运行中的 WPS 会锁住缓存/备份文件，导致清理失败或不完整
        procs = self._wps_procs()
        if procs and not self.app.confirm_danger("检测到 WPS 正在运行", [
                f"检测到 WPS 组件正在运行：{', '.join(procs)}", "",
                "运行中的 WPS 会锁住缓存与备份文件，导致删除失败或不完整。", "",
                "点【确认执行】= 自动关闭 WPS 后继续清理",
                "  （WPS 打开的未保存文档会丢失，请先保存！）",
                "点【取消】= 不清理，先手动处理 WPS。"]):
            self.app.logger.log("WPS 清理已取消（用户选择先处理运行中的 WPS）")
            return
        if procs:
            killed = []
            for im in procs:
                try:
                    run_hidden(["taskkill", "/F", "/IM", im, "/T"], timeout=15)
                    killed.append(im)
                except Exception:
                    pass
            if killed:
                self.app.logger.log(f"已自动结束 WPS 进程：{', '.join(killed)}")
        lines = [
            f"将删除以下 {len(sel)} 项（合计 "
            f"{human_size(sum(i['size'] for i in sel))}）：",
            "",
        ]
        lines += [f"  · [{i['group']}] {i['label']}" for i in sel]
        lines += [
            "",
            "可能导致：",
            "  · “自动备份/未保存草稿”删除后，本次未保存内容的恢复记录丢失",
            "",
            "注意：回收站可能无法完整恢复此类缓存与数据库文件，请确认不再需要。",
            "是否确认执行？",
        ]
        if not self.app.confirm_danger("WPS/Office 缓存清理确认", lines):
            return
        self._cleaning_sel = sel
        self.hint.configure(text="清理中...")
        self.app.run_bg(lambda: wps_office.clean_cache(sel, self.app.logger.log),
                        self._after_clean)

    def _after_clean(self, res):
        ok, fail = res
        self.app.logger.log(f"WPS/Office 缓存清理完成：成功 {ok}，失败 {len(fail)}")
        total = sum(i.get("size", 0) for i in getattr(self, "_cleaning_sel", []))
        lines = [f"缓存清理完成：成功 {ok} 项 / 失败 {len(fail)} 项，"
                 f"释放 {human_size(total)}", "", "本次清理内容："]
        for it in getattr(self, "_cleaning_sel", []):
            lines.append(f"  · [{it['group']}] {it['label']} — {human_size(it.get('size', 0))}")
        if fail:
            lines.append("")
            lines.append("失败项（明细见操作日志「展开」）：")
            for p, err in fail[:5]:
                lines.append(f"  ✗ {os.path.basename(p)}（{err}）")
        lines.append("")
        lines.append("缓存已入回收站，可恢复。")
        self.clean_result.configure(text="\n".join(lines))
        self.scan()

    def clean_recent(self):
        lines = [
            "将清除以下“最近打开”记录：",
            "  · Office（Word/Excel/PowerPoint 等）注册表 File MRU / User MRU",
            "  · Office Recent 目录下的快捷方式",
            "  · WPS 注册表中的最近文件记录",
            "",
            "可能导致：所有组件的“最近使用”列表清空。",
            "不影响文档本身，文档内容与文件均不受影响。",
            "是否确认执行？",
        ]
        if not self.app.confirm_danger("最近打开记录清除确认", lines):
            return
        self.app.run_bg(lambda: wps_office.clean_recent(self.app.logger.log),
                        self._after_recent)

    def _after_recent(self, r):
        self.recent_label.configure(
            text=f"完成：Office 注册表 {r['office_reg']} 项 / Recent {r['office_lnk']} 个 / WPS {r['wps_reg']} 项")

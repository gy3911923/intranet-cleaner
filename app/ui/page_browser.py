# -*- coding: utf-8 -*-
"""F2 浏览器清理页：清内容、保收藏夹/扩展/设置。"""
import os

import customtkinter as ctk

from core import browsers
from core.config import save_config
from core.util import human_size
from ui import theme

GROUPS = list(browsers.CHROMIUM_GROUPS.keys())


class BrowserPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.found = []
        self.items = []
        self.bvars = {}
        self.gvars = {}
        self._build()

    def _build(self):
        # ---- 卡片1：检测与清理范围 ----
        box1, c1 = theme.card(self, "① 检测浏览器  ② 扫描体积  ③ 清理",
                              subtitle="保留收藏夹、扩展插件、浏览器设置")
        box1.pack(fill="x", padx=2, pady=(0, 8))
        top = ctk.CTkFrame(c1, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkButton(top, text="① 检测浏览器", width=130,
                      fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER,
                      command=self.detect).pack(side="left")
        ctk.CTkButton(top, text="② 扫描待清体积", width=130,
                      fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER,
                      command=self.scan).pack(side="left", padx=8)
        ctk.CTkButton(top, text="③ 开始清理", width=110, fg_color=theme.DANGER,
                      hover_color=theme.DANGER_HOVER,
                      command=self.clean).pack(side="left")
        self.kill_var = ctk.CTkCheckBox(
            top, text="自动结束浏览器进程（否则文件被锁清不掉）", font=(theme.FONT, 12),
            command=self._save_kill)
        if self.app.cfg.get("auto_kill_browser", True):
            self.kill_var.select()
        self.kill_var.pack(side="left", padx=14)

        self.browser_bar = ctk.CTkFrame(c1, fg_color="transparent")
        self.browser_bar.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(self.browser_bar, text="清理范围（先点①检测）：",
                     font=(theme.FONT, 12, "bold"),
                     text_color=theme.TEXT).pack(side="left")
        grp = ctk.CTkFrame(c1, fg_color="transparent")
        grp.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(grp, text="清理项：", font=(theme.FONT, 12, "bold"),
                     text_color=theme.TEXT).pack(side="left")
        for g in GROUPS:
            v = ctk.StringVar(value="on")
            self.gvars[g] = v
            ctk.CTkCheckBox(grp, text=g, variable=v, onvalue="on",
                            offvalue="off", font=(theme.FONT, 12)).pack(
                side="left", padx=(4, 8))

        # ---- 卡片2：执行结果（多行只读）----
        box2, c2 = theme.card(self, "检测结果 / 统计")
        box2.pack(fill="both", expand=True, padx=2, pady=(0, 8))
        self.result_box = ctk.CTkTextbox(c2, font=(theme.FONT, 12), wrap="word",
                                         fg_color="#fbfcfe", height=150)
        self.result_box.pack(fill="both", expand=True)
        self.result_box.insert("1.0", "点【① 检测浏览器】开始。")
        self.result_box.configure(state="disabled")

    # -- 结果区输出 --
    def _result(self, text):
        self.result_box.configure(state="normal")
        self.result_box.delete("1.0", "end")
        self.result_box.insert("1.0", text)
        self.result_box.configure(state="disabled")

    def _save_kill(self):
        self.app.cfg["auto_kill_browser"] = bool(self.kill_var.get())
        save_config(self.app.cfg)

    def detect(self):
        self._result("检测中...")
        self.app.run_bg(browsers.detect, self._after_detect)

    def _after_detect_then_scan(self, found):
        self._after_detect(found)
        self.scan()

    def _after_detect(self, found):
        self.found = found
        for w in self.browser_bar.winfo_children()[1:]:
            w.destroy()
        names = []
        for b in found:
            v = ctk.StringVar(value="on")
            self.bvars[b["name"]] = v
            run = "（运行中）" if b["running"] else ""
            names.append(f'{b["name"]}{run}')
            ctk.CTkCheckBox(self.browser_bar, text=f'{b["name"]}{run}',
                            variable=v, onvalue="on", offvalue="off",
                            font=(theme.FONT, 12)).pack(side="left", padx=(10, 4))
        if found:
            head = f"检测到 {len(found)} 款浏览器：{'、'.join(names)}"
        else:
            head = "未发现受支持的浏览器"
        self._result(head)

    def _checked(self):
        return [b for b in self.found if self.bvars.get(b["name"]) and
                self.bvars[b["name"]].get() == "on"]

    def _checked_groups(self):
        return [g for g, v in self.gvars.items() if v.get() == "on"]

    def scan(self):
        if not self.found:
            self._result("检测中...（检测完成后自动开始扫描）")
            self.app.run_bg(browsers.detect, self._after_detect_then_scan)
            return
        self._result("扫描中...")
        bs, gs = self._checked(), self._checked_groups()
        self.app.run_bg(lambda: browsers.collect_items(bs, gs, self.app.logger.log),
                        self._after_scan)

    def _after_scan(self, items):
        self.items = items
        total = sum(i["size"] for i in items)
        by = {g: [0, 0] for g in GROUPS}  # 全量分组为键，未勾选组也安全
        for i in items:
            by[i["group"]][0] += 1
            by[i["group"]][1] += i["size"]
        lines = ["各清理项统计："]
        for g in self._checked_groups():
            cnt, sz = by.get(g, (0, 0))
            lines.append(f"  · {g}：{cnt} 项 / {human_size(sz)}")
        lines.append(f"合计：{len(items)} 项 / {human_size(total)}")
        lines.append("确认无误后点【③ 开始清理】。")
        self._result("\n".join(lines))

    def clean(self):
        if not self.items:
            self.app.logger.log("请先扫描待清体积")
            return
        # 以当前勾选为准过滤（扫描后调整勾选时，删除范围必须与确认弹窗一致）
        # P1-2 修复：统一走 filter_scope，浏览器维度真正生效
        bs_now, gs_now = self._checked(), self._checked_groups()
        items = browsers.filter_scope(self.items,
                                      {b["name"] for b in bs_now}, gs_now)
        if not items:
            self.app.logger.log("当前勾选范围内没有可清理项")
            return
        running = [b["name"] for b in self._checked() if b["running"]]
        if running and not self.kill_var.get():
            self.app.logger.log(f"浏览器运行中：{', '.join(running)}。请先关闭或勾选自动结束进程")
            return
        bs = self._checked()
        gs = self._checked_groups()
        total = sum(i["size"] for i in items)
        lines = [
            f"将清理 {'、'.join(b['name'] for b in bs)} 的以下内容：",
            f"  · 清理项：{'、'.join(gs)}",
            f"  · 共 {len(items)} 项，合计 {human_size(total)}",
            "",
            "可能导致：",
            "  · 所有网站登录态退出，需重新登录",
            "  · 保存的密码、表单记录被清除，需重新输入",
            "  · 打开的网页会话与标签丢失",
            "",
            "保留内容：收藏夹、扩展插件、浏览器设置。",
            "注意：清理项删除后回收站可能无法完整恢复（数据库文件与浏览器运行状态耦合），请确认不再需要。",
            "是否确认执行？",
        ]
        if not self.app.confirm_danger("浏览器数据清理确认", lines):
            return
        self._result("清理中...")
        self._cleaning_items = items
        self.app.run_bg(lambda: self._do_clean(bs, items), self._after_clean)

    def _do_clean(self, bs, items):
        killed = []
        if self.kill_var.get() and any(b["running"] for b in bs):
            killed = browsers.kill_processes(bs)
        ok, fail = browsers.clean(items, self.app.logger.log)
        return killed, ok, fail

    def _after_clean(self, res):
        killed, ok, fail = res
        if killed:
            self.app.logger.log(f"已结束进程：{', '.join(killed)}")
        self.app.logger.log(f"浏览器清理完成：成功 {ok} 项，失败 {len(fail)} 项"
                            + ("（明细见日志）" if fail else ""))
        # 按清理组汇总明细反馈
        by = {}
        for it in getattr(self, "_cleaning_items", []):
            cnt, sz = by.get(it["group"], (0, 0))
            by[it["group"]] = (cnt + 1, sz + it.get("size", 0))
        lines = [f"清理完成：成功 {ok} 项 / 失败 {len(fail)} 项", "", "本次清理内容："]
        for g, (cnt, sz) in by.items():
            lines.append(f"  · {g}：{cnt} 项 / {human_size(sz)}")
        if killed:
            lines.append("")
            lines.append(f"已结束浏览器进程：{'、'.join(killed)}")
        if fail:
            lines.append("")
            lines.append(f"失败 {len(fail)} 项（明细见下方操作日志「展开」）：")
            for p, err in fail[:5]:
                lines.append(f"  ✗ {os.path.basename(p)}（{err}）")
            if len(fail) > 5:
                lines.append(f"  …… 其余 {len(fail) - 5} 项见日志")
        lines.append("")
        lines.append("已删除文件均进入回收站；建议重启浏览器验证收藏夹与登录状态。")
        lines.append("（浏览器列表未自动刷新，需要时点【① 检测浏览器】）")
        self._result("\n".join(lines))
        self.items = []
        # 不再自动 detect()：此前会在 1~2 秒后用检测结果覆盖掉清理明细，
        # 用户明确要求"清理后要有反馈"，明细必须常驻（v1.8.6）

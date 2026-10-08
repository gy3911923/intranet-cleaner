# -*- coding: utf-8 -*-
"""主窗体：侧边导航 + 五功能页 + 全局日志面板 + 高风险确认/关于反馈弹窗。"""
import json
import os
import queue
import socket
import threading

import customtkinter as ctk

from core import config as cfgmod
from core.config import APP_NAME, APP_VERSION, build_stamp
from ui import theme
from ui.page_software import SoftwarePage
from ui.page_browser import BrowserPage
from ui.page_wps import WpsPage
from ui.page_downloads import DownloadsPage
from ui.page_search import SearchPage

NAV = [("software", "软件扫描清理"), ("browser", "浏览器清理"),
       ("wps", "WPS/Office清理"), ("downloads", "下载目录管理"),
       ("search", "关键词检索")]


DISCLAIMER_TEXT = """使用须知与免责声明

本软件用于对 Windows 电脑进行本地数据清理。使用前请务必阅读以下条款：

一、本软件可能删除的内容包括但不限于：浏览器历史记录、Cookie、保存的密码、自动填充数据、缓存与会话数据；WPS/Office 本地缓存与自动备份；您勾选删除的文件、目录与软件。上述内容删除后可能无法通过回收站完整恢复。

二、清理浏览器数据将导致各网站登录态退出、保存的密码被清除，请提前确认不影响正常使用。清理“自动备份/未保存草稿”后，相应内容的恢复记录将丢失。

三、本软件仅限本单位内部测试使用，请勿用于未经授权的设备或数据。使用者应确保对所操作的设备与数据具有相应管理权限，并在操作前自行确认清理范围。

四、因使用本软件造成的任何数据损失及相关后果，由使用者自行承担。本软件按“现状”提供，开发者不对功能的适用性作任何明示或默示的保证。

如已理解并接受以上全部条款，请点击“同意并继续”进入软件；如有异议，请点击“不同意并退出”。"""


class App(ctk.CTk):
    def __init__(self, cfg, logger):
        super().__init__(fg_color=theme.BG)
        theme.apply_theme()
        self.cfg = cfg
        self.logger = logger
        self.deleted_paths = set()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1200x800")
        self.minsize(1040, 700)
        self._pages = {}
        self._ui_queue = queue.Queue()   # 后台线程 -> 主线程的唯一通道
        self._build()
        self.show_page("software")
        self._pump_queue()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ---- 侧边栏（近白淡蓝）----
        side = ctk.CTkFrame(self, width=200, corner_radius=0,
                            fg_color=theme.SIDEBAR_BG)
        side.grid(row=0, column=0, rowspan=2, sticky="nsw")
        ctk.CTkLabel(side, text=APP_NAME, font=(theme.FONT, 17, "bold"),
                     text_color=theme.PRIMARY_DARK).pack(pady=(26, 2), padx=12)
        ctk.CTkLabel(side, text=f"v{APP_VERSION} · 构建 {build_stamp()}",
                     font=(theme.FONT, 11), text_color=theme.MUTED).pack(pady=(0, 22))
        self._nav_btns = {}
        for key, text in NAV:
            b = ctk.CTkButton(side, text=text, height=42, anchor="w",
                              corner_radius=8, fg_color="transparent",
                              text_color="#3d4d63",
                              hover_color=theme.SIDEBAR_SEL,
                              font=(theme.FONT, 13),
                              command=lambda k=key: self.show_page(k))
            b.pack(fill="x", padx=10, pady=3)
            self._nav_btns[key] = b

        # 最左下角：小号"关于与反馈"入口（署名保留在弹窗内）
        ctk.CTkButton(side, text="关于与反馈", height=26,
                      fg_color="transparent", text_color=theme.MUTED,
                      hover_color=theme.SIDEBAR_SEL, font=(theme.FONT, 11),
                      anchor="w", command=self.open_about
                      ).pack(side="bottom", fill="x", padx=14, pady=12)

        # ---- 内容区 ----
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.grid(row=0, column=1, sticky="nsew", padx=10, pady=(10, 0))

        # ---- 日志面板（卡片，默认收起，点击标题展开）----
        logbox = ctk.CTkFrame(self, height=40, fg_color=theme.CARD,
                              corner_radius=10, border_width=1,
                              border_color=theme.BORDER)
        logbox.grid(row=1, column=1, sticky="ew", padx=10, pady=(8, 10))
        logbox.grid_propagate(False)
        logbox.pack_propagate(False)  # 日志框用 pack 子件，必须双重锁定高度
        self.logbox = logbox
        head = ctk.CTkFrame(logbox, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(6, 0))
        ctk.CTkFrame(head, width=4, height=14, fg_color=theme.PRIMARY,
                     corner_radius=2).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(head, text="操作日志", font=(theme.FONT, 12, "bold"),
                     text_color=theme.TEXT, anchor="w").pack(side="left")
        self.log_preview = ctk.CTkLabel(head, text="", font=(theme.FONT, 11),
                                        text_color=theme.MUTED, anchor="w")
        self.log_preview.pack(side="left", padx=10, fill="x", expand=True)
        self.log_open = False
        self.log_btn = ctk.CTkButton(head, text="展开 ▾", width=72, height=22,
                                     fg_color="#eceff4", text_color=theme.TEXT,
                                     hover_color="#dde3ec", font=(theme.FONT, 11),
                                     command=self._toggle_log)
        self.log_btn.pack(side="right")
        self.log_text = ctk.CTkTextbox(logbox, font=("Consolas", 12), wrap="none",
                                       fg_color="#fbfcfe")
        self.log_text.configure(state="disabled")
        self.logger.subscribe(self._append_log)

    def _toggle_log(self):
        """展开/收起日志面板；收起时只留标题条并显示最后一条。"""
        self.log_open = not self.log_open
        if self.log_open:
            self.logbox.configure(height=220)
            self.log_text.pack(fill="both", expand=True, padx=10, pady=(4, 10))
            self.log_btn.configure(text="收起 ▴")
            self.log_preview.configure(text="")
        else:
            self.log_text.pack_forget()
            self.logbox.configure(height=40)
            self.log_btn.configure(text="展开 ▾")

    def _append_log(self, line):
        # 线程安全：子线程只入队，主线程统一消费
        self._ui_queue.put(("log", line))

    def post(self, fn):
        """线程安全：把零参可调用对象投递到主线程执行。

        子线程里严禁直接调用 self.after()/控件方法（Tk 非线程安全），
        一律走本方法入队，由 _pump_queue 在主线程执行。
        """
        self._ui_queue.put(("job", fn))

    def _write_log(self, line):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        if not self.log_open:      # 收起状态：标题条显示最后一条动态
            self.log_preview.configure(text=line[:80])

    def _pump_queue(self):
        """主线程轮询消费 UI 队列（替代跨线程直接调用 after）。

        教训（v1.7.0 → v1.8.3 修复）：原实现把 `get_nowait()` 与消息分发
        写在同一个只捕获 queue.Empty 的 try 里，一旦某条消息结构异常
        （run_bg 误入队嵌套元组 → ValueError），异常逃逸导致 after() 重排
        语句永不执行——泵彻底停摆，此后所有后台回调（检索结果渲染、
        清理反馈）静默失灵，界面表现为"结果全空 + 状态卡住"。
        现在：单条消息失败只记日志，泵必须自我重排。
        """
        while True:
            try:
                item = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                self._dispatch(item)
            except Exception:
                import traceback
                try:
                    self._write_log("[回调异常] " + traceback.format_exc())
                except Exception:
                    pass
        try:
            self.after(60, self._pump_queue)
        except Exception:
            pass    # 窗口销毁后 Tk 抛 TclError（非 RuntimeError 子类），进程将退出，静默即可

    def _dispatch(self, item):
        """分发一条 UI 队列消息（结构容错，非法消息静默丢弃）。"""
        if not isinstance(item, tuple) or not item:
            return
        kind, rest = item[0], item[1:]
        if kind == "log":
            self._write_log(rest[0] if rest else "")
        elif kind == "job":
            if rest and callable(rest[0]):
                rest[0]()
        elif kind == "call":
            # 兼容 ("call", fn, arg) 与历史误写的 ("call", (fn, arg))
            if len(rest) == 1 and isinstance(rest[0], (tuple, list)) and len(rest[0]) == 2:
                if not getattr(self, "_compat_hit", False):   # 只记一次，防刷屏
                    self._compat_hit = True
                    self._write_log("[队列] 命中历史结构兼容分支"
                                    "（仍存在旧式入队点，建议排查）")
                fn, arg = rest[0]
            elif len(rest) == 2:
                fn, arg = rest
            else:
                self._write_log(f"[队列消息结构异常，已忽略] {item!r:.200}")
                return
            fn(arg)

    def report_callback_exception(self, exc, val, tb):
        """Tkinter 回调异常（按钮点击等）落日志，windowed 模式可见化。"""
        import traceback
        try:
            self.logger.log(f"[界面异常] {''.join(traceback.format_exception(exc, val, tb))}")
        except Exception:
            pass

    def show_page(self, key):
        for k, b in self._nav_btns.items():
            if k == key:
                b.configure(fg_color=theme.SIDEBAR_SEL,
                            text_color=theme.SIDEBAR_SEL_TEXT)
            else:
                b.configure(fg_color="transparent", text_color="#3d4d63")
        for w in self.container.winfo_children():
            w.pack_forget()
        if key not in self._pages:
            try:
                makers = {"software": SoftwarePage, "browser": BrowserPage,
                          "wps": WpsPage, "downloads": DownloadsPage,
                          "search": SearchPage}
                self._pages[key] = makers[key](self.container, self)
            except Exception:
                import traceback
                err = traceback.format_exc()
                self.logger.log(f"[页面构建异常] {key}\n{err}")
                err_box = ctk.CTkFrame(self.container, fg_color=theme.CARD,
                                       corner_radius=10, border_width=1,
                                       border_color=theme.BORDER)
                ctk.CTkLabel(err_box, text=f"页面 [{key}] 加载失败（错误已写入操作日志，请截图日志反馈）",
                             font=(theme.FONT, 14, "bold"), text_color=theme.DANGER,
                             wraplength=800, justify="left").pack(anchor="w", padx=20, pady=(16, 8))
                ctk.CTkTextbox(err_box, font=("Consolas", 11), wrap="word",
                               fg_color="#fff5f5", text_color=theme.TEXT, height=300
                               ).pack(fill="both", expand=True, padx=20, pady=(0, 16))
                tb = err_box.winfo_children()[-1]
                tb.insert("1.0", err)
                tb.configure(state="disabled")
                err_box.pack(fill="both", expand=True)
                return
        self._pages[key].pack(fill="both", expand=True)

    # ---- 公共服务 ----
    def log(self, msg):
        self.logger.log(msg)

    def _disclaimer_flag_path(self):
        """免责声明同意状态：绑机器+用户存储，不随 config.json / exe 复制传播。"""
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "IntranetCleaner")
        try:
            os.makedirs(d, exist_ok=True)
            return os.path.join(d, "disclaimer.json")
        except OSError:
            return None

    def _disclaimer_agreed_here(self):
        """仅当本机本用户已同意过才返回 True（防随包传播）。"""
        p = self._disclaimer_flag_path()
        if not p or not os.path.isfile(p):
            return False
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            return bool(d.get("agreed")) and d.get("machine") == socket.gethostname() \
                and d.get("user") == os.environ.get("USERNAME", "")
        except Exception:
            return False

    def _write_disclaimer_flag(self):
        p = self._disclaimer_flag_path()
        if not p:
            return
        try:
            import datetime
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"agreed": True, "machine": socket.gethostname(),
                           "user": os.environ.get("USERNAME", ""),
                           "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                          f, ensure_ascii=False, indent=2)
        except OSError as e:
            self.logger.log(f"免责声明同意状态写入失败（下次仍会弹窗）：{e}")

    def show_first_run_disclaimer(self):
        """首次启动免责声明（按机器+用户判定，不随配置文件传播）。
        同意→写入本机标记返回 True；不同意→返回 False，调用方应退出。"""
        if self._disclaimer_agreed_here():
            return True
        dlg = ctk.CTkToplevel(self, fg_color=theme.CARD)
        dlg.title("使用须知与免责声明")
        dlg.geometry("620x560")
        dlg.resizable(False, True)
        dlg.transient(self)
        dlg.attributes("-topmost", True)
        agreed = {"v": False}

        band = ctk.CTkFrame(dlg, fg_color=theme.PRIMARY, corner_radius=0, height=52)
        band.pack(fill="x")
        ctk.CTkLabel(band, text="⚠  使用须知与免责声明",
                     font=(theme.FONT, 15, "bold"),
                     text_color="#ffffff").pack(pady=12)

        body = ctk.CTkTextbox(dlg, font=(theme.FONT, 13), wrap="word",
                              fg_color="#fbfcfe", text_color=theme.TEXT)
        body.pack(fill="both", expand=True, padx=16, pady=(14, 6))
        body.insert("1.0", DISCLAIMER_TEXT)
        body.configure(state="disabled")

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=(6, 16))

        def _agree():
            agreed["v"] = True
            self._write_disclaimer_flag()      # 机器级标记，不写入 config.json
            self.logger.log(f"用户已同意使用须知与免责声明（本机记录："
                            f"{socket.gethostname()}/{os.environ.get('USERNAME','')}）")
            dlg.destroy()

        ctk.CTkButton(btns, text="同意并继续", height=38,
                      font=(theme.FONT, 13, "bold"),
                      fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER,
                      command=_agree).pack(side="right", padx=(10, 0), ipadx=10)
        ctk.CTkButton(btns, text="不同意并退出", height=38, font=(theme.FONT, 13),
                      fg_color="#eceff4", text_color=theme.TEXT,
                      hover_color="#dde3ec",
                      command=dlg.destroy).pack(side="right", ipadx=8)

        dlg.update_idletasks()
        self.update_idletasks()
        w = 620
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + 60
        dlg.geometry(f"{w}x{dlg.winfo_reqheight() + 10}+{max(x, 0)}+{max(y, 0)}")
        dlg.grab_set()
        dlg.wait_window()
        return agreed["v"]

    def confirm(self, message):
        from tkinter import messagebox
        return messagebox.askyesno("确认操作", message, parent=self)

    def offer_keyword_restore(self):
        """检索词为空但备份中有词时，提示一键恢复（防"一键全删"导致词表丢失）。"""
        if self.cfg.get("search_keywords"):
            return
        n = cfgmod.backup_keyword_count()
        if not n:
            return
        if not self.confirm(f"检测到检索关键词列表为空，但上一版备份"
                            f"（config.json.bak）中保留着 {n} 个关键词。\n\n"
                            f"是否从备份恢复？"):
            self.logger.log(f"用户选择不恢复（备份中仍有 {n} 个关键词，"
                            f"可随时从 config.json.bak 手工找回）")
            return
        got = cfgmod.restore_keywords_from_backup()
        if got:
            self.cfg["search_keywords"] = cfgmod.load_config().get("search_keywords", [])
            self.logger.log(f"已从备份恢复 {got} 个检索关键词")
            page = self._pages.get("search")
            if page is not None and hasattr(page, "_reload_chips"):
                page._reload_chips()
        else:
            self.logger.log("从备份恢复关键词失败，请检查 config.json.bak 是否完好")

    def open_about(self):
        """关于与反馈：开发者、版本、内网邮箱（一键复制/唤起邮件客户端）。"""
        dlg = ctk.CTkToplevel(self, fg_color=theme.CARD)
        dlg.title("关于与反馈")
        dlg.geometry("520x430")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.attributes("-topmost", True)

        ctk.CTkLabel(dlg, text=APP_NAME, font=(theme.FONT, 18, "bold"),
                     text_color=theme.PRIMARY_DARK).pack(pady=(22, 2))
        ctk.CTkLabel(dlg, text=f"版本 v{APP_VERSION}  ·  构建 {build_stamp()}  ·  绿色免安装",
                     font=(theme.FONT, 12), text_color=theme.MUTED).pack()
        ctk.CTkLabel(dlg, text="开发者：郭扬", font=(theme.FONT, 13),
                     text_color=theme.TEXT).pack(pady=(14, 6))

        box, c = theme.card(dlg, "问题反馈", subtitle="反馈时请附上 exe 旁的「操作日志.log」")
        box.pack(fill="x", padx=22, pady=(6, 0))
        for addr in self.cfg.get("feedback_mail", []):
            row = ctk.CTkFrame(c, fg_color="transparent")
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=addr, font=(theme.FONT, 12),
                         text_color=theme.TEXT, anchor="w").pack(side="left", fill="x",
                                                                 expand=True)
            ctk.CTkButton(row, text="复制", width=56, height=26,
                          fg_color="#eceff4", text_color=theme.TEXT,
                          hover_color="#dde3ec",
                          command=lambda a=addr: self._copy_mail(a)
                          ).pack(side="left", padx=(6, 0))
            ctk.CTkButton(row, text="写邮件", width=68, height=26,
                          fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER,
                          command=lambda a=addr: self._mail_to(a)
                          ).pack(side="left", padx=(6, 0))
        if not self.cfg.get("feedback_mail"):
            ctk.CTkLabel(c, text="未配置反馈邮箱（可在 config.json 的 feedback_mail 中添加）",
                         font=(theme.FONT, 11), text_color=theme.MUTED).pack(anchor="w", pady=4)
        tip = ctk.CTkLabel(dlg, text="点「写邮件」会打开你电脑的默认邮件客户端，"
                                     "主题已按软件名+版本预填。",
                           font=(theme.FONT, 11), text_color=theme.MUTED,
                           wraplength=460, justify="left")
        tip.pack(anchor="w", padx=26, pady=(10, 0))
        disclaimer = ctk.CTkLabel(dlg, text="本软件仅限本单位内部测试使用；清理删除的数据可能无法通过回收站完整恢复，"
                                            "详见首次启动时的《使用须知与免责声明》。",
                                  font=(theme.FONT, 11), text_color="#a8322e",
                                  wraplength=460, justify="left")
        disclaimer.pack(anchor="w", padx=26, pady=(6, 16))

        dlg.update_idletasks()
        w, h = 520, dlg.winfo_reqheight() + 20
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + (self.winfo_height() - h) // 2
        dlg.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")
        dlg.grab_set()

    def _copy_mail(self, addr):
        self.clipboard_clear()
        self.clipboard_append(addr)
        self.logger.log(f"已复制邮箱：{addr}")

    def _mail_to(self, addr):
        subject = f"[{APP_NAME} v{APP_VERSION} 构建{build_stamp()}] 问题反馈"
        try:
            os.startfile(f"mailto:{addr}?subject={subject}")  # noqa
            self.logger.log(f"已唤起邮件客户端：{addr}")
        except Exception as e:
            self.logger.log(f"唤起邮件客户端失败（可点「复制」手动发）：{e}")

    def confirm_danger(self, title, lines):
        """高风险操作模态确认框：红色警示条 + 逐条后果说明 + 确认/取消两键。
        必须在主线程调用（页面按钮回调内）。"""
        dlg = ctk.CTkToplevel(self, fg_color=theme.CARD)
        dlg.title(title)
        dlg.geometry("580x470")
        dlg.resizable(False, True)
        dlg.transient(self)
        dlg.attributes("-topmost", True)
        ok = {"v": False}

        band = ctk.CTkFrame(dlg, fg_color=theme.DANGER, corner_radius=0, height=52)
        band.pack(fill="x")
        ctk.CTkLabel(band, text=f"⚠  {title}", font=(theme.FONT, 15, "bold"),
                     text_color="#ffffff").pack(pady=12)

        body = ctk.CTkTextbox(dlg, font=(theme.FONT, 13), wrap="word",
                              fg_color="#fff8f7", text_color=theme.TEXT)
        body.pack(fill="both", expand=True, padx=16, pady=(14, 6))
        body.insert("1.0", "\n".join(lines))
        body.configure(state="disabled")

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=(6, 16))

        def _ok():
            ok["v"] = True
            dlg.destroy()

        ctk.CTkButton(btns, text="确认执行", height=38, font=(theme.FONT, 13, "bold"),
                      fg_color=theme.DANGER, hover_color=theme.DANGER_HOVER,
                      command=_ok).pack(side="right", padx=(10, 0), ipadx=10)
        ctk.CTkButton(btns, text="取消", height=38, font=(theme.FONT, 13),
                      fg_color="#eceff4", text_color=theme.TEXT,
                      hover_color="#dde3ec",
                      command=dlg.destroy).pack(side="right", ipadx=14)

        # 居中到主窗
        dlg.update_idletasks()
        self.update_idletasks()
        w, h = 580, max(470, dlg.winfo_reqheight())
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + (self.winfo_height() - h) // 2
        dlg.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")
        dlg.grab_set()
        dlg.wait_window()
        return ok["v"]

    def run_bg(self, fn, on_done=None, on_error=None):
        """后台线程执行 fn，UI 不卡死。回调经队列回主线程执行。"""

        def wrap():
            try:
                res = fn()
            except Exception as e:  # noqa
                err = f"后台任务出错：{e}"
                self.logger.log(err)
                if on_error:
                    self._ui_queue.put(("call", on_error, e))
                return
            if on_done:
                self._ui_queue.put(("call", on_done, res))

        threading.Thread(target=wrap, daemon=True).start()

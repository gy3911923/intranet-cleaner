# -*- coding: utf-8 -*-
"""GUI 冒烟：启动主窗、切换五个页签、2 秒后自动退出。"""
import io
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from core.config import load_config  # noqa
from core.logger import Logger  # noqa


def main():
    from ui.app import App
    cfg = load_config()
    log = Logger(logfile=os.path.join(tempfile.gettempdir(), "cleaner_test_gui.log"))
    app = App(cfg, log)
    order = ["browser", "wps", "downloads", "search", "software"]

    def step(i=0):
        if i >= len(order):
            page = app._pages.get("search")
            n = len(page.chip_vars) if page else 0
            print(f"关键词 chips 数量: {n}")
            assert n > 0, "关键词 chips 为空！"
            app.update()
            # 日志面板：默认收起 40px，展开后 220px（折叠设计）
            h_closed = app.logbox.winfo_height()
            app._toggle_log()
            app.update()
            h_open = app.logbox.winfo_height()
            print(f"日志面板高度：收起 {h_closed}px / 展开 {h_open}px")
            assert app.log_open and h_open > h_closed, "日志面板展开异常！"
            app._toggle_log()
            print("GUI 冒烟：5 个页签全部切换成功")
            app.destroy()
            return
        app.show_page(order[i])
        app.update()
        print(f"  页签切换 OK: {order[i]}")
        app.after(150, lambda: step(i + 1))

    app.after(300, step)
    app.mainloop()
    print("结果：GUI 冒烟 PASS")


if __name__ == "__main__":
    main()

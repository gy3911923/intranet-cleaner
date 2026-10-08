# -*- coding: utf-8 -*-
"""内网检查清理工具 — 入口。

绿色单文件 exe（PyInstaller --onefile），双击即用。
config.json 与 exe 同目录，关键词黑名单/检索词可手动编辑。
"""
import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import config as cfgmod  # noqa
from core.config import APP_NAME, APP_VERSION, CONFIG_PATH, load_config, save_config, app_dir  # noqa
from core.logger import Logger  # noqa


def _try_elevate(cfg):
    """非管理员且配置允许时，自动请求管理员权限重启自身（UAC 弹窗）。

    目的：消除"权限不足"类删除失败（Program Files/其他用户目录/受保护路径）。
    仅打包版生效（源码运行测试场景不提权）；用户取消 UAC 则按普通权限继续，
    并在日志中说明能力受限。config.json 的 auto_elevate=false 可永久关闭。
    """
    if not getattr(sys, "frozen", False):
        return False
    if not cfg.get("auto_elevate", True):
        return False
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return False    # 已是管理员
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, None, None, 1)
        return rc > 32      # 用户确认 UAC，已交棒给管理员实例
    except Exception:
        return False


def main():
    if sys.platform == "win32":
        try:  # 高 DPI 适配
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    cfg = load_config()

    # 管理员自动提权（先于一切 UI；用户取消 UAC 则按普通权限继续）
    if _try_elevate(cfg):
        return

    # 首次运行落盘默认配置（便于手动编辑关键词）；启动落盘不动备份
    if not save_config(cfg, roll_backup=False):
        print(f"警告：配置文件写入失败，请检查目录权限：{CONFIG_PATH}")
    cfgmod.seed_backup()   # 首启播种安全网（分发目录无需随带 .bak）

    log = Logger(logfile=os.path.join(app_dir(), "操作日志.log"),
                 max_lines=cfg.get("log_max_lines", 2000))

    # 全局异常捕获：windowed 模式下异常不可见，全部落日志便于定位
    def _excepthook(t, v, tb):
        log.log(f"[异常] {''.join(__import__('traceback').format_exception(t, v, tb))}")
    sys.excepthook = _excepthook

    for w in cfgmod.LOAD_WARNINGS:
        log.log("配置告警：" + w)
    log.log(f"{APP_NAME} v{APP_VERSION} 启动（构建 {cfgmod.build_stamp()}）")
    log.log(f"配置文件：{CONFIG_PATH}")
    log.log("删除操作统一送入回收站，可在回收站恢复")
    try:
        if not ctypes.windll.shell32.IsUserAnAdmin():
            log.log("提示：当前未以管理员身份运行，受保护目录中的文件可能无法删除"
                    "（config.json 中 auto_elevate=false 可关闭自动提权）")
    except Exception:
        pass
    if not cfg.get("search_keywords"):
        _bak_n = cfgmod.backup_keyword_count()
        if _bak_n:
            log.log(f"提示：当前关键词为空，但 config.json.bak 备份中保留着 {_bak_n} 个关键词"
                    f"（可从该备份文件手工恢复，或用界面重新录入）")

    try:
        from ui.app import App
    except ImportError as e:
        # 常见场景：用系统 Python 直接跑源码（依赖装在项目 .venv 中）
        msg = (f"启动失败：缺少依赖（{e}）。\n\n"
               f"源码运行请使用项目虚拟环境：\n"
               f"  .venv\\Scripts\\python.exe app\\main.py\n"
               f"或直接双击运行打包好的 dist\\IntranetCleaner.exe。")
        log.log(f"[启动失败] 缺少依赖：{e}")
        print(msg)
        try:
            import tkinter.messagebox as mb
            mb.showerror("检查清理工具 启动失败", msg)
        except Exception:
            pass
        return
    app = App(cfg, log)

    # 首次启动免责声明：不同意则退出
    if not app.show_first_run_disclaimer():
        log.log("用户未同意使用须知，程序退出")
        app.destroy()
        return

    app.offer_keyword_restore()   # 关键词被清空时提示从备份一键恢复

    app.mainloop()


if __name__ == "__main__":
    main()

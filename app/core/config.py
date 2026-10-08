# -*- coding: utf-8 -*-
"""配置管理：config.json 读写，关键词列表预留手动配置入口。"""
import json
import os
import sys
import time

APP_NAME = "检查清理工具"
APP_VERSION = "1.9.5"


def build_stamp():
    """本次构建时间（判断"手里这份是不是最新"的唯一可靠依据）。

    frozen 下取 exe 自身的修改时间；源码模式下取本文件修改时间。
    显示在侧栏与关于弹窗——历史上多次出现"打开了旧副本以为还是新 bug"的误判。
    """
    try:
        path = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
        return time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
    except Exception:
        return "--"


def app_dir():
    """程序所在目录（兼容 PyInstaller onefile：配置固定放在 exe 旁边，便于手动编辑）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # 源码模式：config.py -> core -> app -> 项目根
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def tools_dir():
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # onefile 解包临时目录
    else:
        base = app_dir()
    return os.path.join(base, "tools")


CONFIG_PATH = os.path.join(app_dir(), "config.json")

# 配置加载过程中的告警（main.py 启动后写入日志）
LOAD_WARNINGS = []

DEFAULT_CONFIG = {
    # ---- 需移除软件黑名单（功能1）：软件名包含任一关键词即标记 ----
    "remove_keywords": [],
    # ---- 文件检索关键词（功能5）：搜索页默认关键词，可在界面增删 ----
    "search_keywords": [],
    # ---- 下载目录（功能4），支持 %USERPROFILE% 等环境变量 ----
    "download_dirs": ["%USERPROFILE%\\Downloads"],
    # ---- 检索结果上限 ----
    "search_max_results": 3000,
    # ---- 检索引擎：everything(文件名) / anytxt(文档内容) ----
    "search_engine": "everything",
    # ---- 检索盘符：留空=自动取本机全部本地固定硬盘（U盘/光驱/网络盘自动排除）----
    #     如需限定或追加，手工填写如 ["C:", "D:", "E:", "F:", "G:"]
    "search_drives": [],
    # ---- 浏览器清理：自动结束占用中的浏览器进程 ----
    "auto_kill_browser": True,
    # 启动时非管理员自动请求提权重启（UAC 一次）；false = 不提权（受保护目录可能删不掉）
    "auto_elevate": True,
    "log_max_lines": 2000,
}


def _embedded_config_path():
    """打包时嵌入的 config.json（--add-data "config.json;."）。"""
    if getattr(sys, "frozen", False):
        p = os.path.join(sys._MEIPASS, "config.json")  # noqa
        return p if os.path.isfile(p) else None
    return None


def load_config():
    """三级加载：exe 旁外置 > 打包嵌入 > 默认。首次运行自动导出嵌入版。"""
    cfg = dict(DEFAULT_CONFIG)
    source = None
    if os.path.exists(CONFIG_PATH):
        source = CONFIG_PATH
    else:
        emb = _embedded_config_path()
        if emb:
            # 首次运行：导出嵌入版到 exe 旁，目标机可继续手动编辑
            try:
                import shutil
                shutil.copyfile(emb, CONFIG_PATH)
                source = CONFIG_PATH
            except OSError:
                source = emb
    if source:
        try:
            with open(source, "r", encoding="utf-8") as f:
                user = json.load(f)
            if isinstance(user, dict):
                cfg.update(user)
            else:
                raise ValueError("配置内容不是 JSON 对象")
        except Exception as e:
            # 配置损坏：先备份再回落默认值，避免关键词等数据无声丢失
            try:
                import shutil as _sh
                import time as _t
                bak = f"{source}.bak.{_t.strftime('%Y%m%d-%H%M%S')}"
                _sh.copyfile(source, bak)
                LOAD_WARNINGS.append(
                    f"配置文件解析失败（{e}），已备份为 {bak}，本次使用默认配置")
            except Exception:
                LOAD_WARNINGS.append(
                    f"配置文件解析失败（{e}），且备份失败，本次使用默认配置")
    # 废弃键清理：免责声明同意状态改为机器级标记（%APPDATA%），不再随配置分发
    cfg.pop("agreed_disclaimer", None)
    return cfg


def _read_keyword_count(path):
    """读取某配置文件的检索词数量；解析失败返回 None。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        k = d.get("search_keywords")
        return len(k) if isinstance(k, list) else 0
    except Exception:
        return None


def save_config(cfg, roll_backup=True):
    """原子写配置；roll_backup=True 时滚动保留一份 config.json.bak。

    备份策略针对"关键词被误删清空"这一事故：**只有新配置的词数不少于当前文件时
    才滚动覆盖备份**，保证备份始终保存着"词最全的那一版"，不会被一次误删抹掉。
    启动时的默认落盘应传 roll_backup=False（那不是用户编辑，不该动备份）。
    写盘失败返回 False。
    """
    try:
        if roll_backup and os.path.exists(CONFIG_PATH):
            cur = _read_keyword_count(CONFIG_PATH)
            new = len(cfg.get("search_keywords") or [])
            if cur is not None and new >= cur:
                # 仅当当前文件可解析且词数不减时才滚动备份；
                # 解析失败（cur=None）时绝不用坏数据覆盖健康备份（Marvis N2）
                try:
                    import shutil as _sh
                    _sh.copyfile(CONFIG_PATH, CONFIG_PATH + ".bak")
                except Exception:
                    pass                        # 备份失败不阻断保存
            elif cur is None:
                # 坏文件另存一份供排查，不进入备份链
                try:
                    import shutil as _sh
                    _sh.copyfile(CONFIG_PATH, CONFIG_PATH + ".corrupt")
                except Exception:
                    pass
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)   # 原子写，防写一半损坏
        return True
    except Exception:
        return False


def seed_backup():
    """首启播种：主配置完好且无备份时，生成 config.json.bak。

    使分发目录无需随带 .bak（避免多一份名单副本流转），目标机首次运行
    即自建安全网。幂等：已有备份时不覆盖。
    """
    try:
        if os.path.exists(CONFIG_PATH + ".bak"):
            return False
        if (_read_keyword_count(CONFIG_PATH) or 0) > 0:
            import shutil as _sh
            _sh.copyfile(CONFIG_PATH, CONFIG_PATH + ".bak")
            return True
    except Exception:
        pass
    return False


def backup_keyword_count():
    """读取 config.json.bak 里的关键词数量（无备份/读取失败返回 None）。"""
    return _read_keyword_count(CONFIG_PATH + ".bak")


def restore_keywords_from_backup():
    """从 config.json.bak 恢复关键词列表，返回恢复的词数（失败返回 0）。"""
    try:
        with open(CONFIG_PATH + ".bak", "r", encoding="utf-8") as f:
            kws = json.load(f).get("search_keywords") or []
        if not isinstance(kws, list):
            return 0
        cfg = load_config()
        cfg["search_keywords"] = kws
        save_config(cfg, roll_backup=False)     # 恢复动作不覆盖备份
        return len(kws)
    except Exception:
        return 0

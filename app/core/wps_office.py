# -*- coding: utf-8 -*-
"""WPS / Office 本地缓存与最近打开记录清理。"""
import os

from .registry import clear_office_mru, clear_wps_mru
from .util import expand, path_size

# (标签, 路径模板, 组别)  仅展示实际存在的项
WPS_CACHE = [
    ("WPS 自动备份", r"%APPDATA%\kingsoft\office6\backup", "备份"),
    ("WPS 缓存", r"%APPDATA%\kingsoft\office6\cache", "缓存"),
    ("WPS 云文档本地缓存", r"%LOCALAPPDATA%\Kingsoft\WPS Cloud Files", "缓存"),
    ("WPS 崩溃转储", r"%APPDATA%\kingsoft\office6\log", "缓存"),
]

OFFICE_CACHE = [
    ("Office 文件缓存(16.0)", r"%LOCALAPPDATA%\Microsoft\Office\16.0\OfficeFileCache", "缓存"),
    ("Office 文件缓存(15.0)", r"%LOCALAPPDATA%\Microsoft\Office\15.0\OfficeFileCache", "缓存"),
    ("Office 未保存草稿(Word)", r"%APPDATA%\Microsoft\Word", "草稿"),
    ("Office 未保存草稿(Excel)", r"%APPDATA%\Microsoft\Excel", "草稿"),
    ("Office 未保存草稿(PowerPoint)", r"%APPDATA%\Microsoft\PowerPoint", "草稿"),
]


def collect_items():
    items = []
    for label, pat, grp in WPS_CACHE + OFFICE_CACHE:
        p = expand(pat)
        if os.path.exists(p):
            items.append({"label": label, "path": p, "group": grp,
                          "size": path_size(p)})
    return items


def clean_cache(items, log):
    """缓存目录/文件送回收站。返回 (成功数, 失败明细)。"""
    from .util import delete_to_recycle
    ok, fail = 0, []
    for it in items:
        o, f = delete_to_recycle([it["path"]], log)
        ok += o
        fail.extend(f)
    return ok, fail


def clean_recent(log):
    """Office + WPS 最近打开记录（注册表 MRU + Recent LNK）。"""
    c1, c2 = clear_office_mru(log)
    c3 = clear_wps_mru(log)
    return {"office_reg": c1, "office_lnk": c2, "wps_reg": c3}

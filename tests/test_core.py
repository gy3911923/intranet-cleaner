# -*- coding: utf-8 -*-
"""headless 核心逻辑自检（不启 GUI）。"""
import io
import json
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from core import browsers, downloads, everything, registry, wps_office  # noqa
from core.config import load_config, save_config  # noqa
from core.util import delete_to_recycle, human_size, path_size  # noqa

PASS, FAIL = 0, []


def check(name, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  {extra}")


print("== 1. config 读写 ==")
# 备份真实配置，测试后恢复，避免污染词表
import shutil as _sh
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CFG = os.path.join(_ROOT, "config.json")
_cfg_backup = None
if os.path.exists(_CFG):
    _sh.copyfile(_CFG, _CFG + ".testbak")
    _cfg_backup = _CFG + ".testbak"
cfg = load_config()
check("默认配置加载", isinstance(cfg, dict) and "remove_keywords" in cfg)
cfg["search_keywords"] = ["测试词A"]
save_config(cfg)
cfg2 = load_config()
check("配置持久化", cfg2.get("search_keywords") == ["测试词A"])
if _cfg_backup:
    _sh.move(_cfg_backup, _CFG)

print("== 2. 已装软件扫描 ==")
items = registry.list_installed(["chrome"])
check("软件列表非空", len(items) > 10, f"n={len(items)}")
names = [i["name"] for i in items]
print(f"  共 {len(items)} 款软件，前5：{names[:5]}")
flagged = [i for i in items if i["flagged"]]
check("黑名单标记生效", all("chrome" in i["name"].lower() for i in flagged) and len(flagged) >= 0)
drives = registry.list_drives_usage()
check("磁盘概览", len(drives) >= 1, str(drives))

print("== 3. 浏览器检测 ==")
found = browsers.detect()
for b in found:
    print(f"  - {b['name']}: {len(b['profiles'])} 个 profile, running={b['running']}")
check("至少检测到一款浏览器", len(found) >= 1)
if found:
    items_b = browsers.collect_items(found, list(browsers.CHROMIUM_GROUPS.keys()))
    total = sum(i["size"] for i in items_b)
    print(f"  待清项 {len(items_b)} 个，合计 {human_size(total)}")
    KEEP = {"bookmarks", "bookmarks.bak", "preferences", "secure preferences",
            "extensions", "local extension settings", "sync data",
            "extension state", "extension scripts", "extension rules"}
    bad = [i["path"] for i in items_b
           if os.path.basename(i["path"]).lower() in KEEP]
    check("收藏夹/设置/扩展绝不在待清列表", not bad, str(bad[:3]))

print("== 4. WPS/Office 缓存与 MRU ==")
oc = wps_office.collect_items()
print(f"  缓存项 {len(oc)}：{[(i['label'], human_size(i['size'])) for i in oc]}")
check("缓存扫描可执行", isinstance(oc, list))

print("== 5. 检索引擎 ==")
es_ok = everything.es_available()
print(f"  es.exe 存在：{es_ok}")
if es_ok:
    ok = everything.ensure_everything(timeout=25, log=print)
    print(f"  Everything 就绪：{ok}")
    if ok:
        eng, res = everything.search("config.json", 50, log=print)
        print(f"  引擎={eng}，命中 {len(res)}，示例：{res[:2]}")
        check("es 检索返回结果", eng == "everything" and len(res) >= 1)
else:
    eng, res = everything.search("config.json", 50, log=print)
    check("兜底扫描可用", eng == "scan" and len(res) >= 1)

print("== 6. 下载目录 ==")
dl = downloads.list_files("%USERPROFILE%\\Downloads")
print(f"  {downloads.summary(dl)}")

print("== 7. 回收站删除 ==")
tmp = os.path.join(tempfile.gettempdir(), "cleaner_test_recycle.txt")
with open(tmp, "w") as f:
    f.write("recycle test")
ok_n, fail = delete_to_recycle([tmp], print)
check("回收站删除成功", ok_n == 1 and os.path.exists(tmp) is False, str(fail))

print()
print(f"结果：PASS {PASS}，FAIL {len(FAIL)} {FAIL if FAIL else ''}")
sys.exit(1 if FAIL else 0)

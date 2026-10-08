# -*- coding: utf-8 -*-
"""浏览器清理（Chrome/Edge/QQ/360/Firefox）。

策略（依据 BleachBit cleaner 定义 + 保收藏夹要求）：
- Chromium 系：删除内容数据文件/目录（历史/Cookie/密码/自动填充/缓存/会话/站点数据），
  保留 Bookmarks、Preferences、Secure Preferences、Extensions、Sync Data。
- Firefox：收藏夹与历史同库（places.sqlite），不能删文件——用 sqlite 清空
  moz_historyvisits/moz_places（保留书签锚点），Cookie/密码/表单/缓存直接删文件。
- 全部删除走回收站（send2trash），清理前检测/可结束浏览器进程。
"""
import os
import sqlite3

from .util import expand, path_size, delete_to_recycle

# ---------------- 浏览器定义 ----------------

CHROMIUM_BROWSERS = [
    ("Google Chrome", r"%LocalAppData%\Google\Chrome\User Data", ["chrome.exe"]),
    ("Microsoft Edge", r"%LocalAppData%\Microsoft\Edge\User Data", ["msedge.exe"]),
    ("QQ浏览器", r"%LocalAppData%\Tencent\QQBrowser\User Data", ["QQBrowser.exe"]),
    ("360极速浏览器", r"%LocalAppData%\360Chrome\Chrome\User Data", ["360chrome.exe"]),
    ("360安全浏览器", r"%APPDATA%\360se6\User Data", ["360se.exe"]),
]

FIREFOX = ("Mozilla Firefox", ["firefox.exe"])

# ---------------- 未知 Chromium 浏览器自动识别（单位定制安全浏览器等）----------------
# 判定源=卸载注册表（浏览器类软件必然登记为已安装程序且名称含"浏览器/Browser"），
# 不做纯文件系统扫描——Electron 应用（AI 助手/工具软件）内嵌 Chromium 数据目录，
# 文件特征无法区分浏览器与应用，误清会毁掉应用数据。

def _browser_uninstall_entries():
    """枚举卸载注册表中名称含"浏览器/Browser"的条目。返回 [(DisplayName, InstallLocation)]。"""
    import winreg
    out = []
    seen = set()
    for root, path in ((winreg.HKEY_LOCAL_MACHINE,
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                       (winreg.HKEY_LOCAL_MACHINE,
                        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                       (winreg.HKEY_CURRENT_USER,
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")):
        try:
            k = winreg.OpenKey(root, path)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(k)[0]):
            try:
                sub = winreg.EnumKey(k, i)
                sk = winreg.OpenKey(k, sub)
                name = str(winreg.QueryValueEx(sk, "DisplayName")[0]).strip()
                low = name.lower()
                if not name or not ("浏览器" in name or "browser" in low):
                    continue
                if name in seen:
                    continue
                seen.add(name)
                loc = ""
                for v in ("InstallLocation", "DisplayIcon"):
                    try:
                        loc = str(winreg.QueryValueEx(sk, v)[0])
                        break
                    except OSError:
                        pass
                out.append((name, loc))
            except OSError:
                continue
    return out


def _resolve_user_data(name, install_loc):
    """为已登记浏览器定位 User Data 目录；找不到返回 None。"""
    import glob

    def valid(ud):
        if not os.path.isdir(ud):
            return False
        for d in os.listdir(ud):
            p = os.path.join(ud, d)
            if not os.path.isdir(p):
                continue
            probe = [os.path.join(p, "History"), os.path.join(p, "Cookies"),
                     os.path.join(p, "Network", "Cookies")]
            if any(os.path.exists(f) for f in probe):
                return True
        return False

    def scan_children(base, depth=1):
        """在 base 下 depth 层内找名为 User Data 且有效的目录。"""
        if depth < 0 or not os.path.isdir(base):
            return None
        ud = os.path.join(base, "User Data")
        if os.path.isdir(ud) and valid(ud):
            return ud
        if depth > 0:
            try:
                for d in os.listdir(base):
                    p = os.path.join(base, d)
                    if os.path.isdir(p):
                        r = scan_children(p, depth - 1)
                        if r:
                            return r
            except OSError:
                pass
        return None

    # 1) 安装目录（含 DisplayIcon 所在目录）1~2 层
    for loc in (install_loc, os.path.dirname(install_loc) if install_loc else ""):
        if loc:
            loc = loc.strip('"').split(",-")[0].strip()
            if os.path.isdir(loc):
                r = scan_children(loc, 2)
                if r:
                    return r
    # 2) LocalAppData / AppData 按名称匹配（全名或去空格）
    tokens = {name.replace(" ", ""), name.replace(" ", "").replace("浏览器", "")}
    for env in (r"%LocalAppData%", r"%APPDATA%"):
        base = expand(env)
        if not os.path.isdir(base):
            continue
        for cand in list(tokens) + [name]:
            for pattern in (os.path.join(base, cand, "User Data"),
                            os.path.join(base, cand, "*", "User Data")):
                for ud in glob.glob(pattern):
                    if valid(ud):
                        return ud
    return None


def discover_unknown_chromium(known_bases, candidates=None, log=None):
    """识别未登记的定制浏览器（如单位配发的安全浏览器）。

    candidates: [(DisplayName, InstallLocation)]；None 则枚举卸载注册表中
    名称含"浏览器/Browser"的条目。对每个条目定位其 User Data 目录并验证
    Chromium 数据特征（profile 内 History/Cookies），通过才登记。
    返回与 detect() 同结构的浏览器 dict 列表（kind=chromium）。
    """
    known = {os.path.normcase(os.path.normpath(b)) for b in known_bases if b}
    if candidates is None:
        candidates = _browser_uninstall_entries()
    found, seen = [], set()
    for name, loc in candidates:
        ud = _resolve_user_data(name, loc)
        if not ud:
            if log:
                log(f"自动识别：{name} 已登记但未定位到 User Data 数据目录，跳过")
            continue
        nc = os.path.normcase(os.path.normpath(ud))
        if nc in seen or any(nc == k or nc.startswith(k + os.sep)
                             for k in known):
            continue
        seen.add(nc)
        profiles = [os.path.join(ud, d) for d in sorted(os.listdir(ud))
                    if os.path.isdir(os.path.join(ud, d))
                    and (d == "Default" or d.startswith("Profile "))]
        if not profiles:
            profiles = [os.path.join(ud, d) for d in sorted(os.listdir(ud))
                        if os.path.isdir(os.path.join(ud, d))
                        and any(os.path.exists(os.path.join(ud, d, f))
                                for f in ("History", "Cookies",
                                          os.path.join("Network", "Cookies")))]
        found.append({"kind": "chromium", "discover": True, "procs": [],
                      "name": name, "base": ud, "profiles": profiles,
                      "running": False})
    if found and log:
        log("自动识别到未登记的浏览器：" + "、".join(b["name"] for b in found))
    return found


def _discover_procs(base):
    """按可执行文件路径找占用该浏览器目录的进程名（用于结束进程）。"""
    try:
        from .util import run_hidden
        script = ("Get-Process | Where-Object { $_.Path -like '"
                  + base.replace("'", "''") + "*' } | "
                  "Select-Object -Unique -ExpandProperty Name")
        r = run_hidden(["powershell", "-NoProfile", "-Command", script], timeout=20)
        out = r.stdout.decode("utf-8", errors="replace")
        return sorted({l.strip() for l in out.splitlines() if l.strip()})
    except Exception:
        return []

# Chromium 每个 profile 的清理清单：组名 -> (文件名列表, 目录名列表)
CHROMIUM_GROUPS = {
    "历史记录": (["History", "History-journal", "Archived History", "Archived History-journal",
                 "Top Sites", "Top Sites-journal", "Shortcuts", "Shortcuts-journal",
                 "Visited Links", "Thumbnails", "Thumbnails-journal", "Media History",
                 "Network Action Predictor", "Network Action Predictor-journal",
                 "DIPS", "DownloadMetadata", "History Provider Cache",
                 "Favicons", "Favicons-journal"], []),
    "Cookie": (["Cookies", "Cookies-journal",
                r"Network\Cookies", r"Network\Cookies-journal",
                "Extension Cookies", "Extension Cookies-journal",
                "TransportSecurity",
                r"..\Safe Browsing Cookies", r"..\Safe Browsing Cookies-journal"], []),
    "保存的密码": (["Login Data", "Login Data-journal",
                  "Login Data For Account", "Login Data For Account-journal"], []),
    "自动填充": (["Web Data", "Web Data-journal"], []),
    "缓存": ([], ["Cache", "Code Cache", "GPUCache", "Media Cache",
                "Application Cache", "DawnCache",
                r"..\GrShaderCache", r"..\ShaderCache", r"..\GraphiteDawnCache",
                r"..\component_crx_cache", r"..\extensions_crx_cache",
                r"..\Safe Browsing Channel IDs", r"..\Safe Browsing Channel IDs-journal"]),
    "会话/最近关闭": ([], ["Sessions", "Session Storage"],
                 ),
    "站点数据(LocalStorage等)": ([], ["Local Storage", "IndexedDB", "Service Worker"]),
}
# User Data 根目录的会话残留
CHROMIUM_UD_ROOT_FILES = ["chrome_shutdown_ms.txt"]

CHROMIUM_KEEP = {"bookmarks", "bookmarks.bak", "preferences", "secure preferences",
                 "extensions", "local extension settings", "sync data",
                 "extension state", "extension scripts", "extension rules"}

FIREFOX_GROUPS_FILES = {
    "Cookie": ["cookies.sqlite", "cookies.sqlite-wal", "cookies.sqlite-shm"],
    "保存的密码": ["logins.json", "key4.db", "logins-backup.json"],
    "自动填充": ["formhistory.sqlite"],
    "会话/最近关闭": ["sessionstore.js", "recovery.jsonlz4", "previous.jsonlz4",
                   "sessionstore-backups"],
}


def _proc_running(image):
    try:
        from .util import run_hidden
        r = run_hidden(["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"], timeout=10)
        return image.lower() in r.stdout.decode("gbk", errors="replace").lower()
    except Exception:
        return False


def detect():
    """返回浏览器检测结果：名称、profile 列表、进程占用。"""
    found = []
    for name, base_pat, procs in CHROMIUM_BROWSERS:
        base = expand(base_pat)
        if not os.path.isdir(base):
            continue
        profiles = []
        for d in sorted(os.listdir(base)):
            p = os.path.join(base, d)
            if not os.path.isdir(p):
                continue
            if d == "Default" or d.startswith("Profile "):
                profiles.append(p)
            elif name.startswith("360安全"):
                # 360se6 目录结构不统一：凡含 History/Cookies 的子目录均视为 profile
                probe = [os.path.join(p, "History"), os.path.join(p, "Cookies"),
                         os.path.join(p, "Network", "Cookies")]
                if any(os.path.exists(f) for f in probe):
                    profiles.append(p)
        running = any(_proc_running(x) for x in procs)
        found.append({"kind": "chromium", "name": name, "base": base,
                      "profiles": profiles, "procs": procs, "running": running})
    ff_dir = expand(r"%APPDATA%\Mozilla\Firefox\Profiles")
    if os.path.isdir(ff_dir):
        profiles = [os.path.join(ff_dir, d) for d in sorted(os.listdir(ff_dir))
                    if os.path.isdir(os.path.join(ff_dir, d))]
        if profiles:
            ff_cache = expand(r"%LOCALAPPDATA%\Mozilla\Firefox\Profiles")
            found.append({"kind": "firefox", "name": FIREFOX[0], "base": ff_dir,
                          "profiles": profiles, "cache_base": ff_cache,
                          "procs": FIREFOX[1],
                          "running": any(_proc_running(x) for x in FIREFOX[1])})
    # 未知 Chromium 浏览器自动识别（单位定制安全浏览器等）
    known_bases = [b["base"] for b in found if b["kind"] == "chromium"]
    found.extend(discover_unknown_chromium(known_bases))
    # 自动识别的浏览器：按路径识别运行中进程
    for b in found:
        if b.get("discover"):
            procs = _discover_procs(b["base"])
            b["procs"] = procs
            b["running"] = bool(procs) or any(_proc_running(x) for x in procs)
    return found


def kill_processes(browsers):
    """结束相关浏览器进程。返回被结束的进程名列表。"""
    killed = []
    names = set()
    for b in browsers:
        names.update(b.get("procs", []))
    for n in names:
        try:
            from .util import run_hidden
            run_hidden(["taskkill", "/F", "/IM", n, "/T"], timeout=15)
            killed.append(n)
        except Exception:
            pass
    return killed


def collect_items(browsers, groups, log=None):
    """按勾选的组收集清理项。

    返回 [{browser, group, path, kind, size, special}]。
    browser 键必须保留：page_browser.clean() 依赖它做"勾选了哪款浏览器就只清哪款"
    的范围过滤（v1.8.6 修复 P1-2：此前无此键导致过滤判据恒假、越权删除）。
    """
    items = []
    for b in browsers:
        _mark = len(items)          # 本浏览器产出的条目起点
        if b["kind"] == "chromium":
            for prof in b["profiles"]:
                for g in groups:
                    if g not in CHROMIUM_GROUPS:
                        continue
                    files, dirs = CHROMIUM_GROUPS[g]
                    for f in files:
                        p = os.path.normpath(os.path.join(prof, f))
                        if os.path.exists(p):
                            items.append({"group": g, "path": p, "kind": "file",
                                          "size": path_size(p), "special": None})
                    for d in dirs:
                        p = os.path.normpath(os.path.join(prof, d))
                        if os.path.isdir(p):
                            items.append({"group": g, "path": p, "kind": "dir",
                                          "size": path_size(p), "special": None})
                if "历史记录" in groups:   # 仅在勾选范围内收集，避免越权删除
                    for f in CHROMIUM_UD_ROOT_FILES:
                        p = os.path.join(b["base"], f)
                        if os.path.exists(p):
                            items.append({"group": "历史记录", "path": p, "kind": "file",
                                          "size": path_size(p), "special": None})
        else:  # firefox
            for prof in b["profiles"]:
                cache_prof = os.path.join(b["cache_base"], os.path.basename(prof))
                for g in groups:
                    if g in FIREFOX_GROUPS_FILES:
                        for f in FIREFOX_GROUPS_FILES[g]:
                            p = os.path.join(prof, f)
                            if os.path.exists(p):
                                items.append({"group": g, "path": p, "kind": "file",
                                              "size": path_size(p), "special": None})
                    elif g == "历史记录":
                        p = os.path.join(prof, "places.sqlite")
                        if os.path.exists(p):
                            items.append({"group": g, "path": p, "kind": "file",
                                          "size": path_size(p),
                                          "special": "firefox_history"})
                    elif g == "缓存":
                        p = os.path.join(cache_prof, "cache2")
                        if os.path.isdir(p):
                            items.append({"group": g, "path": p, "kind": "dir",
                                          "size": path_size(p), "special": None})
                    elif g == "站点数据(LocalStorage等)":
                        p = os.path.join(prof, "storage", "default")
                        if os.path.isdir(p):
                            items.append({"group": g, "path": p, "kind": "dir",
                                          "size": path_size(p),
                                          "special": "firefox_storage"})
        for it in items[_mark:]:    # 全部条目带上所属浏览器（P1-2 修复）
            it["browser"] = b["name"]
    # 二道防线：无论分组如何配置，保留项（收藏夹/设置/扩展）一律剔除
    return filter_keep(items, log)


def filter_scope(items, browser_names, groups):
    """按勾选的浏览器与清理组过滤删除范围（P1-2 修复的落点）。

    删除范围 = 勾选浏览器 ∩ 勾选组。browser 键缺失的条目一律排除
    （宁可漏删不可越权删）。page_browser.clean() 与单测共用本函数。
    """
    names = set(browser_names)
    gs = set(groups)
    return [i for i in items
            if i.get("group") in gs and i.get("browser") in names]


def filter_keep(items, log=None):
    """安全校验：剔除保留项（收藏夹/设置/扩展），返回安全清单。"""
    safe, blocked = [], []
    for it in items:
        if os.path.basename(it["path"]).lower() in CHROMIUM_KEEP:
            blocked.append(it["path"])
            continue
        safe.append(it)
    if blocked and log:
        log(f"安全校验：已跳过 {len(blocked)} 个保留项（收藏夹/设置/扩展）")
    return safe


def clean_firefox_history(db_path, log):
    """sqlite 清历史、保书签。失败则保留文件（返回 False）。"""
    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        try:
            cur.execute("PRAGMA secure_delete=ON")   # 防取证恢复已删历史
        except sqlite3.Error:
            pass
        cur.execute("DELETE FROM moz_historyvisits")
        cur.execute("""DELETE FROM moz_places WHERE id NOT IN
                       (SELECT fk FROM moz_bookmarks WHERE fk IS NOT NULL)""")
        for tbl in ("moz_inputhistory", "moz_annos", "moz_places_extra",
                    "moz_historyvisits_extra"):
            try:
                cur.execute(f"DELETE FROM {tbl}")
            except sqlite3.OperationalError:
                pass
        con.commit()
        cur.execute("VACUUM")
        con.close()
        log(f"[Firefox] 历史记录已清空（书签保留）：{db_path}")
        return True
    except Exception as e:
        log(f"[Firefox] 历史清理失败（已保留原文件）：{db_path} -> {e}")
        return False


def clean_firefox_storage(root, log):
    """删除 storage/default 下非扩展的站点存储。"""
    ok, fail = 0, []
    try:
        for d in os.listdir(root):
            if d.lower().startswith("moz-extension+++"):
                continue
            p = os.path.join(root, d)
            o, f = delete_to_recycle([p], log)
            ok += o
            fail.extend(f)
    except OSError as e:
        fail.append((root, str(e)))
    return ok, fail


def clean(items, log):
    """执行清理。返回 (成功数, 失败明细)。"""
    ok, fail = 0, []
    for it in items:
        sp, p = it.get("special"), it["path"]
        if sp == "firefox_history":
            if clean_firefox_history(p, log):
                ok += 1
            else:
                fail.append((p, "sqlite 清理失败，文件已保留"))
        elif sp == "firefox_storage":
            o, f = clean_firefox_storage(p, log)
            ok += o
            fail.extend(f)
        else:
            o, f = delete_to_recycle([p], log)
            ok += o
            fail.extend(f)
    return ok, fail

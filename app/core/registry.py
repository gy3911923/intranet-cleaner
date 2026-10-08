# -*- coding: utf-8 -*-
"""注册表：已装软件扫描、Office/WPS 最近打开记录（MRU）清理、磁盘概览。"""
import os
import shutil
import winreg

from .util import expand

UNINSTALL_ROOTS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]


def list_installed(remove_keywords=()):
    """返回已装软件列表；命中 remove_keywords 的条目 flagged=True。"""
    kws = [k.lower() for k in remove_keywords if k.strip()]
    items, seen = [], set()
    for hive, path in UNINSTALL_ROOTS:
        try:
            key = winreg.OpenKey(hive, path)
        except OSError:
            continue
        try:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(key, i)
                except OSError:
                    break
                i += 1
                try:
                    sk = winreg.OpenKey(key, sub)
                except OSError:
                    continue
                try:
                    def get(name):
                        try:
                            v, _ = winreg.QueryValueEx(sk, name)
                            return v
                        except OSError:
                            return ""
                    name = get("DisplayName")
                    if not name or name in seen:
                        continue
                    seen.add(name)
                    syst = get("SystemComponent")
                    if str(syst).strip() in ("1", "True", "true"):  # DWORD 实测为 int
                        continue
                    items.append({
                        "name": name,
                        "version": str(get("DisplayVersion")),
                        "publisher": str(get("Publisher")),
                        "size_kb": get("EstimatedSize") or 0,
                        "install_loc": get("InstallLocation"),
                        "uninstall": get("UninstallString"),
                        "quiet": get("QuietUninstallString"),
                        "flagged": any(k in name.lower() for k in kws),
                    })
                finally:
                    sk.Close()
        finally:
            key.Close()
    items.sort(key=lambda x: (not x["flagged"], x["name"].lower()))
    return items


def launch_uninstall(item):
    cmd = item.get("quiet") or item.get("uninstall")
    if not cmd:
        raise RuntimeError("该软件未提供卸载命令")
    os.startfile = os.startfile  # noqa - 保持可读
    import subprocess
    subprocess.Popen(cmd, shell=True)


def list_drives_usage():
    out = []
    for d in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        root = f"{d}:\\"
        if os.path.exists(root):
            try:
                u = shutil.disk_usage(root)
                out.append({"drive": root, "total": u.total, "free": u.free})
            except OSError:
                pass
    return out


# ---------------- MRU（最近打开记录） ----------------

def _delete_values_of_key(hive, path, log, counter):
    try:
        key = winreg.OpenKey(hive, path, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE)
    except OSError:
        return
    try:
        vals = []
        i = 0
        while True:
            try:
                vals.append(winreg.EnumValue(key, i)[0])
                i += 1
            except OSError:
                break
        for v in vals:
            try:
                winreg.DeleteValue(key, v)
                counter[0] += 1
            except OSError:
                pass
        if vals:
            log(f"  清空注册表值 {counter[0]} 项 <- {path}")
    finally:
        key.Close()


def _walk_keys(hive, path):
    """yield (子键全路径)。"""
    try:
        key = winreg.OpenKey(hive, path)
    except OSError:
        return
    try:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(key, i)
            except OSError:
                break
            i += 1
            full = f"{path}\\{sub}"
            yield full
            yield from _walk_keys(hive, full)
    finally:
        key.Close()


def clear_office_mru(log=None):
    """Office 各组件 File MRU / User MRU 值清空 + Recent 文件夹 LNK。"""
    counter = [0]
    for ver in ("15.0", "16.0"):
        for app in ("Word", "Excel", "PowerPoint", "OneNote", "Access"):
            base = rf"Software\Microsoft\Office\{ver}\{app}"
            _delete_values_of_key(winreg.HKEY_CURRENT_USER, rf"{base}\File MRU", log, counter)
            # User MRU 下还有 GUID 子键再套 File MRU
            for sub in _walk_keys(winreg.HKEY_CURRENT_USER, rf"{base}\User MRU"):
                if sub.lower().endswith("file mru"):
                    _delete_values_of_key(winreg.HKEY_CURRENT_USER, sub, log, counter)
    recent = expand(r"%APPDATA%\Microsoft\Office\Recent")
    removed = 0
    if os.path.isdir(recent):
        for f in os.listdir(recent):
            try:
                os.remove(os.path.join(recent, f))
                removed += 1
            except OSError:
                pass
    if log:
        log(f"Office 最近记录：注册表清空 {counter[0]} 项，Recent 目录删除 {removed} 个快捷方式")
    return counter[0], removed


def clear_wps_mru(log=None):
    """WPS：Kingsoft\\Office\\6.0 下所有含 Recent/FileMRU 的键，清空其值。"""
    counter = [0]
    root = r"Software\Kingsoft\Office\6.0"
    for sub in _walk_keys(winreg.HKEY_CURRENT_USER, root):
        low = sub.split("\\")[-1].lower()
        if "recent" in low or "filemru" in low or "file mru" in low:
            _delete_values_of_key(winreg.HKEY_CURRENT_USER, sub, log, counter)
    if log:
        log(f"WPS 最近记录：注册表清空 {counter[0]} 项")
    return counter[0]

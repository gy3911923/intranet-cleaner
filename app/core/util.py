# -*- coding: utf-8 -*-
"""通用工具：回收站删除、目录/文件体积计算、路径展开、隐藏窗口子进程。"""
import os
import subprocess
import traceback

CREATE_NO_WINDOW = 0x08000000


def run_hidden(args, timeout=15):
    """执行子进程且不弹 CMD 黑框。返回 CompletedProcess。"""
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return subprocess.run(args, capture_output=True, timeout=timeout,
                          startupinfo=si, creationflags=CREATE_NO_WINDOW)


def run_hidden_ok(args, timeout=15):
    return run_hidden(args, timeout=timeout).returncode == 0


def human_size(n):
    if n is None or n < 0:
        return "-"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0


def path_size(path):
    """文件或目录大小（字节）。统计失败按 0。"""
    try:
        if os.path.isfile(path):
            return os.path.getsize(path)
        total = 0
        for root, dirs, files in os.walk(path, onerror=lambda e: None):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        return total
    except OSError:
        return 0


def expand(p):
    return os.path.expandvars(os.path.expanduser(p))


def _humanize_delete_error(e, path):
    """把删除异常翻译成中文原因 + 处理建议（供日志与失败清单显示）。"""
    s = str(e)
    low = s.lower()
    winerror = getattr(e, "winerror", None) or getattr(e, "errno", None)
    if winerror == 32 or "being used by another process" in low:
        return "正被其他程序占用（请先关闭对应的浏览器/WPS/办公软件后重试）"
    if winerror == 5 or "access is denied" in low or "拒绝访问" in s:
        return "权限不足（请右键以管理员身份运行本软件）"
    if winerror == 2 or "cannot find" in low or "找不到" in s:
        return "文件已不存在（可能已被清理或移走）"
    if winerror == 206 or "filename or extension is too long" in low or len(path) > 240:
        return "路径过长（Windows 260 字符限制），请手动删除该文件"
    if "read-only" in low or "只读" in s:
        return "文件为只读属性，请去除只读后重试"
    return s[:120]


def delete_to_recycle(paths, log=None):
    """批量送回收站。返回 (成功数, 失败明细列表 [(路径, 中文原因), ...])。

    - 路径已不存在：视为已清理（计数成功，日志标注跳过）；
    - 超长路径（>240 字符）：自动加 \\\\?\\ 前缀重试一次；
    - 失败原因全部翻译为中文 + 处理建议。
    """
    ok, fail = 0, []
    from send2trash import send2trash
    for p in paths:
        try:
            if not os.path.exists(p):
                ok += 1
                if log:
                    log(f"[跳过] 文件已不存在（视为已清理）：{p}")
                continue
            try:
                send2trash(p)
            except Exception as first:
                # 长路径重试：\\?\ 前缀绕过 260 字符限制
                if len(p) > 240 and not p.startswith("\\\\?\\"):
                    send2trash("\\\\?\\" + os.path.abspath(p))
                else:
                    raise first
            ok += 1
            if log:
                log(f"[回收站] {p}")
        except Exception as e:
            # 事后复查：IFileOperation 偶发竞态（如杀毒扫描瞬间）会误报失败，
            # 但文件实际已删除——复查文件已消失即视为成功，消除假失败
            if not os.path.exists(p):
                ok += 1
                if log:
                    log(f"[回收站] {p}（接口报错但文件已删除，视为成功）")
                continue
            reason = _humanize_delete_error(e, p)
            fail.append((p, reason))
            if log:
                log(f"[失败] {p} -> {reason}")
    return ok, fail


def format_exc(e):
    return "".join(traceback.format_exception_only(type(e), e)).strip()


# ---- 检索盘符范围（内容检索与文件名兜底共用）----
DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3


def drive_type(letter):
    """GetDriveTypeW：2 可移动 / 3 本地固定 / 4 网络 / 5 光驱 / 0 未知。"""
    try:
        import ctypes
        return int(ctypes.windll.kernel32.GetDriveTypeW(f"{letter}:\\"))
    except Exception:
        return 0


def drive_scope():
    """检索盘符范围：默认 = 本机全部本地固定硬盘。

    U盘/移动硬盘、光驱、网络盘一律排除——现场 U 盘会被拔走，且通常没有
    内容索引，检索它只会报错刷屏。
    config.search_drives 非空时以其为准（手工指定，如 ["C:", "D:", "E:", "F:"]）。
    返回 (targets, excluded)，均为 str 列表：targets=['C:', ...]，
    excluded=['I:（可移动盘）', ...]（仅用于日志说明）。
    """
    import string as _string
    manual = []
    try:
        from .config import load_config
        for d in load_config().get("search_drives", []) or []:
            s = str(d).strip().upper().rstrip("\\")
            if s:
                manual.append(s if s.endswith(":") else s + ":")
    except Exception:
        manual = []
    if manual:
        return [d for d in manual if os.path.exists(d + "\\")], []

    targets, excluded = [], []
    for ch in _string.ascii_uppercase:
        if not os.path.exists(f"{ch}:\\"):
            continue
        t = drive_type(ch)
        if t == DRIVE_FIXED:
            targets.append(f"{ch}:")
        elif t == DRIVE_REMOVABLE:
            excluded.append(f"{ch}:（可移动盘）")
        elif t == 5:
            excluded.append(f"{ch}:（光驱）")
        elif t == 4:
            excluded.append(f"{ch}:（网络盘）")
    return targets, excluded

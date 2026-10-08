# -*- coding: utf-8 -*-
"""全盘关键词检索：Everything(es.exe) 优先，自建遍历兜底。

Everything 便携版作为无感知后端：用户全程只见本软件界面。
"""
import os
import string
import subprocess
import threading

from .config import tools_dir
from .util import drive_scope, run_hidden





def time_sleep(sec):
    import time
    time.sleep(sec)


_EV_LOCK = threading.Lock()


def _paths():
    base = os.path.join(tools_dir(), "everything")
    return (os.path.join(base, "es.exe"), os.path.join(base, "everything.exe"))


def es_available():
    es, _ = _paths()
    return os.path.isfile(es)


def everything_running_count():
    """运行中的 Everything.exe 实例数（多实例会互相冲突拖慢 es 查询）。"""
    try:
        r = run_hidden(["tasklist", "/FI", "IMAGENAME eq Everything.exe", "/NH"],
                       timeout=10)
        return sum(1 for l in r.stdout.decode("gbk", errors="replace").splitlines()
                   if "everything.exe" in l.lower())
    except Exception:
        return 0


def everything_running():
    return everything_running_count() > 0


def ensure_everything(timeout=8, log=None):
    """确保 Everything 后端就绪（加锁防并发重复启动）；True 表示 es 可查询。

    timeout=快速探活重试次数（每次 3 秒超时）。多实例冲突是 es 查询变慢的
    常见根因（毫秒级变秒级），检测到时记日志提示用户。
    """
    with _EV_LOCK:
        return _ensure_everything_locked(timeout=timeout, log=log)


def _ensure_everything_locked(timeout=8, log=None):
    es, ev = _paths()
    if not es_available():
        return False
    n = everything_running_count()
    if n > 1 and log:
        log(f"警告：检测到 {n} 个 Everything 实例同时运行，查询会互相冲突变慢，"
            f"建议关闭多余的 Everything 窗口")
    if n == 0:
        if not os.path.isfile(ev):
            return False
        try:
            # -startup：托盘后台启动，无窗口
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            subprocess.Popen([ev, "-startup"], close_fds=True,
                             creationflags=0x08000000, startupinfo=si)
            if log:
                log("Everything 索引服务启动中（首次建索引可能需要数十秒）...")
        except Exception:
            return False
    probe = [es, "-n", "1"]
    for _ in range(timeout):
        try:
            r = run_hidden(probe, timeout=3)
            if r.returncode == 0:
                return True
        except Exception:
            pass
        time_sleep(1)
    return False


def _decode(raw):
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def es_search(keyword, max_results=3000, timeout=20):
    """es.exe 查询，返回路径列表。超时快速失败（正常查询毫秒级）。"""
    es, _ = _paths()
    r = run_hidden([es, "-n", str(max_results), keyword], timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(_decode(r.stderr).strip() or "es.exe 查询失败")
    out = _decode(r.stdout)
    return [ln.strip().strip('"') for ln in out.splitlines() if ln.strip()]


SKIP_DIRS = {"$recycle.bin", "system volume information", "$windows.~bt",
             "$windows.~ws", "windows.old", "recovery", "config.msi"}


def list_drives():
    """自建兜底扫描的盘符范围：仅本地固定硬盘（排除U盘/光驱/网络盘）。"""
    return [d + "\\" for d in drive_scope()[0]]


def fallback_scan(keyword, max_results=3000, progress=None):
    """自建遍历兜底：文件名包含关键词（不区分大小写）。"""
    kw = keyword.lower()
    results = []
    for drive in list_drives():
        stack = [drive]
        while stack and len(results) < max_results:
            cur = stack.pop()
            try:
                it = os.scandir(cur)
            except OSError:
                continue
            with it:
                for e in it:
                    try:
                        name = e.name
                        if e.is_dir(follow_symlinks=False):
                            if name.lower() not in SKIP_DIRS:
                                stack.append(e.path)
                        else:
                            if kw in name.lower():
                                results.append(e.path)
                                if len(results) >= max_results:
                                    break
                    except OSError:
                        continue
            if progress and len(results) % 50 == 0:
                progress(len(results))
    return results


def search(keyword, max_results=3000, progress=None, log=None):
    """统一入口。返回 (engine, results)。engine: 'everything' | 'scan'。"""
    if es_available() and ensure_everything(log=log):
        try:
            return "everything", es_search(keyword, max_results)
        except Exception as e:
            if log:
                log(f"es 查询失败，回退自建扫描：{e}")
    if log:
        log("使用自建全盘扫描（无 Everything 引擎，速度较慢）...")
    return "scan", fallback_scan(keyword, max_results, progress)


def search_all(keywords, max_results=3000, workers=8, progress=None, log=None,
               allow_fallback=False):
    """多关键词并发检索。返回 {kw: [path,...]}。progress(done,total)。

    与单词 search() 不同：批量模式**前置一次性探活**（避免 52 词线程逐个排队
    探活），且默认**禁用逐词全盘扫描回退**——引擎不可用时抛 RuntimeError，
    由上层给出明确指引（52 词逐词 fallback 全盘扫描等于永远查不完）。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    if not es_available():
        raise RuntimeError("未找到 Everything 检索组件（tools/everything/es.exe 缺失）")
    if not ensure_everything(timeout=8, log=log):
        n = everything_running_count()
        msg = "Everything 引擎未响应"
        if n > 1:
            msg += f"（检测到 {n} 个实例同时运行，互相冲突）"
        raise RuntimeError(msg + "。请关闭多余的 Everything 窗口后重试，"
                                 "或切换 AnyTXT 引擎。")
    out, done = {}, [0]
    def one(kw):
        try:
            return kw, es_search(kw, max_results)
        except Exception as e:
            if log:
                log(f"[{kw}] es 查询失败：{e}")
            if allow_fallback:
                return kw, fallback_scan(kw, max_results)
            return kw, []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, kw) for kw in keywords]
        for f in as_completed(futs):
            kw, res = f.result()
            out[kw] = res
            done[0] += 1
            if progress:
                try:
                    progress(done[0], len(keywords))
                except Exception:
                    pass
    return out

# -*- coding: utf-8 -*-
"""AnyTXT 内容搜索引擎集成（官方 anytxt.v1 JSON-RPC API）。

协议实测（本机 Anytxt 1.3.3541，2026-09-10，依据 9924 端口官方文档页）：
  POST http://127.0.0.1:9924/rpc   Content-Type: application/json
  method 命名空间 anytxt.v1.*，参数直接放 params：
    anytxt.v1.status      → data.output.return = True 表示索引加载完成
    anytxt.v1.getResult   {pattern, filterDir, filterExt, limit(1..300),
                           offset, order, lastModifyBegin/End}
                          → data.output = {count, field:[fid,lastModify,size,file], files}
                          → **filterDir 必须是合法盘符（如 "C:"）或省略（默认 C:），
                             传 "*" 会 errno:1**。全盘搜索=逐盘查询后合并。
    anytxt.v1.getFragment {fid, pattern} → data.output.text（含 <<*kw*>> 高亮标记）
  errno:0=成功；GUI（ATGUI.exe）运行时 9924 才监听。
"""
import glob
import json
import os
import subprocess
import time
import urllib.request

from .config import app_dir
from .util import drive_scope, run_hidden

ATGUI_DEFAULT = r"C:\Program Files\Anytxt Searcher\ATGUI.exe"
SERVICE_NAME = "ATService"
API_URL = "http://127.0.0.1:9924/rpc"
PAGE_LIMIT = 300          # 官方上限：单次 ≤300
TIMEOUT = 20


def _rpc(method, params, timeout=TIMEOUT):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1,
                          "method": method, "params": params}).encode("utf-8")
    req = urllib.request.Request(API_URL, data=payload,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read().decode("utf-8", errors="replace"))
    if "error" in resp:
        raise RuntimeError(f"AnyTXT API error: {resp['error']}")
    result = resp.get("result", {})
    errno = result.get("errno")
    if errno not in (0, None):
        raise RuntimeError(f"AnyTXT errno={errno}")
    return result.get("data", {})


def _port_alive():
    try:
        d = _rpc("anytxt.v1.status", {}, timeout=5)
        return bool(d.get("output", {}).get("return"))
    except Exception:
        return False


def _service_installed():
    try:
        r = run_hidden(["sc", "query", SERVICE_NAME], timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def _find_atgui():
    """探测 ATGUI 实际路径：常见安装目录 + 注册表卸载项，硬编码仅兜底。"""
    cands = []
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        base = os.environ.get(env)
        if base:
            cands.append(os.path.join(base, "Anytxt Searcher", "ATGUI.exe"))
    cands.append(ATGUI_DEFAULT)
    for c in cands:
        if os.path.isfile(c):
            return c
    try:
        import winreg
        key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for flag in (0, winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
                try:
                    with winreg.OpenKey(root, key, 0, winreg.KEY_READ | flag) as k:
                        for i in range(winreg.QueryInfoKey(k)[0]):
                            try:
                                sub = winreg.EnumKey(k, i)
                                with winreg.OpenKey(k, sub) as sk:
                                    name = str(winreg.QueryValueEx(sk, "DisplayName")[0])
                                    if "anytxt" in name.lower():
                                        loc = str(winreg.QueryValueEx(sk, "InstallLocation")[0])
                                        p = os.path.join(loc, "ATGUI.exe")
                                        if os.path.isfile(p):
                                            return p
                            except Exception:
                                continue
                except Exception:
                    continue
    except Exception:
        pass
    return ATGUI_DEFAULT


def anytxt_installed():
    return _service_installed() or os.path.isfile(_find_atgui())


def anytxt_ready():
    return _port_alive()


def _gui_running():
    try:
        r = run_hidden(["tasklist", "/FI", "IMAGENAME eq ATGUI.exe", "/NH"], timeout=10)
        return b"ATGUI.exe" in r.stdout
    except Exception:
        return False


def ensure_running(timeout=300, log=None, progress=None):
    """确保 ATGUI 运行且索引加载完成（9924 仅在 GUI 进程运行时监听）。

    冷启动时 AnyTXT 主窗口会弹出一次（属正常，可最小化到托盘）。
    progress(msg) 用于 UI 状态栏实时反馈。"""
    def _notify(msg):
        if log:
            log(msg)
        if progress:
            try:
                progress(msg)
            except Exception:
                pass

    if anytxt_ready():
        return True
    if not anytxt_installed():
        return False
    if not _gui_running():
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            subprocess.Popen([_find_atgui()], close_fds=True)
            _notify("AnyTXT 引擎启动中（其主窗口会弹出，可最小化到托盘，不影响本软件使用）...")
        except Exception as e:
            _notify(f"AnyTXT 启动失败：{e}")
            return False
    else:
        _notify("AnyTXT 引擎正在加载索引，请稍候...")
    deadline = time.time() + timeout
    waited = 0
    while time.time() < deadline:
        waited += 2
        try:
            d = _rpc("anytxt.v1.status", {}, timeout=5)
            if d.get("output", {}).get("return"):
                _notify("AnyTXT 引擎就绪")
                return True
            _notify(f"AnyTXT 索引加载中（已等待 {waited} 秒，首次启动约需几分钟）...")
        except Exception:
            _notify(f"等待 AnyTXT 引擎响应（已等待 {waited} 秒）...")
        time.sleep(2)
    _notify(f"AnyTXT 引擎等待超时（{timeout} 秒），请确认 AnyTXT 主窗口是否正在加载索引")
    return False


def installer_path():
    """查找 AnyTXT 安装包：优先 exe/软件同目录（单位配发包随发放置）。"""
    bases = [app_dir(), os.getcwd()]
    seen = set()
    for base in bases:
        if base in seen or not os.path.isdir(base):
            continue
        seen.add(base)
        cands = sorted(glob.glob(os.path.join(base, "Anytxt_*Windows*.exe")))
        if cands:
            return cands[-1]
    return None


def install_anytxt(pkg=None, log=None, timeout=900):
    """静默安装官方原版（Inno Setup /VERYSILENT），完成后等服务+启动 GUI。

    注意：**不带 /SUPPRESSMSGBOXES**——本机环境（腾讯管家+360 双实时防护）会随机
    锁住新写入的 DLL，导致 Inno 弹"MoveFile 拒绝访问"提示；保留弹窗让用户点
    【重试】（杀毒扫描完成后即可通过）。实测 /SUPPRESSMSGBOXES 下重试被自动
    按"中止"处理，安装必然失败（v1.8.9 教训）。超时 900s：OCR 大包 + 慢盘余量。
    """
    pkg = pkg or installer_path()
    if not pkg or not os.path.isfile(pkg):
        raise RuntimeError("未找到 AnyTXT 安装包（请将单位配发的 Anytxt 安装包与本软件放同一目录）")
    if log:
        log(f"开始静默安装 AnyTXT：{pkg}")
        log("提示：安装中若弹出『文件正在使用/拒绝访问』提示，请点【重试】（杀毒软件扫描所致）")
    proc = subprocess.Popen([pkg, "/VERYSILENT", "/NORESTART"])
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError("AnyTXT 安装超时")
    if not _service_installed():
        raise RuntimeError("安装完成但未检测到 AnyTXT 服务")
    try:
        ensure_running(timeout=60, log=log)
    except Exception:
        pass
    ok = anytxt_ready()
    if log:
        log("AnyTXT 安装完成" + ("，引擎就绪" if ok else "（引擎未就绪，稍后自动重试）"))
    return ok


def _exact_pattern(keyword):
    """AnyTXT 高级语法：双引号包裹 = 短语精确匹配。

    不加引号时 AnyTXT 默认模糊匹配（多字词会被拆开分别命中，
    如三字人名被拆成"前两字"与"末字"），人名/业务词场景必须精确匹配。实测：加引号后片段为连续完整关键词。
    """
    kw = str(keyword).replace('"', "").strip()
    return f'"{kw}"'


def anytxt_search(keyword, max_results=3000, filter_ext="*", log=None,
                  drives=None, skip_report=None):
    """内容搜索：逐盘查询合并（官方 API 单次 limit≤300，自动翻页）。

    drives 由调用方传入（多关键词批量检索时只枚举一次盘符范围）；
    skip_report 为 set，用于汇总"无索引被跳过的盘"，避免逐关键词刷日志。
    返回 (total, [(path, size, mtime, fid), ...])。
    """
    pattern = _exact_pattern(keyword)
    merged, seen = [], set()
    if drives is None:
        drives, _ = drive_scope()
    for drive in drives:
        offset, got = 0, 0
        while offset < max_results:
            limit = min(PAGE_LIMIT, max_results - offset)
            try:
                d = _rpc("anytxt.v1.getResult", {
                    "pattern": pattern, "filterDir": drive,
                    "filterExt": filter_ext, "limit": limit, "offset": offset,
                    "order": 2, "lastModifyBegin": 0,
                    "lastModifyEnd": 2147483647})
            except RuntimeError:
                # 该盘无内容索引/未纳入索引范围 → 汇总，不逐词刷日志
                if skip_report is not None:
                    skip_report.add(drive)
                break
            except Exception as e:
                if log:
                    log(f"AnyTXT [{drive}] 查询失败：{e}")
                break
            out = d.get("output", {})
            files = out.get("files", [])
            for row in files:
                try:
                    fid, mtime, size, path = row[0], row[1], row[2], row[3]
                except (IndexError, TypeError):
                    continue
                # AnyTXT 字段类型不严格（size/mtime 可能是字符串），强制规范化
                try:
                    size = int(size) if size not in (None, "") else 0
                except (TypeError, ValueError):
                    size = 0
                try:
                    mtime = float(mtime) if mtime not in (None, "") else 0
                except (TypeError, ValueError):
                    mtime = 0
                if mtime > 4102444800:
                    mtime = mtime / 1000
                if path in seen:
                    continue
                seen.add(path)
                merged.append((path, size, mtime, str(fid)))
                got += 1
                if len(merged) >= max_results:
                    return len(merged), merged
            cnt = out.get("count") or 0        # count 可能为 None
            if len(files) < limit or got >= cnt:
                break
            offset += limit
    return len(merged), merged


def anytxt_fragment(fid, keyword, timeout=TIMEOUT):
    """取关键词上下文片段（精确短语模式，清理高亮标记符）。失败返回空串。"""
    try:
        d = _rpc("anytxt.v1.getFragment",
                 {"fid": str(fid), "pattern": _exact_pattern(keyword)}, timeout=timeout)
        text = d.get("output", {}).get("text", "") or ""
        for sym in ("<<*", "*>>", "<<", ">>"):
            text = text.replace(sym, "")
        return text
    except Exception:
        return ""


def search_all(keywords, max_results=3000, workers=6, progress=None, log=None):
    """多关键词并发内容检索。返回 {kw: [(path,size,mtime,fid),...]}。

    盘符范围在批量开始前**枚举一次**并写入日志（用户据此确认检索覆盖范围），
    无索引被跳过的盘在结束时汇总一条，不再逐关键词刷屏。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    out, done = {}, [0]
    drives, excluded = drive_scope()
    skipped = set()
    if log:
        scope = "、".join(drives) if drives else "（未发现可用本地硬盘）"
        log(f"内容检索范围：{scope}"
            + (f"；已排除 {'、'.join(excluded)}" if excluded else ""))

    def one(kw):
        try:
            _, rows = anytxt_search(kw, max_results, drives=drives,
                                    skip_report=skipped)
            return kw, rows
        except Exception as e:
            if log:
                log(f"[{kw}] AnyTXT 检索失败：{e}")
            return kw, []

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, kw) for kw in keywords]
        for f in as_completed(futs):
            kw, rows = f.result()
            out[kw] = rows
            done[0] += 1
            if progress:
                try:
                    progress(done[0], len(keywords))
                except Exception:
                    pass
    if skipped and log:
        log(f"以下盘符未纳入 AnyTXT 索引，本次已跳过：{'、'.join(sorted(skipped))}"
            f"（如需检索，请在 AnyTXT 设置里把这些盘加入索引范围）")
    return out

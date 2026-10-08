# -*- coding: utf-8 -*-
"""回调层单测：直接调用 UI 回调，覆盖冒烟测试触达不到的路径。

背景：v1.6.x 连续出现 3 个 P0（软件黑名单保存崩溃 / 删除回调解包崩溃 /
未勾选分组统计 KeyError），全部位于按钮回调路径，页签切换型冒烟测试无法发现。
本文件把这些回调纳入自动回归。
"""
import io
import os
import tkinter as tk
import shutil
import sys
import tempfile
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "app"))

from core.config import load_config  # noqa
from core.logger import Logger  # noqa

CFG = os.path.join(_ROOT, "config.json")
BAK = CFG + ".cbtest.bak"

PASS, FAIL = 0, []


def check(name, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  {extra}")


def main():
    from ui.app import App
    # 全程使用临时配置：真实 config.json（含 52 人名/业务词）绝不入测试
    import json as _json
    _cfg_dir = tempfile.mkdtemp(prefix="cleaner_testcfg_")
    _json.dump(_json.load(open(CFG, encoding="utf-8")),
               open(os.path.join(_cfg_dir, "config.json"), "w", encoding="utf-8"),
               ensure_ascii=False)
    import core.config as _cm0
    _cm0.CONFIG_PATH = os.path.join(_cfg_dir, "config.json")
    cfg = load_config()
    log = Logger(logfile=os.path.join(tempfile.gettempdir(), "cleaner_test_cb.log"))
    app = App(cfg, log)
    app.update()

    # ---------- P0-1 软件黑名单保存（相对导入越界）----------
    print("== 回调1：软件黑名单保存 ==")
    if os.path.exists(CFG):
        shutil.copyfile(CFG, BAK)
    BAK2 = CFG + ".bak"
    BAK2_SAVE = BAK2 + ".cbtest"
    if os.path.exists(BAK2):                 # 安全网备份也要保护，防测试覆盖真实备份
        shutil.copyfile(BAK2, BAK2_SAVE)
    try:
        app.show_page("software")
        app.update()
        sp = app._pages["software"]
        sp._save_kw(["测试黑名单词"])
        check("_save_kw 无 ImportError 且配置已更新",
              app.cfg["remove_keywords"] == ["测试黑名单词"])
        import json
        with open(CFG, encoding="utf-8") as f:
            check("_save_kw 已落盘", json.load(f)["remove_keywords"] == ["测试黑名单词"])
    except Exception as e:
        check("_save_kw 无 ImportError 且配置已更新", False, repr(e))

    # ---------- P0-2 / P1-1 删除回调（payload 字符串 + 失败项）----------
    print("== 回调2：删除完成标记 ==")
    app.show_page("search")
    app.update()
    pg = app._pages["search"]
    pg.ct.clear()
    iid1 = pg.ct.insert(("文档内容", "a.txt", "1 KB", "-", "", "C:/tmp/a.txt"),
                        payload="C:/tmp/a.txt")
    iid2 = pg.ct.insert(("文档内容", "b.txt", "1 KB", "-", "", "C:/tmp/b.txt"),
                        payload="C:/tmp/b.txt")
    try:
        # 全部成功
        pg._after_delete(["C:/tmp/a.txt", "C:/tmp/b.txt"], (2, []))
        check("_after_delete 字符串 payload 不抛异常",
              "C:/tmp/a.txt" in app.deleted_paths)
        check("成功项已标记为已删除", pg.ct.tree.item(iid1, "tags") == ("deleted",))
    except Exception as e:
        check("_after_delete 字符串 payload 不抛异常", False, repr(e))

    # 部分失败：失败项不得进入 deleted_paths
    app.deleted_paths.clear()
    pg.ct.clear()
    iid3 = pg.ct.insert(("文档内容", "c.txt", "1 KB", "-", "", "C:/tmp/c.txt"),
                        payload="C:/tmp/c.txt")
    iid4 = pg.ct.insert(("文档内容", "d.txt", "1 KB", "-", "", "C:/tmp/d.txt"),
                        payload="C:/tmp/d.txt")
    try:
        pg._after_delete(["C:/tmp/c.txt", "C:/tmp/d.txt"],
                         (1, [("C:/tmp/d.txt", "占用中")]))
        check("失败项未被标记为已删除", "C:/tmp/d.txt" not in app.deleted_paths)
        check("成功项正常标记", "C:/tmp/c.txt" in app.deleted_paths)
        check("失败行仍可勾选（未灰显）", pg.ct.tree.item(iid4, "tags") != ("deleted",))
    except Exception as e:
        check("失败项未被标记为已删除", False, repr(e))

    # ---------- P0-3 扫描统计键缺失 ----------
    print("== 回调3：浏览器扫描统计 ==")
    app.show_page("browser")
    app.update()
    bp = app._pages["browser"]
    for g, v in bp.gvars.items():      # 仅勾选"缓存"，不勾"历史记录"
        v.set("on" if g == "缓存" else "off")
    try:
        bp._after_scan([{"group": "历史记录", "path": "C:/x/chrome_shutdown_ms.txt",
                         "kind": "file", "size": 10, "special": None}])
        check("_after_scan 含未勾选分组不抛 KeyError", True)
    except Exception as e:
        check("_after_scan 含未勾选分组不抛 KeyError", False, repr(e))

    # ---------- P1-2 clean 按当前勾选过滤 ----------
    print("== 回调4：清理范围与勾选一致（弹窗内容结果断言）==")
    bp.found = [{"kind": "chromium", "name": "Google Chrome", "running": False,
                 "base": "C:/x", "profiles": [], "cache_base": ""},
                {"kind": "chromium", "name": "Microsoft Edge", "running": False,
                 "base": "C:/y", "profiles": [], "cache_base": ""}]
    for b in bp.found:
        if b["name"] not in bp.bvars:
            bp.bvars[b["name"]] = tk.StringVar(value="off")
    bp.bvars["Google Chrome"].set("on")
    bp.bvars["Microsoft Edge"].set("off")
    bp.items = [{"group": "缓存", "path": "C:/x/Cache", "kind": "dir", "size": 100,
                 "special": None, "browser": "Google Chrome"},
                {"group": "历史记录", "path": "C:/x/History", "kind": "file",
                 "size": 200, "special": None, "browser": "Google Chrome"},
                {"group": "缓存", "path": "C:/y/Cache", "kind": "dir", "size": 400,
                 "special": None, "browser": "Microsoft Edge"},
                {"group": "历史记录", "path": "C:/y/History", "kind": "file",
                 "size": 800, "special": None, "browser": "Microsoft Edge"}]
    captured4 = {}
    app.confirm_danger = lambda t, lines: (
        captured4.__setitem__("v", list(lines)), False)[1]   # 捕获弹窗内容并取消
    for g, v in bp.gvars.items():
        v.set("on" if g == "缓存" else "off")
    bp.clean()
    app.update()
    l4 = captured4.get("v", [])
    check("回调4：弹窗范围=勾选范围（仅 Chrome+缓存 → 共 1 项，不含 Edge）",
          any("共 1 项" in l for l in l4) and l4 and not any("Edge" in l for l in l4),
          str(l4[:3]))
    bp.bvars["Google Chrome"].set("off")
    bp.bvars["Microsoft Edge"].set("on")
    captured4.clear()
    bp.clean()
    app.update()
    l4b = captured4.get("v", [])
    check("回调4：切换勾选后弹窗范围同步（Edge+缓存，不含 Chrome）",
          any("共 1 项" in l for l in l4b) and l4b and not any("Chrome" in l for l in l4b),
          str(l4b[:3]))
    captured4.clear()
    bp.bvars["Microsoft Edge"].set("off")
    bp.clean()
    app.update()
    check("回调4：全部取消勾选 → 不弹窗（提示无可清理项）", "v" not in captured4)

    # ---------- P1-5 下载目录打开（环境变量展开）----------
    print("== 回调5：打开目录（含环境变量）==")
    app.show_page("downloads")
    app.update()
    dp = app._pages["downloads"]
    called = []
    import core.util as util_mod
    import os as _os
    orig_isdir, orig_start = _os.path.isdir, _os.startfile
    _os.path.isdir = lambda p: True
    _os.startfile = lambda p: called.append(p)
    try:
        dp.combo.set("%USERPROFILE%\\Downloads")
        dp.open_dir()
        check("环境变量已展开后打开目录",
              bool(called) and "%USERPROFILE%" not in called[0], str(called))
    except Exception as e:
        check("环境变量已展开后打开目录", False, repr(e))
    finally:
        _os.path.isdir, _os.startfile = orig_isdir, orig_start

    # ---------- P1-6 首次点击扫描自动继续 ----------
    print("== 回调6：扫描一次到位 ==")
    bp2 = bp
    bp2.found = []
    bp2.items = []
    invoked = {"n": 0}

    def fake_run_bg(fn, on_done=None, on_error=None):
        invoked["n"] += 1
        if on_done:
            on_done([])          # 空扫描结果，验证 _after_scan 空列表安全
    _real_run_bg = bp2.app.run_bg        # 存档原件，用后必须还原（防污染后续用例）
    bp2.app.run_bg = fake_run_bg
    bp2._after_detect_then_scan([{"name": "Google Chrome", "kind": "chromium",
                                  "running": False, "base": "C:/x",
                                  "profiles": [], "cache_base": ""}])
    check("检测回调后自动继续触发扫描（run_bg 再次调用）",
          invoked["n"] >= 1 and len(bp2.found) == 1, f"n={invoked['n']}")
    check("_after_scan(空列表) 不抛异常", True)
    bp2.app.run_bg = _real_run_bg

    # ---------- 本轮内网反馈新增功能 ----------
    print("== 回调8：内网反馈修复项 ==")
    app.show_page("search")
    app.update()
    pg2 = app._pages["search"]

    # 关键词一键全选 / 全不选
    pg2._toggle_all_chips()
    on_n = sum(1 for st in pg2.chip_vars.values() if st["on"])
    pg2._toggle_all_chips()
    off_n = sum(1 for st in pg2.chip_vars.values() if st["on"])
    check("关键词一键全选/全不选", on_n == len(pg2.chip_vars) and off_n == 0,
          f"on={on_n} off={off_n}")

    # 新增关键词为增量插入（不重建已有 chip 控件）
    before_ids = {k: id(st["btn"]) for k, st in pg2.chip_vars.items()}
    pg2.kw_entry.insert(0, "回归测试词")
    pg2._add_kw()
    app.update()
    after = pg2.chip_vars.get("回归测试词")
    keep_ok = all(id(pg2.chip_vars[k]["btn"]) == v
                  for k, v in before_ids.items() if k in pg2.chip_vars)
    check("新增关键词为增量插入（已有 chips 未被重建）",
          after is not None and keep_ok)
    # 清理测试词
    app.cfg["search_keywords"] = [k for k in app.cfg["search_keywords"]
                                  if k != "回归测试词"]
    pg2._reload_chips()

    # 已删除行被选中时自动取消选中（保持灰显）
    pg2.ct.clear()
    iid_del = pg2.ct.insert(("文档内容", "gone.txt", "1 KB", "-", "", "C:/tmp/gone.txt"),
                            payload="C:/tmp/gone.txt")
    pg2.ct.mark_deleted(iid_del)
    pg2.ct.tree.selection_set(iid_del)
    pg2._on_tree_select()
    check("已删除行选中后自动取消（保持灰显）",
          iid_del not in pg2.ct.tree.selection())

    # 右键菜单行路径解析（仅子行可打开）
    check("右键/双击行路径解析（子行有效、组头为空）",
          pg2._row_path(iid_del) == "C:/tmp/gone.txt")

    # 表格：列宽固定 + 勾选列最小宽 + 横向滚动条
    cols = pg2.ct.tree["columns"]
    stretched = [c for c in cols if pg2.ct.tree.column(c, "stretch")]
    check("所有列 stretch=False（拖列头不影响其他列）", not stretched, str(stretched))
    check("勾选列最小宽锁定 44",
          int(pg2.ct.tree.column("chk", "minwidth")) == 44)
    has_hsb = any(isinstance(w, __import__("tkinter").ttk.Scrollbar)
                  for w in pg2.ct.tree.master.winfo_children())
    check("结果表格存在滚动条组件", has_hsb)

    # 日志面板折叠
    before_h = app.logbox.winfo_height()
    app._toggle_log()
    opened = app.log_open
    app._toggle_log()
    check("操作日志可展开/收起", opened and not app.log_open)

    # ---------- 免责声明：按机器/用户记录，不随配置文件传播 ----------
    print("== 回调9：免责声明状态隔离 ==")
    import json as _json
    import socket as _socket
    flag_dir = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                            "IntranetCleaner")
    flag = os.path.join(flag_dir, "disclaimer.json")
    backup = None
    if os.path.isfile(flag):
        backup = flag + ".cbtest"
        shutil.copyfile(flag, backup)
        os.remove(flag)
    try:
        check("无标记时需弹窗（未同意）", app._disclaimer_agreed_here() is False)
        app._write_disclaimer_flag()
        check("本机本用户同意后不再弹窗", app._disclaimer_agreed_here() is True)
        # 伪造"他人电脑"的标记（模拟配置文件/标记被复制传播）
        with open(flag, "w", encoding="utf-8") as f:
            _json.dump({"agreed": True, "machine": "OTHER-PC",
                        "user": os.environ.get("USERNAME", "")}, f)
        check("他人机器的同意记录不被认可（防传播）",
              app._disclaimer_agreed_here() is False)
    finally:
        if os.path.isfile(flag):
            os.remove(flag)
        if backup:
            shutil.move(backup, flag)
    check("同意状态不写入 config.json（不再随包分发）",
          "agreed_disclaimer" not in app.cfg)

    print("== 回调10：UI 队列泵健壮性（v1.8.3 致命 bug 防复发）==")
    import time as _time
    # ① 畸形消息不得让泵停摆（历史误写结构 + 未知类型 + 非元组）
    app._ui_queue.put(("call", (lambda x: None, 1)))
    app._ui_queue.put(("garbage",))
    app._ui_queue.put("not-a-tuple")
    got = {"v": 0}
    app._ui_queue.put(("call", lambda x: got.__setitem__("v", x), 7))
    deadline = _time.time() + 6
    while _time.time() < deadline and got["v"] != 7:
        app.update()
        _time.sleep(0.05)
    check("泵吃到畸形消息后仍继续工作（后续回调仍触达）", got["v"] == 7)

    # ② run_bg → on_done 真实触达（v1.7.0 起该链路曾被结构错误整体打断）
    done = {"v": None}
    app.run_bg(lambda: 42, on_done=lambda r: done.__setitem__("v", r))
    deadline = _time.time() + 8
    while _time.time() < deadline and done["v"] is None:
        app.update()
        _time.sleep(0.05)
    check("run_bg 后台回调经队列回到主线程执行", done["v"] == 42, str(done["v"]))

    # ③ post()：子线程投递可调用对象（替代跨线程 after）
    posted = {"v": False}
    app.post(lambda: posted.__setitem__("v", True))
    deadline = _time.time() + 6
    while _time.time() < deadline and not posted["v"]:
        app.update()
        _time.sleep(0.05)
    check("post() 线程安全投递可用", posted["v"] is True)

    # ④ 端到端：AnyTXT 检索结果真的渲染进树（用户实测"结果全空"的正面断言）
    try:
        from core import content_search as _cs
        page = app._pages.get("search")
        if page is None:
            app.show_page("search")
            app.update()
            page = app._pages["search"]
        if _cs.anytxt_ready():
            _kw = next((k for k in (app.cfg.get("search_keywords") or []) if k.strip()),
                       "内容检索渲染占位词")   # 关键词取自本地配置（不入库），仓库不含真实名单
            res = _cs.search_all([_kw], 30)
            page._after_search("anytxt", res)
            app.update()
            heads = len(page.ct.tree.get_children())
            kids = sum(len(v) for v in page.ct.children.values())
            if kids:
                check("AnyTXT 检索结果渲染进树（组头≥1 且命中行>0）",
                      heads >= 1 and kids > 0, f"heads={heads} kids={kids}")
            else:
                check("AnyTXT 检索渲染链路正常（无命中时组头以 empty 标记渲染）",
                      heads >= 1, f"heads={heads}")
        else:
            check("AnyTXT 引擎未就绪，跳过渲染断言（环境相关）", True)
    except Exception as e:
        check("AnyTXT 检索结果端到端渲染", False, str(e))

    # ---------- 回调12：关键词删除确认 + 增量移除 ----------
    print("== 回调12：关键词删除保护 ==")
    app.show_page("search")
    app.update()
    pg = app._pages["search"]
    pg._reload_chips()
    app.update()
    n0 = len(pg.chip_vars)
    check("关键词方框已加载", n0 > 3, f"n={n0}")

    # ① 取消确认 → 一个都不许删
    _real_cd = app.confirm_danger
    app.confirm_danger = lambda title, lines: False
    keep_key = list(pg.chip_vars)[3]
    keep_id = id(pg.chip_vars[keep_key]["btn"])
    pg._toggle_chip(list(pg.chip_vars)[0])
    pg._toggle_chip(list(pg.chip_vars)[1])
    pg._del_selected_kw()
    app.update()
    check("取消确认后关键词数量不变", len(pg.chip_vars) == n0, f"{len(pg.chip_vars)}")

    # ② 确认删除 → 只删勾选的两个，其余方框控件实例原地保留（增量移除，非重建）
    app.confirm_danger = lambda title, lines: True
    pg._del_selected_kw()
    app.update()
    check("确认后仅删除勾选的关键词", len(pg.chip_vars) == n0 - 2, f"{len(pg.chip_vars)}")
    check("未删除的方框控件实例保持不变（增量移除，非重建）",
          keep_key in pg.chip_vars and id(pg.chip_vars[keep_key]["btn"]) == keep_id)
    check("计数标签已同步", str(n0 - 2) in pg.kw_count.cget("text"),
          pg.kw_count.cget("text"))
    app.confirm_danger = _real_cd      # 还原打桩

    # ---------- 回调13：各页动作链路（防"全部卡住"复发）----------
    print("== 回调13：各页动作链路 ==")
    import time as _t2

    def _pump(cond, timeout=90):
        t0 = _t2.time()
        while _t2.time() - t0 < timeout:
            app.update()
            if cond():
                return True
            _t2.sleep(0.05)
        return False

    # 下载目录：点"加载列表"必须出结果（曾被队列泵停摆卡成"加载中…"）
    app.show_page("downloads")
    app.update()
    dpg = app._pages["downloads"]
    dpg.load()
    ok = _pump(lambda: dpg.summary.cget("text")
               and "加载中" not in dpg.summary.cget("text"), 90)
    check("下载目录'加载列表'能出结果（回调链路通）", ok,
          dpg.summary.cget("text")[:40])

    # 浏览器：点"检测"必须出结果
    app.show_page("browser")
    app.update()
    bpg = app._pages["browser"]
    bpg.result_box.configure(state="normal")
    bpg.result_box.delete("1.0", "end")
    bpg.result_box.configure(state="disabled")
    bpg.detect()
    ok = _pump(lambda: "检测中" not in bpg.result_box.get("1.0", "end")
               and bpg.result_box.get("1.0", "end").strip(), 90)
    check("浏览器'检测'能出结果（回调链路通）", ok)

    # WPS/Office：点"扫描"必须出结果
    app.show_page("wps")
    app.update()
    wpg = app._pages["wps"]
    wpg.scan()
    ok = _pump(lambda: (lambda t: bool(t) and "扫描中" not in t and t != "未扫描")(wpg.hint.cget("text")), 90)
    check("WPS/Office'扫描'能出结果（回调链路通）", ok,
          wpg.hint.cget("text")[:40])

    # 构建时间指纹（防"打开了旧副本"的版本误判）
    from core.config import build_stamp as _bs
    check("构建时间指纹可用（版本辨识）", _bs() not in ("--", ""), _bs())

    # ---------- 回调14：Marvis 复核报告 N1/N2/P1-2/N3/N4 修复断言 ----------
    print("== 回调14：复核问题修复验证 ==")

    # ① N1：_after_clean 带"失败项"不再崩，结果区含 ✗ 明细
    app.show_page("browser")
    app.update()
    bpg = app._pages["browser"]
    bpg._cleaning_items = [{"browser": "Google Chrome", "group": "缓存",
                            "path": r"C:\x\Cache", "kind": "dir",
                            "size": 1024, "special": None}]
    bpg._after_clean(([], 1, [(r"C:\x\locked.db", "文件被占用")]))
    app.update()
    txt_ = bpg.result_box.get("1.0", "end")
    check("N1：清理有失败项时明细正常显示（含 ✗ 与成功/失败统计）",
          "✗" in txt_ and "失败 1 项" in txt_ and "清理中" not in txt_,
          txt_[:80].replace("\n", " "))

    # ② P1-2（数据侧）：collect_items 产出的条目必须带 browser 键
    import tempfile as _tf
    from core import browsers as _br
    prof = _tf.mkdtemp(prefix="cleaner_prof_")
    open(os.path.join(prof, "History"), "w").write("x")
    open(os.path.join(prof, "Cookies"), "w").write("x")
    fake_b = {"kind": "chromium", "name": "TestChrome", "running": False,
              "base": prof, "profiles": [prof], "cache_base": prof}
    got = _br.collect_items([fake_b], ["历史记录", "Cookie"])
    check("P1-2：collect_items 条目全部带 browser 键",
          bool(got) and all(i.get("browser") == "TestChrome" for i in got),
          f"{len(got)} 项, keys={sorted(got[0]) if got else '[]'}")

    # ③ P1-2（逻辑侧）：filter_scope 只保留勾选浏览器的勾选组
    out = _br.filter_scope(got, {"TestChrome"}, {"Cookie"})
    check("P1-2：filter_scope 按 勾选浏览器∩勾选组 过滤（结果实质断言）",
          bool(out) and all(i["browser"] == "TestChrome" and i["group"] == "Cookie"
                            for i in out),
          str([(i.get("browser"), i.get("group")) for i in out]))
    check("P1-2：browser 键缺失的条目一律排除（宁漏删不越权）",
          _br.filter_scope([{"group": "Cookie", "path": "z"}], {"X"}, {"Cookie"}) == [])

    # ④ N2：配置损坏时不得覆盖健康备份，坏文件另存 .corrupt
    from core import config as _cm
    _td = tempfile.mkdtemp(prefix="cleaner_cfg2_")
    _old = _cm.CONFIG_PATH
    try:
        _cm.CONFIG_PATH = os.path.join(_td, "config.json")
        import json as _j
        _j.dump({"search_keywords": ["A", "B", "C", "D", "E"]},
                open(_cm.CONFIG_PATH, "w", encoding="utf-8"))
        _cm.save_config({"search_keywords": ["A", "B", "C", "D", "E", "F"]})
        open(_cm.CONFIG_PATH, "w", encoding="utf-8").write("{ 坏JSON")
        _cm.save_config({"search_keywords": ["X"]})     # 主文件已损坏
        check("N2：主文件损坏时健康备份不被覆盖",
              _cm.backup_keyword_count() == 5, str(_cm.backup_keyword_count()))
        check("N2：坏文件另存 .corrupt 供排查（不进入备份链）",
              os.path.exists(_cm.CONFIG_PATH + ".corrupt")
              and "坏JSON" in open(_cm.CONFIG_PATH + ".corrupt",
                                   encoding="utf-8").read())
    finally:
        _cm.CONFIG_PATH = _old

    # ⑤ N3：build.bat 不得存在"续行后空行"（cmd 会在此截断命令）
    bat = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "build.bat")
    if os.path.exists(bat):
        lines = open(bat, encoding="utf-8", errors="replace").read().splitlines()
        broken = [i + 1 for i, l in enumerate(lines[:-1])
                  if l.rstrip().endswith("^")
                  and not lines[i + 1].strip()]
        check("N3：build.bat 无断裂续行（^ 后不能是空行）", not broken, str(broken))
    else:
        check("N3：build.bat 不存在（跳过）", True)

    # ⑥ N4：发布前校验脚本存在 + 实跑通过（回执"实跑"承诺的兑现）
    import subprocess as _sp
    rc = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "tools", "release_check.py")
    check("N4：发布前校验脚本存在", os.path.exists(rc), rc)
    if os.path.exists(rc):
        _r = _sp.run([sys.executable, rc], capture_output=True, text=True,
                     encoding="utf-8", errors="replace")
        check("N4：发布前校验实跑 returncode=0（GitHub 侧零词表）",
              _r.returncode == 0 and "全部通过" in (_r.stdout or ""),
              f"rc={_r.returncode} {( _r.stdout or _r.stderr)[:60]}")

    # ⑦ 首启播种安全网（配合 dist 去除随带 .bak）
    _cm2 = _cm
    _td2 = tempfile.mkdtemp(prefix="cleaner_seed_")
    _old2 = _cm2.CONFIG_PATH
    try:
        _cm2.CONFIG_PATH = os.path.join(_td2, "config.json")
        import json as _j2
        _j2.dump({"search_keywords": ["甲", "乙", "丙"]},
                 open(_cm2.CONFIG_PATH, "w", encoding="utf-8"))
        check("seed_backup：无备份时首启播种成功", _cm2.seed_backup() is True)
        check("seed_backup：幂等（已有备份不覆盖）", _cm2.seed_backup() is False)
        check("seed_backup：播种内容为主配置快照",
              _cm2.backup_keyword_count() == 3, str(_cm2.backup_keyword_count()))
    finally:
        _cm2.CONFIG_PATH = _old2

    # ---------- 回调15：软件页扫描存储与卸载/打开目录链路 ----------
    print("== 回调15：软件页 _after_scan 存储正确性（卸载按钮崩溃回归）==")
    app.show_page("software")
    app.update()
    sp = app._pages["software"]
    fake_drives = [{"drive": "C:", "total": 100, "free": 50}]
    fake_items = [{"name": "TestApp 1.0", "version": "1.0", "publisher": "T",
                   "size_kb": 1024, "flagged": False, "install_loc": "C:/app",
                   "uninstall": "C:/app/unins.exe"}]
    sp._after_scan((fake_drives, fake_items))
    app.update()
    check("回调15：_after_scan 后 self.items 是软件列表（非整个元组）",
          isinstance(sp.items, list) and len(sp.items) == 1
          and isinstance(sp.items[0], dict), f"type={type(sp.items)}")
    kids = sp.tree.get_children()
    assert kids, "表格应有数据行"
    sp.tree.selection_set(kids[0])          # 模拟用户点击选中第一行
    sp.tree.focus(kids[0])
    it = sp._selected_item()
    check("回调15：选中项可取到字典（卸载按钮不再 TypeError）",
          isinstance(it, dict) and it["name"] == "TestApp 1.0",
          str(type(it)))
    # 卸载链路：拦截 confirm 与 launch_uninstall，验证真实调起
    calls = {}
    app.confirm = lambda *a, **k: calls.setdefault("confirmed", True) or True
    import core.registry as _reg
    _orig_launch = _reg.launch_uninstall
    _reg.launch_uninstall = lambda item: calls.setdefault("uninstall", item["name"])
    try:
        sp.uninstall()
        check("回调15：卸载调起成功（launch_uninstall 收到正确软件）",
              calls.get("uninstall") == "TestApp 1.0", str(calls))
    finally:
        _reg.launch_uninstall = _orig_launch
    # 打开目录链路（目录存在时调 os.startfile）
    _tmpdir3 = tempfile.mkdtemp(prefix="cleaner_openloc_")
    sp.items[0]["install_loc"] = _tmpdir3
    started = {}
    _orig_startfile = os.startfile
    os.startfile = lambda p: started.setdefault("p", p)  # noqa
    try:
        sp.open_dir()
        check("回调15：打开安装目录调起成功", started.get("p") == _tmpdir3,
              str(started))
    finally:
        os.startfile = _orig_startfile

    # ---------- 回调16：未知浏览器自动识别（定制安全浏览器等，注册表判定源）----------
    print("== 回调16：未知浏览器自动识别 ==")
    from core import browsers as _brd
    _td4 = tempfile.mkdtemp(prefix="cleaner_disc_")
    # 构造"安全浏览器示例"安装目录：User Data 在安装目录 1 层下（Inno 常见布局）
    _tsec = os.path.join(_td4, "TestSecureBrowser")
    _ud1 = os.path.join(_tsec, "User Data")
    _ud1d = os.path.join(_ud1, "Default")
    _ud1p = os.path.join(_ud1, "Profile 1")
    for prof, fname in ((_ud1d, "History"), (_ud1p, "Cookies")):
        os.makedirs(prof, exist_ok=True)
        open(os.path.join(prof, fname), "w").close()
    # 构造"无效候选"：登记为浏览器但无 User Data（应跳过）
    _empty = os.path.join(_td4, "EmptyBrowser")
    os.makedirs(_empty, exist_ok=True)

    candidates = [("安全浏览器示例", _tsec), ("某无数据浏览器", _empty)]
    disc = _brd.discover_unknown_chromium([], candidates=candidates)
    names = {b["name"] for b in disc}
    check("回调16：登记为浏览器的条目被识别并使用登记名",
          "安全浏览器示例" in names, str(names))
    check("回调16：无 User Data 的候选被跳过",
          "某无数据浏览器" not in names, str(names))
    sg = [b for b in disc if b["name"] == "安全浏览器示例"]
    check("回调16：User Data 定位到安装目录 1 层下且含 2 个 profile",
          len(sg) == 1 and len(sg[0]["profiles"]) == 2,
          str([(b["base"], len(b["profiles"])) for b in sg]))
    # User Data 在安装目录 2 层下（嵌套布局）也应找到
    _nest = os.path.join(_td4, "NestBrowser", "app")
    _udn = os.path.join(_nest, "bin", "User Data", "Default")
    os.makedirs(_udn, exist_ok=True)
    open(os.path.join(_udn, "History"), "w").close()
    disc2 = _brd.discover_unknown_chromium(
        [], candidates=[("嵌套浏览器", _nest)])
    check("回调16：嵌套布局（安装目录 2 层下）可定位",
          len(disc2) == 1 and disc2[0]["name"] == "嵌套浏览器",
          str([(b["name"], b["base"]) for b in disc2]))
    # known_bases 排除：已登记的不重复识别
    disc3 = _brd.discover_unknown_chromium(
        [_ud1], candidates=[("安全浏览器示例", _tsec)])
    check("回调16：已登记浏览器不重复识别", not disc3, str(disc3))
    # 识别结果可直接走标准清理管线
    if disc:
        items = _brd.collect_items(sg, ["历史记录", "Cookie"])
        check("回调16：识别浏览器可走标准清理管线（条目带 browser 键）",
              bool(items) and all(i["browser"] == "安全浏览器示例" for i in items),
              str([(i["group"], os.path.basename(i["path"])) for i in items[:4]]))

    # ---------- 回调17：按关键词批量删除命中文档 ----------
    print("== 回调17：按关键词批量删除命中文档 ==")
    app.show_page("search")
    app.update()
    pg2 = app._pages["search"]
    cfg_kws = [k for k in app.cfg.get("search_keywords", []) if k.strip()]
    kw1, kw2 = cfg_kws[0], cfg_kws[1]
    _td5 = tempfile.mkdtemp(prefix="cleaner_kwdel_")
    fA = os.path.join(_td5, "docA_" + kw1 + ".txt")
    fB = os.path.join(_td5, "docB_" + kw2 + ".txt")
    open(fA, "w").write("A")
    open(fB, "w").write("B")
    pg2._after_search("everything", {kw1: [(fA, 100, time.time(), None)],
                                     kw2: [(fB, 200, time.time(), None)]})
    app.update()
    # 未选中任何关键词 → 提示且不动作
    pg2._delete_kw_hits()
    check("回调17：未选关键词时给出提示不动作",
          "请先点击关键词方框选中" in pg2.status.cget("text"),
          pg2.status.cget("text"))
    # 选中 kw1 → 弹窗内容只含 kw1 的命中文件（结果断言）
    captured17 = {}
    app.confirm_danger = lambda t, lines: (
        captured17.__setitem__("v", list(lines)), False)[1]
    pg2._toggle_chip(kw1)
    pg2._delete_kw_hits()
    app.update()
    l17 = captured17.get("v", [])
    checked = pg2.ct.checked_payloads()
    check("回调17：勾选 kw1 后其命中文件被自动全选",
          checked == [fA], str(checked))
    check("回调17：确认弹窗列出该词命中的文件名",
          any(os.path.basename(fA) in l for l in l17)
          and not any(os.path.basename(fB) in l for l in l17), str(l17[:5]))
    # 组头状态框可见性（□/√ 字形回归：中文字体必须能渲染）
    from ui.components import CHK_ON as _CKON
    _head17 = pg2._group_of_kw.get(kw1)
    check("回调19：组头状态框随全组勾选显示 √（勾选可见性）",
          _head17 and pg2.ct.tree.item(_head17, "values")[0] == _CKON,
          str(pg2.ct.tree.item(_head17, "values")[0] if _head17 else None))
    # 未执行检索（清空映射）→ 提示先检索
    pg2._group_of_kw = {}
    pg2._delete_kw_hits()
    check("回调17：未检索时提示先执行检索",
          "请先执行检索" in pg2.status.cget("text"), pg2.status.cget("text"))
    # 切换选择：改为 kw2 → 只勾 kw2 的命中
    pg2._after_search("everything", {kw1: [(fA, 100, time.time(), None)],
                                     kw2: [(fB, 200, time.time(), None)]})
    app.update()
    pg2._toggle_chip(kw1)      # 取消 kw1
    pg2._toggle_chip(kw2)      # 选中 kw2
    captured17.clear()
    pg2._delete_kw_hits()
    app.update()
    checked2 = pg2.ct.checked_payloads()
    check("回调17：切换勾选后仅 kw2 命中被选中",
          checked2 == [fB], str(checked2))

    # ---------- 回调18：Everything 引擎前置探活（多实例冲突防护）----------
    print("== 回调18：Everything 引擎探活与批量检索 ==")
    from core import everything as _ev
    n_inst = _ev.everything_running_count()
    check("回调18：实例计数为非负整数", isinstance(n_inst, int) and n_inst >= 0,
          str(n_inst))
    if n_inst > 1:
        print(f"  （本机当前 {n_inst} 个实例——多实例场景已覆盖日志警告路径）")
    _kws2 = [k for k in app.cfg.get("search_keywords", []) if k.strip()][:2]
    if n_inst > 0 and _kws2:
        _t0 = time.time()
        _err, res18 = None, None
        try:
            res18 = _ev.search_all(_kws2, 10)
        except RuntimeError as e:
            _err = e
        _el = time.time() - _t0
        if _err is None:
            check("回调18：批量检索前置探活后正常返回（52词不再卡死）",
                  isinstance(res18, dict) and set(res18.keys()) == set(_kws2)
                  and _el < 120, f"耗时 {_el:.1f}s")
        else:
            check("回调18：引擎未响应时快速失败并带指引（不卡死）",
                  "Everything" in str(_err) and _el < 60,
                  f"{_el:.1f}s {str(_err)[:60]}")
    else:
        check("回调18：批量检索（本机无运行实例或无关键词，跳过）", True)

    # ---------- 回调20：删除失败原因中文化 + 已不存在/长路径处理 ----------
    print("== 回调20：删除失败原因中文化 ==")
    from core import util as _ut
    e32 = OSError(32, "The process cannot access the file because it is being used by another process.")
    e32.winerror = 32
    check("回调20：错误32 → 占用提示", "占用" in _ut._humanize_delete_error(e32, "x"))
    e5 = OSError(5, "Access is denied.")
    e5.winerror = 5
    check("回调20：错误5 → 管理员提示", "管理员" in _ut._humanize_delete_error(e5, "x"))
    e2 = FileNotFoundError(2, "The system cannot find the file specified.")
    e2.winerror = 2
    check("回调20：错误2 → 已不存在提示", "不存在" in _ut._humanize_delete_error(e2, "x"))
    # delete_to_recycle：不存在的路径视为已清理（不计失败）
    ok, fail = _ut.delete_to_recycle(
        [os.path.join(tempfile.gettempdir(), "no_such_file_xyz_123.txt")])
    check("回调20：不存在的文件视为已清理（不计失败）",
          ok == 1 and not fail, str((ok, fail)))
    # 正常临时文件 → 回收站删除成功
    _tf = os.path.join(tempfile.gettempdir(), "cleaner_del_ok.txt")
    open(_tf, "w").close()
    ok, fail = _ut.delete_to_recycle([_tf])
    check("回调20：正常文件回收站删除成功", ok == 1 and not fail, str((ok, fail)))
    # 模拟占用失败 → 失败原因为人话
    import send2trash as _s2t
    _orig_s2t = _s2t.send2trash

    def _raiser(p):
        e = OSError(32, "The process cannot access the file.")
        e.winerror = 32
        raise e

    _s2t.send2trash = _raiser
    try:
        _f2 = os.path.join(tempfile.gettempdir(), "cleaner_del_locked.txt")
        open(_f2, "w").close()
        ok, fail = _ut.delete_to_recycle([_f2])
        check("回调20：模拟占用 → 中文失败原因",
              ok == 0 and fail and "占用" in fail[0][1], str(fail))
    finally:
        _s2t.send2trash = _orig_s2t

    app.destroy()

    # ---------- P2-7 保留项二道防线（不依赖 GUI）----------
    print("== 回调7：保留项安全校验 ==")
    from core import browsers as br
    keep_test = [{"group": "缓存", "path": r"C:\x\Default\Cache", "kind": "dir",
                  "size": 1, "special": None},
                 {"group": "历史记录", "path": r"C:\x\Default\Bookmarks",
                  "kind": "file", "size": 1, "special": None},
                 {"group": "历史记录", "path": r"C:\x\Default\Preferences",
                  "kind": "file", "size": 1, "special": None}]
    kept = br.filter_keep(keep_test)
    check("保留项二道防线生效（收藏夹/设置被剔除）",
          len(kept) == 1 and kept[0]["path"].endswith("Cache"), str([k["path"] for k in kept]))

    # ---------- 回调11：检索盘符范围（U盘排除 + 日志不刷屏）----------
    print("== 回调11：检索盘符范围 ==")
    import ctypes as _ct
    from core.util import drive_scope, drive_type as _drive_type
    from core import content_search as _cs2
    targets, excluded = drive_scope()
    check("检索范围非空且含系统盘 C:", "C:" in targets, str(targets))
    check("范围仅含本地固定硬盘（DriveType=3）",
          all(_drive_type(d.rstrip(":")) == 3 for d in targets), str(targets))
    removable = [f"{c}:" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                 if os.path.exists(f"{c}:\\")
                 and _ct.windll.kernel32.GetDriveTypeW(f"{c}:\\") == 2]
    check("U盘/移动盘已排除出检索范围",
          all(d not in targets for d in removable),
          f"removable={removable} targets={targets}")

    scope_logs = []
    try:
        _cs2.search_all(["__不存在的词_用于范围日志断言__"], 10, log=scope_logs.append)
    except Exception as e:
        check("范围日志采集不抛异常", False, str(e))
    lines = [l for l in scope_logs if "内容检索范围" in l]
    check("检索范围日志每批量只报一条（不再逐关键词刷屏）",
          len(lines) == 1, str(scope_logs))

    # ---------- 回调12b：关键词备份安全网（隔离到临时目录，不碰真实配置）----------
    print("== 回调12b：关键词备份安全网 ==")
    from core import config as _cm
    _tmpdir = tempfile.mkdtemp(prefix="cleaner_cfg_")
    _old_path = _cm.CONFIG_PATH
    try:
        _cm.CONFIG_PATH = os.path.join(_tmpdir, "config.json")
        import json as _j
        _j.dump({"search_keywords": ["A", "B", "C"]},
                open(_cm.CONFIG_PATH, "w", encoding="utf-8"))
        _cm.save_config({"search_keywords": ["A", "B", "C", "D"]})   # 词数增加 → 滚动备份
        check("词数增加时备份滚动更新",
              _cm.backup_keyword_count() == 3, str(_cm.backup_keyword_count()))
        _cm.save_config({"search_keywords": ["A", "B", "C", "D"]})
        _cm.save_config({"search_keywords": []})                     # 一键清空 → 不覆盖备份
        check("关键词被清空时备份不被覆盖（安全网核心）",
              _cm.backup_keyword_count() == 4, str(_cm.backup_keyword_count()))
        n = _cm.restore_keywords_from_backup()
        check("可从备份一键恢复关键词", n == 4, f"n={n}")
        check("恢复后配置文件已写回 4 个词",
              _cm._read_keyword_count(_cm.CONFIG_PATH) == 4)
    finally:
        _cm.CONFIG_PATH = _old_path

    if os.path.exists(BAK):
        shutil.move(BAK, CFG)
    if os.path.exists(BAK2_SAVE):
        shutil.move(BAK2_SAVE, BAK2)

    print()
    print(f"回调层单测结果：PASS {PASS}，FAIL {len(FAIL)} {FAIL if FAIL else ''}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

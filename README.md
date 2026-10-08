# 检查清理工具（Intranet Cleaner）

面向 Windows 的**本地数据检查与清理工具**。单文件绿色版，双击即用，无需安装、无网络依赖，所有删除操作统一送入回收站可恢复。

> 适用场景：办公电脑的定期自查与数据清理——软件清点、浏览器痕迹清理、办公软件缓存与最近记录清理、下载目录整理、按关键词全盘检索并批量处理文件。

## 功能特性

| 模块 | 能力 |
|---|---|
| 软件扫描清理 | 注册表三锚点枚举已装软件（名称/版本/发布者/体积），黑名单关键词标红"需移除"，一键调起卸载 |
| 浏览器清理 | Chrome / Edge / QQ / 360极速 / 360安全 / Firefox；清历史、Cookie、密码、自动填充、缓存、会话、站点数据；**收藏夹、扩展、浏览器设置三重保护**（分组白名单 + 文件名校验二道防线）；Firefox 采用数据库级清理保书签并启用安全删除 |
| WPS / Office 清理 | 本地缓存、自动备份、未保存草稿；一键清除 Office/WPS"最近打开"注册表 MRU |
| 下载目录管理 | 多目录、按体积排序、勾选批量删除、回收站兜底 |
| 关键词检索 | **双引擎**：Everything（文件名，毫秒级）+ AnyTXT（文档内容，覆盖 .doc/.xls/.ppt/.wps/.docx/.pdf/OFD 等）；52+ 关键词并发检索；树形汇总（每词一组，可折叠）；结果含命中片段上下文；勾选批量删除；双击/右键打开文件 |
| 安全机制 | 全链路回收站、高风险操作红色确认弹窗（列明影响）、操作日志（可折叠）、首次启动免责声明（按机器记录） |

## 环境要求

- Windows 10 / 11（x64）
- 打包版：无额外依赖，双击 `IntranetCleaner.exe` 即可
- 源码运行：Python 3.13 + `customtkinter` + `send2trash`（见 `requirements.txt`）

## 快速开始

### 使用打包版（推荐）

```
IntranetCleaner.exe   # 主程序（不含任何关键词）
config.json           # 配置与关键词（与 exe 同目录）
```

两个文件放同一目录即可运行。首次启动会弹出《使用须知与免责声明》，同意后进入主界面。

### 从源码运行

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python.exe app\main.py
```

> 注意：依赖安装在项目 `.venv` 中，请使用 `.venv\Scripts\python.exe` 运行；直接用系统 Python 会提示缺少依赖。

## 构建

```bat
build.bat
```

构建脚本调用 PyInstaller（onefile + windowed）。产物输出到 `dist\IntranetCleaner.exe`。

第三方工具需自备并放入 `tools/`（不随仓库分发）：

| 目录 | 内容 | 用途 |
|---|---|---|
| `tools/everything/` | Everything 便携版（`es.exe`、`everything.exe`） | 文件名秒级检索引擎 |
| `<exe 同目录>/` | Anytxt 官方安装包（`Anytxt_*Windows*.exe`） | 可选：文档内容检索引擎，检测到未安装时可一键静默安装 |

## 测试

```bat
.venv\Scripts\python.exe tests\test_core.py        # 核心逻辑（含引擎实测）
.venv\Scripts\python.exe tests\test_callbacks.py   # UI 回调层（防"回调路径未覆盖"类缺陷）
.venv\Scripts\python.exe tests\test_gui_smoke.py   # 界面冒烟（页签/控件断言）
```

## 架构

```
app/
├─ main.py              入口：依赖自检、配置加载、全局异常落日志
├─ core/                纯逻辑层（无 UI 依赖，可 headless 测试）
│  ├─ config.py         配置读写（三级加载 + 废弃键清理 + 原子写）
│  ├─ logger.py         线程安全日志（订阅式，支持 UI 回显）
│  ├─ util.py           回收站删除、体积计算、隐藏窗口子进程
│  ├─ registry.py       软件扫描 / 卸载调起 / Office+WPS MRU
│  ├─ browsers.py       6 款浏览器检测与清理（Firefox sqlite 特例 + 保留项校验）
│  ├─ wps_office.py     WPS / Office 缓存与最近记录
│  ├─ downloads.py      下载目录枚举
│  ├─ everything.py     Everything 引擎（es.exe 查询 + 自建扫描兜底 + 并发锁）
│  └─ content_search.py AnyTXT 官方 API 集成（JSON-RPC + 逐盘翻页 + 片段提取）
└─ ui/                  CustomTkinter 界面层
   ├─ theme.py          浅蓝主题 token / ttk 样式 / 卡片工厂
   ├─ components.py     表格（复选框/分组/双向滚动条）、关键词编辑器
   ├─ app.py            主窗：导航 + 页面栈 + 日志面板 + 高风险确认弹窗 + UI 消息队列
   └─ page_*.py         五个功能页

tests/                  三套回归测试
```

关键设计：**后台线程只入队 UI 消息**（`queue.Queue` + 主线程轮询），UI 回调异常自动落日志并在界面显示，避免"无窗口模式异常无声消失"。

## 配置说明

`config.json`（与 exe 同目录）字段：

| 字段 | 说明 |
|---|---|
| `remove_keywords` | 软件黑名单关键词（软件名包含即标红） |
| `search_keywords` | 检索关键词列表（界面可增删，或直接编辑本文件） |
| `download_dirs` | 下载目录（支持 `%USERPROFILE%` 等环境变量） |
| `search_max_results` | 单关键词结果上限（默认 3000） |
| `search_engine` | 检索默认引擎：`everything` / `anytxt` |
| `auto_kill_browser` | 浏览器清理时自动结束占用进程 |
| `log_max_lines` | 日志行数上限 |

> **敏感提示**：`search_keywords` 可能包含人名、单位名等敏感词汇。该文件**不随程序打包**（exe 内不含任何关键词），请与 exe 分开保管、按需分发，切勿提交到版本库（已在 `.gitignore` 中排除）。
> 免责声明的同意状态按**机器+用户**记录于 `%APPDATA%\IntranetCleaner\`，不随配置文件传播。

## 第三方组件

- **Everything**（voidtools）——文件名检索引擎，便携版随发行包提供
- **Anytxt Searcher**（CBEWIN TECH LIMITED）——文档内容检索引擎，官方安装包原样分发、不做任何修改；版权归其开发者所有，使用需遵循其许可条款

两者均为独立第三方软件，本项目仅通过其公开接口/命令行调用，不修改其任何文件。

## 免责声明

本工具用于对本机数据进行清理，删除内容统一送入回收站但**可能无法完整恢复**；清理浏览器数据会导致登录态退出、保存的密码被清除。请在充分理解清理范围后使用，使用前请确认对操作设备与数据具有相应管理权限。软件按"现状"提供，因使用造成的任何数据损失由使用者自行承担。

## 版本

当前版本见 `app/core/config.py` 的 `APP_VERSION`。主要迭代：

- **v1.0** 五大基础功能
- **v1.3** 首次启动免责声明
- **v1.4~v1.6** 双引擎检索（Everything + AnyTXT 内容搜索）、命中片段、精确匹配、并发检索
- **v1.7** 依据代码审计全面加固（并发安全、配置保护、保留项二道防线、词表剥离）
- **v1.8** 交互完善（折叠日志、右键/双击、勾选列锁定、关键词全选）、免责声明按机器记录
- **v1.8.3** 修复后台回调链路（结果不显示）、内容检索范围改为全部本地硬盘（自动排除U盘/光驱/网络盘）
- **v1.8.4** 关键词删除加确认弹窗 + 增量移除（不再整片刷新）+ `config.json.bak` 安全网备份与一键恢复
- **v1.8.5** 界面/日志显示构建时间（版本辨识）、各页动作链路回归断言（防回调链路整体失效）
- **v1.8.6** 修复浏览器清理明细崩溃与勾选越权（filter_scope）、备份安全网防坏文件覆盖、build.bat 重写 + tools/release_check.py 发布前零词表校验
- **v1.8.7~v1.8.9** 终审收尾（.corrupt 防护、首启播种备份、内容级名单扫描）、双杀毒环境安装适配
- **v1.8.10** 修复软件页"卸载选中软件/打开安装目录"自 v1.0 起的存储笔误（链式赋值陷阱），补 6 项回归断言

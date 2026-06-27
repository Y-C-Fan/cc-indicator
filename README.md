# cc-indicator

桌面悬浮小圆点，告诉你 [Claude Code](https://claude.com/claude-code) 每个会话现在是「在干活」还是「等你输入」——不用一直盯着终端。

![status](https://img.shields.io/badge/platform-Windows-blue) ![python](https://img.shields.io/badge/python-3.10%2B-blue)

## 这是啥

每开一个 Claude Code 会话，屏幕上就多一个小圆点：

- 🟡 **黄色呼吸** — Claude 正在干活
- 🟢 **绿色常亮** — 这一轮做完了 / 等你输入

所有圆点装在一个**可拖动**的圆角面板里，默认贴右上角。鼠标悬停在圆点上 → 气泡显示 cwd、状态、持续时间，还有标签输入框；按 cwd 持久化，下次同目录起 Claude Code 自动套上同样的标签。

## 装

需要 Python 3.10+（C 盘 D 盘都行；脚本会在自己目录下建 venv 把 PySide6 装进去，不污染全局环境）。

```cmd
cd cc-indicator
install.bat
```

会做：
1. `python -m venv venv`
2. 用 venv 的 pip 装 PySide6（国内 pip 源加速）
3. 把 hooks 写进 `%USERPROFILE%\.claude\settings.json`，**只 merge 不覆盖**你已有的别的配置

## 跑

```cmd
start.bat
```

启动一个无窗口的 `pythonw` 进程，托盘里出现绿圆点图标。

新开一个 Claude Code 会话 → 面板上自动冒出一个圆点。

要关掉：托盘右键 → 退出，或者跑 `stop.bat`。

## 用

| 操作 | 效果 |
|---|---|
| 鼠标悬停圆点 | 弹气泡：cwd、状态、持续时间、标签输入框 |
| 气泡里打字按回车 | 标签按 cwd 持久化，下次同目录自动套上 |
| 拖动面板空白处（不是圆点本身） | 移动整个面板，位置自动存盘 |
| 右键圆点 | 单点菜单：编辑标签 / 复制 session id / 从面板移除 |
| 右键面板空白 / 托盘 | 全局菜单：重置位置 / 开机自启 / 清标签 / 退出 |

## 卸

```cmd
venv\Scripts\python.exe install_hooks.py --remove
```

按 `cc_hook.py` 的绝对路径识别本工具写入的 hook 条目，只移除自己的，不动你别的 hook。

## 工作原理

```
┌─ Claude Code session ────────┐
│                              │
│  fires hook on each event ──→│── cc_hook.py ──→ state/<sid>.json
│  (SessionStart, UserPrompt-  │      (zero-dep,
│   Submit, Stop, Notification │       just stdlib)
│   …)                         │
└──────────────────────────────┘                       │
                                                       ↓
┌─ indicator.py (PySide6) ─────────────────────────────┐
│  • polls state/ every 800ms                          │
│  • one Dot widget per session, packed in a draggable │
│    PanelFrame                                        │
│  • Bubble widget shows cwd / status / label editor   │
│    on hover                                          │
└──────────────────────────────────────────────────────┘
```

每个 hook 调用是一个独立的短生命周期 Python 进程（< 200ms），写完 state 文件就退出，不阻塞 Claude。

## 文件结构

```
cc-indicator/
├── cc_hook.py          # 被 Claude Code 调用，写 state/<sid>.json（stdlib only）
├── indicator.py        # 悬浮窗主程序（PySide6 + 系统托盘）
├── install_hooks.py    # merge / 移除 hooks 配置到 ~/.claude/settings.json
├── install.bat         # 一键 venv + pip + hook 注册
├── start.bat           # 启动悬浮窗（无控制台）
├── stop.bat            # taskkill pythonw（粗暴但有效）
├── state/              # 各会话状态文件（运行时由 cc_hook.py 维护，gitignored）
├── venv/               # 虚拟环境（gitignored）
└── config.json         # 标签、面板位置、开机自启（运行时生成，gitignored）
```

## 已知限制

- **多屏**：只在主屏摆面板；副屏待加
- **点圆点跳到对应终端**：还没接（要从 hook 拿 pid 链一路找终端窗口，比较脏）
- **平台**：只在 Windows 11 上测过；macOS / Linux 没测，理论上 PySide6 部分能跑、`install.bat`/`start.bat` 要换 shell

## 故障排查

- **圆点不出现**：先看 `state/` 有没有 json 文件。
  - 没有 → hook 没触发。检查 `~/.claude/settings.json` 里 hooks 是不是写进去了。
  - 有但 0 字节 → 看 `cc_hook.log` 找 traceback；常见原因是中文路径下 stdin 编码问题（本工具已修复，stdin 强制 UTF-8 decode）。
- **PySide6 装不上**：网络问题，换源 `pip install PySide6 -i https://pypi.tuna.tsinghua.edu.cn/simple`。
- **面板飞到屏幕外**：托盘右键 → 重置位置。

## License

MIT

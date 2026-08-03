# better-your-harness

给本地项目做一次 AI Harness 体检，产出一份自包含的可视化 HTML 报告，最后给你一串**可以直接粘给 Claude Code / Codex / 任何 Agent 去修**的口令。

零依赖，只需要 Python 3.8+。不联网，不上传任何东西。

---

## 它解决什么问题

你给 Agent 配了 CLAUDE.md、装了几十上百个 Skill、接了 MCP、建了记忆目录。然后呢？

- 那些 Skill 到底有几个真的被调用过
- Agent 读你这个仓库要先吃掉多少 token
- 有没有明文密钥躺在一个没被 `.gitignore` 覆盖的地方
- 你在 CLAUDE.md 里写的规则，有多少条指向的文件根本不存在

这些问题都有确定的答案，只是没人扫过。

## 快速开始

```bash
git clone https://github.com/SpaceZephyr/build-your-harness.git
cd build-your-harness/better-your-harness

# 1. 扫描（大仓库约 15-30 秒）
python3 scripts/scan.py /path/to/your/project -o findings.json

# 2. 渲染（不带 AI 判断，也能出一份纯事实报告）
python3 scripts/render.py findings.json -o report.html
```

装成 Skill，让 Agent 帮你写判断和修复口令。软链到你用的那个 runtime 的 Skill 目录：

```bash
ln -s "$(pwd)" ~/.claude/skills/better-your-harness   # Claude Code
ln -s "$(pwd)" ~/.codex/skills/better-your-harness    # Codex
```

然后跟你的 Agent 说「帮我给这个项目做个 harness 体检」。

不装也行，脚本是纯 Python CLI，不依赖任何 runtime。

## 报告里有什么

| 区块 | 内容 |
|------|------|
| 总览 | 覆盖度环形、判词、仓库可见性（PUBLIC 会标红） |
| 五层雷达 | 安全与卫生 / 上下文质量 / 工具装备 / 记忆 / 学习，34 项检查逐项列出 |
| 上下文质量 | 噪音比甜甜圈、冷启动 token 刻度、目录可读性、超大文件、扁平目录 |
| 工具装备 | **僵尸 Skill 点阵**：一个点一个 Skill，真实调用过的点亮 |
| 待办 | 按严重度排序，每条一个「复制修复口令」按钮 |
| 方法与局限 | 主动写明这份体检**证明不了**什么 |

图表全是手绘内联 SVG，深浅色自适应，可打印。

## 五层查了什么

**安全与卫生** — `.gitignore` 存在与覆盖度、被跟踪文件噪音比、明文凭证（文件 glob + 7 类 token 模式 + 变量名启发）、凭证是否被跟踪或被 ignore、仓库可见性、Agent 权限里的 yolo/bypass、hooks 数量

**上下文质量** — 入口文件（CLAUDE.md / AGENTS.md 等）体量与结构、是否含目录地图和行为规则、冷启动 token 成本、顶层目录 README 覆盖率、目录深度与扁平度、超大文本文件、jsonl 索引的悬空条目

**工具装备** — Skill 去重后装机量、缺 SKILL.md、缺 frontmatter、description 过短、软链接、MCP 服务、自定义命令、子 Agent

**记忆** — 记忆目录、索引是否存在、悬空条目、未入索引的文件、结构化日志

**学习** — 迭代与复盘目录、距上次提交多少天、未提交改动堆积量、Skill 更新与陈旧比例

## 三条设计铁律

这个工具的价值全在这三条上。

### 1. 数字只能来自脚本

报告里每一个数字都能在 `findings.json` 里找到出处。仓库可见性走 `gh repo view --json visibility`，不从 remote URL 猜。

> 做这个工具的直接动机，是某商业审计工具把一个 PRIVATE 仓库报成了 public，仓主名字也写错了 —— 而那恰恰是它给最高优先级定级的前提。脚本能查的数字它一个没错，唯独这个「靠推断」的字段错了。

### 2. 密钥的值永远不出现

扫描器只输出「文件路径 + 变量名 + 命中的模式名」。报告里、对话里、修复口令里，都不会有任何密钥的值。发现密钥的正确反应是让你加 ignore，不是把它展示一遍。

### 3. AI 不许发明发现

架构是三段分离：

```
scan.py    →  findings.json    确定性事实 + 带固定 id 的候选发现
AI         →  analysis.json    只能给已有 id 填严重度和文案
render.py  →  report.html      固定模板，样式每次都一样
```

AI 拿不到发明新发现的权限。看到脚本没扫到的问题，只能在总判词里提一句，不能伪造成一条带证据的条目。

## 不打分，打覆盖度

报告顶部是 `15/34`，意思是「已具备项 / 应有项」。

不用百分制。「任务理解 55 分」这种数字需要一个不存在的基线，而且不可证伪 —— 用户既不知道满分多少，也不知道怎么让它变成 60。`15/34` 修一项就变一项。

## 修复口令的规矩

口令是这个工具真正产生价值的地方，报告只是让你相信该修。

- 写绝对路径，不写「你的项目根目录」
- 列具体文件名，不写「相关文件」
- 带验证步骤（跑什么命令、看什么输出）
- **破坏性操作一律要求「先给我看，不要直接改」**

因为你是把口令粘给另一个没有上下文的 Agent，刹车必须写在口令自己身上。

## 尊重刻意设计

看到反常结构，先想它是不是有意为之。

用 codename 命名目录（`01 forge`、`02 scope`）牺牲了可读性，但如果入口文件里有解码表，那是「隐蔽性换可读性」的主动权衡，报成观察项，不当缺陷扣分。从 Notion 导出的存档目录扁平，那是导出工具决定的。

体检工具不该把用户的设计判断当 bug。

## 僵尸 Skill 的统计口径

只认会话日志里 `tool_use(name="Skill")` 的 `input.skill`，不认「出现在系统提示词的 Skill 清单里」。

这两个口径能差两个数量级：每轮对话都会带上全部可用 Skill 的列表，按关键词 grep 会把每个 Skill 都算成用过。开发过程中我自己先踩了这个坑，第一版统计出「252 个用过」，改对口径后是 7 个。

## 局限

- 只描述仓库当前状态，**不评估你的效率、产出质量或模型选择**
- 会话统计依赖本地日志，换客户端或清过日志就统计不到
- 凭证扫描是启发式的，可能漏（自定义格式）也可能误报（占位符已尽量排除）
- 覆盖度里的「应有项」是这个工具定的，不是行业标准
- 仓库可见性检测需要 `gh` CLI，没装就显示 UNKNOWN

## 文件

```
better-your-harness/
├── SKILL.md              Skill 说明书，标准 SKILL.md 格式
└── scripts/
    ├── scan.py           确定性扫描 → findings.json，不做任何判断
    └── render.py         findings.json + analysis.json → 单页 HTML
```

`.gitignore` 里排除了 `*.html`、`findings.json`、`analysis.json` —— 体检产物含被扫项目的真实路径和结构，不该进仓库。

## License

MIT

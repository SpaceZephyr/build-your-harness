<div align="center">

# build-your-harness

---

`star-your-harness.skill` &nbsp;·&nbsp; `better-your-harness.skill` &nbsp;·&nbsp; `view-your-harness.skill`

<br>

![LICENSE](https://img.shields.io/badge/LICENSE-MIT-DFB317?style=for-the-badge&labelColor=555555)
![AGENT SKILLS](https://img.shields.io/badge/AGENT_SKILLS-STANDARD-4CAF50?style=for-the-badge&labelColor=555555)
![DEPENDENCIES](https://img.shields.io/badge/DEPENDENCIES-ZERO-2196F3?style=for-the-badge&labelColor=555555)

![RUNTIME](https://img.shields.io/badge/RUNTIME-CLAUDE_CODE_%C2%B7_CODEX_%C2%B7_CURSOR_%C2%B7_OPENCLAW-7C3AED?style=for-the-badge&labelColor=555555)

公众号 / 小红书 / B站 / 知乎：空格的键盘 &nbsp;|&nbsp; [wzfh520@gmail.com](mailto:wzfh520@gmail.com)

</div>

---

三个配套的 Agent Skill：**一个负责搭 harness，一个负责给 harness 体检，一个负责日常翻。**

| Skill | 干什么 | 产出 |
|-------|--------|------|
| [**star-your-harness**](star-your-harness/) | 从零搭一个 harness | 可视化方案报告 → 你确认 → 目录骨架落盘 |
| [**better-your-harness**](better-your-harness/) | 给现有 harness 体检 | 可视化体检报告 + 可一键复制的修复口令 |
| [**view-your-harness**](view-your-harness/) | 日常翻你的 harness | 本地只读工作台：文件清单 + Skill 装备台 |

零依赖，只需要 Python 3.8+。不联网，不上传任何东西。

## 不绑定任何一个 Agent

三个 Skill 用的是标准 `SKILL.md` 格式（YAML frontmatter + 正文），**任何能读它的 Agent 都能用**：Claude Code、Codex、Cursor、OpenClaw、以及各种 buddy 系工具。

更彻底一点：**底层全是纯 Python 命令行脚本，不 import 任何 Agent 相关的东西。** 你完全不用 Skill 机制，直接当 CLI 跑也行，产出的 HTML 报告是一样的。Skill 那层只是替你把访谈、判断、串流程这些事包起来。

体检工具还会**同时扫描多个 runtime 的 Skill 目录**（`~/.claude/skills`、`~/.codex/skills`、项目级 `.claude/skills` 和 `.agents/skills`），按唯一名字去重，所以你混着用几个 Agent 也能得到一个统一的清单。

## 什么是 harness

不是笔记软件，不是知识库，是**你和 Agent 之间的那层结构**。

你写过 CLAUDE.md 或 AGENTS.md、装过 Skill、接过 MCP、建过记忆目录，那些零件加起来就是 harness。问题是大多数人的 harness 是**攒**出来的不是**搭**出来的：目录随手建，规则想起来才写，资料散在三个地方，每次让 Agent 干活都要重新解释一遍背景。

更麻烦的是你不知道它现在什么状况。装了多少 Skill 真正被调用过？Agent 读你这个仓库要先吃掉多少 token？有没有明文密钥躺在一个没被 `.gitignore` 覆盖的地方？

star 管搭，better 管查状况，view 管你每天翻着看手上到底有什么。

## 五层框架

三个工具共用同一套语言，所以搭出来的东西能直接被体检、被翻阅：

| 层 | 是什么 | 落地成什么 |
|----|--------|-----------|
| **安全与卫生** | 别把自己搞出事故 | `.gitignore`、凭证保护、Agent 权限、hooks |
| **上下文质量** | Agent 读你这儿有多费劲 | 入口文件、目录地图、README 覆盖、噪音比、冷启动成本 |
| **工具装备** | 手上有什么家伙 | Skill、MCP、子 Agent、自定义命令 |
| **记忆** | 跨会话记得住什么 | 记忆目录 + 索引 |
| **学习** | 系统会不会越用越顺 | 迭代记录、复盘、提交节奏 |

## 装

```bash
git clone https://github.com/SpaceZephyr/build-your-harness.git
cd build-your-harness
```

**Claude Code**

```bash
ln -s "$(pwd)/star-your-harness"   ~/.claude/skills/star-your-harness
ln -s "$(pwd)/better-your-harness" ~/.claude/skills/better-your-harness
ln -s "$(pwd)/view-your-harness"   ~/.claude/skills/view-your-harness
```

**Codex**

```bash
ln -s "$(pwd)/star-your-harness"   ~/.codex/skills/star-your-harness
ln -s "$(pwd)/better-your-harness" ~/.codex/skills/better-your-harness
ln -s "$(pwd)/view-your-harness"   ~/.codex/skills/view-your-harness
```

**其他 Agent** — 软链到它的 Skill 目录就行，三个 Skill 除了 `SKILL.md` 和 `scripts/` 没有别的依赖。项目级也可以：`<项目>/.claude/skills/` 或 `<项目>/.agents/skills/`。

装完说一句「帮我搭一个 harness」「给这个项目做个体检」或者「打开工作台」。

**不装也能用**

```bash
# 体检
python3 better-your-harness/scripts/scan.py <项目目录> -o findings.json
python3 better-your-harness/scripts/render.py findings.json -o report.html

# 搭建
python3 star-your-harness/scripts/plan.py profile.json -o plan.html
python3 star-your-harness/scripts/apply.py plan.json -d decisions.json --apply

# 工作台
python3 view-your-harness/scripts/serve.py <任意目录>
```

> 实测跑过 Claude Code 和 Codex。其他 runtime 因为格式是标准的、脚本是纯 Python，理论上都行，但我没逐个验证过 —— 遇到问题开个 issue。

## 三个工具怎么配合

```
                    ┌─────────────────────┐
   什么都没有   ──▶  │  star-your-harness  │ ──▶  一个立得住的骨架
                    └─────────────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
   用了一阵    ──▶   │ better-your-harness │ ──▶  覆盖度 + 待办 + 修复口令
                    └─────────────────────┘
                              │
                              ├──▶ 修完再体检，看覆盖度有没有涨
                              ▼
                    ┌─────────────────────┐
   东西堆多了  ──▶   │  view-your-harness  │ ──▶  能翻能搜的工作台
                    └─────────────────────┘
```

体检回答「我这儿哪里有问题」，工作台回答「我这儿都有什么」。装到一百多个 Skill 之后，后者才是你每天真正会打开的那个。

**验收标准是可测的：star 生成出来的 harness，直接跑 better，安全层和上下文层必须满分。**

实测一个刚生成的：

```
覆盖度 28/34
  安全与卫生   7/7   ← 满分
  上下文质量   9/9   ← 满分
  记忆         5/5   ← 满分
  学习         5/6
  工具装备     2/7
```

后两层扣的分是时间问题：新 harness 还没装 Skill 和 MCP，git 也只有一天的提交历史。**这个如实说，不粉饰。**

这套闭环不只是好看，它真的抓过 bug：搭出来的 `40-memory/` 被体检判成 0/5，查下去发现体检器只认死名字 `cortex` / `memory`，带序号前缀的一律看不见。两个工具互相验证，比各自单测有用。

## 三条共同的设计原则

### 数字只能来自脚本

报告里每一个数字都能在 `findings.json` / `plan.json` 里找到出处。仓库可见性走 `gh repo view --json visibility`，不从 remote URL 猜。

> 做这套东西的直接动机，是某商业审计工具把一个 PRIVATE 仓库报成了 public、仓主名字也写错了 —— 而那恰恰是它给最高优先级定级的前提。它脚本能查的数字一个没错，唯独这个「靠推断」的字段错了。

### 破坏性动作必须人点头

`plan.py` 一个字节都不写盘。`scan.py` 只读不写。`serve.py` 整个服务没有写、改、删接口，只绑 `127.0.0.1`，路径越界一律 403。搬运用 `copy` 不用 `move`，同名一律跳过不覆盖。

体检报告不直接改你的仓库，它给你一段修复口令，你自己决定粘不粘给 Agent。

凭证扫描只输出「文件路径 + 变量名 + 命中的模式名」，**任何密钥的值都不会出现在报告、对话或修复口令里**。

### 不打分，打覆盖度

`28/34` 是「已具备项 / 应有项」，可数、可解释、修一项变一项。

不用百分制。「任务理解 55 分」这种数字需要一个不存在的基线，而且不可证伪 —— 你既不知道满分多少，也不知道怎么让它变成 60。

## 目录

```
build-your-harness/
├── star-your-harness/          搭
│   ├── SKILL.md                Skill 说明书（含四问访谈流程）
│   ├── GUIDE.md                完整文档
│   └── scripts/
│       ├── plan.py             profile → 可视化方案报告（不写盘）
│       ├── apply.py            方案 + 你的决定 → 落盘
│       ├── scaffold.py         骨架生成
│       └── migrate.py          旧资料归类
├── better-your-harness/        体检
│   ├── SKILL.md                Skill 说明书（含三条铁律）
│   ├── GUIDE.md                完整文档
│   └── scripts/
│       ├── scan.py             确定性扫描 → findings.json
│       └── render.py           findings + analysis → 可视化报告
└── view-your-harness/          翻
    ├── SKILL.md                Skill 说明书（含三条铁律）
    ├── GUIDE.md                完整文档
    └── scripts/
        ├── index.py            目录 + Skill 清点 → index.json
        ├── serve.py            本地只读服务，只绑 127.0.0.1
        └── ui.html             单页工作台，原生 JS
```

`.gitignore` 排除了 `*.html`、`findings.json`、`plan.json` 这些产物 —— 它们含被扫或被搭项目的真实路径和结构，不该跟着开源代码走。

## 局限

- 只在 macOS / Linux 上测过
- 会话统计依赖本地日志，换 Agent 或清过日志就统计不到
- 凭证扫描是启发式的，可能漏（自定义格式）也可能误报（占位符已尽量排除）
- 归类规则是中英混合关键词匹配，小众命名习惯会认不准
- 工作台默认最多索引 20000 个文件，卡片墙一次最多渲染 300 张
- **「从未调用」不等于「没用」** —— 刚装的、只看过 reference 的、被别的 Skill 内部引用的，都会显示成从未调用
- 覆盖度里的「应有项」是这套工具定的，不是行业标准
- **只描述仓库状态，不评估你的效率、产出质量或模型选择**

## License

MIT

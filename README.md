<div align="center">

# build-your-harness

---

`star` &nbsp;·&nbsp; `know` &nbsp;·&nbsp; `sync` &nbsp;·&nbsp; `better` &nbsp;·&nbsp; `view` &nbsp;·&nbsp; **v2.0**

<br>

![LICENSE](https://img.shields.io/badge/LICENSE-MIT-DFB317?style=for-the-badge&labelColor=555555)
![AGENT SKILLS](https://img.shields.io/badge/AGENT_SKILLS-STANDARD-4CAF50?style=for-the-badge&labelColor=555555)
![DEPENDENCIES](https://img.shields.io/badge/DEPENDENCIES-ZERO-2196F3?style=for-the-badge&labelColor=555555)

![RUNTIME](https://img.shields.io/badge/RUNTIME-CLAUDE_CODE_%C2%B7_CODEX_%C2%B7_CURSOR_%C2%B7_OPENCLAW-7C3AED?style=for-the-badge&labelColor=555555)

公众号 / 小红书 / B站 / 知乎：空格的键盘 &nbsp;|&nbsp; [wzfh520@gmail.com](mailto:wzfh520@gmail.com)

</div>

---

五个配套的 Agent Skill，覆盖一个个人 harness 的完整生命周期：**搭起来、认识你、同步出去、定期体检、日常翻看。**

| Skill | 干什么 | 产出 |
|-------|--------|------|
| [**star-your-harness**](star-your-harness/) | 从零搭，或者把已有的乱目录原地重组 | 可视化方案 → 你确认 → 落盘。入口 AGENTS.md + NOW.md + TOOLS.md |
| [**know-your-harness**](know-your-harness/) | 用真实数据生成你的画像 | 各平台内容的最好与最差、有依据的规律、填好的工具清单 |
| [**sync-your-harness**](sync-your-harness/) | 让 harness 跨设备、跨 Agent 可用 | 推送预演、白名单 `.gitignore`、大文件拦截、共享记忆、Skill 清点 |
| [**better-your-harness**](better-your-harness/) | 给现有 harness 体检 | 可视化体检报告 + 可一键复制的修复口令 + 换 Agent 自测 |
| [**view-your-harness**](view-your-harness/) | 日常翻你的 harness | 本地只读工作台：文件清单 + Skill 装备台 |

不想装 Skill，只想要几句能直接用的话？看 [PROMPTS.md](PROMPTS.md)：7 条提示词，复制给任何 Agent 就能优化你本地的 harness。

## 2.0 改了什么

1.0 能搭出一个空骨架。用了几个月之后发现，真正难的是另外四件事，2.0 就是补这四件：

| 问题 | 1.0 | 2.0 |
|------|-----|-----|
| 我已经有一个乱了几年的目录 | 只能新建一个再复制过去 | **改造模式**：原地重组顶层，只移动不删除，留 MANIFEST 和 undo.sh |
| 换一个 Agent 就不认识我了 | 入口是 CLAUDE.md，只有 Claude Code 读 | **AGENTS.md 是唯一正本**，CLAUDE.md 只留一行引用。加了 NOW.md（当前主线）和 TOOLS.md（工具清单） |
| `about-me` 永远填不完 | 三份空模板等你手写 | **know-your-harness**：拉你自己发过的内容，脚本算出什么表现好，画像里每个数字都有出处 |
| 推到 GitHub 怕泄露、怕臃肿 | 一份基础 `.gitignore` | **sync-your-harness**：白名单规则、推送预演、密钥位置扫描、pre-commit 拦大文件 |
| 怎么知道 harness 真的能用 | 结构体检 | 体检新增 4 项，外加**上手自测**：换一个 Agent 读完入口，答 5 道只有读过你资料才答得出的题 |

零依赖，只需要 Python 3.8+。不联网，不上传任何东西。

## 不绑定任何一个 Agent

五个 Skill 用的是标准 `SKILL.md` 格式（YAML frontmatter + 正文），**任何能读它的 Agent 都能用**：Claude Code、Codex、Cursor、OpenClaw、以及各种 buddy 系工具。

更彻底一点：**底层全是纯 Python 命令行脚本，不 import 任何 Agent 相关的东西。** 你完全不用 Skill 机制，直接当 CLI 跑也行，产出的 HTML 报告是一样的。Skill 那层只是替你把访谈、判断、串流程这些事包起来。

体检工具还会**同时扫描多个 runtime 的 Skill 目录**（`~/.claude/skills`、`~/.codex/skills`、项目级 `.claude/skills` 和 `.agents/skills`），按唯一名字去重，所以你混着用几个 Agent 也能得到一个统一的清单。

## 什么是 harness

不是笔记软件，不是知识库，是**你和 Agent 之间的那层结构**。

你写过 CLAUDE.md 或 AGENTS.md、装过 Skill、接过 MCP、建过记忆目录，那些零件加起来就是 harness。问题是大多数人的 harness 是**攒**出来的不是**搭**出来的：目录随手建，规则想起来才写，资料散在三个地方，每次让 Agent 干活都要重新解释一遍背景。

更麻烦的是你不知道它现在什么状况。装了多少 Skill 真正被调用过？Agent 读你这个仓库要先吃掉多少 token？有没有明文密钥躺在一个没被 `.gitignore` 覆盖的地方？

star 管搭，know 管让它认识你，sync 管让它走出这台电脑，better 管查状况，view 管你每天翻着看手上到底有什么。

## 五层框架

五个工具共用同一套语言，所以搭出来的东西能直接被体检、被翻阅：

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
for s in star know sync better view; do
  ln -s "$(pwd)/$s-your-harness" ~/.claude/skills/$s-your-harness
done
```

**Codex**

```bash
for s in star know sync better view; do
  ln -s "$(pwd)/$s-your-harness" ~/.codex/skills/$s-your-harness
done
```

**其他 Agent** — 软链到它的 Skill 目录就行，五个 Skill 除了 `SKILL.md` 和 `scripts/` 没有别的依赖。项目级也可以：`<项目>/.claude/skills/` 或 `<项目>/.agents/skills/`。

装完说一句「帮我搭一个 harness」「我的目录太乱了帮我重组」「帮我生成画像」「推到 GitHub 安全吗」「给这个项目做个体检」或者「打开工作台」。

**不装也能用**

```bash
# 体检
python3 better-your-harness/scripts/scan.py <项目目录> -o findings.json
python3 better-your-harness/scripts/render.py findings.json -o report.html

# 搭建
python3 star-your-harness/scripts/plan.py profile.json -o plan.html
python3 star-your-harness/scripts/apply.py plan.json -d decisions.json --apply

# 改造已有目录（scan 只读，apply 默认预演）
python3 star-your-harness/scripts/restructure.py scan <harness目录> -o <输出目录>
python3 star-your-harness/scripts/restructure.py apply restructure-plan.json -d decisions.json --apply

# 画像
python3 know-your-harness/scripts/probe.py
python3 know-your-harness/scripts/rank.py <任意平台导出的.json>

# 同步
python3 sync-your-harness/scripts/sync.py preview <harness目录>

# 工作台
python3 view-your-harness/scripts/serve.py <任意目录>
```

> 实测跑过 Claude Code 和 Codex。其他 runtime 因为格式是标准的、脚本是纯 Python，理论上都行，但我没逐个验证过 —— 遇到问题开个 issue。

## 五个工具怎么配合

```
 什么都没有 ─┐
             ├─▶ star   搭骨架 / 原地重组      ─▶ AGENTS.md + NOW.md + TOOLS.md + 七层目录
 一个乱目录 ─┘        │
                      ▼
                   know   拉数据、算排名、写画像  ─▶ Agent 知道你是谁、什么内容表现好
                      │
                      ▼
                   sync   预演、白名单、共享记忆  ─▶ 换电脑、换 Agent 都能接着用
                      │
                      ▼
                   better 结构体检 + 换 Agent 自测 ─▶ 覆盖度 + 待办 + 修复口令
                      │        └─▶ 修完再体检，看覆盖度有没有涨
                      ▼
                   view   能翻能搜的工作台
```

体检回答「我这儿哪里有问题」，工作台回答「我这儿都有什么」。装到一百多个 Skill 之后，后者才是你每天真正会打开的那个。

**验收标准是可测的：star 生成出来的 harness，直接跑 better，安全层和上下文层必须满分。**

实测一个刚生成的：

```
覆盖度 32/38
  安全与卫生   7/7   ← 满分
  上下文质量   13/13 ← 满分（2.0 新增 4 项：入口只有一份正本、NOW.md、TOOLS.md、上手自测）
  记忆         5/5   ← 满分
  学习         5/6
  工具装备     2/7
```

后两层扣的分是时间问题：新 harness 还没装 Skill 和 MCP，git 也只有一天的提交历史。**这个如实说，不粉饰。**

这套闭环不只是好看，它真的抓过 bug：搭出来的 `40-memory/` 被体检判成 0/5，查下去发现体检器只认死名字 `cortex` / `memory`，带序号前缀的一律看不见。两个工具互相验证，比各自单测有用。

## 三条共同的设计原则

2.0 新增的脚本守的是同一套。

### 数字只能来自脚本

报告里每一个数字都能在 `findings.json` / `plan.json` 里找到出处。仓库可见性走 `gh repo view --json visibility`，不从 remote URL 猜。

> 做这套东西的直接动机，是某商业审计工具把一个 PRIVATE 仓库报成了 public、仓主名字也写错了 —— 而那恰恰是它给最高优先级定级的前提。它脚本能查的数字一个没错，唯独这个「靠推断」的字段错了。

### 破坏性动作必须人点头

`plan.py` 一个字节都不写盘。`scan.py` 只读不写。`serve.py` 整个服务没有写、改、删接口，只绑 `127.0.0.1`，路径越界一律 403。搬运用 `copy` 不用 `move`，同名一律跳过不覆盖。

2.0 的改造模式是唯一会移动你文件的地方，所以规矩最严：`scan` 的输出目录不允许在 harness 里面，`apply` 不加 `--apply` 只预演，只移动不删除，目标有同名就跳过，每一步写进 `MANIFEST.md` 并生成 `undo.sh`。同步工具不执行任何 git 命令，已有的 `.gitignore` 和 hook 不覆盖，新规则写成 `.proposed` 文件等你对比。

体检报告不直接改你的仓库，它给你一段修复口令，你自己决定粘不粘给 Agent。

凭证扫描只输出「文件路径 + 变量名 + 命中的模式名」，**任何密钥的值都不会出现在报告、对话或修复口令里**。

### 不打分，打覆盖度

`32/38` 是「已具备项 / 应有项」，可数、可解释、修一项变一项。

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
│       ├── scaffold.py         骨架生成（--entry-only 只补入口文件）
│       ├── migrate.py          旧资料归类
│       └── restructure.py      改造模式：原地重组已有目录
├── know-your-harness/          认识你
│   ├── SKILL.md
│   └── scripts/
│       ├── probe.py            探测可用工具和数据源（只读变量名）
│       ├── collect.py          GitHub 仓库 + 本地文本统计
│       └── rank.py             任意平台 JSON → 最好 / 最差 / 分布
├── sync-your-harness/          同步
│   ├── SKILL.md
│   └── scripts/
│       └── sync.py             preview / apply / memory / skills
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

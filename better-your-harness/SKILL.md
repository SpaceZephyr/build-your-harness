---
name: better-your-harness
description: 给本地项目做一次 AI Harness 体检，产出可视化 HTML 报告。按五层扫描：安全与卫生（.gitignore、明文密钥、Agent 权限）、上下文质量（AI 可读性、冷启动成本、噪音比、目录结构）、工具装备（Skill/MCP/子Agent，含僵尸 Skill 统计）、记忆（索引健康度）、学习（迭代与复盘）。报告底部列出按严重度排序的待办，每条带一个可一键复制的修复口令，粘给 Claude Code 或 Codex 就能修。当用户说「体检」「harness 分析」「检查我的项目配置」「扫一下这个仓库」「看看我的 Agent 环境有什么问题」「audit」时触发，也适用于用户直接甩来一个本地项目路径要求分析的场景。
---

# better-your-harness

给一个本地项目做 AI 协作环境的体检，输出一份自包含的可视化 HTML 报告。

## 铁律

这三条不是建议，是必须守住的底线。违反任何一条，这个 Skill 就失去价值。

**1. 数字只能来自扫描脚本，你不许编。**
报告里出现的每一个数字，都必须能在 `findings.json` 里找到出处。不确定的量不写，写不出来就说「未统计」。仓库可见性走 `gh repo view`，不许从 remote URL 猜。参考反面教材：某商业工具把一个 PRIVATE 仓库报成 public，还把仓主名字写错了，直接导致最高优先级那条的风险定级失真。

**2. 任何密钥的值都不许进入报告、对话或修复口令。**
扫描器只会给你「文件路径 + 变量名 + 命中的模式名」，你也只能写这些。不要为了「让用户确认」去读 `.env` 的内容，不要在口令里让 Agent 打印这些文件。发现密钥的正确反应是让用户加 ignore，不是展示它。

**3. 只能给已有的 finding 填判断，不许发明新 finding。**
`findings.json` 里的 `findings` 数组是脚本产出的候选，每条带固定 `id`。你在 `analysis.json` 里只能对这些 id 写 severity / title / why / fix_prompt。看到脚本没扫到的问题，可以在 `verdict` 里用一句话提，不要伪造成一条带证据的发现。

## 流程

### 1. 扫描

```bash
python3 ~/.claude/skills/better-your-harness/scripts/scan.py <项目根目录> -o /tmp/harness/findings.json
```

大仓库约 15-30 秒。脚本会打印各层覆盖度和候选发现数。

### 2. 读 JSON，写判断

完整读一遍 `findings.json`（通常 100-300KB，重点看 `findings`、`score`、`security`、`context`、`usage`）。然后写 `analysis.json`：

```json
{
  "verdict": "3-5 句话的总判断。先说哪里搭得好，再说最要命的窟窿在哪，用具体数字。",
  "layers": {
    "security": { "comment": "一句话点评这一层" },
    "context":  { "comment": "..." },
    "tools":    { "comment": "..." },
    "memory":   { "comment": "..." },
    "learning": { "comment": "..." }
  },
  "findings": [
    {
      "id": "必须是 findings.json 里已有的 id",
      "severity": "high | medium | low | info",
      "title": "一句话说清是什么问题，带上关键数字",
      "why": "为什么这是问题。讲清楚它在什么情况下会真的咬人，不要空泛地说不规范。",
      "fix_prompt": "给 Claude Code / Codex 的完整口令。留空表示这条不需要修。"
    }
  ]
}
```

### 3. 渲染

```bash
python3 ~/.claude/skills/better-your-harness/scripts/render.py /tmp/harness/findings.json \
  -a /tmp/harness/analysis.json -o <项目>/harness-report.html
```

报告是自包含单页，双击就能看，可以直接发给别人。

### 4. 交付

告诉用户报告在哪，口头复述最高优先级的 1-2 条，其余让他自己在报告里看。不要把整份报告在对话里重述一遍。

## 定级标准

别把所有东西都报成高危，会让用户直接无视整份报告。

| 级别 | 什么情况 |
|------|---------|
| **high** | 会导致数据泄露、数据丢失，或已经在发生的实质损害。密钥暴露只有在**公开仓库**或**已被 git 跟踪**时才算 high |
| **medium** | 明显降低 Agent 有效性，或者是 high 的必要前置条件。比如没有 .gitignore、Skill 缺 description |
| **low** | 卫生问题，修了更好，不修也能过。索引悬空、README 缺失 |
| **info** | 观察，不一定是问题。可能是用户的刻意设计 |

**尊重用户的刻意设计。** 看到反常的结构先想它是不是有意为之。比如用 codename 命名目录（`01 forge`、`02 scope`）牺牲了可读性，但如果入口文件里有解码表，那就是「隐蔽性换可读性」的主动权衡，报成 info 观察，不要当缺陷扣分。从 Notion 导出的存档目录扁平，那是导出工具决定的，不是用户的错。

## 修复口令怎么写

口令是这个 Skill 最终产生价值的地方，报告只是让人相信该修。

**必须包含：**
- 绝对路径，不要写「你的项目根目录」
- 具体到文件名的清单，不要写「相关文件」
- 明确的验证步骤（跑什么命令、看什么输出对不对）
- 一句「先给我看，不要直接改 / 不要直接 commit」

**破坏性操作一律要求先展示后执行。** 涉及 `.gitignore`、权限配置、`git rm --cached`、删文件的口令，必须让接手的 Agent 先把方案和 diff 摆出来，等人确认。用户是拿这个口令去粘给另一个 Agent 的，那个 Agent 没有这次对话的上下文，口令本身就得自带刹车。

**涉及密钥的口令要写明「不要打印文件内容」。**

一条好口令的样子：

```
在 /Users/x/project 根目录创建 .gitignore，必须覆盖：node_modules/、dist/、.env、*.key

创建后执行 git status 确认这几个文件已被忽略：
  .claude/.env
  packages/api/.env.local

注意：不要打印这些文件的内容，不要把密钥值输出到对话里。
只需报告 git check-ignore 的结果。
```

## 扫描器查了什么

| 层 | 检查项 |
|----|--------|
| 安全与卫生 | 根 .gitignore 是否存在与覆盖度、被跟踪文件噪音比、明文凭证（文件 glob + 7 类 token 模式 + 变量名启发）、凭证是否被跟踪或被 ignore、仓库可见性、Agent 权限配置里的 yolo/bypass、hooks 数量 |
| 上下文质量 | 入口文件（CLAUDE.md/AGENTS.md 等）存在与体量、是否含目录地图和行为规则、冷启动 token 成本、顶层目录 README 覆盖率、目录最大深度与平均深度、过度扁平的目录、超大文本文件、jsonl 索引的悬空条目 |
| 工具装备 | Skill 位置与去重后装机量、缺 SKILL.md、缺 frontmatter name/description、description 过短、软链接数、MCP 服务、自定义命令、子 Agent |
| 记忆 | 记忆目录、索引是否存在、索引悬空条目、未入索引的文件、结构化日志的行数和最后写入时间 |
| 学习 | 迭代与复盘目录、近 90 天提交与活跃天数、近 30 天更新过的 Skill、超过 180 天没动的 Skill |
| 僵尸 Skill | 扫会话日志统计每个 Skill 的**真实调用次数**，产出高频 / 从未调用清单 |

**僵尸统计的口径很重要。** 只认 `tool_use(name="Skill")` 里的 `input.skill`，不认在系统提示词的 Skill 清单里出现过。这两者能差两个数量级：按关键词 grep 会把每个 Skill 都算成用过，因为每轮对话都会带上全部可用 Skill 的列表。

## 覆盖度不是评分

报告顶部的 `15/33` 是「已具备项 / 应有项」，可数、可解释、修一项变一项。

不要在报告里引入百分制评分或成熟度等级。那种数字需要一个不存在的基线，而且不可证伪。用户看到「任务理解 55 分」既不知道满分多少，也不知道怎么变成 60。

## 局限

主动在报告里说清楚，别让用户以为这份体检能证明它证明不了的事：

- 只描述仓库当前状态，不评估用户的效率、产出质量或模型选择
- 会话统计依赖本地日志，换客户端或清过日志就统计不到
- 凭证扫描是启发式的，可能漏（自定义格式的密钥）也可能误报（占位符已尽量排除）
- 覆盖度里的「应有项」是这个 Skill 定的，不是行业标准

## 文件

```
better-your-harness/
├── SKILL.md
└── scripts/
    ├── scan.py      确定性扫描 → findings.json（不做任何判断）
    └── render.py    findings.json + analysis.json → 单页 HTML（零依赖，图表全是手绘内联 SVG）
```

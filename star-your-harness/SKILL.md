---
name: star-your-harness
description: 帮用户从零搭一个自己的 AI harness 工作目录。先用四个问题做一次简短访谈（你是干什么的、想让 AI 帮你做什么、现在的资料散在哪、放哪儿），然后按职业生成目录骨架，含入口 CLAUDE.md（目录地图 + 行为规则 + 任务路由）、about-me 上下文层、记忆层与索引、协议层与复盘、工具层、.gitignore 和 hooks，最后给出把已有资料搬进来的归类计划。生成的 harness 能直接通过 better-your-harness 的体检。当用户说「帮我搭一个 harness」「我想建自己的 AI 工作目录」「怎么组织我的 AI 协作环境」「从零开始配 Claude Code 的项目结构」「我的资料太乱了想重新组织」「star my harness」时触发。
---

# star-your-harness

帮用户从零搭一个 harness。跟 [better-your-harness](https://github.com/SpaceZephyr/build-your-harness) 是一对：这个负责搭，那个负责体检。

**验收标准是可测的：生成出来的 harness 直接跑一遍 better-your-harness，安全层和上下文层应该满分。** 做不到就是这个 Skill 有问题。

## 铁律

**0. 先出方案，确认了再执行。**
任何写盘动作之前，必须先跑 `plan.py` 出一份 HTML 方案报告，让用户在页面上看清楚会建什么、会搬什么、哪些拿不准。他把「我的决定」复制回来，你才能跑 `apply.py --apply`。**不要因为方案看起来没问题就替他确认。**

**1. 绝不覆盖用户已有的文件。**
脚手架遇到同名文件一律跳过并报告。搬运脚本用 `cp -n` 不用 `mv`。用户攒了几年的东西，宁可少搬也不能弄丢。

**2. 搬运只出计划，不动手。**
`migrate.py` 永远不移动文件，它产出一份可读可审的 `migrate.sh`。归类是按文件名猜的，猜错很正常，必须由人过目再自己执行。你可以帮用户读那个脚本、解释某一行为什么这么归类，但不要替他跑。

**3. 不预设用不上的目录。**
空目录是负资产：它让 Agent 以为那里有东西，还拉低信噪比。只生成用户这个职业真正需要的，剩下的等他用到再加。

**4. 访谈要短。**
四个问题就够开工了。问全了再动手，人会在第七个问题的时候放弃。骨架立起来之后，剩下的慢慢填。

## 流程

### 第一步：访谈（四个问题，一次问一个）

像聊天，不像填表。用户随时可以说「跳过」或者「就这样开始吧」。

**1. 你平时主要做什么？**
听出他的角色，映射到模板：`content-creator` / `pm` / `engineer` / `researcher` / `consultant` / `generalist`。不要念这些英文给他听，你自己心里对上就行。听不准就问一句「那你产出的东西主要是文章、文档、代码，还是别的？」

**2. 你想让 AI 主要帮你做什么？**
这一问决定哪几层要重。他说「帮我写东西」，产出层和 about-me 就是重点；说「帮我记住事情」，记忆层要先立起来；说「帮我少重复劳动」，协议层和工具层优先。把答案原话记下来，之后要写进种子记忆里。

**3. 你现在的资料都散在哪儿？**
这是迁移入口，也是这个 Skill 比「给你一个模板」有价值的地方。让他列出目录路径。可能有好几个（Obsidian 库、下载文件夹、某个项目目录）。没有也没关系，说明是全新开始。

**4. 这个 harness 放在哪儿？**
要一个绝对路径。**如果目录已存在且非空，必须明确告诉他「已有文件一个都不会被覆盖，同名的会跳过」，等他确认再继续。**

顺带确认命名风格，给三个选项让他挑，别问开放题：
- `numbered-en`（默认）：`00-inbox` `10-about-me` `20-forge`
- `numbered-zh`：`00 收件箱` `10 关于我` `20 创作`
- `plain-en`：`inbox` `about-me` `forge`

### 第二步：写 profile.json

```json
{
  "name": "给这个 harness 起的名字",
  "dir": "/绝对路径",
  "role": "content-creator",
  "naming": "numbered-en",
  "why": "用户原话：他为什么要搭这个",
  "purposes": ["产出内容", "沉淀方法"],
  "git": true,
  "hooks": true
}
```

想改产出层目录就加 `outputs`，覆盖职业模板的默认值：

```json
"outputs": [
  {"key": "forge", "label": "创作", "desc": "成稿和草稿"},
  {"key": "scope", "label": "选题", "desc": "待写清单"}
]
```

`why` 一定要用用户的原话，别润色。这句会写进种子记忆，半年后他回来看的就是这一句。

### 第三步：出方案报告

```bash
python3 ~/.claude/skills/star-your-harness/scripts/plan.py profile.json -o plan.html
```

把用户提到的来源目录写进 profile 的 `sources` 数组，方案里会一并给出归类建议。

产出两份：`plan.html` 给人看，`plan.json` 给 `apply.py` 用。**这一步不写任何文件。**

报告里有四块：会建成什么样（目录树 + 每层用途）、需要注意的地方（风险）、要你判断的（可改的下拉框）、确认执行（复制按钮）。

把报告路径给用户，让他自己打开看。本地 `file://` 下剪贴板可能不可用，报告里有兜底：复制失败会把内容展开让他手选。想稳一点就起个本地服务：

```bash
cd <报告目录> && python3 -m http.server 8899
```

### 第四步：等用户的决定

他在页面上调完下拉框，点「复制我的决定」，粘回对话，是这样一段：

```json
{"harness": "...", "decisions": {"<文件绝对路径>": "<目标目录名>|__skip__"}, "include_bulk": []}
```

存成 `decisions.json`。**带 markdown 围栏也能直接存，`apply.py` 会自己剥掉。**

用户说「就按你的建议来」也算确认，这时候不传 `-d` 直接跑就行，脚本会用方案里的默认归类。

### 第五步：预演 → 执行

```bash
python3 ~/.claude/skills/star-your-harness/scripts/apply.py plan.json -d decisions.json          # 预演
python3 ~/.claude/skills/star-your-harness/scripts/apply.py plan.json -d decisions.json --apply  # 执行
```

预演会报「建几个目录、新建几个文件、跳过几个、搬几个、不搬几个分别为什么」。给用户看一眼再加 `--apply`。

搬运用 `copy`，来源文件一个不动。执行完主动告诉他这一点，让他自己决定要不要清理原文件。

### 第六步：体检验收

体检工具就在同一个仓库的隔壁目录：

```bash
python3 ../better-your-harness/scripts/scan.py <harness目录> -o findings.json
```

装成 Skill 的话是 `~/.claude/skills/better-your-harness/scripts/scan.py`。

安全层和上下文层应该是满分。工具层会很低（新 harness 还没装 Skill 和 MCP），学习层缺「近 90 天活跃超 10 天」，这两个是时间问题，如实告诉他不用管。

### 第七步：交代下一步

按优先级说三件事，别多：

1. **去填 `about-me/` 里那三份文件。** harness 的质量几乎全取决于这一步，目录本身不产生价值。
2. **用一周，然后去 `protocols/iterations/` 写第一条迭代记录。** 哪里不顺就改哪里。
3. **一个月后再体检一次，看覆盖度有没有涨。**

## 生成出来是什么

```
CLAUDE.md              入口：目录地图 + 6 条行为规则 + 任务路由表
README.md
.gitignore             含凭证兜底那几行
.claude/settings.json  一个 hook：拦截 git add -A

00-inbox/              没想好放哪的先扔这
10-about-me/           我是谁 / 工作偏好 / 质量标准     ← 上下文层
20-<产出>/             因职业而异                      ← 产出层
30-vault/              别人的东西：摘录、参考          ← 上下文层
40-memory/             MEMORY.md 索引 + 种子记忆       ← 记忆层
50-protocols/          workflows.jsonl + daily-log.jsonl + iterations/  ← 学习层
60-garage/             脚本、Skill、自动化             ← 工具层
```

每个目录一份 README，说明放什么、不放什么、怎么命名。

## 职业模板

只有产出层因职业而异，其余六层是通用的。这是个刻意的设计判断：**harness 的骨架跟你干哪行没关系，只有你产出什么东西才有关系。**

| role | 产出层 |
|------|--------|
| `content-creator` | 创作 / 选题 / 已发布 |
| `pm` | 需求 / 调研 / 已交付 |
| `engineer` | 项目 / 技术笔记 / 已交付 |
| `researcher` | 课题 / 文献 / 产出 |
| `consultant` | 客户 / 提案 / 交付 |
| `generalist` | 项目 / 产出 |

用户的职业不在表里，用 `generalist` 然后靠 `outputs` 自定义。别硬套。

## 几个容易做错的地方

**别把访谈变成需求评审。** 用户说「我就想有个地方放我的东西」，那就够了，直接用 `generalist` 开工。不要追问他的长期目标和 KPI。

**别在他有旧资料的时候先建空目录再说。** 先跑一次 `migrate.py` 的预演，看看他的东西大概分几类，可能会发现需要调整产出层的划分。

**别承诺搬运脚本是对的。** 它是按文件名猜的。说清楚这是「省掉 80% 的体力活」，不是「帮你分好了」。

**别替用户确认方案。** 你把报告生成出来、路径给他，就停下等他。哪怕方案在你看来毫无问题，确认这个动作也得他自己做，这是铁律 0 的全部意义。

**「归类明确」不等于判对了。** 报告里折叠区那批也能改，实测就抓到过：一个文件名带「迭代」的发版记录被判进协议层，实际该进已交付。让用户展开扫一眼。

**目标目录非空时一定要先说清楚。** 这是唯一可能让用户丢东西的环节，虽然脚手架不覆盖，但他心里得有数。

## 文件

```
star-your-harness/
├── SKILL.md
└── scripts/
    ├── plan.py       profile.json → plan.json + plan.html（方案报告，可交互判断，不写盘）
    ├── apply.py      plan.json + decisions.json → 真正落盘（预演 / --apply 两段式）
    ├── scaffold.py   骨架生成的底层实现，也可单独当 CLI 用
    └── migrate.py    归类规则的底层实现，也可单独出 migrate.sh
```

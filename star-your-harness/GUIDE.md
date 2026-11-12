# star-your-harness

跟 AI 聊四句话，给自己搭一个 harness：一个专门给 AI 协作用的工作目录。

先出一份**可视化方案报告**让你过目，你在页面上把拿不准的地方判断掉，确认之后才落盘。**在你点头之前，一个文件都不会被创建或移动。**

零依赖，只需要 Python 3.8+。不联网，不上传任何东西。

跟 [better-your-harness](https://github.com/SpaceZephyr/build-your-harness) 是一对：**这个负责搭，那个负责体检。**

---

## 什么是 harness

不是笔记软件，不是知识库，是**你和 AI 之间的那层结构**。

你写过 CLAUDE.md 或 AGENTS.md、装过 Skill、建过记忆目录，那些零件加起来就是 harness。问题是大多数人是攒出来的，不是搭出来的：目录随手建，规则想起来才写，资料散在三个地方，每次让 Agent 干活都要重新解释一遍背景。

这个工具给你一个**立得住的骨架**，剩下的你往里填。

## 一分钟上手

```bash
git clone https://github.com/SpaceZephyr/build-your-harness.git
cd build-your-harness/star-your-harness
```

写一份 `profile.json`：

```json
{
  "name": "我的写作 harness",
  "dir": "/Users/you/harness",
  "role": "content-creator",
  "naming": "numbered-en",
  "why": "资料散在三个地方，每次让 AI 干活都要重新解释背景",
  "sources": ["/Users/you/旧笔记"]
}
```

三步走：

```bash
# 1. 出方案（不写盘）
python3 scripts/plan.py profile.json -o plan.html

# 2. 浏览器打开 plan.html，把「要你判断的」那几行调好，点「复制我的决定」
#    存成 decisions.json

# 3. 预演 → 执行
python3 scripts/apply.py plan.json -d decisions.json
python3 scripts/apply.py plan.json -d decisions.json --apply
```

装成 Skill，让 Agent 替你跑完整流程（含访谈）。软链到你用的那个 runtime 的 Skill 目录：

```bash
ln -s "$(pwd)" ~/.claude/skills/star-your-harness   # Claude Code
ln -s "$(pwd)" ~/.codex/skills/star-your-harness    # Codex
```

然后跟你的 Agent 说一句「帮我搭一个 harness」。

不装也行，脚本是纯 Python CLI，不依赖任何 runtime。

## 方案报告长什么样

一个自包含的 HTML，四块：

| 区块 | 内容 |
|------|------|
| **1 会建成什么样** | 目录树，左边色条标它属于 harness 哪一层，右边标会写几个文件 |
| **2 需要注意的地方** | 目标目录非空、来源是代码工程、同名冲突 |
| **3 要你判断的** | 每个待搬文件一个下拉框，带判断依据和把握程度，**全都能改** |
| **4 确认执行** | 「复制我的决定」按钮 |

判断结果通过复制按钮回传。深浅色自适应，可打印，图表全是手绘内联 SVG。

## 生成出来是什么

```
AGENTS.md              唯一入口：必读清单 + 目录地图 + 行为规则 + 任务路由 + 边界 + 上手自测
CLAUDE.md              只有一行 @AGENTS.md，让 Claude Code 读到同一份
NOW.md                 当前状态：主线、做与不做、本周
TOOLS.md               工具清单：能调什么、怎么调、花多少钱
README.md
.gitignore             含凭证兜底那几行
.claude/settings.json  一个 hook：拦截 git add -A

00-inbox/              没想好放哪的先扔这                    ← 入口
10-about-me/           我是谁 / 工作偏好 / 质量标准           ← 上下文层
20-<产出>/             因职业而异                            ← 产出层
30-vault/              别人的东西：摘录、案例、参考           ← 上下文层
40-memory/             MEMORY.md 索引 + 种子记忆             ← 记忆层
50-protocols/          workflows + daily-log + iterations/   ← 学习层
60-garage/             脚本、Skill、自动化                   ← 工具层
```

每个目录一份 README，写清楚放什么、不放什么、怎么命名。

## 改造模式

2.0 新增。已经有一个乱目录时，不建新的，原地重组：`restructure.py scan` 出方案报告，你在页面上逐项决定保留、并入哪一层还是归档，确认后 `restructure.py apply --apply` 执行。只移动不删除，每一步记进 `MANIFEST.md`，附 `undo.sh` 可原路退回。完整流程见 [SKILL.md](SKILL.md) 的「改造模式」一节。

## 职业模板

**只有产出层因职业而异，其余六层是通用的。**

这是个刻意的设计判断：harness 的骨架跟你干哪行没关系，只有你产出什么东西才有关系。

| role | 产出层 |
|------|--------|
| `content-creator` | 创作 / 选题 / 已发布 |
| `pm` | 需求 / 调研 / 已交付 |
| `engineer` | 项目 / 技术笔记 / 已交付 |
| `researcher` | 课题 / 文献 / 产出 |
| `consultant` | 客户 / 提案 / 交付 |
| `generalist` | 项目 / 产出 |

不在表里就用 `generalist`，再用 `outputs` 自定义：

```json
"outputs": [
  {"key": "specs",     "label": "需求", "desc": "PRD、验收标准"},
  {"key": "prototype", "label": "原型", "desc": "原型稿、交互说明"}
]
```

目录命名三选一：`numbered-en`（`00-inbox`）、`numbered-zh`（`00 收件箱`）、`plain-en`（`inbox`）。

## 验收标准是可测的

这个工具不靠「看起来挺整齐」交差。**生成出来的 harness 直接跑一遍 better-your-harness，安全层和上下文层必须满分。**

实测一个刚生成的 harness：

```
覆盖度 28/34
  安全与卫生   7/7   ← 满分
  上下文质量   9/9   ← 满分
  记忆         5/5   ← 满分
  学习         5/6
  工具装备     2/7
```

前三层满分是设计出来的：`.gitignore`、AGENTS.md 的目录地图和行为规则、每层 README、记忆索引加种子记忆、结构化日志、git 初始化，这些不是可选项，是默认动作。

后两层扣的分是时间问题：新 harness 还没装 Skill 和 MCP，git 也只有一天的提交历史。**这个如实说，不粉饰。**

## 四条铁律

### 0. 先出方案，确认了再执行

`plan.py` 一个字节都不写盘。只有 `apply.py --apply` 才动文件。

这条是被自己打脸打出来的：第一版跑通闭环时，我为了测试自己把页面上的下拉框设好、替用户点了确认。测试和替人做决定是两回事，加这条就是为了把这件事写死。

### 1. 绝不覆盖已有文件

同名一律跳过并报告。搬运用 `copy` 不用 `move`，来源文件一个不动。你攒了几年的东西，宁可少搬也不能弄丢。

### 2. 搬运只出计划，不动手

归类是按文件名和后缀猜的，猜错很正常。报告里标了把握程度，标「拿不准」的那些一定要人过目。

**「归类明确」也不等于判对了。** 实测抓到过：一个文件名带「迭代」的发版记录被判进协议层，实际该进已交付。所以折叠区那批也能改。

### 3. 不预设用不上的目录

空目录是负资产。它让 Agent 以为那里有东西，还拉低信噪比。

参考过 [LifeOS](https://github.com/danielmiessler/LifeOS)，它的 `USER/` 树预设了 FINANCES、HEALTH、CONTACTS、GEAR、FEED 这些。对一个只做内容创作的人，90% 是空的。这里改成按职业生成最小结构，用到再加。

## 一个具体的拦截

用户选了两个前端项目当迁移源。工具拦了下来：

```
hunyuan-console-prototype — 建议不搬
检测到 package.json、tsconfig.json、node_modules，这是代码工程不是文档目录。
代码归代码仓库，harness 只放文档和决策。
需要 Agent 看代码时直接给它绝对路径，比复制一份进来强。
```

**判据不是体量，是工程标记。** 第一版按文件数和大小判断，结果完全失效：排掉 `node_modules` 之后，一个 Next.js 工程只剩 22 个文件、0.2 MB，但它依然是代码。改成看 `package.json` / `Cargo.toml` / `go.mod` / `.git` 这类标记文件，一抓一个准。

想强搬也行，报告里有个「我还是要搬（不推荐）」的勾选框。

## 从 LifeOS 抄了什么

- **两阶段**：先建结构，再灌意义
- **访谈是对话不是表单**，一次问一件事，随时能跳过，部分完成也算数
- **迁移入口**：把已有材料交过来，不用重新打一遍

拒绝的是它的重运行时（仪表盘、语音通知、常驻进程）。那是产品，不是 harness。这里只产出文件和目录。

## 局限

- 归类规则是中英混合的关键词匹配，小众命名习惯会认不准
- 只在 macOS / Linux 上测过
- 生成的 AGENTS.md 是骨架，**约 3500 token**，够 Agent 理解结构，但你的个人偏好得自己填
- 不做发布、排期、数据回收，harness 只管到产出成品

## 建完之后最要紧的一件事

**去填 `about-me/` 里那三份文件**（我是谁 / 工作偏好 / 质量标准）。

目录本身不产生价值。harness 的质量几乎全取决于这一步。

然后用一周，去 `protocols/iterations/` 写第一条迭代记录：哪里不顺，改了什么，改完好没好。没有这一层，harness 只会越堆越大，不会越用越顺。

## 文件

```
star-your-harness/
├── SKILL.md          Skill 说明书（含访谈流程），标准 SKILL.md 格式
└── scripts/
    ├── plan.py       profile.json → plan.json + plan.html（方案报告，不写盘）
    ├── apply.py      plan.json + decisions.json → 真正落盘（预演 / --apply）
    ├── scaffold.py   骨架生成的底层实现，也可单独当 CLI
    └── migrate.py    归类规则的底层实现，也可单独出 migrate.sh
```

## License

MIT

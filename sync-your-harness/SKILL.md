---
name: sync-your-harness
description: 让一个 harness 能安全地跨设备、跨 Agent 同步。按白名单规则预演哪些文件会被推送、哪些被挡住、有没有疑似密钥落在要推送的文件里；确认后写入白名单 .gitignore、拦截大文件的 pre-commit hook 和一份推送规则文档；把某个 Agent 私有的记忆复制成所有 Agent 共用的共享记忆；清点各个 Agent 的 Skill 目录找出不一致。全程不 commit、不 push。当用户说「怎么同步我的 harness」「推到 GitHub 安全吗」「哪些不该推」「多台电脑共用」「让 Codex 也能读到我的记忆」「Skill 存哪」「整理 .gitignore」「sync my harness」时触发。
---

# sync-your-harness

harness 搭好之后的下一个问题：怎么让它活在不止一台电脑、不止一个 Agent 上，又不把不该出去的东西带出去。

## 先讲清楚一个原则

**本地保存全部，远端只同步文字。** harness 推到远端的目的只有一个：让任何 Agent、任何设备拿到这个仓库就能了解你。图片、视频、代码项目、原始数据、私密计划都留在本地。

所以 `.gitignore` 用的是白名单写法：默认忽略全部，只放行 `.md`、`.jsonl`、`.txt` 这几种文本。这比黑名单安全，因为以后新增任何奇怪的文件，默认都是不推。

## 铁律

**1. 不 commit，不 push，不碰远端。**
这个 Skill 只准备规则和预演结果。提交和推送永远由用户自己说了才做。

**2. 已有的 `.gitignore` 和 hook 不覆盖。**
新规则写成 `.gitignore.proposed` 和 `pre-commit.proposed`，让用户对比之后自己替换。他明确说「直接替换」时才加 `--replace-gitignore`，脚本会先备份旧的。

**3. 密钥只报位置和模式名，不显示内容。**
不要为了「帮用户确认」去打开那个文件念出来。告诉他哪个文件、哪种模式、几处，让他自己看。

**4. 复制记忆之前让用户过目。**
私有记忆里可能有他只想留给自己的东西。进了 harness 就可能被同步出去。

## 流程

### 第一步：问两个问题

1. **「有没有哪些内容只想留在本地？」** 每个人不一样，常见的有财务、个人计划、雇主的资料、客户信息。把答案变成文件名通配或目录名。
2. **「除了文本，有没有别的格式必须同步？」** 多数人没有。有的话用 `--allow-ext` 加。

### 第二步：预演

```bash
python3 ~/.claude/skills/sync-your-harness/scripts/sync.py preview <harness> \
  --private "<通配1>,<通配2>" --exclude-dir "<目录1>,<目录2>"
```

把这几个数字原样讲给用户：

- 会推送多少个文件、多大
- 挡住了多少、分别因为什么
- 有几个自带 git 仓库的子目录（它们不会进这个仓库）
- **有没有疑似密钥落在会推送的文件里**。有的话这是第一优先级，先处理再谈别的

### 第三步：写入规则

```bash
python3 ~/.claude/skills/sync-your-harness/scripts/sync.py apply <harness> [同上参数]          # 预演
python3 ~/.claude/skills/sync-your-harness/scripts/sync.py apply <harness> [同上参数] --apply  # 写入
```

写三样东西：

| 文件 | 作用 |
|------|------|
| `.gitignore` 或 `.gitignore.proposed` | 白名单规则 |
| `.git/hooks/pre-commit` | 拦截超过 1MB 的文件和凭证文件 |
| `<协议目录>/push-rules.md` | 给人和 Agent 看的规则说明 |

写完之后在入口文件（AGENTS.md）的任务路由里加一行：「提交或推送之前先读 push-rules.md」。

**注意 hook 不随仓库同步。** `.git/hooks/` 不会被推送，换一台电脑要重跑一次 apply。告诉用户这一点。

**注意历史。** 如果以前已经提交过大文件，`.gitignore` 管不了历史。脚本不处理这个，如实告诉用户，由他决定要不要清理历史。

### 第四步：共享记忆

每个 Agent 都有自己的私有记忆位置，别的 Agent 读不到。比如 Claude Code 的在 `~/.claude/projects/<项目>/memory/`。

```bash
python3 ~/.claude/skills/sync-your-harness/scripts/sync.py memory <harness>          # 预演，列出会复制哪些
python3 ~/.claude/skills/sync-your-harness/scripts/sync.py memory <harness> --apply
```

自动找不到来源时用 `--from <目录>` 指定。脚本把记忆复制到 `<记忆目录>/shared/`，并在 `MEMORY.md` 补索引。来源不动，已存在的不覆盖。

然后在入口文件里加一条规则：**以后用户纠正了做法或确认了偏好，新增记忆时同时写进共享目录。** 没有这一条，共享记忆一周之后就过期了。

### 第五步：清点 Skill

```bash
python3 ~/.claude/skills/sync-your-harness/scripts/sync.py skills <harness>
```

输出各个位置的 Skill 数量、只在一处有的、同名但内容不一致的。脚本只报告，不动任何 Agent 的配置目录。

给用户的建议固定是这一条：**选一处当主库，其余位置改成指向它的软链接。** 具体怎么改，出方案让他确认后再逐条执行。跨 Agent 分发也可以直接用 `npx skills` 这类现成工具。

### 第六步：交代多端怎么用

- 另一台电脑：`git clone`，然后重跑第三步装 hook
- 另一个 Agent：打开这个目录，让它读 AGENTS.md 并回答末尾的自测题
- 云端运行的 Agent 读不到本机的 Skill、脚本和环境变量，依赖这些的任务只能在本机跑

## 几个容易做错的地方

**别因为预演干净就替用户推送。** 预演只是规则检查，推不推是他的决定。

**别把 `.gitignore.proposed` 直接改名成 `.gitignore`。** 他原来的规则里可能有你不知道原因的条目。让他对比。

**密钥扫描有漏有误。** 它按常见模式匹配。扫到的未必是真密钥，没扫到也不保证没有。如实说。

**白名单会挡住用户没想到的东西。** 比如他想同步的 `.json` 配置或 `.csv`。预演里「按扩展名」那一行就是给他看这个的，主动问一句。

## 文件

```
sync-your-harness/
├── SKILL.md
└── scripts/
    └── sync.py    preview / apply / memory / skills 四个子命令
```

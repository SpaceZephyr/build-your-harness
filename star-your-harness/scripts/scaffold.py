#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
star-your-harness 脚手架：按用户画像生成一个 harness 目录。

设计目标：生成出来的东西要能直接通过 better-your-harness 的体检。
所以 .gitignore、CLAUDE.md 的目录地图与行为规则、每层 README、
记忆索引、复盘目录、git 初始化，这些不是可选项，是默认动作。

铁律：绝不覆盖已存在的文件。同名一律跳过并报告。

用法：
  python3 scaffold.py profile.json            # 预演，只打印会做什么
  python3 scaffold.py profile.json --apply    # 真的写盘
"""
import json, os, sys, subprocess, datetime
from pathlib import Path

# ---------- 职业模板：只有产出层因职业而异，骨架是通用的 ----------
ROLES = {
    'content-creator': {
        'label': '内容创作者',
        'outputs': [
            ('forge',   '创作',   '成稿和草稿。一篇一个文件或一个文件夹。'),
            ('scope',   '选题',   '待写清单、热点采集、选题公式。'),
            ('shipped', '已发布', '发出去的成品，按平台和日期归档。'),
        ],
    },
    'pm': {
        'label': '产品经理',
        'outputs': [
            ('specs',    '需求',   'PRD、需求文档、验收标准。'),
            ('research', '调研',   '竞品拆解、用户访谈、数据分析。'),
            ('shipped',  '已交付', '上线的功能、复盘、埋点方案。'),
        ],
    },
    'engineer': {
        'label': '工程师',
        'outputs': [
            ('projects', '项目',   '按项目分文件夹，放方案和决策记录。'),
            ('notes',    '技术笔记', '踩坑、方案对比、可复用片段。'),
            ('shipped',  '已交付', '上线记录、事故复盘。'),
        ],
    },
    'researcher': {
        'label': '研究者',
        'outputs': [
            ('topics',   '课题',   '按课题分文件夹。'),
            ('lit',      '文献',   '论文笔记、摘要、引用。'),
            ('outputs',  '产出',   '论文、报告、演讲稿。'),
        ],
    },
    'consultant': {
        'label': '顾问 / 自由职业',
        'outputs': [
            ('clients',  '客户',   '一个客户一个文件夹，放 brief 和往来。'),
            ('proposals','提案',   '方案、报价、标书。'),
            ('delivery', '交付',   '交付物归档。'),
        ],
    },
    'generalist': {
        'label': '通用',
        'outputs': [
            ('projects', '项目',   '按项目分文件夹。'),
            ('outputs',  '产出',   '做完的东西。'),
        ],
    },
}

# 通用骨架。序号固定，保证目录排序稳定。
# (序号, key, 中文名, 英文名, 说明, 属于 harness 哪一层)
CORE = [
    ('00', 'inbox',     '收件箱', 'inbox',     '临时存放，还没想好放哪的东西先扔这。定期清空。', '入口'),
    ('10', 'about-me',  '关于我', 'about-me',  '我是谁、我怎么工作、我的标准。Agent 每次都要读的底座。', '上下文'),
    ('30', 'vault',     '素材库', 'vault',     '别人的东西：摘录、案例、引用、参考资料。', '上下文'),
    ('40', 'memory',    '记忆',   'memory',    '跨会话记忆。MEMORY.md 是索引，一条记忆一个文件。', '记忆'),
    ('50', 'protocols', '协议',   'protocols', '工作流定义、迭代记录、复盘。系统怎么演进都记在这。', '学习'),
    ('60', 'garage',    '车库',   'garage',    '脚本、Skill、自动化、小工具。', '工具'),
]


def dirname(num, key, zh, en, naming):
    if naming == 'numbered-zh':
        return f'{num} {zh}'
    if naming == 'plain-en':
        return en
    return f'{num}-{en}'   # numbered-en，默认


def build_plan(p):
    """产出一个 [(相对路径, 内容 or None表示目录)] 的清单。先算清楚再落盘。"""
    naming = p.get('naming', 'numbered-en')
    role = ROLES.get(p.get('role'), ROLES['generalist'])
    outs = p.get('outputs') or [
        {'key': k, 'label': zh, 'desc': d} for k, zh, d in role['outputs']]
    name = p.get('name') or Path(p['dir']).name
    lang = p.get('lang', 'zh')

    dirs = []   # (dirname, zh, desc, layer)
    for num, key, zh, en, desc, layer in CORE:
        dirs.append((dirname(num, key, zh, en, naming), zh, desc, layer))
        if key == 'about-me':
            # 产出层插在 about-me 之后，编号 20 起
            for i, o in enumerate(outs):
                n = str(20 + i) if i == 0 else f'2{i}'
                dirs.append((dirname(n, o['key'], o.get('label', o['key']), o['key'], naming),
                             o.get('label', o['key']), o.get('desc', ''), '产出'))
    dirs.sort(key=lambda x: x[0])

    files = {}

    # ---- CLAUDE.md：目录地图 + 行为规则 + 任务路由，三样都要有 ----
    tree = '\n'.join(f'{d}/{" " * max(1, 22 - len(d))}{desc}' for d, _, desc, _ in dirs)
    routes = '\n'.join(
        f'| {zh} | `{d}/` | {layer} |' for d, zh, _, layer in dirs)
    files['CLAUDE.md'] = f'''# {name}

这是我的 harness：给 AI 协作用的工作目录。你（Agent）每次进来先读这份文件。

## 目录地图

```
{tree}
```

## 各层职责

| 目录 | 路径 | 属于哪一层 |
|------|------|-----------|
{routes}

## 行为规则

这几条是硬规则，不是建议。

1. **进入任何目录前先读它的 `README.md`**，那里写了这个目录的命名约定和放什么。
2. **操作 `.jsonl` 文件时只允许追加**，绝不整体重写。
3. **写任何东西之前先读 `{dirname('10','about-me','关于我','about-me',naming)}/`** 里的资料，那是我的偏好和标准。
4. **新建文件前先确认该放哪个目录**，不确定就放 `{dirname('00','inbox','收件箱','inbox',naming)}/` 并告诉我。
5. **不要覆盖已有文件**。要改就先展示 diff，我确认再动。
6. **涉及 `git push`、批量删除、改配置这类不可逆操作，先问我。**

## 任务路由

> 详细步骤定义在 `{dirname('50','protocols','协议','protocols',naming)}/workflows.jsonl`，下面是速查。

### 开始一件新工作
1. 读 `{dirname('10','about-me','关于我','about-me',naming)}/` 确认我的偏好和标准
2. 读 `{dirname('50','protocols','协议','protocols',naming)}/workflows.jsonl` 看有没有现成流程
3. 搜 `{dirname('30','vault','素材库','vault',naming)}/` 找可用素材
4. 动手，产出写进对应的产出目录

### 记住一件事
1. 判断这条信息值不值得跨会话保留
2. 值得的话，在 `{dirname('40','memory','记忆','memory',naming)}/` 建一个文件
3. **同时**在 `{dirname('40','memory','记忆','memory',naming)}/MEMORY.md` 补一行索引，否则等于没记

### 复盘
1. 读 `{dirname('50','protocols','协议','protocols',naming)}/iterations/` 最近的记录
2. 对比这段时间实际做了什么
3. 新的一份写进 `{dirname('50','protocols','协议','protocols',naming)}/iterations/`

## 这个 harness 的健康度

用 [better-your-harness](https://github.com/SpaceZephyr/build-your-harness) 定期体检：

```bash
python3 scripts/scan.py {p['dir']} -o findings.json
```
'''

    # ---- .gitignore ----
    files['.gitignore'] = '''# 依赖与构建产物
node_modules/
dist/
build/
.next/
target/
out/
__pycache__/
*.pyc
.venv/
venv/

# 系统
.DS_Store
Thumbs.db
*.log

# 凭证：这几行是底线，不要删
.env
.env.*
*.env
*.key
*.pem
credentials*.json

# 体检产物
findings.json
analysis.json
harness-report.html
'''

    # ---- 各目录的 README ----
    for d, zh, desc, layer in dirs:
        files[f'{d}/README.md'] = f'''# {zh}

{desc}

## 属于 harness 的哪一层

{layer}

## 放什么

- 待补充

## 不放什么

- 待补充

## 命名约定

`MMDD-标题.md`，比如 `0803-第一篇.md`。日期前缀让文件天然按时间排序。
'''

    # ---- about-me 的种子文件 ----
    am = dirname('10', 'about-me', '关于我', 'about-me', naming)
    files[f'{am}/我是谁.md'] = f'''# 我是谁

> 这份文件是 Agent 理解你的起点。写得越具体，它的产出越像你。
> 现在填不完没关系，用一次改一次。

## 基本情况

- 我是：{role['label']}
- 我主要做：（一句话）
- 我的读者 / 客户 / 协作对象是：

## 我在乎什么

-

## 我讨厌什么

-
'''
    files[f'{am}/工作偏好.md'] = '''# 工作偏好

> 告诉 Agent 怎么跟你配合。这份比「我是谁」更常被读到。

## 我希望 Agent 怎么做

- 有判断就直说，不要每件事都问我
- 不确定的地方标出来，不要编
- 长任务先给方案再动手

## 我不希望 Agent 怎么做

- 不要在没确认的情况下改我已有的文件
- 不要一次性输出几千字

## 交付格式偏好

-
'''
    files[f'{am}/质量标准.md'] = '''# 质量标准

> 什么样的产出算过关。Agent 自查和你审稿都用这一份。

## 必须满足

- [ ]
- [ ]

## 加分项

-

## 一票否决

-
'''

    # ---- 记忆层：索引 + 一条种子记忆（必须在索引里，否则体检会判未入索引）----
    mem = dirname('40', 'memory', '记忆', 'memory', naming)
    files[f'{mem}/MEMORY.md'] = f'''# 记忆索引

> 每条记忆一个文件，这里一行一条指针。
> **加了文件就要加索引**，索引里没有的东西对 Agent 等于不存在。

- [这个 harness 怎么来的](how-this-started.md) — 建立时间、当初想解决什么
'''
    files[f'{mem}/how-this-started.md'] = f'''---
name: how-this-started
type: project
---

# 这个 harness 怎么来的

建立于 {datetime.date.today().isoformat()}，用 star-your-harness 生成。

**当初想解决的问题：** {p.get('why') or '（补一句：你为什么要搭这个）'}

**主要用途：** {'、'.join(p.get('purposes') or []) or '（待补充）'}

**Why:** 记下动机，半年后回来看才知道当初的取舍是为了什么。
**How to apply:** 每次要往 harness 里加东西时，先问一句「这跟当初的目的还对得上吗」。
'''

    # ---- 协议层：工作流 + 迭代记录目录 ----
    pro = dirname('50', 'protocols', '协议', 'protocols', naming)
    files[f'{pro}/workflows.jsonl'] = json.dumps({
        'id': 'new-work', 'name': '开始一件新工作',
        'steps': [f'读 {am}/', f'查 {pro}/workflows.jsonl',
                  f'搜 {dirname("30","vault","素材库","vault",naming)}/', '产出'],
        'created': datetime.date.today().isoformat(),
    }, ensure_ascii=False) + '\n'
    # 结构化日志：一天一行，只追加。体检会查有没有这一层。
    files[f'{pro}/daily-log.jsonl'] = json.dumps({
        'date': datetime.date.today().isoformat(),
        'did': ['用 star-your-harness 建立了 harness 骨架'],
        'note': '一天一行，只追加不重写。Agent 帮你记，你也可以自己补。',
    }, ensure_ascii=False) + '\n'
    files[f'{pro}/iterations/README.md'] = '''# 迭代记录

系统本身怎么变的，记在这。命名 `MMDD-改了什么.md`。

每次改动记三件事：

1. 改之前哪里不顺
2. 改成了什么
3. 改完之后是不是真的好了（过一阵回来补）

没有这一层，harness 只会越堆越大，不会越用越顺。
'''
    files[f'{pro}/iterations/{datetime.date.today().strftime("%m%d")}-harness-建立.md'] = f'''# {datetime.date.today().isoformat()} 建立 harness

## 改之前哪里不顺

{p.get('why') or '（补一句）'}

## 做了什么

用 star-your-harness 生成了基础骨架：{len(dirs)} 个目录，含入口文件、行为规则、任务路由、记忆索引。

## 效果

（用一阵之后回来填）
'''

    # ---- 车库：放个说明 ----
    gar = dirname('60', 'garage', '车库', 'garage', naming)
    files[f'{gar}/README.md'] = files.get(f'{gar}/README.md', '') + '''
## 建议放这些

- `scripts/` 一次性脚本和自动化
- `skills/` 这个 harness 专用的 Skill（软链到全局 Skill 库也行）
- `hooks/` 给 Agent 用的钩子
'''

    # ---- hooks 骨架（体检会查有没有守门）----
    if p.get('hooks', True):
        files['.claude/settings.json'] = json.dumps({
            'hooks': {
                'PreToolUse': [{
                    'matcher': 'Bash',
                    'hooks': [{
                        'type': 'command',
                        'command': ('bash -c \'grep -qE "git add -A|git add \\." <<< "$CLAUDE_TOOL_INPUT" '
                                    '&& echo "别用 git add -A，逐个挑文件加，避免误提交凭证" >&2 && exit 2 || exit 0\''),
                    }],
                }],
            },
        }, ensure_ascii=False, indent=2) + '\n'

    files['README.md'] = f'''# {name}

我的 harness。给 AI 协作用的工作目录。

结构和规则见 [CLAUDE.md](CLAUDE.md)。

- 用 [star-your-harness](https://github.com/SpaceZephyr/build-your-harness) 搭的
- 用 [better-your-harness](https://github.com/SpaceZephyr/build-your-harness) 定期体检
'''
    return dirs, files


def apply(root, dirs, files, do_git):
    root = Path(root)
    made, skipped = [], []
    root.mkdir(parents=True, exist_ok=True)
    for d, *_ in dirs:
        (root / d).mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            skipped.append(rel)     # 铁律：绝不覆盖
            continue
        p.write_text(content, encoding='utf-8')
        made.append(rel)
    if do_git and not (root / '.git').exists():
        subprocess.run(['git', 'init', '-q'], cwd=root, capture_output=True)
        subprocess.run(['git', 'add', '-A'], cwd=root, capture_output=True)
        subprocess.run(['git', 'commit', '-q', '-m', 'chore: 用 star-your-harness 建立 harness 骨架'],
                       cwd=root, capture_output=True)
    return made, skipped


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if not args:
        print('用法: scaffold.py profile.json [--apply]'); sys.exit(1)
    p = json.loads(Path(args[0]).read_text(encoding='utf-8'))
    if not p.get('dir'):
        print('profile 里必须有 dir'); sys.exit(1)
    dirs, files = build_plan(p)
    root = Path(p['dir'])

    if '--apply' not in sys.argv:
        print(f'预演（不写盘）。目标：{root}\n')
        print(f'会创建 {len(dirs)} 个目录：')
        for d, zh, _, layer in dirs:
            print(f'  {d}/'.ljust(26) + f'{zh}  [{layer}]')
        print(f'\n会写入 {len(files)} 个文件：')
        exist = [r for r in files if (root / r).exists()]
        for r in sorted(files):
            print(f'  {"跳过（已存在）" if r in exist else "新建"}  {r}')
        if exist:
            print(f'\n{len(exist)} 个文件已存在，会被跳过，不覆盖。')
        print('\n确认无误后加 --apply 真正执行。')
        return

    made, skipped = apply(root, dirs, files, p.get('git', True))
    print(f'已生成 → {root}')
    print(f'  目录 {len(dirs)} 个，新建文件 {len(made)} 个' +
          (f'，跳过已存在 {len(skipped)} 个' if skipped else ''))
    if skipped:
        for r in skipped[:10]:
            print(f'    跳过 {r}')
    print('\n下一步：')
    print('  1. 填 about-me 里那三份文件，harness 的质量取决于这一步')
    print('  2. 把已有材料搬进来：python3 scripts/migrate.py <来源目录> ' + str(root))
    print('  3. 体检：better-your-harness 的 scan.py')


if __name__ == '__main__':
    main()

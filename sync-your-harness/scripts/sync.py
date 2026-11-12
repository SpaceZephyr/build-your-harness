#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync-your-harness：让一个 harness 能安全地跨设备、跨 Agent 同步。

四个子命令，前三个默认只读：

  preview <harness>   按白名单规则预演：会推送哪些、挡住哪些、有没有疑似密钥
  apply   <harness>   写入 .gitignore 白名单、pre-commit 大文件拦截、推送规则文档
  memory  <harness>   把某个 Agent 私有的记忆复制进 harness，变成所有 Agent 共用
  skills  <harness>   清点各个 Agent 的 Skill 目录，找出只在一处有的和内容不一致的

铁律：
- 不替用户 commit，不替用户 push，不碰远端
- 已有的 .gitignore 和 hook 不覆盖，新规则写成 .proposed 文件让人对比
- 密钥只报「哪个文件、哪种模式」，永远不打印值
- 写盘的命令都要加 --apply，不加就是预演

用法：
  python3 sync.py preview <harness> [--private "*private*,*.secret.md"] [--exclude-dir "data,work"] [-o preview.json]
  python3 sync.py apply   <harness> [同上参数] [--apply] [--replace-gitignore]
  python3 sync.py memory  <harness> [--from <私有记忆目录>] [--apply]
  python3 sync.py skills  <harness>
"""
import datetime, fnmatch, hashlib, json, os, re, shutil, sys
from pathlib import Path

HOME = Path.home()
NOISE = {'node_modules', '.next', 'dist', 'build', '.venv', 'venv', '__pycache__', '.cache',
         'target', 'out', '.trash', '.obsidian', '.DS_Store'}
TOOL_DIRS = {'.claude', '.agents', '.codex', '.cursor', '.workbuddy'}
ALLOW_EXT = ['.md', '.jsonl', '.txt', '.canvas', '.base']
MAX_KB = 1024

# (模式名, 正则)。只用来定位，命中的内容不输出。
SECRETS = [
    ('OpenAI / Anthropic 风格密钥', r'\bsk-[A-Za-z0-9_\-]{20,}'),
    ('GitHub token', r'\bgh[pousr]_[A-Za-z0-9]{30,}'),
    ('AWS access key', r'\bAKIA[0-9A-Z]{16}\b'),
    ('Slack token', r'\bxox[baprs]-[A-Za-z0-9\-]{10,}'),
    ('私钥块', r'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
    ('赋值形式的密钥', r'(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*["\'][A-Za-z0-9_\-]{24,}["\']'),
    ('export 形式的密钥', r'(?i)export\s+\w*(TOKEN|KEY|SECRET)\w*=["\']?[A-Za-z0-9_\-]{24,}'),
]


def die(msg):
    print(msg); sys.exit(1)


def opt(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv else default


def parse(argv):
    flags_with_val = ('--private', '--exclude-dir', '-o', '--from', '--allow-ext', '--max-kb')
    skip, pos = set(), []
    for i, a in enumerate(argv):
        if a in flags_with_val:
            skip.add(i + 1)
    for i, a in enumerate(argv):
        if i not in skip and not a.startswith('-'):
            pos.append(a)
    if not pos:
        die(__doc__)
    root = Path(pos[0]).expanduser().resolve()
    if not root.is_dir():
        die(f'目录不存在：{root}')
    cfg = dict(
        root=root,
        private=[x.strip() for x in (opt(argv, '--private') or '').split(',') if x.strip()],
        exclude_dirs=[x.strip().strip('/') for x in (opt(argv, '--exclude-dir') or '').split(',') if x.strip()],
        allow=ALLOW_EXT + ['.' + x.strip().lstrip('.') for x in (opt(argv, '--allow-ext') or '').split(',') if x.strip()],
        max_kb=int(opt(argv, '--max-kb', MAX_KB)),
    )
    return cfg


def classify(cfg):
    """走一遍目录，按白名单规则判断每个文件推不推。返回 (pushed, blocked, nested_repos)。"""
    root = cfg['root']
    pushed, blocked, nested = [], [], []
    for dp, dns, fns in os.walk(root):
        d = Path(dp)
        rel_d = d.relative_to(root)
        if d != root and (d / '.git').exists():
            nested.append(str(rel_d)); dns[:] = []
            n = sum(len(f) for _, _, f in os.walk(d))
            blocked.append(dict(path=str(rel_d) + '/', why='自带 git 仓库，应该用它自己的仓库同步', kb=0, files=n))
            continue
        keep = []
        for x in dns:
            r = str(rel_d / x) if str(rel_d) != '.' else x
            if x == '.git':
                continue
            if x in NOISE or x in TOOL_DIRS:
                blocked.append(dict(path=r + '/', why='依赖、构建产物或工具自己的目录', kb=0, files=None)); continue
            if any(r == e or r.startswith(e + '/') for e in cfg['exclude_dirs']):
                blocked.append(dict(path=r + '/', why='你指定排除的目录', kb=0, files=None)); continue
            keep.append(x)
        dns[:] = keep
        for fn in fns:
            p = d / fn
            rel = str(p.relative_to(root))
            try:
                kb = p.stat().st_size / 1024
            except OSError:
                continue
            ext = p.suffix.lower()
            if fn == '.gitignore':
                pushed.append(dict(path=rel, kb=kb)); continue
            if fn.startswith('.env') or ext in ('.key', '.pem'):
                blocked.append(dict(path=rel, why='凭证文件', kb=kb)); continue
            if any(fnmatch.fnmatch(fn, pat) or fnmatch.fnmatch(rel, pat) for pat in cfg['private']):
                blocked.append(dict(path=rel, why='命中你设的私密规则', kb=kb)); continue
            if ext not in cfg['allow']:
                blocked.append(dict(path=rel, why=f'{ext or "无扩展名"} 不在白名单', kb=kb)); continue
            if kb > cfg['max_kb']:
                blocked.append(dict(path=rel, why=f'超过 {cfg["max_kb"]}KB', kb=kb)); continue
            pushed.append(dict(path=rel, kb=kb))
    return pushed, blocked, nested


def scan_secrets(root, pushed):
    hits = []
    for f in pushed:
        try:
            txt = (root / f['path']).read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        for name, pat in SECRETS:
            n = len(re.findall(pat, txt))
            if n:
                hits.append(dict(path=f['path'], pattern=name, count=n))
    return hits


def do_preview(cfg, quiet=False):
    root = cfg['root']
    pushed, blocked, nested = classify(cfg)
    secrets = scan_secrets(root, pushed)
    by_why = {}
    for b in blocked:
        k = '扩展名不在白名单' if '不在白名单' in b['why'] else b['why']
        e = by_why.setdefault(k, dict(n=0, kb=0)); e['n'] += 1; e['kb'] += b['kb']
    by_ext = {}
    for b in blocked:
        if '不在白名单' in b['why']:
            ext = b['why'].split(' ')[0]
            e = by_ext.setdefault(ext, dict(n=0, kb=0)); e['n'] += 1; e['kb'] += b['kb']
    res = dict(root=str(root), is_git=(root / '.git').exists(), has_gitignore=(root / '.gitignore').exists(),
               pushed=dict(files=len(pushed), mb=round(sum(f['kb'] for f in pushed) / 1024, 2)),
               blocked=dict(entries=len(blocked), mb=round(sum(b['kb'] for b in blocked) / 1024, 1)),
               blocked_by_reason={k: dict(n=v['n'], mb=round(v['kb'] / 1024, 1)) for k, v in by_why.items()},
               blocked_by_ext={k: dict(n=v['n'], mb=round(v['kb'] / 1024, 1))
                               for k, v in sorted(by_ext.items(), key=lambda x: -x[1]['kb'])[:12]},
               nested_repos=nested, secrets=secrets,
               largest_pushed=sorted(pushed, key=lambda f: -f['kb'])[:8],
               largest_blocked=sorted([b for b in blocked if b['kb']], key=lambda b: -b['kb'])[:8])
    if quiet:
        return res
    print(f'预演 {root}（只读）\n')
    print(f'会推送：{res["pushed"]["files"]} 个文件，{res["pushed"]["mb"]} MB')
    print(f'会挡住：{res["blocked"]["entries"]} 项，约 {res["blocked"]["mb"]} MB')
    for k, v in res['blocked_by_reason'].items():
        print(f'   {k}：{v["n"]} 项，{v["mb"]} MB')
    if res['blocked_by_ext']:
        print('   其中按扩展名：' + ' · '.join(f'{k} {v["n"]}个' for k, v in list(res['blocked_by_ext'].items())[:8]))
    if nested:
        print(f'\n自带 git 仓库的子目录 {len(nested)} 个（不会进这个仓库）：{"、".join(nested[:8])}')
    if secrets:
        print(f'\n要处理：{len(secrets)} 处疑似密钥落在会推送的文件里（只报位置，不显示内容）')
        for h in secrets[:15]:
            print(f'   {h["path"]}  [{h["pattern"]} × {h["count"]}]')
        print('   先把这些改成环境变量名，再考虑推送。')
    else:
        print('\n会推送的文件里没有扫到疑似密钥。')
    if res['largest_pushed']:
        print('\n会推送的最大几个：' + ' · '.join(f'{Path(f["path"]).name} {f["kb"]:.0f}KB' for f in res['largest_pushed'][:4]))
    if not res['is_git']:
        print('\n这个目录还不是 git 仓库。apply 不会替你 git init，要同步请自己初始化并建远端。')
    return res


def gitignore_text(cfg, nested):
    L = ['# 由 sync-your-harness 生成。白名单写法：默认全部忽略，只放行文本。',
         '# 目标：只同步能让 Agent 了解你的文字。大文件、代码项目、私密内容留在本地。',
         '*', '!*/', '!.gitignore', '']
    L += ['# 放行的格式'] + [f'!*{e}' for e in cfg['allow']] + ['']
    L += ['# 依赖、构建产物、工具目录'] + [f'{n}/' if not n.startswith('.DS') else n for n in sorted(NOISE)]
    L += [f'{t}/' for t in sorted(TOOL_DIRS)] + ['']
    L += ['# 凭证：这几行是底线，不要删', '.env', '.env.*', '*.key', '*.pem', 'credentials*.json', '']
    if nested:
        L += ['# 自带 git 仓库的目录，用它们自己的仓库同步'] + [f'/{n}/' for n in nested] + ['']
    if cfg['exclude_dirs']:
        L += ['# 你指定不同步的目录'] + [f'/{e}/' for e in cfg['exclude_dirs']] + ['']
    if cfg['private']:
        L += ['# 私密内容：只留本地'] + cfg['private'] + ['']
    return '\n'.join(L)


def hook_text(max_kb):
    return f'''#!/bin/sh
# 由 sync-your-harness 生成：拦截超过 {max_kb}KB 的文件和凭证文件进入提交。
# 确实要提交大文件时：git commit --no-verify（想清楚再用）
limit={max_kb * 1024}
fail=0
for f in $(git diff --cached --name-only --diff-filter=AM -z | tr '\\0' '\\n'); do
  [ -f "$f" ] || continue
  case "$f" in .env|.env.*|*.pem|*.key) echo "拦截：凭证文件 $f"; fail=1; continue;; esac
  size=$(wc -c < "$f" | tr -d ' ')
  if [ "$size" -gt "$limit" ]; then echo "拦截：$f 有 $((size / 1024))KB，超过 {max_kb}KB"; fail=1; fi
done
[ "$fail" -eq 0 ] || {{ echo "提交已中止。大文件留在本地，或加进 .gitignore。"; exit 1; }}
'''


def rules_text(cfg, res):
    today = datetime.date.today().isoformat()
    return f'''# 推送规则

> 生成于 {today}，由 sync-your-harness 写入。任何 Agent 在 commit 或 push 之前先读这一页。

## 原则

本地保存全部内容。推到远端的只有一类：**能让 Agent 了解我的文字上下文**。

## 推什么

- 扩展名在白名单里的文本：{'、'.join(cfg['allow'])}
- 单个文件不超过 {cfg['max_kb']}KB

## 不推什么

| 类别 | 原因 |
|------|------|
| 图片、视频、PDF 等大文件 | 仓库会膨胀，Agent 也读不了 |
| 自带 git 仓库的代码项目 | 它们有自己的仓库，重复推送只会制造两份真相 |
| 依赖和构建产物 | 可以重新生成 |
| `.env`、密钥、凭证 | 泄露了就是事故 |
| 私密内容（{'、'.join(cfg['private']) or '尚未设置'}） | 只留本地 |
| 原始数据导出 | 体积大且常含个人信息 |

## 靠什么保证

1. `.gitignore` 用白名单写法：默认忽略全部，只放行上面的扩展名
2. `.git/hooks/pre-commit` 拦截超过 {cfg['max_kb']}KB 的文件和凭证文件
3. 推送前跑一次预演：`python3 sync.py preview <harness目录>`

## Agent 要守的

- 不 commit、不 push，除非我明确要求
- 不用 `git add -A` 或 `git add .`，逐个文件加
- 提交前跑预演，把「会推送多少、有没有疑似密钥」告诉我
- 新增一种要同步的文件类型时，先问我，再改 `.gitignore`

## 生成时的快照

会推送 {res['pushed']['files']} 个文件（{res['pushed']['mb']} MB），挡住约 {res['blocked']['mb']} MB。
'''


def cmd_apply(argv):
    cfg = parse(argv)
    root, live = cfg['root'], '--apply' in argv
    res = do_preview(cfg, quiet=True)
    todo = []                                           # (目标路径, 内容, 说明, mode)
    gi = root / '.gitignore'
    text = gitignore_text(cfg, res['nested_repos'])
    if not gi.exists():
        todo.append((gi, text, '新建 .gitignore（白名单）', None))
    elif '--replace-gitignore' in argv:
        bak = root / f'.gitignore.bak-{datetime.date.today().strftime("%Y%m%d")}'
        todo.append((bak, gi.read_text(encoding='utf-8', errors='ignore'), '备份现有 .gitignore', None))
        todo.append((gi, text, '替换 .gitignore 为白名单写法', 'overwrite'))
    else:
        todo.append((root / '.gitignore.proposed', text,
                     '已有 .gitignore，不覆盖。新规则写到 .gitignore.proposed 供对比', 'overwrite'))
    if (root / '.git').is_dir():
        hk = root / '.git/hooks/pre-commit'
        if hk.exists():
            todo.append((root / '.git/hooks/pre-commit.proposed', hook_text(cfg['max_kb']),
                         '已有 pre-commit，不覆盖。新 hook 写到 pre-commit.proposed', 'overwrite'))
        else:
            todo.append((hk, hook_text(cfg['max_kb']), '新建 pre-commit：拦截大文件和凭证', 'exec'))
    else:
        print('不是 git 仓库，跳过 pre-commit hook。')
    pro = next((d for d in sorted(root.iterdir()) if d.is_dir()
                and re.search(r'protocol|协议|review|rules|规则', d.name, re.I)), None)
    rules = (pro / 'push-rules.md') if pro else (root / 'PUSH-RULES.md')
    if rules.exists():
        print(f'{rules.relative_to(root)} 已存在，不覆盖。')
    else:
        todo.append((rules, rules_text(cfg, res), '新建推送规则文档', None))

    print(f'{"执行" if live else "预演（不写盘）"} → {root}\n')
    for p, _, note, _ in todo:
        print(f'  {note}\n     {p.relative_to(root)}')
    print(f'\n按这套规则：会推送 {res["pushed"]["files"]} 个文件 {res["pushed"]["mb"]} MB，'
          f'挡住约 {res["blocked"]["mb"]} MB，疑似密钥 {len(res["secrets"])} 处')
    if not live:
        print('确认无误后加 --apply。'); return
    for p, content, _, mode in todo:
        if p.exists() and mode != 'overwrite':
            print(f'  跳过已存在 {p.name}'); continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
        if mode == 'exec':
            os.chmod(p, 0o755)
    print('\n完成。没有执行任何 git 命令。')
    print(f'下一步：在入口文件里加一行指向 {rules.relative_to(root)}，再跑一次 preview 确认。')
    if (root / '.gitignore.proposed').exists():
        print('      对比 .gitignore 和 .gitignore.proposed，确认后自己替换，或重跑并加 --replace-gitignore。')
    if (root / '.git').is_dir():
        print('      如果之前已经提交过大文件，.gitignore 管不了历史，需要另外清理，这一步脚本不做。')


def fm(txt, key):
    m = re.search(rf'^{key}:\s*(.+)$', txt.split('---')[1] if txt.startswith('---') and txt.count('---') >= 2 else '', re.M)
    return m.group(1).strip().strip('"\'') if m else ''


def cmd_memory(argv):
    cfg = parse(argv)
    root, live = cfg['root'], '--apply' in argv
    src = opt(argv, '--from')
    cands = [Path(src).expanduser()] if src else [
        HOME / '.claude/projects' / re.sub(r'[^A-Za-z0-9]', '-', str(root)) / 'memory',
        HOME / '.claude/projects' / str(root).replace('/', '-') / 'memory',
        root / '.claude/memory']
    src_dir = next((c for c in cands if c.is_dir()), None)
    if not src_dir:
        die('没找到私有记忆目录。用 --from <目录> 指定。找过：\n  ' + '\n  '.join(map(str, cands)))
    mem = next((d for d in sorted(root.iterdir()) if d.is_dir() and not d.name.startswith('.')
                and re.search(r'memory|记忆', d.name, re.I)), None)
    if not mem:
        mem = next((d for d in root.glob('*/memory') if d.is_dir()), None)
    if not mem:
        die('harness 里没有记忆目录。先用 star-your-harness 建骨架，或手动建一个 memory/。')
    shared, index = mem / 'shared', mem / 'MEMORY.md'
    idx_txt = index.read_text(encoding='utf-8') if index.exists() else ''
    files = [p for p in sorted(src_dir.glob('*.md')) if p.name not in ('MEMORY.md', 'INDEX.md', 'README.md')]
    copy, add_idx, same = [], [], 0
    for p in files:
        txt = p.read_text(encoding='utf-8', errors='ignore')
        dest = shared / p.name
        if dest.exists():
            same += 1
        else:
            copy.append((p, dest))
        if f'shared/{p.name}' not in idx_txt and f'({p.name})' not in idx_txt:
            title = fm(txt, 'name') or p.stem
            desc = fm(txt, 'description')
            add_idx.append(f'- [{title}](shared/{p.name})' + (f' — {desc}' if desc else ''))
    print(f'{"执行" if live else "预演（不写盘）"}：{src_dir} → {shared}\n')
    print(f'私有记忆 {len(files)} 条 · 要复制 {len(copy)} 条 · 已存在 {same} 条 · 索引要补 {len(add_idx)} 行')
    for p, _ in copy[:12]:
        print(f'   {p.name}')
    print('\n复制之前请确认这些记忆里没有只想留给自己的内容。它们进了 harness 就可能被同步出去。')
    if not live:
        print('确认无误后加 --apply。'); return
    shared.mkdir(parents=True, exist_ok=True)
    for p, dest in copy:
        shutil.copy2(p, dest)
    if add_idx:
        with open(index, 'a', encoding='utf-8') as fh:
            fh.write(('' if idx_txt.endswith('\n') or not idx_txt else '\n') + '\n'.join(add_idx) + '\n')
    print(f'\n完成。复制 {len(copy)} 条，索引补了 {len(add_idx)} 行。来源一个没动。')
    print('下一步：在入口文件里加一条规则，以后新增偏好时同时写进这个共享目录。')


def cmd_skills(argv):
    cfg = parse(argv)
    root = cfg['root']
    places = [('Claude Code 全局', HOME / '.claude/skills'), ('Codex 全局', HOME / '.codex/skills'),
              ('通用全局', HOME / '.agents/skills'), ('项目 .claude', root / '.claude/skills'),
              ('项目 .agents', root / '.agents/skills'), ('项目 .codex', root / '.codex/skills')]
    inv, seen_real = {}, {}
    print(f'清点 Skill（只读）\n')
    print('| 位置 | 路径 | 数量 | 备注 |\n|---|---|---|---|')
    for label, d in places:
        if not d.exists():
            continue
        real = d.resolve()
        note = f'软链接，指向 {real}' if d.is_symlink() else ''
        if real in seen_real:
            print(f'| {label} | `{d}` | 同上 | 和「{seen_real[real]}」是同一个目录 |'); continue
        seen_real[real] = label
        skills = {}
        for s in sorted(real.iterdir()):
            md = s / 'SKILL.md'
            if s.is_dir() and md.exists():
                skills[s.name] = hashlib.md5(md.read_bytes()).hexdigest()
        inv[label] = skills
        print(f'| {label} | `{d}` | {len(skills)} | {note} |')
    if len(inv) < 2:
        print('\n只有一处有 Skill，不存在不一致的问题。'); return
    all_names = set().union(*[set(v) for v in inv.values()])
    only = {lab: sorted(n for n in sk if sum(n in o for o in inv.values()) == 1) for lab, sk in inv.items()}
    differ = sorted(n for n in all_names
                    if len({sk[n] for sk in inv.values() if n in sk}) > 1)
    print(f'\n共 {len(all_names)} 个不同名字的 Skill')
    for lab, names in only.items():
        if names:
            print(f'只在「{lab}」有 {len(names)} 个：{"、".join(names[:10])}{" 等" if len(names) > 10 else ""}')
    if differ:
        print(f'同名但内容不一致 {len(differ)} 个：{"、".join(differ[:12])}{" 等" if len(differ) > 12 else ""}')
    biggest = max(inv, key=lambda k: len(inv[k]))
    print(f'\n建议：选「{biggest}」当主库，其余位置改成指向它的软链接。')
    print('这一步会改动 Agent 的配置目录，脚本不做，方案确认后由用户自己执行或让 Agent 逐条执行。')
    print('跨 Agent 分发也可以用现成工具，比如 npx skills，不必自己维护同步脚本。')


if __name__ == '__main__':
    cmds = {'preview': lambda a: (lambda c: (lambda r: Path(opt(a, '-o')).write_text(
                json.dumps(r, ensure_ascii=False, indent=1), encoding='utf-8') if opt(a, '-o') else None)(do_preview(c)))(parse(a)),
            'apply': cmd_apply, 'memory': cmd_memory, 'skills': cmd_skills}
    if len(sys.argv) < 3 or sys.argv[1] not in cmds:
        die(__doc__)
    cmds[sys.argv[1]](sys.argv[2:])

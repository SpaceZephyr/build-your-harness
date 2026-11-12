#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
star-your-harness 改造模式：把一个已经攒了很久的乱目录，重组成有层次的 harness。

scaffold.py 解决「从零开始」，这个脚本解决「我已经有一堆东西了」。
它只动顶层：每个顶层目录要么保留、要么并进某一层、要么归档。目录内部不拆。

铁律：
- scan 只读，产出方案（JSON + HTML），不写 harness 里的任何东西
- apply 默认预演，加 --apply 才真的移动
- 只移动，不删除。唯一的删除是 rmdir 空目录
- 目标位置已存在同名的，一律跳过，不合并、不覆盖
- 每一次移动都记进 MANIFEST.md，同时生成 undo.sh，能原路退回

用法：
  python3 restructure.py scan <harness目录> [-o 输出目录] [--naming numbered-en|numbered-zh|plain-en]
  python3 restructure.py apply restructure-plan.json [-d decisions.json] [--apply]
"""
import datetime, html, json, os, re, shutil, sys, time
from pathlib import Path
from urllib.parse import quote

SKIP = {'.git', 'node_modules', '.next', 'dist', 'build', '.venv', 'venv',
        '__pycache__', '.cache', 'target', 'out', '.trash'}
ENTRY = {'AGENTS.md', 'CLAUDE.md', 'NOW.md', 'TOOLS.md', 'README.md', 'GEMINI.md',
         'LICENSE', '.gitignore', '.cursorrules'}
TEXT_EXT = {'.md', '.txt', '.markdown', '.jsonl', '.json', '.canvas', '.base', '.sh', '.py'}

# 七层。(key, 默认目录名, 中文名, 说明)
LAYERS = [
    ('inbox',     '00-inbox',     '收件箱', '还没想好放哪的东西'),
    ('about-me',  '10-about-me',  '关于我', '我是谁、偏好、标准、画像'),
    ('output',    '20-output',    '产出',   '我自己做出来的东西：文章、文档、项目'),
    ('vault',     '30-vault',     '素材库', '别人的东西：摘录、参考、收藏'),
    ('memory',    '40-memory',    '记忆',   '跨会话记忆和索引'),
    ('protocols', '50-protocols', '协议',   '流程、目标、复盘、规则、日志'),
    ('garage',    '60-garage',    '车库',   '脚本、代码、Skill、自动化'),
    ('archive',   '90-archive',   '归档',   '停用的目录和旧项目'),
]
LAYER_KEYS = [k for k, *_ in LAYERS]

# 顶层目录名 → 层。从上往下，命中即停。
NAME_RULES = [
    ('archive',   r'(archive|归档|old|旧|backup|备份|deprecated|废弃|bak\b|副本|copy|trash|回收)'),
    ('inbox',     r'(inbox|收件箱|草稿箱|untitled|未分类|temp\b|tmp\b|临时|杂项|misc)'),
    ('about-me',  r'(about|关于我|profile|画像|persona|me\b|个人介绍|简历|resume)'),
    ('memory',    r'(memory|记忆|cortex|journal|diary|日记)'),
    ('protocols', r'(protocol|协议|workflow|流程|sop|review|复盘|retro|goal|目标|plan|计划|compass|rule|规则|log|周报|weekly|daily)'),
    ('garage',    r'(garage|车库|script|脚本|tool|工具|code|代码|project|dev|build|skill|plugin|插件|extension|bot|app|src)'),
    ('vault',     r'(vault|素材|input|输入|摘录|剪藏|clip|reference|参考|收藏|book|读书|文献|paper|quote|引用|podcast|播客|tweet|inspiration|灵感|source|资料|trend|research|调研)'),
    ('output',    r'(output|产出|forge|创作|content|内容|article|文章|post|blog|博客|writing|写作|column|专栏|publish|发布|shipped|draft|稿|video|视频|course|课程|client|客户)'),
]


def die(msg):
    print(msg); sys.exit(1)


def measure(d):
    """一个顶层目录的体量、最近修改、有没有嵌套仓库、主要是什么类型。"""
    n = size = code = text = 0
    newest = 0.0
    nested_git = False
    samples = []
    for dp, dns, fns in os.walk(d):
        if '.git' in dns and Path(dp) != d:
            nested_git = True
        if Path(dp) == d and '.git' in dns:
            nested_git = True
        dns[:] = [x for x in dns if x not in SKIP]
        for fn in fns:
            if fn == '.DS_Store':
                continue
            p = Path(dp) / fn
            try:
                st = p.stat()
            except OSError:
                continue
            n += 1; size += st.st_size; newest = max(newest, st.st_mtime)
            ext = p.suffix.lower()
            if ext in ('.py', '.ts', '.js', '.tsx', '.go', '.rs', '.sh', '.swift'):
                code += 1
            elif ext in ('.md', '.txt', '.markdown'):
                text += 1
            if len(samples) < 4 and not fn.startswith('.'):
                samples.append(str(p.relative_to(d))[:60])
        if n > 20000:
            break
    days = round((time.time() - newest) / 86400) if newest else -1
    return dict(files=n, mb=round(size / 1048576, 1), days_idle=days, nested_git=nested_git,
                code_ratio=round(code / n, 2) if n else 0, text_ratio=round(text / n, 2) if n else 0,
                samples=samples)


def existing_layers(root):
    """harness 里已经有哪些层目录。有就沿用它的名字，不另起一套。"""
    found = {}
    pats = {'inbox': r'inbox|收件箱', 'about-me': r'about-?me|关于我|^\d*\s*me$', 'vault': r'vault|素材库|input',
            'memory': r'^\d*[-\s]*(memory|记忆)$', 'protocols': r'protocols?|协议|review',
            'garage': r'garage|车库|^\d*[-\s]*build$', 'archive': r'archive|归档',
            'output': r'output|产出|content|forge'}
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith('.'):
            continue
        for key, pat in pats.items():
            if key not in found and re.search(pat, d.name, re.I) and re.match(r'^\d', d.name):
                found[key] = d.name
    return found


def suggest(name, m, stale_days):
    low = name.lower()
    if m['files'] == 0:
        return 'remove-empty', None, '空目录'
    for key, pat in NAME_RULES:
        if re.search(pat, low, re.I):
            if key == 'archive':
                return 'archive', None, '名字像旧东西或备份'
            return 'move', key, f'名字像「{dict((k, z) for k, _, z, _ in LAYERS)[key]}」'
    if m['days_idle'] > stale_days:
        return 'archive', None, f'{m["days_idle"]} 天没动过'
    if m['nested_git'] or m['code_ratio'] > 0.4:
        return 'move', 'garage', '主要是代码，或自带 git 仓库'
    if m['text_ratio'] > 0.5:
        return 'move', 'output', '主要是文本，猜是你的产出'
    return 'move', 'inbox', '看不出来，先进收件箱'


def cmd_scan(argv):
    args = [a for a in argv if not a.startswith('-')]
    if not args:
        die('用法: restructure.py scan <harness目录> [-o 输出目录] [--stale 180]')
    root = Path(args[0]).expanduser().resolve()
    if not root.is_dir():
        die(f'目录不存在：{root}')
    if root in (Path.home(), Path('/')) or len(root.parts) < 3:
        die(f'拒绝处理 {root}：范围太大。请指向具体的 harness 目录。')
    outdir = Path(argv[argv.index('-o') + 1]) if '-o' in argv else Path.cwd()
    stale = int(argv[argv.index('--stale') + 1]) if '--stale' in argv else 180
    if root in outdir.resolve().parents or outdir.resolve() == root:
        die('输出目录不能在 harness 里面。scan 阶段不往 harness 写任何东西，换个 -o。')
    outdir.mkdir(parents=True, exist_ok=True)

    have = existing_layers(root)
    naming = argv[argv.index('--naming') + 1] if '--naming' in argv else 'numbered-en'
    def _name(default, zh):
        num, en = default.split('-', 1)
        return {'numbered-zh': f'{num} {zh}', 'plain-en': en}.get(naming, default)
    # 已有的层目录沿用原名；要新建的按用户选的命名风格
    layer_dir = {k: have.get(k, _name(default, zh)) for k, default, zh, _ in LAYERS}
    items = []
    for d in sorted(root.iterdir()):
        if d.name.startswith('.') or d.name in SKIP:
            continue
        if d.is_file():
            if d.name in ENTRY:
                continue
            items.append(dict(name=d.name, kind='file', files=1, mb=round(d.stat().st_size / 1048576, 2),
                              days_idle=round((time.time() - d.stat().st_mtime) / 86400), nested_git=False,
                              samples=[], action='move', target='inbox', why='散落在根目录的文件'))
            continue
        if d.name in have.values():
            m = measure(d)
            items.append(dict(name=d.name, kind='dir', action='keep', target=None,
                              why='已经是层目录', **m))
            continue
        m = measure(d)
        action, target, why = suggest(d.name, m, stale)
        items.append(dict(name=d.name, kind='dir', action=action, target=target, why=why, **m))

    batch = datetime.date.today().strftime('%Y-%m') + '-restructure'
    plan = dict(meta=dict(root=str(root), created=datetime.datetime.now().isoformat(timespec='seconds'),
                          batch=batch, stale_days=stale),
                layers=[dict(key=k, dir=layer_dir[k], label=zh, desc=desc, exists=k in have)
                        for k, _, zh, desc in LAYERS],
                items=items)
    pj, ph = outdir / 'restructure-plan.json', outdir / 'restructure-plan.html'
    pj.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    ph.write_text(render(plan), encoding='utf-8')

    by = {}
    for it in items:
        by[it['action']] = by.get(it['action'], 0) + 1
    label = {'keep': '保留', 'move': '并入某一层', 'archive': '归档', 'remove-empty': '删除空目录'}
    print(f'扫描 {root}（只读）')
    print(f'顶层 {len(items)} 项 → ' + ' · '.join(f'{label[k]} {v}' for k, v in by.items()))
    after = len({layer_dir[i["target"]] for i in items if i["action"] == "move"}
                | {i["name"] for i in items if i["action"] == "keep"}
                | ({layer_dir["archive"]} if by.get("archive") else set()))
    print(f'按建议执行后顶层目录数：{after}')
    risky = [i['name'] for i in items if i.get('nested_git')]
    if risky:
        print(f'注意：{len(risky)} 个目录自带 git 仓库：{"、".join(risky[:6])}')
    print(f'\n方案 → {ph}\n数据 → {pj}')
    print('把 HTML 路径给用户看。归类是按名字和文件类型猜的，必须由人过目。')


def render(plan):
    e = html.escape
    opts_layers = ''.join(f'<option value="move:{l["key"]}">并入 {e(l["dir"])}（{e(l["label"])}）</option>'
                          for l in plan['layers'] if l['key'] != 'archive')
    rows = []
    for it in plan['items']:
        cur = it['action'] if it['action'] != 'move' else f'move:{it["target"]}'
        warn = ' <span class="w">自带 git 仓库</span>' if it.get('nested_git') else ''
        idle = f'{it["days_idle"]} 天前' if it['days_idle'] >= 0 else ''
        rows.append(
            f'<tr data-name="{e(it["name"])}" data-default="{cur}">'
            f'<td><b>{e(it["name"])}</b>{"" if it["kind"] == "dir" else " <span class=m>文件</span>"}{warn}'
            f'<div class="m">{e("、".join(it.get("samples", [])[:3]))}</div></td>'
            f'<td class="n">{it["files"]}</td><td class="n">{it["mb"]} MB</td><td class="n">{idle}</td>'
            f'<td><select><option value="keep">原地保留</option>{opts_layers}'
            f'<option value="archive">归档</option><option value="remove-empty">删除（仅当为空）</option></select>'
            f'<input placeholder="并入后的名字（可不填）"></td>'
            f'<td class="m">{e(it["why"])}</td></tr>')
    layers = ''.join(f'<li><code>{e(l["dir"])}</code> {e(l["label"])}：{e(l["desc"])}'
                     f'{"" if l["exists"] else " <span class=m>（会新建）</span>"}</li>' for l in plan['layers'])
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>harness 改造方案</title>
<style>
:root{{--bg:#faf9f6;--card:#fff;--ink:#1f1e1c;--mute:#77746e;--line:#e6e3dc;--acc:#b4532a}}
@media(prefers-color-scheme:dark){{:root{{--bg:#171614;--card:#201f1c;--ink:#ecebe6;--mute:#a09d96;--line:#33312d;--acc:#e08a5f}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"PingFang SC",sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:32px 16px 80px}}h1{{font-size:24px;margin:0 0 4px}}h2{{font-size:17px;margin:32px 0 8px}}
.m{{color:var(--mute);font-size:12px}}.w{{color:var(--acc);font-size:12px;border:1px solid var(--acc);border-radius:4px;padding:0 4px}}
.box{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;overflow-x:auto}}
table{{border-collapse:collapse;width:100%;min-width:760px}}th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{font-size:12px;color:var(--mute)}}td.n{{white-space:nowrap;font-variant-numeric:tabular-nums}}
select,input{{font:inherit;font-size:13px;padding:4px 6px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);max-width:230px;display:block;margin-bottom:4px}}
tr.changed td:first-child{{box-shadow:inset 3px 0 0 var(--acc)}}
button{{font:inherit;background:var(--acc);color:#fff;border:0;border-radius:8px;padding:10px 18px;cursor:pointer}}
textarea{{width:100%;height:160px;margin-top:12px;font:12px/1.5 ui-monospace,monospace;display:none;background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px}}
ul{{margin:4px 0;padding-left:20px}}code{{background:var(--line);border-radius:4px;padding:0 4px}}
</style><main>
<h1>harness 改造方案</h1>
<p class="m">{e(plan["meta"]["root"])} · 生成于 {e(plan["meta"]["created"])} · 这一页不会改动任何文件</p>
<h2>改完之后的顶层</h2><div class="box"><ul>{layers}</ul></div>
<h2>每一项去哪（{len(plan["items"])} 项，下拉框可改）</h2>
<div class="box"><table><tr><th>现在的名字</th><th>文件数</th><th>体积</th><th>最后改动</th><th>你的决定</th><th>建议理由</th></tr>
{"".join(rows)}</table></div>
<h2>规则</h2><div class="box"><ul>
<li>只移动，不删除。归档的东西进 <code>{e(next(l["dir"] for l in plan["layers"] if l["key"] == "archive"))}/{e(plan["meta"]["batch"])}/</code>，附 MANIFEST.md 和 undo.sh</li>
<li>目标位置已有同名的会跳过，不合并不覆盖</li>
<li>「删除」只对空目录生效，非空会被拒绝</li>
<li>自带 git 仓库的目录移动后仓库照常可用，但如果它被外部脚本或定时任务引用，路径要自己改</li></ul></div>
<h2>确认</h2><p>调完之后点下面的按钮，把内容粘回对话。</p>
<button onclick="copy()">复制我的决定</button><span id="ok" class="m"></span><textarea id="out"></textarea>
<script>
document.querySelectorAll('tr[data-name]').forEach(tr=>{{const s=tr.querySelector('select');s.value=tr.dataset.default;
 const f=()=>tr.classList.toggle('changed',s.value!==tr.dataset.default||tr.querySelector('input').value!=='');
 s.onchange=f;tr.querySelector('input').oninput=f}});
function copy(){{const d={{}};document.querySelectorAll('tr[data-name]').forEach(tr=>{{
 const v=tr.querySelector('select').value,as=tr.querySelector('input').value.trim();
 const o=v.startsWith('move:')?{{action:'move',target:v.slice(5)}}:{{action:v}};if(as)o.as=as;d[tr.dataset.name]=o}});
 const t=JSON.stringify({{root:{json.dumps(plan["meta"]["root"])},decisions:d}},null,1);
 const ta=document.getElementById('out');ta.value=t;
 (navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(()=>document.getElementById('ok').textContent=' 已复制')
 .catch(()=>{{ta.style.display='block';ta.select();document.getElementById('ok').textContent=' 复制失败，请手动全选下面的内容'}})}}
</script></main></html>'''


def load_decisions(path):
    if not path:
        return {}
    raw = Path(path).read_text(encoding='utf-8')
    if '```' in raw:
        raw = raw.split('```')[1]
        raw = raw[4:] if raw.startswith('json') else raw
    return json.loads(raw).get('decisions', {})


def find_stale_links(root, moves):
    """移动之后，哪些文本文件里还写着旧路径。只报告，不改。"""
    olds = [(Path(a).name, b) for a, b in moves if Path(a).parent == root]
    hits = []
    if not olds:
        return hits
    for dp, dns, fns in os.walk(root):
        dns[:] = [x for x in dns if x not in SKIP and not x.startswith('.')]
        for fn in fns:
            p = Path(dp) / fn
            if p.suffix.lower() not in TEXT_EXT or p.stat().st_size > 2_000_000:
                continue
            try:
                txt = p.read_text(encoding='utf-8', errors='ignore')
            except OSError:
                continue
            for old, new in olds:
                # 三种写法都要认：原样、全编码、只把空格编码成 %20（Obsidian 常见）
                forms = {old, quote(old), old.replace(' ', '%20')}
                c = sum(txt.count(f + '/') for f in forms)
                if c:
                    hits.append((str(p.relative_to(root)), old, c))
    return hits


def cmd_apply(argv):
    args = [a for a in argv if not a.startswith('-')]
    dpath = argv[argv.index('-d') + 1] if '-d' in argv else None
    args = [a for a in args if a != dpath]
    if not args:
        die('用法: restructure.py apply restructure-plan.json [-d decisions.json] [--apply]')
    plan = json.loads(Path(args[0]).read_text(encoding='utf-8'))
    decisions = load_decisions(dpath)
    live = '--apply' in argv
    root = Path(plan['meta']['root'])
    ldir = {l['key']: l['dir'] for l in plan['layers']}
    batch_dir = root / ldir['archive'] / plan['meta']['batch']

    moves, removes, skipped = [], [], []          # moves: (src, dest, 说明)
    for it in plan['items']:
        d = decisions.get(it['name'], {'action': it['action'], 'target': it.get('target')})
        act, src = d.get('action'), root / it['name']
        if not src.exists():
            skipped.append((it['name'], '已经不在原位置')); continue
        if act == 'keep':
            continue
        if act == 'remove-empty':
            leftovers = [x for x in src.rglob('*') if x.name != '.DS_Store'] if src.is_dir() else [src]
            if leftovers:
                skipped.append((it['name'], '不是空目录，拒绝删除'))
            else:
                removes.append(src)
            continue
        if act == 'archive':
            dest = batch_dir / (d.get('as') or it['name'])
            note = '归档'
        elif act == 'move' and d.get('target') in ldir and d['target'] != 'archive':
            dest = root / ldir[d['target']] / (d.get('as') or it['name'])
            note = f'并入 {ldir[d["target"]]}'
        else:
            skipped.append((it['name'], f'看不懂的决定：{d}')); continue
        if dest.exists():
            skipped.append((it['name'], f'目标已存在 {dest.relative_to(root)}，不覆盖')); continue
        if src in dest.parents:
            skipped.append((it['name'], '目标在它自己里面')); continue
        moves.append((src, dest, note))

    print(f'{"执行" if live else "预演（不写盘）"} → {root}\n')
    for s, t, note in moves:
        print(f'  {s.name:<28} → {t.relative_to(root)}   [{note}]')
    for r in removes:
        print(f'  {r.name:<28} → 删除空目录')
    for n, why in skipped:
        print(f'  跳过 {n}：{why}')
    print(f'\n移动 {len(moves)} 项 · 删空目录 {len(removes)} 个 · 跳过 {len(skipped)} 项')
    if not live:
        print('确认无误后加 --apply 真正执行。'); return
    if not moves and not removes:
        print('没有要做的事。'); return

    done = []
    for s, t, note in moves:
        t.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(s), str(t)); done.append((s, t, note))
        except Exception as ex:
            print(f'  移动失败 {s.name}: {ex}')
    for r in removes:
        try:
            ds = r / '.DS_Store'
            if ds.exists():
                ds.unlink()
            r.rmdir()
        except OSError as ex:
            print(f'  删除失败 {r.name}: {ex}')
    # 新建的层目录补一份 README，说明这层放什么
    for l in plan['layers']:
        p = root / l['dir']
        if p.is_dir() and not (p / 'README.md').exists():
            (p / 'README.md').write_text(f'# {l["label"]}\n\n{l["desc"]}。\n', encoding='utf-8')

    batch_dir.mkdir(parents=True, exist_ok=True)
    stale = find_stale_links(root, [(str(s), str(t)) for s, t, _ in done])
    man = batch_dir / 'MANIFEST.md'
    lines = [] if man.exists() else ['# MANIFEST', '', '这一批改造里每一次移动的原路径和新路径。要退回就跑同目录下的 undo.sh。', '']
    lines += [f'## {datetime.datetime.now().isoformat(timespec="minutes")}', '',
              '| 原路径 | 新路径 | 说明 |', '|---|---|---|']
    lines += [f'| `{s.relative_to(root)}` | `{t.relative_to(root)}` | {note} |' for s, t, note in done]
    lines += [f'| `{r.relative_to(root)}` | （已删除） | 空目录 |' for r in removes]
    if stale:
        lines += ['', '### 可能失效的引用', '', '下面这些文件里还写着旧路径，需要人或 Agent 逐个确认后修改。', '',
                  '| 文件 | 旧目录名 | 出现次数 |', '|---|---|---|']
        lines += [f'| `{f}` | `{old}` | {c} |' for f, old, c in stale[:200]]
    with open(man, 'a', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n\n')
    undo = batch_dir / 'undo.sh'
    with open(undo, 'a', encoding='utf-8') as fh:
        if undo.stat().st_size == 0:
            fh.write('#!/bin/bash\n# 原路退回这一批移动。mv -n：原位置已有同名则不动。执行前过目。\nset -e\n')
        for s, t, _ in reversed(done):
            fh.write(f'mv -n "{t}" "{s}"\n')
    os.chmod(undo, 0o755)

    print(f'\n完成。移动 {len(done)} 项，没有删除任何文件。')
    print(f'清单 → {man}\n退回 → {undo}')
    if stale:
        print(f'{len(stale)} 处文本还写着旧路径，已列在 MANIFEST 里，需要逐个确认。')
    print('下一步：更新入口文件里的目录地图，然后跑一次 better-your-harness 体检。')


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('scan', 'apply'):
        die(__doc__)
    (cmd_scan if sys.argv[1] == 'scan' else cmd_apply)(sys.argv[2:])

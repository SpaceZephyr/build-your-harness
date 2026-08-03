#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
star-your-harness 方案报告：profile.json → plan.json + plan.html

不执行任何写盘动作。产出一份可视化方案，让人在页面上把拿不准的地方判断掉，
点「复制我的决定」把选择带回对话，再交给 apply.py 执行。

用法：
  python3 plan.py profile.json -o plan.html
"""
import json, os, re, sys, math, html, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scaffold import build_plan, ROLES                     # noqa: E402
from migrate import classify, harness_dirs, SKIP_DIRS      # noqa: E402

ACCENT = '#5eead4'
WARN = '#ffb020'
DANGER = '#ff5f56'

# 超过这个体量的来源目录，默认建议不搬（搬进来会毁掉信噪比）
BULK_FILES = 3000
BULK_BYTES = 150 * 1024 * 1024

# 代码工程的标记文件。有这些说明它是个仓库，不该被整个搬进 harness。
# 光看体量会漏：排掉 node_modules 之后一个 Next.js 工程可能只剩 20 个文件、
# 200KB，但它依然是代码，不是文档。
CODE_MARKERS = ['package.json', 'Cargo.toml', 'go.mod', 'pyproject.toml', 'requirements.txt',
                'Gemfile', 'pom.xml', 'build.gradle', 'tsconfig.json', 'composer.json']


def looks_like_codebase(src):
    src = Path(src)
    hits = [m for m in CODE_MARKERS if (src / m).exists()]
    if (src / '.git').is_dir():
        hits.append('.git')
    if (src / 'node_modules').is_dir():
        hits.append('node_modules')
    return hits


def e(s):
    return html.escape(str(s if s is not None else ''))


def measure(src):
    n, b = 0, 0
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.')]
        for fn in filenames:
            if fn.startswith('.'):
                continue
            try:
                b += (Path(dirpath) / fn).stat().st_size
                n += 1
            except Exception:
                pass
    return n, b


def scan_sources(profile, dirs):
    """对每个来源目录出一份归类建议。体量过大的直接建议不搬。"""
    root = Path(profile['dir'])
    layer_map, outputs = {}, []
    for d, zh, desc, layer in dirs:
        low = d.lower().replace('-', '').replace(' ', '')
        for key in ('inbox', 'about-me', 'vault', 'memory', 'protocols', 'garage'):
            if key.replace('-', '') in low:
                layer_map.setdefault(key, d)
        for zhk, key in (('收件箱', 'inbox'), ('关于我', 'about-me'), ('素材', 'vault'),
                         ('记忆', 'memory'), ('协议', 'protocols'), ('车库', 'garage')):
            if zhk in d:
                layer_map.setdefault(key, d)
    outputs = [d for d, _, _, layer in dirs if layer == '产出']

    out = []
    for s in profile.get('sources', []):
        src = Path(s).expanduser()
        if not src.exists():
            out.append({'src': str(src), 'error': '目录不存在', 'items': [], 'bulk': False})
            continue
        n, b = measure(src)
        markers = looks_like_codebase(src)
        bulk = bool(markers) or n > BULK_FILES or b > BULK_BYTES
        items = []
        if not bulk:
            for dirpath, dirnames, filenames in os.walk(src):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.')]
                for fn in filenames:
                    if fn.startswith('.'):
                        continue
                    p = Path(dirpath) / fn
                    rel = str(p.relative_to(src))
                    dest, why, conf = classify(p, rel, layer_map, outputs)
                    exists = (root / dest / Path(rel).name).exists()
                    try:
                        kb = round(p.stat().st_size / 1024, 1)
                    except Exception:
                        kb = 0
                    items.append({'src': str(p), 'rel': rel, 'name': Path(rel).name,
                                  'dest': dest, 'why': why, 'conf': conf,
                                  'kb': kb, 'collision': exists})
        out.append({'src': str(src), 'files': n, 'mb': round(b / 1024 / 1024, 1),
                    'bulk': bulk, 'markers': markers, 'items': items, 'error': ''})
    return out, [d for d, *_ in dirs]


def build(profile):
    dirs, files = build_plan(profile)
    root = Path(profile['dir'])
    sources, all_dirs = scan_sources(profile, dirs)

    risks = []
    if root.exists() and any(root.iterdir()):
        n = len(list(root.iterdir()))
        risks.append({
            'level': 'warn',
            'title': f'目标目录已经有 {n} 个条目',
            'body': f'{root} 不是空的。同名文件一律跳过不覆盖，但你心里要有数。',
        })
    for s in sources:
        if s.get('error'):
            risks.append({'level': 'warn', 'title': f'来源读不了：{Path(s["src"]).name}', 'body': s['error']})
        # bulk 来源不进 risks：下面有带勾选框的专用卡片，同一件事不说两遍
    collide = sum(1 for s in sources for i in s['items'] if i['collision'])
    if collide:
        risks.append({'level': 'warn', 'title': f'{collide} 个文件在目标目录已有同名',
                      'body': '这些默认跳过，不会覆盖。想换个名字放进来的话在下面单独指定。'})

    plan = {
        'meta': {
            'name': profile.get('name') or root.name,
            'dir': str(root),
            'role': ROLES.get(profile.get('role'), ROLES['generalist'])['label'],
            'role_key': profile.get('role', 'generalist'),
            'why': profile.get('why', ''),
            'purposes': profile.get('purposes', []),
            'naming': profile.get('naming', 'numbered-en'),
            'created': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        },
        'dirs': [{'name': d, 'label': zh, 'desc': desc, 'layer': layer} for d, zh, desc, layer in dirs],
        'files': {k: v for k, v in files.items()},
        'sources': sources,
        'risks': risks,
        'git': profile.get('git', True),
        'hooks': profile.get('hooks', True),
    }
    return plan


# ---------- HTML ----------
LAYER_COLOR = {'入口': '#94a3b8', '上下文': ACCENT, '产出': '#7dd3fc',
               '记忆': '#c4b5fd', '学习': WARN, '工具': '#86efac'}


def render(plan):
    m = plan['meta']
    dirs, files, sources, risks = plan['dirs'], plan['files'], plan['sources'], plan['risks']

    # 目录树
    tree = ''
    for d in dirs:
        col = LAYER_COLOR.get(d['layer'], '#94a3b8')
        nfiles = sum(1 for k in files if k.startswith(d['name'] + '/'))
        tree += f'''<div class="node">
  <span class="bar" style="background:{col}"></span>
  <div class="nmain"><b>{e(d['name'])}/</b><span class="ndesc">{e(d['desc'])}</span></div>
  <span class="nlayer" style="color:{col};border-color:{col}">{e(d['layer'])}</span>
  <span class="nfiles">{nfiles} 个文件</span>
</div>'''

    root_files = sorted(k for k in files if '/' not in k)
    rootlist = ''.join(f'<li><code>{e(k)}</code></li>' for k in root_files)
    alllist = ''.join(f'<li><code>{e(k)}</code></li>' for k in sorted(files))

    # 风险
    rhtml = ''
    for r in risks:
        col = DANGER if r['level'] == 'danger' else WARN
        rhtml += (f'<div class="risk" style="--c:{col}"><b>{e(r["title"])}</b>'
                  f'<p>{e(r["body"])}</p></div>')
    if not rhtml:
        rhtml = '<p class="muted">没有检测到风险。目标目录是空的，来源体量正常。</p>'

    # 迁移：分成「需要你判断」和「已确定」
    dir_opts = ''.join(f'<option value="{e(d["name"])}">{e(d["name"])}</option>' for d in dirs)
    need, sure, bulk_cards = [], [], ''
    for s in sources:
        if s.get('error'):
            continue
        if s['bulk']:
            mk = s.get('markers') or []
            if mk:
                reason = (f'检测到 {"、".join(mk[:4])}，这是代码工程不是文档目录。'
                          f'代码归代码仓库，harness 只放文档和决策。需要 Agent 看代码时'
                          f'直接给它绝对路径，比复制一份进来强。')
            else:
                reason = (f'{s["files"]:,} 个文件 · {s["mb"]:,.0f} MB，体量过大，'
                          f'搬进来会让噪音比爆掉，Agent 检索时全是干扰。')
            bulk_cards += f'''<div class="risk" style="--c:{DANGER}">
  <b>{e(Path(s['src']).name)} — 建议不搬</b>
  <p>{e(reason)} 默认整个跳过，改成在产出目录放指针文件。</p>
  <label class="chk"><input type="checkbox" class="bulk" data-src="{e(s['src'])}"> 我还是要搬（不推荐）</label>
</div>'''
            continue
        for it in s['items']:
            (sure if it['conf'] == 'high' and not it['collision'] else need).append(it)

    def row(it, idx, editable):
        badge = {'high': ('确定', ACCENT), 'medium': ('大概', WARN), 'low': ('拿不准', DANGER)}[it['conf']]
        coll = '<span class="coll">目标已有同名</span>' if it['collision'] else ''
        sel = (f'<select class="dec" data-src="{e(it["src"])}">'
               f'<option value="__skip__">不搬</option>{dir_opts}</select>') if editable else \
              f'<span class="fixed">{e(it["dest"])}/</span>'
        return f'''<tr>
  <td class="fn"><code>{e(it['rel'])}</code>{coll}</td>
  <td class="why"><span class="cf" style="color:{badge[1]};border-color:{badge[1]}">{badge[0]}</span>{e(it['why'])}</td>
  <td class="to">{sel}</td>
</tr>'''

    need_rows = ''.join(row(it, i, True) for i, it in enumerate(need))
    sure_rows = ''.join(row(it, i, True) for i, it in enumerate(sure))
    presel = json.dumps(
        {it['src']: ('__skip__' if it['collision'] else it['dest']) for it in need + sure},
        ensure_ascii=False)

    n_dirs, n_files = len(dirs), len(files)
    n_need, n_sure = len(need), len(sure)
    purposes = '、'.join(m['purposes']) or '（未填）'

    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(m['name'])} · 搭建方案</title>
<style>{CSS}</style></head><body>
<button class="theme">切换深浅</button>
<div class="wrap">

<header class="hero">
  <div>
    <div class="eyebrow">STAR YOUR HARNESS · 搭建方案</div>
    <h1>{e(m['name'])}</h1>
    <div class="path">{e(m['dir'])}</div>
    <p class="lead">按「{e(m['role'])}」模板生成。你说想让 AI 帮你 <b>{e(purposes)}</b>，
      所以产出层按这个配。<b>这份方案还没有执行任何写盘动作。</b></p>
    <div class="pills">
      <span class="pill">{n_dirs} 个目录</span>
      <span class="pill">{n_files} 个文件</span>
      <span class="pill">{n_need + n_sure} 个待搬文件</span>
      <span class="pill muted">{e(m['created'])}</span>
    </div>
  </div>
</header>

<section class="card">
  <h2>1 · 会建成什么样 <span class="sub">左边色条是它属于 harness 的哪一层</span></h2>
  <div class="tree">{tree}</div>
  <details class="fold"><summary>根目录还会写 {len(root_files)} 个文件</summary><ul class="flist">{rootlist}</ul></details>
  <details class="fold"><summary>展开全部 {n_files} 个文件</summary><ul class="flist">{alllist}</ul></details>
</section>

<section class="card">
  <h2>2 · 需要注意的地方</h2>
  {rhtml}{bulk_cards}
</section>

<section class="card">
  <h2>3 · 要你判断的 <span class="sub">{n_need} 个文件归类不确定，改完下拉框再复制决定</span></h2>
  {f'<table class="mig"><thead><tr><th>文件</th><th>为什么这么判</th><th>放到哪</th></tr></thead><tbody>{need_rows}</tbody></table>'
     if need else '<p class="muted">没有需要判断的，全部归类明确。</p>'}
  <details class="fold"><summary>另外 {n_sure} 个归类明确，已自动定好（觉得不对也能在这里改）</summary>
    <table class="mig"><tbody>{sure_rows or '<tr><td class="muted">无</td></tr>'}</tbody></table>
  </details>
</section>

<section class="card act">
  <h2>4 · 确认执行</h2>
  <p class="lead">上面调好之后点这里，把你的决定复制回对话，我再执行。
    在此之前不会有任何文件被创建或移动。</p>
  <div class="btns">
    <button class="btn primary" id="copy">复制我的决定</button>
    <button class="btn" id="copyall">连方案一起复制</button>
  </div>
  <pre class="out" id="out" hidden></pre>
</section>

<section class="card method">
  <h2>规矩</h2>
  <ul>
    <li>已存在的文件<b>一律跳过不覆盖</b>，你手写的东西不会被冲掉。</li>
    <li>搬运用 <code>cp</code> 不用 <code>mv</code>，来源文件一个不动，确认没问题你自己决定要不要清理。</li>
    <li>归类是按文件名和后缀猜的，标「拿不准」的那些猜错很正常，所以才要你过一眼。</li>
    <li>体量过大的来源默认不搬。代码工程留在代码仓库，harness 只放文档和决策。</li>
  </ul>
</section>

</div>
<script>
const PRESEL = {presel};
document.querySelector('.theme').onclick=()=>{{
  const r=document.documentElement;
  const cur=r.dataset.theme||(matchMedia('(prefers-color-scheme:light)').matches?'light':'dark');
  r.dataset.theme=cur==='light'?'dark':'light';
}};
document.querySelectorAll('.dec').forEach(s=>{{
  const v=PRESEL[s.dataset.src]; if(v) s.value=v;
}});
function collect(){{
  const d={{}};
  document.querySelectorAll('.dec').forEach(s=>{{ d[s.dataset.src]=s.value; }});
  const bulk=[...document.querySelectorAll('.bulk')].filter(b=>b.checked).map(b=>b.dataset.src);
  return {{harness:{json.dumps(m['dir'], ensure_ascii=False)}, decisions:d, include_bulk:bulk}};
}}
async function cp(t){{
  try{{ if(navigator.clipboard&&isSecureContext){{ await navigator.clipboard.writeText(t); return true; }} }}catch(e){{}}
  try{{ const a=document.createElement('textarea'); a.value=t; a.style.position='fixed'; a.style.opacity='0';
    document.body.appendChild(a); a.select(); const ok=document.execCommand('copy');
    document.body.removeChild(a); return ok; }}catch(e){{ return false; }}
}}
function wire(id, fn){{
  document.getElementById(id).onclick=async(ev)=>{{
    const t=fn(); const ok=await cp(t); const b=ev.target; const old=b.textContent;
    b.textContent=ok?'已复制，粘回对话就行':'复制失败，手动选下面这段';
    if(!ok){{ const o=document.getElementById('out'); o.hidden=false; o.textContent=t; }}
    setTimeout(()=>b.textContent=old,2600);
  }};
}}
wire('copy',()=>'我的决定：\\n```json\\n'+JSON.stringify(collect(),null,2)+'\\n```');
wire('copyall',()=>'方案确认，按这个执行：\\n```json\\n'+JSON.stringify(collect(),null,2)+'\\n```');
</script></body></html>'''


CSS = '''
:root{--bg:#0b0e14;--card:#11151d;--card2:#171c26;--line:#232a36;--grid:#2a3240;
--text:#e8ecf3;--sub:#94a3b8;--accent:#5eead4;--code:#0a0d12;--shadow:rgba(0,0,0,.45)}
:root[data-theme=light]{--bg:#f6f7f9;--card:#fff;--card2:#f1f4f8;--line:#e3e8ef;--grid:#dfe5ee;
--text:#0f172a;--sub:#5b6675;--accent:#0d9488;--code:#f3f5f8;--shadow:rgba(15,30,60,.10)}
@media(prefers-color-scheme:light){:root:not([data-theme=dark]){--bg:#f6f7f9;--card:#fff;--card2:#f1f4f8;
--line:#e3e8ef;--grid:#dfe5ee;--text:#0f172a;--sub:#5b6675;--accent:#0d9488;--code:#f3f5f8;--shadow:rgba(15,30,60,.10)}}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font:14px/1.7 -apple-system,"PingFang SC",system-ui,sans-serif;padding:32px 20px 80px}
.wrap{max-width:980px;margin:0 auto;display:flex;flex-direction:column;gap:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:24px}
h1{font-size:30px;letter-spacing:-.5px;margin:6px 0 4px}
h2{font-size:17px;margin-bottom:18px;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
h2 .sub{font-size:12px;color:var(--sub);font-weight:400}
code{background:var(--code);padding:1px 6px;border-radius:4px;font-size:12px;font-family:ui-monospace,monospace}
.hero{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:28px}
.eyebrow{font-size:11px;letter-spacing:2.5px;color:var(--accent);font-weight:700}
.path{font-family:ui-monospace,monospace;font-size:11.5px;color:var(--sub);word-break:break-all}
.lead{margin:14px 0;font-size:14px;line-height:1.85;max-width:700px}
.pills{display:flex;gap:8px;flex-wrap:wrap;margin-top:6px}
.pill{font-size:11.5px;border:1px solid var(--accent);color:var(--accent);border-radius:999px;padding:3px 11px}
.pill.muted{border-color:var(--line);color:var(--sub)}
.muted{color:var(--sub);font-size:13px}
/* 树 */
.tree{display:flex;flex-direction:column;gap:2px}
.node{display:flex;align-items:center;gap:12px;padding:9px 12px;border-radius:9px;background:var(--card2);
border:1px solid var(--line)}
.bar{width:3px;height:26px;border-radius:99px;flex:none}
.nmain{flex:1;min-width:0;display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.nmain b{font-size:14px;white-space:nowrap}
.ndesc{font-size:12px;color:var(--sub)}
.nlayer{flex:none;font-size:10.5px;border:1px solid;border-radius:5px;padding:1px 7px}
.nfiles{flex:none;font-size:10.5px;color:var(--sub);width:64px;text-align:right}
.fold{margin-top:14px}
.fold summary{font-size:12.5px;color:var(--sub);cursor:pointer}
.fold summary:hover{color:var(--text)}
.flist{list-style:none;display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.flist li code{font-size:11px}
/* 风险 */
.risk{background:var(--card2);border:1px solid var(--line);border-left:3px solid var(--c);
border-radius:10px;padding:14px 16px;margin-bottom:10px}
.risk b{font-size:14px;color:var(--c)}
.risk p{font-size:12.5px;color:var(--sub);margin-top:6px;line-height:1.75}
.chk{display:inline-flex;align-items:center;gap:7px;font-size:12px;color:var(--sub);margin-top:10px;cursor:pointer}
.chk input{accent-color:var(--c)}
/* 迁移表 */
.mig{width:100%;border-collapse:collapse;font-size:12.5px}
.mig th{text-align:left;font-size:11px;color:var(--sub);font-weight:600;padding:6px 8px;border-bottom:1px solid var(--line)}
.mig td{padding:8px;border-bottom:1px solid var(--line);vertical-align:middle}
.fn code{font-size:11.5px}
.coll{font-size:10px;color:var(--sub);border:1px solid var(--line);border-radius:4px;padding:1px 6px;margin-left:8px}
.why{color:var(--sub)}
.cf{font-size:10px;border:1px solid;border-radius:4px;padding:1px 6px;margin-right:8px}
.to{width:190px}
.dec{width:100%;background:var(--card2);color:var(--text);border:1px solid var(--line);
border-radius:8px;padding:6px 9px;font-size:12px;font-family:inherit;outline:none}
.dec:focus{border-color:var(--accent)}
.fixed{font-size:12px;color:var(--sub);font-family:ui-monospace,monospace}
/* 动作 */
.act .btns{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
.btn{border:1px solid var(--line);background:var(--card2);color:var(--text);border-radius:9px;
padding:10px 18px;font-size:13.5px;cursor:pointer;font-family:inherit}
.btn:hover{border-color:var(--accent)}
.btn.primary{background:var(--accent);color:var(--bg);border-color:var(--accent);font-weight:700}
.out{margin-top:14px;background:var(--code);border:1px solid var(--line);border-radius:10px;padding:12px;
font-family:ui-monospace,monospace;font-size:11.5px;white-space:pre-wrap;word-break:break-all;max-height:280px;overflow:auto}
.method ul{list-style:none;display:flex;flex-direction:column;gap:9px}
.method li{font-size:12.5px;color:var(--sub);line-height:1.75;padding-left:16px;position:relative}
.method li::before{content:"";position:absolute;left:0;top:9px;width:5px;height:5px;border-radius:99px;background:var(--accent)}
.theme{position:fixed;top:16px;right:18px;background:var(--card);border:1px solid var(--line);
color:var(--sub);border-radius:99px;padding:6px 14px;font-size:12px;cursor:pointer;font-family:inherit;z-index:9}
@media print{.theme,.btn{display:none}body{padding:0}}
'''


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if not args:
        print('用法: plan.py profile.json [-o plan.html]'); sys.exit(1)
    profile = json.loads(Path(args[0]).read_text(encoding='utf-8'))
    plan = build(profile)

    out = sys.argv[sys.argv.index('-o') + 1] if '-o' in sys.argv else 'plan.html'
    jsonp = str(Path(out).with_suffix('.json'))
    Path(jsonp).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    Path(out).write_text(render(plan), encoding='utf-8')

    need = sum(1 for s in plan['sources'] if not s['bulk']
               for i in s['items'] if i['conf'] != 'high' or i['collision'])
    print(f'方案 → {out}')
    print(f'数据 → {jsonp}')
    print(f'  {len(plan["dirs"])} 个目录 · {len(plan["files"])} 个文件 · '
          f'{need} 项要你判断 · {len(plan["risks"])} 条风险提示')
    print('  没有写盘。让用户看完页面、点「复制我的决定」，再跑 apply.py。')


if __name__ == '__main__':
    main()

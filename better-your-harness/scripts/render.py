#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
better-your-harness 渲染器：findings.json (+ analysis.json) → 单页 HTML。

零依赖，所有图表手绘内联 SVG。样式固定在模板里，所以每次跑出来长得一样，
AI 只贡献文字判断，不碰排版。

用法：
  python3 render.py findings.json -o report.html
  python3 render.py findings.json -a analysis.json -o report.html
"""
import json, sys, html, math
from pathlib import Path

ACCENT = '#5eead4'
SEV = {
    'high':   ('#ff5f56', '高'),
    'medium': ('#ffb020', '中'),
    'low':    ('#7dd3fc', '低'),
    'info':   ('#94a3b8', '观察'),
}
LAYER_ORDER = ['security', 'context', 'tools', 'memory', 'learning']

def e(s):
    return html.escape(str(s if s is not None else ''))

def attr(s):
    return html.escape(str(s if s is not None else ''), quote=True)


# ---------- 图表 ----------
def radar(scores, labels, size=260):
    """五角雷达图，轴 = 各层覆盖度百分比。"""
    n = len(scores)
    cx = cy = size / 2
    R = size / 2 - 46
    rings = ''
    for frac in (0.25, 0.5, 0.75, 1.0):
        pts = []
        for i in range(n):
            a = -math.pi / 2 + i * 2 * math.pi / n
            pts.append(f'{cx + R*frac*math.cos(a):.1f},{cy + R*frac*math.sin(a):.1f}')
        rings += (f'<polygon points="{" ".join(pts)}" fill="none" '
                  f'stroke="var(--grid)" stroke-width="1"/>')
    spokes, labs, pts = '', '', []
    for i, (v, lab) in enumerate(zip(scores, labels)):
        a = -math.pi / 2 + i * 2 * math.pi / n
        x, y = cx + R * math.cos(a), cy + R * math.sin(a)
        spokes += f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="var(--grid)" stroke-width="1"/>'
        lx, ly = cx + (R + 26) * math.cos(a), cy + (R + 26) * math.sin(a)
        anchor = 'middle' if abs(math.cos(a)) < 0.3 else ('start' if math.cos(a) > 0 else 'end')
        labs += (f'<text x="{lx:.1f}" y="{ly + 4:.1f}" text-anchor="{anchor}" '
                 f'class="rl">{e(lab)}</text>')
        pts.append(f'{cx + R*v*math.cos(a):.1f},{cy + R*v*math.sin(a):.1f}')
    dots = ''.join(f'<circle cx="{p.split(",")[0]}" cy="{p.split(",")[1]}" r="3.5" fill="{ACCENT}"/>'
                   for p in pts)
    return (f'<svg viewBox="0 0 {size} {size}" class="radar">{rings}{spokes}'
            f'<polygon points="{" ".join(pts)}" fill="{ACCENT}22" stroke="{ACCENT}" stroke-width="2"/>'
            f'{dots}{labs}</svg>')


def donut(parts, size=150, thick=20):
    """环形图。parts = [(值, 颜色, 标签)]"""
    total = sum(p[0] for p in parts) or 1
    r = size / 2 - thick / 2
    cx = cy = size / 2
    circ = 2 * math.pi * r
    segs, off = '', 0.0
    for val, color, _ in parts:
        frac = val / total
        segs += (f'<circle cx="{cx}" cy="{cy}" r="{r:.2f}" fill="none" stroke="{color}" '
                 f'stroke-width="{thick}" stroke-dasharray="{circ*frac:.2f} {circ:.2f}" '
                 f'stroke-dashoffset="{-circ*off:.2f}" transform="rotate(-90 {cx} {cy})"/>')
        off += frac
    return f'<svg viewBox="0 0 {size} {size}" class="donut">{segs}</svg>'


def bar(frac, color=ACCENT):
    pct = max(0.0, min(1.0, frac)) * 100
    return (f'<div class="bar"><i style="width:{pct:.1f}%;background:{color}"></i></div>')


def dotmatrix(total, lit_names, all_names, per_row=34, cap=300):
    """点阵：每个点一个 Skill，用过的点亮。直观看出装机量和实际使用量的落差。"""
    shown = all_names[:cap]
    lit = set(lit_names)
    cells = ''
    for i, name in enumerate(shown):
        on = name in lit
        cls = 'dm on' if on else 'dm'
        cells += f'<i class="{cls}" title="{attr(name)}"></i>'
    more = f'<span class="dm-more">另有 {total - len(shown)} 个未画出</span>' if total > len(shown) else ''
    return f'<div class="dotmatrix">{cells}</div>{more}'


def gauge(value, danger, warn, unit='', width=190):
    """横向刻度条：越靠右越糟。"""
    if value >= danger:
        color, tone = SEV['high'][0], '偏高'
    elif value >= warn:
        color, tone = SEV['medium'][0], '临界'
    else:
        color, tone = ACCENT, '健康'
    frac = min(1.0, value / (danger * 1.4)) if danger else 0
    return (f'<div class="gauge"><div class="gauge-bar"><i style="width:{frac*100:.1f}%;'
            f'background:{color}"></i></div>'
            f'<div class="gauge-meta"><b style="color:{color}">{value:,}{unit}</b>'
            f'<span>{tone} · 警戒 {warn:,} / 危险 {danger:,}</span></div></div>')


# ---------- 组装 ----------
def build(d, a):
    meta, score, labels = d['meta'], d['score'], d.get('labels', {})
    sec, ctx, tools = d.get('security', {}), d.get('context', {}), d.get('tools', {})
    mem, learn, usage = d.get('memory', {}), d.get('learning', {}), d.get('usage', {})
    sk = tools.get('skills', {})

    got = sum(v['passed'] for v in score.values())
    tot = sum(v['total'] for v in score.values())
    overall = got / tot if tot else 0

    an_find = {f['id']: f for f in (a.get('findings') or [])}
    an_layer = a.get('layers') or {}

    # ---- HERO ----
    ring_r, ring_c = 54, 2 * math.pi * 54
    ring_color = ACCENT if overall >= .7 else (SEV['medium'][0] if overall >= .45 else SEV['high'][0])
    verdict = a.get('verdict') or '扫描已完成，下方为事实清单。判断性结论需要 analysis.json 才会出现。'
    repo = sec.get('repo', {})
    vis = repo.get('visibility', 'UNKNOWN')
    vis_cls = 'pill danger' if vis == 'PUBLIC' else ('pill' if vis == 'PRIVATE' else 'pill muted')

    hero = f'''<header class="hero">
  <div class="hero-l">
    <div class="eyebrow">HARNESS 体检报告</div>
    <h1>{e(meta.get('name'))}</h1>
    <div class="path">{e(meta.get('root'))}</div>
    <p class="verdict">{e(verdict)}</p>
    <div class="pills">
      <span class="{vis_cls}">{e(repo.get('name') or '未连接远程')} · {e(vis)}</span>
      <span class="pill muted">分支 {e(repo.get('branch') or '—')}</span>
      <span class="pill muted">扫描于 {e(meta.get('scanned_at'))}</span>
    </div>
  </div>
  <div class="hero-r">
    <svg viewBox="0 0 140 140" class="ring">
      <circle cx="70" cy="70" r="{ring_r}" fill="none" stroke="var(--grid)" stroke-width="12"/>
      <circle cx="70" cy="70" r="{ring_r}" fill="none" stroke="{ring_color}" stroke-width="12"
        stroke-linecap="round" stroke-dasharray="{ring_c*overall:.1f} {ring_c:.1f}"
        transform="rotate(-90 70 70)"/>
      <text x="70" y="66" class="ring-n">{got}</text>
      <text x="70" y="90" class="ring-d">/ {tot}</text>
    </svg>
    <div class="ring-cap">应有项覆盖度</div>
  </div>
</header>'''

    # ---- 五层 ----
    fr = [score[k]['passed'] / score[k]['total'] if score[k]['total'] else 0 for k in LAYER_ORDER]
    short = {'security': '安全', 'context': '上下文', 'tools': '工具', 'memory': '记忆', 'learning': '学习'}
    lbs = [short.get(k, labels.get(k, k)) for k in LAYER_ORDER]
    rows = ''
    for k, f in zip(LAYER_ORDER, fr):
        s = score[k]
        col = ACCENT if f >= .7 else (SEV['medium'][0] if f >= .45 else SEV['high'][0])
        items = ''.join(
            f'<li class="{"ok" if it["ok"] else "no"}">{e(it["name"])}</li>' for it in s['items'])
        note = an_layer.get(k, {}).get('comment', '')
        rows += f'''<div class="lrow">
  <div class="lhead"><span class="lname">{e(labels.get(k,k))}</span>
    <span class="lnum" style="color:{col}">{s['passed']}<i>/{s['total']}</i></span></div>
  {bar(f, col)}
  {f'<p class="lnote">{e(note)}</p>' if note else ''}
  <ul class="checks">{items}</ul>
</div>'''

    layers = f'''<section class="card split">
  <div class="radar-wrap">{radar(fr, lbs)}<div class="cap">五层覆盖度</div></div>
  <div class="lrows">{rows}</div>
</section>'''

    # ---- 上下文质量 ----
    tr = sec.get('tracked', {})
    noise, source = tr.get('noise', 0), tr.get('source', 0)
    cold = ctx.get('cold_start', {})
    td = ctx.get('top_dirs', {})
    st = ctx.get('structure', {})
    big_rows = ''.join(
        f'<tr><td class="mono">{e(b["path"])}</td><td class="num">{b["kb"]} KB</td></tr>'
        for b in st.get('big_files', [])[:6])
    wide_rows = ''.join(
        f'<tr><td class="mono">{e(w["dir"])}</td><td class="num">{w["children"]}</td></tr>'
        for w in st.get('wide_dirs', [])[:5])
    entry_rows = ''.join(
        f'<tr><td class="mono">{e(x["name"])}</td><td class="num">{x["tokens"]:,} tok</td>'
        f'<td>{"目录地图 " if x["has_dir_map"] else ""}{"行为规则" if x["has_rules"] else ""}</td></tr>'
        for x in ctx.get('entries', []))

    context_sec = f'''<section class="card">
  <h2>上下文质量 <span class="sub">Agent 读这个仓库有多费劲</span></h2>
  <div class="grid3">
    <div class="metric">
      <div class="mtitle">噪音比</div>
      <div class="donut-wrap">{donut([(noise, SEV['high'][0], '噪音'), (source, ACCENT, '源文件')])}
        <div class="donut-c"><b>{(source/(noise+source)*100 if (noise+source) else 0):.1f}%</b><span>是源文件</span></div>
      </div>
      <div class="legend"><i style="background:{ACCENT}"></i>源文件 {source:,}
        <i style="background:{SEV['high'][0]}"></i>依赖与构建产物 {noise:,}</div>
      <p class="mnote">grep 和 glob 会被多少垃圾干扰</p>
    </div>
    <div class="metric">
      <div class="mtitle">冷启动成本</div>
      {gauge(cold.get('tokens', 0), 20000, 10000, ' tok')}
      <p class="mnote">Agent 从零理解这个项目，光读入口文件和各层 README 就要吃掉的上下文。
        入口 {cold.get('entry_chars',0):,} 字，README {cold.get('readme_chars',0):,} 字。</p>
      <table class="mini">{entry_rows or '<tr><td colspan="3">没有入口文件</td></tr>'}</table>
    </div>
    <div class="metric">
      <div class="mtitle">目录可读性</div>
      <div class="kv"><span>顶层目录 README 覆盖</span><b>{td.get('with_readme',0)}/{td.get('total',0)}</b></div>
      {bar(td.get('coverage', 0), ACCENT if td.get('coverage',0)>=.6 else SEV['medium'][0])}
      <div class="kv"><span>最大目录深度</span><b>{st.get('max_depth',0)} 层</b></div>
      <div class="kv"><span>平均文件深度</span><b>{st.get('avg_depth',0)}</b></div>
      <p class="mnote">缺 README 的顶层目录：{e('、'.join(td.get('missing', [])[:6]) or '无')}</p>
    </div>
  </div>
  <div class="grid2">
    <div><div class="mtitle sm">超大文本文件（读一次就吃掉大量窗口）</div>
      <table class="mini">{big_rows or '<tr><td>无</td></tr>'}</table></div>
    <div><div class="mtitle sm">过度扁平的目录（子项过多，难检索）</div>
      <table class="mini">{wide_rows or '<tr><td>无</td></tr>'}</table></div>
  </div>
</section>'''

    # ---- 装备 ----
    used_names = [k for k, _ in usage.get('top', [])]
    all_names = sk.get('names', [])
    installed = usage.get('installed', sk.get('total', 0))
    used_n = usage.get('used_count', 0)
    inv = usage.get('invocations', 0)
    ev = usage.get('evidence') == 'ok'
    top_rows = ''.join(
        f'<tr><td class="mono">{e(n)}</td><td class="num">{c}</td></tr>'
        for n, c in usage.get('top', [])[:10])
    loc_rows = ''.join(
        f'<tr><td class="mono">{e(l["path"])}</td><td class="num">{l["with_skill_md"]}/{l["entries"]}</td>'
        f'<td class="num">{l["symlinks"]}</td><td>{"镜像" if l.get("duplicate_of") else ""}</td></tr>'
        for l in sk.get('locations', []))
    mcp_chips = ''.join(f'<span class="chip">{e(s["name"])}</span>'
                        for s in tools.get('mcp', {}).get('servers', [])[:24])

    zombie = f'''<div class="zombie">
  <div class="zhead">
    <div><b class="big">{installed}</b><span>装了</span></div>
    <div><b class="big" style="color:{ACCENT}">{used_n}</b><span>真实调用过</span></div>
    <div><b class="big" style="color:{SEV['high'][0]}">{usage.get('never_count',0)}</b><span>从未调用</span></div>
    <div><b class="big">{inv}</b><span>总调用次数</span></div>
  </div>
  {dotmatrix(installed, used_names, all_names)}
  <p class="mnote">每个点一个 Skill，亮的是会话日志里真实出现过 <code>tool_use(name=Skill)</code> 的。
  统计只认真实调用，不认「被列在系统提示词里」，两者差两个数量级。
  证据来自 {usage.get('session_files_read',0)} 个会话文件。</p>
</div>''' if ev else '<p class="mnote">没有找到可读的会话日志，僵尸 Skill 无法统计。</p>'

    tools_sec = f'''<section class="card">
  <h2>工具装备 <span class="sub">装了多少，真正在用多少</span></h2>
  {zombie}
  <div class="grid2 gap">
    <div><div class="mtitle sm">Skill 存放位置</div>
      <table class="mini"><thead><tr><th>路径</th><th>有 SKILL.md</th><th>软链</th><th></th></tr></thead>
      {loc_rows}</table></div>
    <div><div class="mtitle sm">调用最多的 Skill</div>
      <table class="mini">{top_rows or '<tr><td>无记录</td></tr>'}</table></div>
  </div>
  <div class="mtitle sm">MCP 服务 · {tools.get('mcp',{}).get('count',0)} 个</div>
  <div class="chips">{mcp_chips or '<span class="chip muted">未检测到</span>'}</div>
  <div class="grid3 gap">
    <div class="kv"><span>自定义子 Agent</span><b>{tools.get('agents',{}).get('count',0)}</b></div>
    <div class="kv"><span>自定义命令</span><b>{tools.get('commands',{}).get('count',0)}</b></div>
    <div class="kv"><span>Hooks</span><b>{sec.get('hooks',{}).get('count',0)}</b></div>
  </div>
</section>'''

    # ---- 待办 ----
    order = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}
    fl = []
    for f in d.get('findings', []):
        an = an_find.get(f['id'], {})
        fl.append({**f, 'severity': an.get('severity', 'medium'),
                   'title': an.get('title') or f['id'],
                   'why': an.get('why', ''), 'fix': an.get('fix_prompt', '')})
    fl.sort(key=lambda x: order.get(x['severity'], 9))
    cards = ''
    for i, f in enumerate(fl):
        col, sl = SEV.get(f['severity'], SEV['medium'])
        fix = f['fix']
        btn = (f'<button class="copy" data-i="{i}">复制修复口令</button>'
               if fix else '<span class="nofix">没有可自动修复的口令</span>')
        pre = f'<pre class="fix" id="fix{i}" hidden>{e(fix)}</pre>' if fix else ''
        cards += f'''<article class="finding" style="--sev:{col}">
  <div class="fhead"><span class="sev">{e(sl)}</span><h3>{e(f['title'])}</h3>
    <span class="flayer">{e(labels.get(f['layer'], f['layer']))}</span></div>
  <p class="fact">{e(f['fact'])}</p>
  {f'<p class="why">{e(f["why"])}</p>' if f['why'] else ''}
  <div class="frow">{btn}</div>{pre}
</article>'''

    todo = f'''<section class="card">
  <h2>待办 <span class="sub">按严重度排序 · 点「复制修复口令」，粘到 Claude Code 或 Codex 发送</span></h2>
  <div class="findings">{cards or '<p class="mnote">没有发现问题。</p>'}</div>
</section>'''

    # ---- 方法 ----
    method = f'''<section class="card method">
  <h2>方法与局限</h2>
  <ul>
    <li>所有数字来自扫描脚本实测，模型只负责解读。仓库可见性走 <code>gh repo view</code>，不做推断。</li>
    <li>凭证扫描只报「文件路径 + 变量名 + 命中的模式」，<b>任何密钥的值都不会进入这份报告</b>。</li>
    <li>Skill 装机量按唯一名字去重（跨位置条目 {sk.get('entries_across_locations','—')} 条，去重后 {sk.get('total','—')} 个）。</li>
    <li>调用统计口径：<code>{e(usage.get('method','—'))}</code>。系统提示词里的 Skill 清单不计入。</li>
    <li>覆盖度是「已具备项 / 应有项」的可数比值，修一项就变一项，不是不可证伪的百分制评分。</li>
    <li>本报告只描述当前仓库状态，不评估你的效率或产出质量。</li>
  </ul>
  <div class="foot">{e(meta.get('scanner'))} · 扫描于 {e(meta.get('scanned_at'))}</div>
</section>'''

    return hero + layers + context_sec + tools_sec + todo + method


CSS = '''
:root{--bg:#0b0e14;--card:#11151d;--card2:#171c26;--line:#232a36;--grid:#2a3240;
--text:#e8ecf3;--sub:#94a3b8;--accent:#5eead4;--code:#0a0d12;--shadow:rgba(0,0,0,.45)}
:root[data-theme=light]{--bg:#f6f7f9;--card:#fff;--card2:#f1f4f8;--line:#e3e8ef;--grid:#dfe5ee;
--text:#0f172a;--sub:#5b6675;--accent:#0d9488;--code:#f3f5f8;--shadow:rgba(15,30,60,.10)}
@media(prefers-color-scheme:light){:root:not([data-theme=dark]){--bg:#f6f7f9;--card:#fff;--card2:#f1f4f8;
--line:#e3e8ef;--grid:#dfe5ee;--text:#0f172a;--sub:#5b6675;--accent:#0d9488;--code:#f3f5f8;--shadow:rgba(15,30,60,.10)}}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font:14px/1.7 -apple-system,"PingFang SC",system-ui,sans-serif;
padding:32px 20px 80px}
.wrap{max-width:1080px;margin:0 auto;display:flex;flex-direction:column;gap:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:24px}
h1{font-size:30px;letter-spacing:-.5px;margin:6px 0 4px}
h2{font-size:17px;margin-bottom:18px;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
h2 .sub{font-size:12px;color:var(--sub);font-weight:400}
h3{font-size:15px;font-weight:700}
.mono{font-family:ui-monospace,SFMono-Regular,monospace;font-size:11.5px;word-break:break-all}
code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:12px;font-family:ui-monospace,monospace}
/* hero */
.hero{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:28px;
display:flex;gap:28px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.hero-l{flex:1;min-width:280px}
.eyebrow{font-size:11px;letter-spacing:2.5px;color:var(--accent);font-weight:700}
.path{font-family:ui-monospace,monospace;font-size:11.5px;color:var(--sub);word-break:break-all}
.verdict{margin:14px 0;font-size:14.5px;line-height:1.8;max-width:640px}
.pills{display:flex;gap:8px;flex-wrap:wrap}
.pill{font-size:11.5px;border:1px solid var(--accent);color:var(--accent);border-radius:999px;padding:3px 11px}
.pill.muted{border-color:var(--line);color:var(--sub)}
.pill.danger{border-color:#ff5f56;color:#ff5f56}
.hero-r{text-align:center}
.ring{width:140px;height:140px}
.ring-n{fill:var(--text);font-size:34px;font-weight:800;text-anchor:middle}
.ring-d{fill:var(--sub);font-size:13px;text-anchor:middle}
.ring-cap{font-size:11.5px;color:var(--sub);margin-top:2px}
/* layers */
.split{display:flex;gap:28px;align-items:flex-start;flex-wrap:wrap}
.radar-wrap{flex:none;text-align:center}
.radar{width:260px;height:260px}
.rl{fill:var(--sub);font-size:11px}
.cap{font-size:11.5px;color:var(--sub)}
.lrows{flex:1;min-width:300px;display:flex;flex-direction:column;gap:14px}
.lhead{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:5px}
.lname{font-weight:700;font-size:14px}
.lnum{font-weight:800;font-size:16px}.lnum i{font-style:normal;font-size:12px;color:var(--sub)}
.bar{height:6px;background:var(--grid);border-radius:99px;overflow:hidden}
.bar i{display:block;height:100%;border-radius:99px}
.lnote{font-size:12.5px;color:var(--sub);margin-top:7px}
.checks{list-style:none;display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}
.checks li{font-size:11px;padding:2px 9px;border-radius:99px;border:1px solid var(--line);color:var(--sub)}
.checks li.ok{border-color:var(--accent);color:var(--accent)}
.checks li.no{border-color:#ff5f5644;color:#ff8a84}
.checks li.no::before{content:"缺 "}
/* metrics */
.grid3{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:20px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}
.gap{margin-top:22px}
.metric{background:var(--card2);border:1px solid var(--line);border-radius:12px;padding:16px}
.mtitle{font-size:12.5px;font-weight:700;margin-bottom:12px}
.mtitle.sm{color:var(--sub);font-weight:600;margin:0 0 8px}
.mnote{font-size:11.5px;color:var(--sub);line-height:1.65;margin-top:10px}
.donut-wrap{position:relative;width:150px;margin:0 auto}
.donut{width:150px;height:150px;display:block}
.donut-c{position:absolute;inset:0;display:grid;place-content:center;text-align:center}
.donut-c b{font-size:22px;display:block;line-height:1.1}
.donut-c span{font-size:10.5px;color:var(--sub)}
.legend{display:flex;flex-wrap:wrap;gap:6px 12px;font-size:11px;color:var(--sub);margin-top:12px;align-items:center}
.legend i{width:9px;height:9px;border-radius:2px;display:inline-block;margin-right:3px}
.gauge-bar{height:8px;background:var(--grid);border-radius:99px;overflow:hidden}
.gauge-bar i{display:block;height:100%;border-radius:99px}
.gauge-meta{display:flex;justify-content:space-between;align-items:baseline;margin-top:7px;font-size:11px;color:var(--sub)}
.gauge-meta b{font-size:17px}
.kv{display:flex;justify-content:space-between;align-items:baseline;font-size:12.5px;color:var(--sub);margin:7px 0}
.kv b{color:var(--text);font-size:15px}
.mini{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}
.mini th{text-align:left;font-size:10.5px;color:var(--sub);font-weight:600;padding:3px 6px;border-bottom:1px solid var(--line)}
.mini td{padding:4px 6px;border-bottom:1px solid var(--line);color:var(--sub);vertical-align:top}
.mini td.num{text-align:right;color:var(--text);white-space:nowrap;font-variant-numeric:tabular-nums}
/* zombie */
.zombie{background:var(--card2);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:6px}
.zhead{display:flex;gap:34px;flex-wrap:wrap;margin-bottom:16px}
.zhead div{display:flex;flex-direction:column}
.big{font-size:30px;font-weight:800;line-height:1.1;font-variant-numeric:tabular-nums}
.zhead span{font-size:11.5px;color:var(--sub)}
.dotmatrix{display:flex;flex-wrap:wrap;gap:4px}
.dm{width:9px;height:9px;border-radius:2px;background:var(--grid);display:block}
.dm.on{background:var(--accent);box-shadow:0 0 6px var(--accent)}
.dm-more{font-size:11px;color:var(--sub);display:block;margin-top:8px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px}
.chip{font-size:11.5px;background:var(--card2);border:1px solid var(--line);border-radius:99px;padding:3px 11px;color:var(--text)}
.chip.muted{color:var(--sub)}
/* findings */
.findings{display:flex;flex-direction:column;gap:12px}
.finding{background:var(--card2);border:1px solid var(--line);border-left:3px solid var(--sev);
border-radius:10px;padding:15px 17px}
.fhead{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.sev{font-size:10.5px;font-weight:800;color:var(--sev);border:1px solid var(--sev);border-radius:4px;padding:1px 7px}
.flayer{font-size:10.5px;color:var(--sub);margin-left:auto}
.fact{font-size:12.5px;color:var(--sub);line-height:1.7}
.why{font-size:13px;margin-top:8px;line-height:1.75}
.frow{margin-top:12px;display:flex;gap:10px;align-items:center}
.copy{background:var(--accent);color:var(--bg);border:none;border-radius:8px;padding:7px 15px;
font-size:12.5px;font-weight:700;cursor:pointer;font-family:inherit}
.copy:hover{filter:brightness(1.08)}
.copy.done{background:var(--grid);color:var(--text)}
.nofix{font-size:11.5px;color:var(--sub)}
.fix{display:none}
/* method */
.method ul{list-style:none;display:flex;flex-direction:column;gap:9px}
.method li{font-size:12.5px;color:var(--sub);line-height:1.75;padding-left:16px;position:relative}
.method li::before{content:"";position:absolute;left:0;top:9px;width:5px;height:5px;border-radius:99px;background:var(--accent)}
.foot{margin-top:18px;padding-top:14px;border-top:1px solid var(--line);font-size:11px;color:var(--sub);
font-family:ui-monospace,monospace}
.theme{position:fixed;top:16px;right:18px;background:var(--card);border:1px solid var(--line);
color:var(--sub);border-radius:99px;padding:6px 14px;font-size:12px;cursor:pointer;font-family:inherit;z-index:9}
@media print{.theme,.copy{display:none}body{padding:0}.card,.hero{break-inside:avoid}}
'''

JS = '''
document.querySelector('.theme').onclick=()=>{
  const r=document.documentElement;
  const cur=r.dataset.theme||(matchMedia('(prefers-color-scheme:light)').matches?'light':'dark');
  r.dataset.theme=cur==='light'?'dark':'light';
};
// 复制修复口令：file:// 下 clipboard API 常常不可用，留 textarea 兜底
async function cp(text){
  try{ if(navigator.clipboard&&isSecureContext){ await navigator.clipboard.writeText(text); return true; } }catch(e){}
  try{
    const t=document.createElement('textarea');
    t.value=text; t.style.position='fixed'; t.style.opacity='0';
    document.body.appendChild(t); t.select();
    const ok=document.execCommand('copy'); document.body.removeChild(t); return ok;
  }catch(e){ return false; }
}
document.querySelectorAll('.copy').forEach(b=>{
  b.onclick=async()=>{
    const pre=document.getElementById('fix'+b.dataset.i);
    const ok=await cp(pre.textContent);
    const old=b.textContent;
    b.textContent=ok?'已复制，去粘给 Claude / Codex':'复制失败，请手动全选下方口令';
    b.classList.add('done');
    if(!ok){ pre.hidden=false; pre.style.display='block'; }
    setTimeout(()=>{ b.textContent=old; b.classList.remove('done'); },2600);
  };
});
'''


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if not args:
        print('用法: render.py findings.json [-a analysis.json] -o report.html'); sys.exit(1)
    d = json.loads(Path(args[0]).read_text(encoding='utf-8'))
    a = {}
    if '-a' in sys.argv:
        ap = Path(sys.argv[sys.argv.index('-a') + 1])
        if ap.exists():
            a = json.loads(ap.read_text(encoding='utf-8'))
    out = sys.argv[sys.argv.index('-o') + 1] if '-o' in sys.argv else 'harness-report.html'

    body = build(d, a)
    doc = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(d['meta']['name'])} · Harness 体检报告</title>
<style>{CSS}</style></head>
<body><button class="theme">切换深浅</button>
<div class="wrap">{body}</div>
<script>{JS}</script></body></html>'''
    Path(out).write_text(doc, encoding='utf-8')
    print(f'报告已生成 → {out}  ({len(doc)/1024:.0f} KB)')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
view-your-harness 索引器：把一个目录清点成 index.json。

只做事实采集，不做判断。产出两份清单：
  1. 文件清单 —— 这个目录里有哪些东西，多大，什么时候动过
  2. Skill 清单 —— 有哪些 Skill 可用，各自被真实调用过多少次

用法：python3 index.py <目录> [-o index.json] [--max-files N]
"""
import os, re, sys, json, time, argparse
from pathlib import Path
from collections import Counter

HOME = Path.home()

SKIP_DIRS = {'.git', 'node_modules', '.next', 'dist', 'build', '.venv', 'venv',
             '__pycache__', '.cache', '.turbo', 'vendor', 'Pods', 'target',
             'out', 'coverage', '.svelte-kit', '.parcel-cache', '.gradle',
             '.obsidian', '.trash', '.DS_Store'}

KIND_BY_EXT = {
    'doc':   {'.md', '.markdown', '.txt', '.rst', '.org', '.pdf', '.docx', '.doc'},
    'code':  {'.py', '.js', '.ts', '.tsx', '.jsx', '.sh', '.zsh', '.rb', '.go',
              '.rs', '.java', '.c', '.h', '.cpp', '.swift', '.lua', '.php', '.sql'},
    'data':  {'.json', '.jsonl', '.csv', '.tsv', '.xlsx', '.xml', '.parquet', '.db'},
    'image': {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.heic', '.avif'},
    'media': {'.mp4', '.mov', '.mp3', '.wav', '.m4a', '.webm'},
    'conf':  {'.yml', '.yaml', '.toml', '.ini', '.cfg', '.conf', '.env'},
}
EXT2KIND = {e: k for k, exts in KIND_BY_EXT.items() for e in exts}
TEXTY = KIND_BY_EXT['doc'] | KIND_BY_EXT['code'] | KIND_BY_EXT['data'] | KIND_BY_EXT['conf']


def read(p, limit=200_000):
    try:
        return Path(p).read_text('utf-8', errors='ignore')[:limit]
    except Exception:
        return ''


def parse_frontmatter(txt):
    """只解析顶层 key: value，够用即可。值里的引号剥掉。"""
    fm = {}
    m = re.match(r'^---\s*\n([\s\S]*?)\n---', txt)
    if not m:
        return fm
    for line in m.group(1).splitlines():
        kv = re.match(r'^([A-Za-z_][\w-]*)\s*:\s*(.*)$', line)
        if kv:
            v = kv.group(2).strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
                v = v[1:-1]
            fm[kv.group(1)] = v
    return fm


def first_heading(txt):
    """拿一个能当标题用的东西：frontmatter title > 第一个 # 标题 > 第一行非空文本。"""
    fm = parse_frontmatter(txt)
    if fm.get('title'):
        return fm['title'][:120]
    body = re.sub(r'^---\s*\n[\s\S]*?\n---\s*\n', '', txt)
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith('#'):
            return s.lstrip('#').strip()[:120]
        return s[:120]
    return ''


# ---------- 文件清单 ----------
def scan_files(root, max_files=20000, max_depth=12):
    root = Path(root).resolve()
    items, dirstat = [], {}
    truncated = False

    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        rel = d.relative_to(root)
        if len(rel.parts) >= max_depth:
            dirnames[:] = []
        dirnames[:] = sorted(x for x in dirnames
                             if x not in SKIP_DIRS and not x.startswith('.git'))
        for fn in sorted(filenames):
            if fn.startswith('.') and fn not in ('.gitignore', '.env.example'):
                continue
            if len(items) >= max_files:
                truncated = True
                break
            fp = d / fn
            try:
                st = fp.stat()
            except Exception:
                continue
            ext = fp.suffix.lower()
            relp = str(fp.relative_to(root))
            it = {
                'path': relp,
                'name': fn,
                'dir': str(rel) if str(rel) != '.' else '',
                'ext': ext,
                'kind': EXT2KIND.get(ext, 'other'),
                'bytes': st.st_size,
                'mtime': int(st.st_mtime),
                'title': '',
                'words': 0,
            }
            # 文本文件多读一点元信息，这是「有哪些文件」里最有用的部分
            if ext in KIND_BY_EXT['doc'] and st.st_size < 400_000:
                txt = read(fp)
                it['title'] = first_heading(txt)
                it['words'] = len(txt)
            items.append(it)
        if truncated:
            break

    # 目录聚合：每个目录直接持有多少文件、多大
    for it in items:
        key = it['dir']
        s = dirstat.setdefault(key, {'files': 0, 'bytes': 0, 'kinds': Counter()})
        s['files'] += 1
        s['bytes'] += it['bytes']
        s['kinds'][it['kind']] += 1

    dirs = []
    for key, s in sorted(dirstat.items()):
        dirs.append({
            'path': key,
            'depth': 0 if key == '' else len(Path(key).parts),
            'files': s['files'],
            'bytes': s['bytes'],
            'kinds': dict(s['kinds']),
        })

    kinds = Counter(i['kind'] for i in items)
    return {
        'total': len(items),
        'bytes': sum(i['bytes'] for i in items),
        'truncated': truncated,
        'kinds': dict(kinds),
        'dirs': dirs,
        'items': items,
    }


# ---------- Skill 清单 ----------
def skill_sources(root):
    root = Path(root)
    out = []
    seen = set()
    cands = [
        (root / '.claude/skills', 'project'),
        (root / '.agents/skills', 'project'),
        (HOME / '.claude/skills', 'global'),
        (HOME / '.codex/skills', 'global'),
    ]
    for p, scope in cands:
        if not p.exists() or not p.is_dir():
            continue
        try:
            real = str(p.resolve())
        except Exception:
            real = str(p)
        if real in seen:      # 项目目录本身就是 ~ 时会撞上，去重
            continue
        seen.add(real)
        out.append((p, scope))
    # 插件市场里的 Skill
    mkt = HOME / '.claude/plugins/marketplaces'
    if mkt.exists():
        for plug in sorted(mkt.rglob('skills')):
            if plug.is_dir() and str(plug.resolve()) not in seen:
                seen.add(str(plug.resolve()))
                out.append((plug, 'plugin'))
    return out


def scan_skills(root):
    items, sources, strays = [], [], []
    for p, scope in skill_sources(root):
        n = 0
        for child in sorted(p.iterdir()):
            if child.name.startswith('.'):
                continue
            if not child.is_dir():
                # skills/ 根下的裸文件不是 Skill，单独记一笔
                if child.suffix.lower() in ('.md', '.txt'):
                    strays.append({'path': str(child), 'name': child.name,
                                   'bytes': child.stat().st_size})
                continue
            sf = None
            for cand in ('SKILL.md', 'skill.md', 'Skill.md'):
                if (child / cand).exists():
                    sf = child / cand
                    break
            rec = {
                'name': child.name,
                'path': str(child),
                'scope': scope,
                'source': str(p),
                'has_skill_md': bool(sf),
                'symlink': child.is_symlink(),
                'fm_name': '', 'desc': '', 'desc_len': 0,
                'mtime': 0, 'files': 0, 'bytes': 0, 'calls': 0,
            }
            if sf:
                txt = read(sf, 60_000)
                fm = parse_frontmatter(txt)
                rec['fm_name'] = fm.get('name', '')
                rec['desc'] = fm.get('description', '')
                rec['desc_len'] = len(rec['desc'])
                try:
                    rec['mtime'] = int(sf.stat().st_mtime)
                except Exception:
                    pass
            # Skill 的体量：有几个文件、多大。带 scripts/references 的是「重」Skill
            try:
                nf, nb = 0, 0
                for sub, dn, fns in os.walk(child):
                    dn[:] = [x for x in dn if x not in SKIP_DIRS]
                    for f in fns:
                        try:
                            nb += (Path(sub) / f).stat().st_size
                            nf += 1
                        except Exception:
                            pass
                rec['files'], rec['bytes'] = nf, nb
            except Exception:
                pass
            items.append(rec)
            n += 1
        sources.append({'path': str(p), 'scope': scope, 'count': n})

    # 同名 Skill 会在多处出现（全局装一份、插件市场又带一份）。
    # 按 project > global > plugin 定优先级留一条，其余折进 dupes，
    # 否则「用过几个」会被重复计数，出现「12 个用过但只有 10 次调用」这种自相矛盾。
    PRI = {'project': 0, 'global': 1, 'plugin': 2}
    best = {}
    for r in items:
        cur = best.get(r['name'])
        if cur is None or (PRI.get(r['scope'], 9), -r['mtime']) < (PRI.get(cur['scope'], 9), -cur['mtime']):
            if cur is not None:
                r.setdefault('dupes', []).extend(cur.get('dupes', []) + [cur['path']])
            best[r['name']] = r
        else:
            cur.setdefault('dupes', []).append(r['path'])
    uniq = sorted(best.values(), key=lambda x: x['name'])
    for r in uniq:
        r['dupes'] = r.get('dupes', [])
    return uniq, sources, strays


def scan_usage(skill_names, max_files=1200):
    """
    真实调用次数 = 会话日志里 tool_use(name="Skill") 的 input.skill。

    不能按关键词 grep：每轮对话的系统提示词都会带上全部可用 Skill 的清单，
    grep 会把 155 个 Skill 全部算成「用过」，差两个数量级。
    """
    counts = Counter()
    read_files, invocations = 0, 0
    dirs = [HOME / '.claude/projects', HOME / '.codex/sessions']
    for d in dirs:
        if not d.exists():
            continue
        for fp in sorted(d.rglob('*.jsonl'))[:max_files]:
            read_files += 1
            try:
                fh = open(fp, encoding='utf-8', errors='ignore')
            except Exception:
                continue
            with fh:
                for line in fh:
                    if '"Skill"' not in line:
                        continue
                    try:
                        o = json.loads(line)
                    except Exception:
                        continue
                    msg = o.get('message') or o
                    content = msg.get('content') if isinstance(msg, dict) else None
                    if not isinstance(content, list):
                        continue
                    for b in content:
                        if not isinstance(b, dict) or b.get('type') != 'tool_use':
                            continue
                        if b.get('name') != 'Skill':
                            continue
                        nm = ((b.get('input') or {}).get('skill') or '').strip()
                        if not nm:
                            continue
                        counts[nm.split(':')[-1]] += 1
                        invocations += 1
    known = set(skill_names)
    return {
        'evidence': 'ok' if read_files else 'none',
        'method': 'tool_use(name=Skill).input.skill',
        'session_files_read': read_files,
        'invocations': invocations,
        'counts': {k: v for k, v in counts.items() if k in known},
        'unknown_invoked': sorted(
            ((k, v) for k, v in counts.items() if k not in known),
            key=lambda x: -x[1])[:10],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root')
    ap.add_argument('-o', '--out', default='')
    ap.add_argument('--max-files', type=int, default=20000)
    ap.add_argument('--no-usage', action='store_true',
                    help='跳过会话日志统计（大日志目录下能快很多）')
    a = ap.parse_args()

    root = Path(a.root).expanduser().resolve()
    if not root.is_dir():
        sys.exit(f'不是一个目录：{root}')

    t0 = time.time()
    files = scan_files(root, a.max_files)
    skills, sources, strays = scan_skills(root)
    if a.no_usage:
        usage = {'evidence': 'skipped', 'counts': {}, 'invocations': 0,
                 'session_files_read': 0, 'unknown_invoked': [],
                 'method': 'tool_use(name=Skill).input.skill'}
    else:
        usage = scan_usage([s['name'] for s in skills])
    for s in skills:
        s['calls'] = usage['counts'].get(s['name'], 0)

    data = {
        'root': str(root),
        'generated_at': int(time.time()),
        'elapsed_sec': round(time.time() - t0, 1),
        'files': files,
        'skills': {
            'total': len(skills),
            'sources': sources,
            'strays': strays,
            'usage': usage,
            'items': sorted(skills, key=lambda x: (-x['calls'], x['name'])),
        },
    }

    out = a.out or str(root / 'harness-index.json')
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    print(f'索引完成 {data["elapsed_sec"]}s → {out}')
    print(f'  文件 {files["total"]}{"（已截断）" if files["truncated"] else ""}'
          f'  目录 {len(files["dirs"])}  体量 {files["bytes"]/1e6:.1f} MB')
    ndup = sum(len(s['dupes']) for s in skills)
    print(f'  Skill {len(skills)} 个（去重后），来自 {len(sources)} 处'
          f'{"，" + str(ndup) + " 个重名副本已折叠" if ndup else ""}'
          f'{"，另有 " + str(len(strays)) + " 个裸文件" if strays else ""}')
    if usage['evidence'] == 'ok':
        used = sum(1 for s in skills if s['calls'] > 0)
        print(f'  调用统计：读 {usage["session_files_read"]} 个会话日志，'
              f'{usage["invocations"]} 次调用，{used} 个 Skill 被真正用过，'
              f'{len(skills) - used} 个从未调用')
    elif usage['evidence'] == 'none':
        print('  调用统计：没找到会话日志，全部 Skill 的调用次数记为未知')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
better-your-harness 扫描器：只做确定性事实采集，不做任何判断。

设计原则：
1. 凡是能实测的一律实测（仓库可见性走 gh，不靠猜）
2. 密钥只报「路径 + 变量名 + 命中模式」，绝不输出值
3. 任何一项失败都不影响整体，坏掉的项标 error 继续跑
4. 候选发现（findings）带固定 id，AI 只能给已有 id 填判断，不能凭空发明

用法：python3 scan.py <项目根目录> [-o findings.json]
"""
import os, sys, re, json, subprocess, time, fnmatch
from pathlib import Path

HOME = Path.home()

# ---------- 工具 ----------
def sh(cmd, cwd=None, timeout=30):
    try:
        r = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str),
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ''
    except Exception:
        return ''

def read(p, limit=400_000):
    try:
        return Path(p).read_text('utf-8', errors='ignore')[:limit]
    except Exception:
        return ''

def approx_tokens(chars):
    # 中文约 1 字 1 token，英文约 4 字符 1 token。混排按 1.8 折中。
    return int(chars / 1.8)

SKIP_DIRS = {'.git', 'node_modules', '.next', 'dist', 'build', '.venv', 'venv',
             '__pycache__', '.cache', '.turbo', 'vendor', '.DS_Store', 'Pods',
             'target', 'out', 'coverage', '.svelte-kit', '.parcel-cache', '.gradle'}

def walk(root, max_depth=12):
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        if len(rel.parts) >= max_depth:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.git')]
        yield Path(dirpath), dirnames, filenames


# ---------- A 安全与卫生 ----------
GITIGNORE_WANT = ['node_modules', '.env', 'dist', '.DS_Store', '*.log', 'build', '.next']

SECRET_PATTERNS = [
    ('OpenAI/Anthropic 风格 key', re.compile(r'\b(sk-[A-Za-z0-9_\-]{16,})')),
    ('GitHub token',              re.compile(r'\b(gh[pousr]_[A-Za-z0-9]{16,})')),
    ('AWS Access Key',            re.compile(r'\b(AKIA[0-9A-Z]{16})\b')),
    ('Slack token',               re.compile(r'\b(xox[baprs]-[A-Za-z0-9\-]{10,})')),
    ('Google API key',            re.compile(r'\b(AIza[0-9A-Za-z_\-]{35})\b')),
    ('HuggingFace token',         re.compile(r'\b(hf_[A-Za-z0-9]{20,})')),
    ('私钥文件头',                 re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
]
SECRET_FILE_GLOBS = ['.env', '.env.*', '*.env', '*.key', '*.pem', '*.p12',
                     'credentials*.json', 'service-account*.json', '*secret*.json']
# 变量名里带这些词，且右边有非空值，就算一条明文凭证
SECRET_KEY_HINT = re.compile(
    r'^\s*(?:export\s+)?([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|APP_ID|ACCESS)[A-Z0-9_]*)\s*[=:]\s*(.+)$')

def scan_security(root):
    out = {}
    root = Path(root)

    # .gitignore
    gi = root / '.gitignore'
    gi_text = read(gi) if gi.exists() else ''
    out['gitignore'] = {
        'exists': gi.exists(),
        'lines': len([l for l in gi_text.splitlines() if l.strip() and not l.startswith('#')]),
        # 白名单写法（第一条规则是 *，再用 ! 放行）默认就挡住了一切，不用逐条列噪音
        'whitelist': bool(re.search(r'^\*\s*$', gi_text, re.M)) and '!' in gi_text,
        'missing_patterns': [] if (re.search(r'^\*\s*$', gi_text, re.M) and '!' in gi_text)
                            else [p for p in GITIGNORE_WANT if p not in gi_text],
        'sub_gitignores': len(list(root.glob('*/.gitignore'))) + len(list(root.glob('*/*/.gitignore'))),
    }

    # git 跟踪噪音
    tracked = sh(['git', 'ls-files'], cwd=root)
    files = [f for f in tracked.splitlines() if f]
    noise_pat = ('node_modules/', '.next/', 'dist/', 'build/', '.venv/', '__pycache__/')
    noise = [f for f in files if any(n in f for n in noise_pat)]
    out['tracked'] = {
        'total': len(files),
        'noise': len(noise),
        'source': len(files) - len(noise),
        'noise_ratio': round(len(noise) / len(files), 4) if files else 0,
        'top_noise': _top_prefix(noise),
    }

    # 远程和可见性：实测，不推断
    remote = sh(['git', 'remote', 'get-url', 'origin'], cwd=root)
    vis = sh(['gh', 'repo', 'view', '--json', 'visibility,nameWithOwner'], cwd=root)
    repo = {}
    if vis:
        try:
            repo = json.loads(vis)
        except Exception:
            repo = {}
    out['repo'] = {
        'remote': remote,
        'name': repo.get('nameWithOwner', ''),
        'visibility': repo.get('visibility', 'UNKNOWN'),
        'branch': sh(['git', 'branch', '--show-current'], cwd=root),
    }

    # 凭证扫描
    tracked_set = set(files)
    hits, scanned = [], 0
    for dirpath, dirnames, filenames in walk(root, max_depth=8):
        for fn in filenames:
            p = dirpath / fn
            rel = str(p.relative_to(root))
            is_secret_file = any(fnmatch.fnmatch(fn, g) for g in SECRET_FILE_GLOBS)
            # 只深读疑似凭证文件和小体积配置，避免把整个仓库读一遍
            if not is_secret_file and p.suffix not in ('.json', '.yml', '.yaml', '.sh', '.toml', '.ini'):
                continue
            try:
                if p.stat().st_size > 200_000:
                    continue
            except Exception:
                continue
            txt = read(p, 200_000)
            if not txt:
                continue
            scanned += 1
            found = []
            for line in txt.splitlines():
                m = SECRET_KEY_HINT.match(line)
                if m and m.group(2).strip().strip('"\'') not in ('', '""', "''", 'null'):
                    val = m.group(2).strip().strip('"\'')
                    # 明显是占位符的跳过
                    if re.search(r'(your|xxx|placeholder|change ?me|<.*>|\.\.\.)', val, re.I):
                        continue
                    found.append({'kind': '明文变量', 'name': m.group(1)})
                for label, pat in SECRET_PATTERNS:
                    if pat.search(line):
                        found.append({'kind': label, 'name': ''})
            if found:
                # 去重，只留类型和变量名，绝不带值
                uniq, seen = [], set()
                for f in found:
                    k = (f['kind'], f['name'])
                    if k not in seen:
                        seen.add(k); uniq.append(f)
                hits.append({
                    'path': rel,
                    'tracked': rel in tracked_set,
                    'ignored': bool(sh(['git', 'check-ignore', rel], cwd=root)),
                    'hits': uniq[:12],
                })
    out['secrets'] = {
        'files_scanned': scanned,
        'files_with_hits': len(hits),
        'tracked_hits': sum(1 for h in hits if h['tracked']),
        'unprotected': sum(1 for h in hits if not h['tracked'] and not h['ignored']),
        'detail': hits[:40],
    }

    # Agent 权限配置
    perms = []
    for rel in ['.claude/settings.json', '.claude/settings.local.json',
                '.claude/claudian-settings.json', '.vscode/settings.json',
                '.codex/config.toml', 'AGENTS.md']:
        p = root / rel
        if not p.exists():
            continue
        txt = read(p, 100_000)
        risky = []
        for kw, why in [('yolo', '绕过所有命令确认'),
                        ('bypassPermissions', '绕过权限检查'),
                        ('dangerouslySkip', '跳过安全检查'),
                        ('"*"', '通配全部权限')]:
            if kw in txt:
                risky.append({'keyword': kw, 'why': why})
        perms.append({'path': rel, 'risky': risky, 'bytes': p.stat().st_size})
    out['permissions'] = {
        'files': perms,
        'risky_count': sum(len(p['risky']) for p in perms),
    }

    # hooks 守门
    hooks = 0
    for rel in ['.claude/settings.json', '.claude/settings.local.json']:
        t = read(root / rel)
        if '"hooks"' in t:
            hooks += t.count('"matcher"') or 1
    out['hooks'] = {'count': hooks}
    return out

def _top_prefix(paths, n=5):
    from collections import Counter
    c = Counter(p.split('/')[0] if '/' in p else p for p in paths)
    return [{'prefix': k, 'count': v} for k, v in c.most_common(n)]


# ---------- B 上下文质量 ----------
ENTRY_FILES = ['CLAUDE.md', 'AGENTS.md', 'AGENT.md', '.cursorrules', 'README.md', 'GEMINI.md']

def scan_context(root):
    root = Path(root)
    out = {}

    entries = []
    for name in ENTRY_FILES:
        p = root / name
        if not p.exists():
            continue
        txt = read(p)
        # 只有一两行、用 @AGENTS.md 之类把内容引到别处的，是指针文件，不是入口正本
        pointer = bool(re.search(r'^@\S+\.md\s*$', txt, re.M)) and len(txt) < 600
        entries.append({
            'name': name,
            'pointer': pointer,
            'chars': len(txt),
            'tokens': approx_tokens(len(txt)),
            # 目录地图三种写法都认：代码块、树形符号、表格里一行一个带反引号的目录
            'has_dir_map': bool(re.search(r'```[\s\S]{80,}?```', txt)) or txt.count('├──') > 2
                           or len(re.findall(r'^\|\s*`[^`|]+`\s*\|', txt, re.M)) >= 4,
            'has_table': txt.count('|---') > 0 or txt.count('| ---') > 0,
            'has_rules': bool(re.search(r'(规则|rules?|必须|禁止|must|never|always)', txt, re.I)),
            'headings': len(re.findall(r'^#{1,3} ', txt, re.M)),
        })
    out['entries'] = entries

    # 2.0：状态页、工具清单、上手自测。入口只放指针，这三样各管一件事
    def _find(names):
        for n in names:
            if (root / n).exists():
                return n
        return ''
    now_f, tools_f = _find(['NOW.md', 'now.md']), _find(['TOOLS.md', 'tools.md'])
    now_age = -1
    if now_f:
        now_age = round((time.time() - (root / now_f).stat().st_mtime) / 86400)
    all_entry = '\n'.join(read(root / e['name']) for e in entries if e['name'] in ('CLAUDE.md', 'AGENTS.md'))
    quiz = re.search(r'^#{1,3} .*(自测|self[- ]?test|quiz|验收)', all_entry, re.I | re.M)
    quiz_n = len(re.findall(r'^\s*\d+[.、]\s*.+[?？]\s*$', all_entry[quiz.start():], re.M)) if quiz else 0
    out['harness2'] = {
        'now_file': now_f, 'now_days_since_update': now_age,
        'tools_file': tools_f,
        'has_quiz': bool(quiz), 'quiz_questions': quiz_n,
        'agents_md_is_source': any(e['name'] == 'AGENTS.md' and not e['pointer'] for e in entries),
        'entry_sources': [e['name'] for e in entries
                          if e['name'] in ('CLAUDE.md', 'AGENTS.md', 'GEMINI.md') and not e['pointer']],
    }

    # 顶层目录 + README 覆盖率
    top = [d for d in sorted(root.iterdir())
           if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith('.')]
    with_readme = [d for d in top if (d / 'README.md').exists() or (d / 'readme.md').exists()]
    out['top_dirs'] = {
        'total': len(top),
        'with_readme': len(with_readme),
        'coverage': round(len(with_readme) / len(top), 3) if top else 0,
        'missing': [d.name for d in top if d not in with_readme][:30],
        'names': [d.name for d in top],
    }

    # 冷启动成本 = 入口文件 + 所有 README
    cold = sum(e['chars'] for e in entries)
    readme_chars = 0
    for d in top:
        for r in ('README.md', 'readme.md'):
            if (d / r).exists():
                readme_chars += len(read(d / r))
    out['cold_start'] = {
        'entry_chars': cold,
        'readme_chars': readme_chars,
        'total_chars': cold + readme_chars,
        'tokens': approx_tokens(cold + readme_chars),
    }

    # 层级结构
    depths, fanout, big, total_files = [], [], [], 0
    for dirpath, dirnames, filenames in walk(root):
        rel = dirpath.relative_to(root)
        d = len(rel.parts)
        n = len(dirnames) + len(filenames)
        if n > 40:
            fanout.append({'dir': str(rel) or '.', 'children': n})
        for fn in filenames:
            if fn.startswith('.'):
                continue
            total_files += 1
            depths.append(d)
            p = dirpath / fn
            try:
                sz = p.stat().st_size
            except Exception:
                continue
            if p.suffix.lower() in ('.md', '.txt', '.jsonl', '.json') and sz > 50_000:
                big.append({'path': str(p.relative_to(root)), 'kb': round(sz / 1024)})
    fanout.sort(key=lambda x: -x['children'])
    big.sort(key=lambda x: -x['kb'])
    out['structure'] = {
        'files': total_files,
        'max_depth': max(depths) if depths else 0,
        'avg_depth': round(sum(depths) / len(depths), 2) if depths else 0,
        'wide_dirs': fanout[:8],
        'big_files': big[:12],
    }

    # 索引健康度：形如 xxx_index.jsonl，看 file 字段指向的文件在不在
    idx = []
    for p in root.rglob('*index*.jsonl'):
        if any(s in str(p) for s in SKIP_DIRS):
            continue
        entries_n, dangling = 0, []
        for line in read(p).splitlines():
            line = line.strip()
            if not line:
                continue
            entries_n += 1
            try:
                obj = json.loads(line)
            except Exception:
                continue
            f = obj.get('file') or obj.get('path')
            if f and not (p.parent / f).exists():
                dangling.append(f)
        idx.append({
            'path': str(p.relative_to(root)),
            'entries': entries_n,
            'dangling': len(dangling),
            'sample_dangling': dangling[:5],
        })
    out['indexes'] = idx[:12]
    return out


# ---------- C 工具（Skill / MCP / Hooks / Agents）----------
SKILL_DIRS = ['.claude/skills', '.agents/skills', '.codex/skills',
              str(HOME / '.claude/skills'), str(HOME / '.codex/skills')]

def scan_tools(root):
    root = Path(root)
    out = {}
    locs, seen_real = [], {}
    all_skills = []
    for sd in SKILL_DIRS:
        p = Path(sd) if os.path.isabs(sd) else root / sd
        if not p.exists():
            continue
        try:
            real = str(p.resolve())
        except Exception:
            real = str(p)
        dup_of = seen_real.get(real)
        seen_real.setdefault(real, str(p))
        items, symlinks = [], 0
        for child in sorted(p.iterdir()):
            if child.name.startswith('.'):
                continue
            if child.is_symlink():
                symlinks += 1
            if not child.is_dir():
                continue
            sf = None
            for cand in ('SKILL.md', 'skill.md', 'Skill.md'):
                if (child / cand).exists():
                    sf = child / cand
                    break
            if not sf:
                items.append({'name': child.name, 'has_skill_md': False,
                              'name_fm': '', 'desc_len': 0, 'symlink': child.is_symlink(),
                              'mtime': 0})
                continue
            txt = read(sf, 60_000)
            fm = {}
            m = re.match(r'^---\s*\n([\s\S]*?)\n---', txt)
            if m:
                for line in m.group(1).splitlines():
                    kv = re.match(r'^([A-Za-z_][\w-]*)\s*:\s*(.*)$', line)
                    if kv:
                        fm[kv.group(1)] = kv.group(2).strip()
            try:
                mt = sf.stat().st_mtime
            except Exception:
                mt = 0
            items.append({
                'name': child.name,
                'has_skill_md': True,
                'name_fm': fm.get('name', ''),
                'desc_len': len(fm.get('description', '')),
                'symlink': child.is_symlink(),
                'mtime': mt,
            })
        locs.append({
            'path': str(p), 'real': real, 'duplicate_of': dup_of,
            'entries': len(items), 'symlinks': symlinks,
            'with_skill_md': sum(1 for i in items if i['has_skill_md']),
        })
        if not dup_of:
            all_skills.extend(items)

    now = time.time()
    from collections import Counter
    # 多个位置常常互为软链或副本，按唯一名字去重才是真实装机量
    by_name = {}
    for s in all_skills:
        prev = by_name.get(s['name'])
        if prev is None or (s['has_skill_md'] and not prev['has_skill_md']):
            by_name[s['name']] = s
    uniq_skills = list(by_name.values())
    namec = Counter(s['name'] for s in all_skills)
    out['skills'] = {
        'locations': locs,
        'total': len(uniq_skills),
        'entries_across_locations': len(all_skills),
        'no_skill_md': [s['name'] for s in uniq_skills if not s['has_skill_md']][:30],
        'no_description': [s['name'] for s in uniq_skills if s['has_skill_md'] and s['desc_len'] == 0][:40],
        'thin_description': [s['name'] for s in uniq_skills
                             if s['has_skill_md'] and 0 < s['desc_len'] < 30][:40],
        'no_name_field': [s['name'] for s in uniq_skills if s['has_skill_md'] and not s['name_fm']][:40],
        'mirrored': [n for n, c in namec.items() if c > 1][:30],
        'symlinked': sum(1 for s in uniq_skills if s['symlink']),
        'fresh_30d': sum(1 for s in uniq_skills if s['mtime'] and now - s['mtime'] < 30 * 86400),
        'stale_180d': sum(1 for s in uniq_skills if s['mtime'] and now - s['mtime'] > 180 * 86400),
        'names': sorted(by_name.keys()),
    }

    # MCP
    servers = {}
    for rel in ['.mcp.json', '.claude/mcp.json', str(HOME / '.claude.json')]:
        p = Path(rel) if os.path.isabs(rel) else root / rel
        t = read(p, 2_000_000) if p.exists() else ''
        if not t:
            continue
        try:
            obj = json.loads(t)
        except Exception:
            continue
        ms = obj.get('mcpServers') or {}
        if isinstance(obj.get('projects'), dict):
            for _, v in obj['projects'].items():
                if isinstance(v, dict):
                    ms.update(v.get('mcpServers') or {})
        for k, v in (ms or {}).items():
            servers.setdefault(k, {'name': k, 'from': str(p),
                                   'transport': 'http' if (isinstance(v, dict) and v.get('url')) else 'stdio'})
    out['mcp'] = {'count': len(servers), 'servers': list(servers.values())[:40]}

    # 命令 / 子 Agent / Hooks
    out['commands'] = {'count': len(list((root / '.claude/commands').glob('*.md')))
                       if (root / '.claude/commands').exists() else 0}
    agents_dir = root / '.claude/agents'
    out['agents'] = {'count': len(list(agents_dir.glob('*.md'))) if agents_dir.exists() else 0,
                     'names': [p.stem for p in agents_dir.glob('*.md')][:20] if agents_dir.exists() else []}
    return out


# ---------- D 记忆 ----------
def scan_memory(root):
    root = Path(root)
    out = {'stores': []}
    enc = str(root).replace('/', '-')
    # 固定位置 + 模糊匹配。记忆目录常带序号前缀（40-memory）或中文名（记忆），
    # 只认死名字会漏掉一整层。
    cands = [root / 'cortex', root / '.claude/memory', root / 'memory',
             HOME / '.claude/projects' / enc / 'memory']
    try:
        for d in root.iterdir():
            if not d.is_dir() or d.name.startswith('.'):
                continue
            n = d.name.lower()
            if ('memory' in n or 'cortex' in n or '记忆' in d.name) and d not in cands:
                cands.append(d)
    except Exception:
        pass
    seen_c = set()
    cands = [c for c in cands if not (str(c) in seen_c or seen_c.add(str(c)))]
    for c in cands:
        if not c.exists() or not c.is_dir():
            continue
        # README / INDEX / MEMORY 是元文件，不是记忆内容，不参与索引完整性判定
        META = {'MEMORY.md', 'INDEX.md', 'README.md', 'readme.md'}
        files = [p for p in c.rglob('*.md') if p.name not in META]
        index = c / 'MEMORY.md'
        if not index.exists():
            index = c / 'INDEX.md'
        idx_txt = read(index) if index.exists() else ''
        linked = set(re.findall(r'\(([^)]+\.md)\)', idx_txt)) | set(re.findall(r'\[\[([^\]]+)\]\]', idx_txt))
        names = {p.name for p in files} | {p.stem for p in files}
        dangling = [l for l in linked if l not in names and Path(l).name not in names]
        # 索引里常写相对路径（shared/xxx.md），按文件名比对，否则子目录里的全被误判成未入索引
        linked_names = linked | {Path(x).name for x in linked}
        unindexed = [p.name for p in files if p.name not in linked_names and p.stem not in linked_names]
        out['stores'].append({
            'path': str(c),
            'files': len(files),
            'has_index': index.exists(),
            'index_name': index.name if index.exists() else '',
            'index_entries': len(linked),
            'dangling': dangling[:10],
            'unindexed': unindexed[:10],
        })
    # jsonl 日志
    logs = []
    for p in list(root.rglob('*log*.jsonl'))[:20] + list(root.rglob('*tracker*.jsonl'))[:10]:
        if any(s in str(p) for s in SKIP_DIRS):
            continue
        try:
            n = sum(1 for _ in open(p, encoding='utf-8', errors='ignore'))
            age = round((time.time() - p.stat().st_mtime) / 86400, 1)
        except Exception:
            continue
        logs.append({'path': str(p.relative_to(root)), 'lines': n, 'days_since_write': age})
    out['logs'] = logs[:12]
    return out


# ---------- E 学习 ----------
def scan_learning(root):
    root = Path(root)
    out = {}
    hits = []
    for pat in ['*iteration*', '*retro*', '*复盘*', '*迭代*', '*postmortem*']:
        for p in root.glob('**/' + pat):
            if p.is_dir() and not any(s in str(p) for s in SKIP_DIRS):
                n = len(list(p.glob('*.md')))
                hits.append({'path': str(p.relative_to(root)), 'files': n})
    seen, uniq = set(), []
    for h in hits:
        if h['path'] in seen:
            continue
        seen.add(h['path']); uniq.append(h)
    out['retro_dirs'] = uniq[:10]

    log = sh(['git', 'log', '--since=90.days', '--pretty=format:%ad', '--date=short'], cwd=root)
    days = [d for d in log.splitlines() if d]
    last_date = sh(['git', 'log', '-1', '--pretty=format:%ad', '--date=short'], cwd=root)
    days_since = -1
    if last_date:
        try:
            import datetime
            days_since = (datetime.date.today() - datetime.date.fromisoformat(last_date)).days
        except Exception:
            pass
    dirty = [x for x in sh(['git', 'status', '--porcelain'], cwd=root).splitlines() if x]
    out['git'] = {
        'commits_90d': len(days),
        'active_days_90d': len(set(days)),
        'last_commit': sh(['git', 'log', '-1', '--pretty=format:%ad %s', '--date=short'], cwd=root)[:120],
        'last_commit_date': last_date,
        'days_since_commit': days_since,
        'uncommitted': len(dirty),
    }
    return out


# ---------- F 僵尸 Skill ----------
def scan_usage(root, skill_names):
    """
    只统计「真实调用」，不统计「被列在系统提示词里」。

    这两者差了两个数量级：会话日志里每一轮都会带上全部可用 Skill 的清单，
    按关键词 grep 会把每个 Skill 都算成用过。真实调用是 tool_use 里
    name == "Skill" 的那条记录，input.skill 才是被调用的 Skill 名。
    """
    from collections import Counter
    root = Path(root)
    counts = Counter()
    sess_files, sess_dirs, invocations = 0, [], 0
    enc = str(root).replace('/', '-')
    cands = [HOME / '.claude/projects' / enc, root / '.claude/sessions', HOME / '.codex/sessions']
    for d in cands:
        if not d.exists():
            continue
        fs = [p for p in d.rglob('*.jsonl')]
        if not fs:
            continue
        sess_dirs.append({'path': str(d), 'files': len(fs)})
        for fp in fs[:600]:
            sess_files += 1
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
                        name = ((b.get('input') or {}).get('skill') or '').strip()
                        if not name:
                            continue
                        # 目录限定的 Skill 形如 "path/to/dir:skill-name"，取冒号后
                        name = name.split(':')[-1]
                        counts[name] += 1
                        invocations += 1

    known = set(skill_names)
    used = {k: v for k, v in counts.items() if k in known}
    unknown = {k: v for k, v in counts.items() if k not in known}
    never = sorted(known - set(used))
    return {
        'session_dirs': sess_dirs,
        'session_files_read': sess_files,
        'evidence': 'ok' if sess_files else 'none',
        'method': 'tool_use(name=Skill).input.skill',
        'invocations': invocations,
        'installed': len(known),
        'used_count': len(used),
        'never_count': len(never),
        'top': sorted(used.items(), key=lambda x: -x[1])[:25],
        'never': never[:200],
        'unknown_invoked': sorted(unknown.items(), key=lambda x: -x[1])[:10],
    }


# ---------- 候选发现 ----------
def build_findings(d):
    """产出候选发现。AI 只能给这些 id 填严重度和文案，不能凭空发明。"""
    f = []
    s, c, t, m, l = d['security'], d['context'], d['tools'], d['memory'], d['learning']

    if not s['gitignore']['exists']:
        f.append(dict(id='gitignore_missing', layer='security',
                      fact=f"根目录没有 .gitignore；{s['tracked']['total']} 个被跟踪文件里 "
                           f"{s['tracked']['noise']} 个是依赖或构建产物，真正的源文件只有 {s['tracked']['source']} 个"))
    elif s['gitignore']['missing_patterns']:
        f.append(dict(id='gitignore_thin', layer='security',
                      fact=f".gitignore 缺少常见条目：{'、'.join(s['gitignore']['missing_patterns'])}"))

    if s['tracked']['noise_ratio'] > 0.3 and s['gitignore']['exists']:
        f.append(dict(id='tracked_noise', layer='security',
                      fact=f"被跟踪文件里 {round(s['tracked']['noise_ratio']*100)}% 是噪音"))

    if s['secrets']['tracked_hits']:
        f.append(dict(id='secrets_tracked', layer='security',
                      fact=f"{s['secrets']['tracked_hits']} 个含明文凭证的文件已被 git 跟踪，"
                           f"仓库可见性 {s['repo']['visibility']}"))
    if s['secrets']['unprotected']:
        f.append(dict(id='secrets_unprotected', layer='security',
                      fact=f"{s['secrets']['unprotected']} 个含明文凭证的文件既未被跟踪也未被 ignore 覆盖，"
                           f"一次 git add -A 就会进仓库；仓库可见性 {s['repo']['visibility']}"))

    if s['permissions']['risky_count']:
        names = [f"{p['path']}（{'、'.join(x['keyword'] for x in p['risky'])}）"
                 for p in s['permissions']['files'] if p['risky']]
        f.append(dict(id='perms_open', layer='security',
                      fact="权限放开：" + '；'.join(names)))
    if s['hooks']['count'] == 0:
        f.append(dict(id='no_hooks', layer='security', fact="没有配置任何 hooks，Agent 行为没有自动守门"))

    if not c['entries']:
        f.append(dict(id='no_entry', layer='context', fact="根目录没有 CLAUDE.md / AGENTS.md 这类入口文件"))
    else:
        big = [e for e in c['entries'] if e['tokens'] > 6000]
        if big:
            f.append(dict(id='entry_too_big', layer='context',
                          fact="入口文件偏大：" + '、'.join(f"{e['name']} 约 {e['tokens']} token" for e in big)))
        nomap = [e['name'] for e in c['entries'] if e['name'] in ('CLAUDE.md', 'AGENTS.md')
                 and not e['has_dir_map'] and not e.get('pointer')]
        if nomap:
            f.append(dict(id='entry_no_map', layer='context',
                          fact=f"{'、'.join(nomap)} 里没有目录地图，Agent 得靠试探找路"))

    h2 = c.get('harness2', {})
    if len(h2.get('entry_sources', [])) > 1:
        f.append(dict(id='entry_split', layer='context',
                      fact=f"{'、'.join(h2['entry_sources'])} 各写了一份完整入口，不同 Agent 读到的规则可能不一样"))
    if c['entries'] and not h2.get('now_file'):
        f.append(dict(id='no_now', layer='context',
                      fact="没有 NOW.md 这类当前状态页，Agent 不知道你现在的主线和明确不做的事"))
    elif h2.get('now_days_since_update', 0) > 30:
        f.append(dict(id='now_stale', layer='context',
                      fact=f"{h2['now_file']} 已经 {h2['now_days_since_update']} 天没更新，Agent 拿到的是过期的主线"))
    if c['entries'] and not h2.get('tools_file'):
        f.append(dict(id='no_tools_doc', layer='context',
                      fact="没有 TOOLS.md 这类工具清单，Agent 不知道能调哪些工具、怎么调、花多少钱"))
    if c['entries'] and not h2.get('has_quiz'):
        f.append(dict(id='no_quiz', layer='context',
                      fact="入口文件里没有上手自测题，没法验证换一个 Agent 读完之后是否真的了解你"))

    td = c['top_dirs']
    if td['total'] and td['coverage'] < 0.6:
        f.append(dict(id='readme_gap', layer='context',
                      fact=f"顶层 {td['total']} 个目录里只有 {td['with_readme']} 个有 README.md，"
                           f"缺：{'、'.join(td['missing'][:8])}"))
    if c['structure']['big_files']:
        b = c['structure']['big_files'][0]
        f.append(dict(id='big_files', layer='context',
                      fact=f"{len(c['structure']['big_files'])} 个文本文件超过 50KB，最大 {b['path']}（{b['kb']}KB）"))
    if c['structure']['wide_dirs']:
        w = c['structure']['wide_dirs'][0]
        f.append(dict(id='wide_dir', layer='context',
                      fact=f"{w['dir']} 下有 {w['children']} 个直接子项，扁平到不好检索"))
    dang = [i for i in c['indexes'] if i['dangling']]
    if dang:
        f.append(dict(id='index_dangling', layer='context',
                      fact='；'.join(f"{i['path']} 有 {i['dangling']} 条指向不存在的文件" for i in dang[:4])))

    sk = t['skills']
    if sk['no_description']:
        f.append(dict(id='skill_no_desc', layer='tools',
                      fact=f"{len(sk['no_description'])} 个 Skill 缺 frontmatter description，语义路由匹配不到："
                           f"{'、'.join(sk['no_description'][:8])}"))
    if sk['no_skill_md']:
        f.append(dict(id='skill_no_md', layer='tools',
                      fact=f"{len(sk['no_skill_md'])} 个目录在 Skill 目录下却没有 SKILL.md："
                           f"{'、'.join(sk['no_skill_md'][:8])}"))
    if t['mcp']['count'] == 0:
        f.append(dict(id='no_mcp', layer='tools', fact="没有检测到任何 MCP 服务"))
    if t['agents']['count'] == 0:
        f.append(dict(id='no_subagents', layer='tools', fact="没有自定义子 Agent，复杂任务无法委派"))

    if not m['stores']:
        f.append(dict(id='no_memory', layer='memory', fact="没有发现任何记忆目录"))
    for st in m['stores']:
        if not st['has_index']:
            f.append(dict(id='mem_no_index', layer='memory',
                          fact=f"{st['path']} 有 {st['files']} 个记忆文件但没有索引，Agent 要全量读才知道有什么"))
        if st['unindexed']:
            f.append(dict(id='mem_unindexed', layer='memory',
                          fact=f"{st['path']} 有 {len(st['unindexed'])} 个文件不在索引里：{'、'.join(st['unindexed'][:5])}"))
        if st['dangling']:
            f.append(dict(id='mem_dangling', layer='memory',
                          fact=f"{st['path']} 索引里 {len(st['dangling'])} 条指向不存在的文件"))

    if not l['retro_dirs']:
        f.append(dict(id='no_retro', layer='learning', fact="没有发现迭代记录或复盘目录，经验没有沉淀的地方"))
    g = l.get('git', {})
    if g.get('days_since_commit', -1) > 60:
        f.append(dict(id='stale_commits', layer='learning',
                      fact=f"最后一次提交是 {g.get('last_commit_date')}，距今 {g['days_since_commit']} 天；"
                           f"近 90 天提交 {g.get('commits_90d', 0)} 次"))
    if g.get('uncommitted', 0) > 200:
        f.append(dict(id='uncommitted_pile', layer='learning',
                      fact=f"工作区有 {g['uncommitted']:,} 项未提交改动堆着"))
    if sk['stale_180d'] and sk['total']:
        f.append(dict(id='skills_stale', layer='learning',
                      fact=f"{sk['stale_180d']} / {sk['total']} 个 Skill 超过 180 天没改过"))

    u = d.get('usage') or {}
    if u.get('evidence') == 'ok' and u.get('never_count'):
        f.append(dict(id='zombie_skills', layer='learning',
                      fact=f"装了 {u['installed']} 个 Skill，会话日志里真实调用过的只有 {u['used_count']} 个"
                           f"（共 {u['invocations']} 次调用，读了 {u['session_files_read']} 个会话文件），"
                           f"{u['never_count']} 个从未被调用"))
    return f


# ---------- 覆盖度 ----------
def score(d):
    s, c, t, m, l = d['security'], d['context'], d['tools'], d['memory'], d['learning']
    sk = t['skills']
    checks = {
        'security': [
            ('根 .gitignore 存在', s['gitignore']['exists']),
            ('.gitignore 覆盖常见噪音', s['gitignore']['exists'] and not s['gitignore']['missing_patterns']),
            ('跟踪文件噪音低于 30%', s['tracked']['noise_ratio'] < 0.3),
            ('没有被跟踪的明文凭证', s['secrets']['tracked_hits'] == 0),
            ('凭证文件都被 ignore 覆盖', s['secrets']['unprotected'] == 0),
            ('Agent 权限没有全面放开', s['permissions']['risky_count'] == 0),
            ('配置了 hooks 守门', s['hooks']['count'] > 0),
        ],
        'context': [
            ('有入口指引文件', bool(c['entries'])),
            ('入口文件带目录地图', any(e['has_dir_map'] for e in c['entries'])),
            ('入口文件带行为规则', any(e['has_rules'] for e in c['entries'])),
            ('入口文件体量适中', all(e['tokens'] < 6000 for e in c['entries']) if c['entries'] else False),
            ('顶层目录 README 覆盖过半', c['top_dirs']['coverage'] >= 0.6),
            ('没有超大文本文件', not c['structure']['big_files']),
            ('没有过度扁平的目录', not c['structure']['wide_dirs']),
            ('冷启动成本低于 2 万 token', c['cold_start']['tokens'] < 20000),
            ('索引没有悬空条目', not any(i['dangling'] for i in c['indexes'])),
            ('入口只有一份正本', len(c.get('harness2', {}).get('entry_sources', [])) == 1),
            ('有当前状态页 NOW.md', bool(c.get('harness2', {}).get('now_file'))),
            ('有工具清单 TOOLS.md', bool(c.get('harness2', {}).get('tools_file'))),
            ('入口带上手自测题', c.get('harness2', {}).get('has_quiz', False)),
        ],
        'tools': [
            ('装了 Skill', sk['total'] > 0),
            ('所有 Skill 都有 SKILL.md', not sk['no_skill_md']),
            ('所有 Skill 都有 description', not sk['no_description']),
            ('description 不过分简略', not sk['thin_description']),
            ('接入了 MCP', t['mcp']['count'] > 0),
            ('有自定义子 Agent', t['agents']['count'] > 0),
            ('有自定义命令', t['commands']['count'] > 0),
        ],
        'memory': [
            ('存在记忆目录', bool(m['stores'])),
            ('记忆有索引', any(st['has_index'] for st in m['stores'])),
            ('索引没有悬空条目', all(not st['dangling'] for st in m['stores']) if m['stores'] else False),
            ('没有未入索引的记忆', all(not st['unindexed'] for st in m['stores']) if m['stores'] else False),
            ('有结构化日志', bool(m['logs'])),
        ],
        'learning': [
            ('有迭代或复盘目录', bool(l['retro_dirs'])),
            ('近 90 天有提交', l['git']['commits_90d'] > 0),
            ('近 90 天活跃超过 10 天', l['git']['active_days_90d'] > 10),
            ('近 30 天有 Skill 更新', sk['fresh_30d'] > 0),
            ('陈旧 Skill 不过半', sk['total'] > 0 and sk['stale_180d'] <= sk['total'] / 2),
            ('工作区没有大量未提交改动', l['git'].get('uncommitted', 0) < 200),
        ],
    }
    out = {}
    for k, items in checks.items():
        out[k] = {
            'passed': sum(1 for _, ok in items if ok),
            'total': len(items),
            'items': [{'name': n, 'ok': bool(ok)} for n, ok in items],
        }
    return out


LAYER_LABEL = {'security': '安全与卫生', 'context': '上下文质量',
               'tools': '工具装备', 'memory': '记忆', 'learning': '学习'}

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    root = os.path.abspath(args[0]) if args else os.getcwd()
    out_path = None
    if '-o' in sys.argv:
        out_path = sys.argv[sys.argv.index('-o') + 1]

    d = {
        'meta': {
            'root': root,
            'name': os.path.basename(root),
            'scanned_at': time.strftime('%Y-%m-%d %H:%M'),
            'scanner': 'better-your-harness/1.0',
        }
    }
    for key, fn in [('security', scan_security), ('context', scan_context),
                    ('tools', scan_tools), ('memory', scan_memory), ('learning', scan_learning)]:
        try:
            d[key] = fn(root)
        except Exception as e:
            d[key] = {'error': f'{type(e).__name__}: {e}'}
    try:
        d['usage'] = scan_usage(root, d['tools']['skills']['names'])
    except Exception as e:
        d['usage'] = {'error': str(e), 'evidence': 'none'}

    d['score'] = score(d)
    d['findings'] = build_findings(d)
    d['labels'] = LAYER_LABEL

    js = json.dumps(d, ensure_ascii=False, indent=2)
    if out_path:
        Path(out_path).write_text(js, encoding='utf-8')
        tot = sum(v['total'] for v in d['score'].values())
        got = sum(v['passed'] for v in d['score'].values())
        print(f"扫描完成 → {out_path}")
        print(f"覆盖度 {got}/{tot} · 候选发现 {len(d['findings'])} 条")
        for k, v in d['score'].items():
            print(f"  {LAYER_LABEL[k]:<10} {v['passed']}/{v['total']}")
    else:
        print(js)

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
know-your-harness 采集器：拉两类零成本的数据，存成原始 JSON。

  github  用 gh 拉你自己的仓库列表（需要 gh 已登录）
  local   统计 harness 里你写过的文本：数量、按目录、按月

其他平台（X、小红书、公众号、飞书……）各家工具不一样，脚本不替你调。
由 Agent 按 TOOLS.md 里写的命令去拉，把原始 JSON 存进同一个数据目录，再交给 rank.py。

铁律：只读自己的数据。只写进 -o 指定的数据目录，已有同名文件不覆盖。

用法：
  python3 collect.py <harness目录> -o <数据目录> [--only github|local]
"""
import datetime, json, os, re, subprocess, sys
from collections import Counter
from pathlib import Path

SKIP = {'.git', 'node_modules', '.next', 'dist', 'build', '.venv', 'venv', '__pycache__',
        '.obsidian', '.trash', '.claude', '.agents', '.codex'}
TEXT = {'.md', '.markdown', '.txt'}


def save(outdir, name, obj):
    p = outdir / name
    if p.exists():
        print(f'  已存在，不覆盖：{p.name}'); return p
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'  写入 {p}')
    return p


def github(outdir, stamp):
    try:
        r = subprocess.run(['gh', 'repo', 'list', '--limit', '300', '--json',
                            'name,description,stargazerCount,forkCount,isFork,visibility,pushedAt,url,primaryLanguage'],
                           capture_output=True, text=True, timeout=60)
    except Exception as ex:
        print(f'github：跑不了 gh（{ex}）'); return
    if r.returncode != 0:
        print('github：gh 没登录或出错，跳过。先跑 gh auth status 看看'); return
    repos = json.loads(r.stdout or '[]')
    own = [x for x in repos if not x.get('isFork')]
    print(f'github：{len(repos)} 个仓库，其中自己的 {len(own)} 个，'
          f'共 {sum(x.get("stargazerCount", 0) for x in own)} 星')
    save(outdir, f'{stamp}-github-repos.json', repos)


def local(root, outdir, stamp):
    by_top, by_month, total, chars = Counter(), Counter(), 0, 0
    dated = 0
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP and not d.startswith('.')]
        for fn in fns:
            p = Path(dp) / fn
            if p.suffix.lower() not in TEXT or fn.lower() == 'readme.md':
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            total += 1; chars += st.st_size
            rel = p.relative_to(root)
            by_top[rel.parts[0] if len(rel.parts) > 1 else '.'] += 1
            by_month[datetime.date.fromtimestamp(st.st_mtime).strftime('%Y-%m')] += 1
            if re.match(r'^\d{4}', fn):
                dated += 1
    out = dict(root=str(root), text_files=total, approx_mb=round(chars / 1048576, 1),
               with_date_prefix=dated, by_top_dir=dict(by_top.most_common()),
               by_month=dict(sorted(by_month.items())[-24:]))
    print(f'local：{total} 个文本文件，分布在 {len(by_top)} 个顶层目录，{dated} 个带日期前缀')
    save(outdir, f'{stamp}-local-writing.json', out)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if '-o' not in sys.argv or not args:
        print(__doc__); sys.exit(1)
    outdir = Path(sys.argv[sys.argv.index('-o') + 1]).expanduser()
    only = sys.argv[sys.argv.index('--only') + 1] if '--only' in sys.argv else None
    root = Path([a for a in args if a not in (str(outdir), only)][0]).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.date.today().strftime('%m%d')
    if only in (None, 'github'):
        github(outdir, stamp)
    if only in (None, 'local'):
        local(root, outdir, stamp)
    print('\n下一步：其他平台的数据让 Agent 按 TOOLS.md 去拉，存进同一个目录，然后用 rank.py 排名。')


if __name__ == '__main__':
    main()

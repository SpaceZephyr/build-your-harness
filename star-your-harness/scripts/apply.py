#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
star-your-harness 执行器：plan.json + 用户的决定 → 真正落盘。

只有走到这一步才会写文件。铁律照旧：
- 已存在的文件一律跳过，绝不覆盖
- 搬运用 copy 不用 move，来源一个不动
- 用户没在页面上确认过的来源，一律不搬

用法：
  python3 apply.py plan.json -d decisions.json          # 预演
  python3 apply.py plan.json -d decisions.json --apply  # 执行
  python3 apply.py plan.json --apply                    # 只建骨架，不搬文件
"""
import json, shutil, subprocess, sys
from pathlib import Path


def load_decisions(path):
    if not path:
        return {}, []
    raw = Path(path).read_text(encoding='utf-8')
    # 容忍用户直接粘了带 ```json 围栏的整段
    if '```' in raw:
        raw = raw.split('```')[1]
        if raw.startswith('json'):
            raw = raw[4:]
    d = json.loads(raw)
    return d.get('decisions', {}), d.get('include_bulk', [])


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if not args:
        print('用法: apply.py plan.json [-d decisions.json] [--apply]'); sys.exit(1)
    plan = json.loads(Path(args[0]).read_text(encoding='utf-8'))
    dpath = sys.argv[sys.argv.index('-d') + 1] if '-d' in sys.argv else None
    decisions, include_bulk = load_decisions(dpath)
    live = '--apply' in sys.argv

    root = Path(plan['meta']['dir'])
    valid = {d['name'] for d in plan['dirs']}

    # ---- 1. 骨架 ----
    mk_dirs = [d['name'] for d in plan['dirs']]
    new_files, skip_files = [], []
    for rel in sorted(plan['files']):
        (skip_files if (root / rel).exists() else new_files).append(rel)

    # ---- 2. 搬运 ----
    copies, skipped_moves = [], []
    for s in plan['sources']:
        if s.get('error'):
            continue
        if s['bulk'] and s['src'] not in include_bulk:
            skipped_moves.append((s['src'], '体量过大，页面上没勾选强制搬运'))
            continue
        for it in s['items']:
            choice = decisions.get(it['src'])
            if choice is None:
                # 没在页面上出现过的（归类明确那批）走默认，但同名冲突一律跳过
                choice = '__skip__' if it['collision'] else it['dest']
            if choice == '__skip__':
                skipped_moves.append((it['rel'], '按你的选择不搬' if it['src'] in decisions else '目标已有同名'))
                continue
            if choice not in valid:
                skipped_moves.append((it['rel'], f'目标目录 {choice} 不在方案里'))
                continue
            dest = root / choice / it['name']
            if dest.exists():
                skipped_moves.append((it['rel'], '目标已有同名，不覆盖'))
                continue
            copies.append((it['src'], str(dest), choice))

    # ---- 报告 ----
    tag = '执行' if live else '预演（不写盘）'
    print(f'{tag} → {root}\n')
    print(f'骨架：{len(mk_dirs)} 个目录 · 新建 {len(new_files)} 个文件'
          + (f' · 跳过已存在 {len(skip_files)} 个' if skip_files else ''))
    if copies:
        by = {}
        for _, _, c in copies:
            by[c] = by.get(c, 0) + 1
        print(f'搬运：{len(copies)} 个文件')
        for c, n in sorted(by.items()):
            print(f'   {c}/  {n} 个')
    if skipped_moves:
        print(f'不搬：{len(skipped_moves)} 个')
        for r, why in skipped_moves[:10]:
            print(f'   {Path(r).name}  ({why})')

    if not live:
        print('\n确认无误后加 --apply 真正执行。')
        return

    # ---- 落盘 ----
    root.mkdir(parents=True, exist_ok=True)
    for d in mk_dirs:
        (root / d).mkdir(parents=True, exist_ok=True)
    for rel in new_files:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(plan['files'][rel], encoding='utf-8')
    done = 0
    for src, dest, _ in copies:
        try:
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)      # copy 不是 move，来源不动
            done += 1
        except Exception as ex:
            print(f'   搬运失败 {Path(src).name}: {ex}')
    if plan.get('git') and not (root / '.git').exists():
        subprocess.run(['git', 'init', '-q'], cwd=root, capture_output=True)
        subprocess.run(['git', 'add', '-A'], cwd=root, capture_output=True)
        subprocess.run(['git', 'commit', '-q', '-m',
                        'chore: 用 star-your-harness 建立 harness 骨架'], cwd=root, capture_output=True)

    print(f'\n完成。新建 {len(new_files)} 个文件，搬入 {done} 个。')
    print('来源文件一个没动，确认无误后你自己决定要不要清理。')
    print('\n下一步：')
    # 别按序号猜，目录名会随命名风格变（plain-en 下按字母排序，索引 1 是 garage）
    am = next((d['name'] for d in plan['dirs'] if d['layer'] == '上下文' and
               ('about' in d['name'].lower() or '关于我' in d['name'])), 'about-me')
    print(f'  1. 填 {am}/ 里那三份文件，harness 的质量取决于这一步')
    print('  2. 体检：better-your-harness 的 scan.py')


if __name__ == '__main__':
    main()

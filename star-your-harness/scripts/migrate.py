#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
star-your-harness 搬运助手：扫来源目录，给出「哪个文件该去哪」的映射，
生成一份可读可审的 migrate.sh。

铁律：这个脚本永远不移动任何文件。它只产出计划。
搬别人攒了几年的资料是高危操作，必须由人过目之后自己执行。

用法：
  python3 migrate.py <来源目录> <harness目录>              # 打印计划
  python3 migrate.py <来源目录> <harness目录> -o migrate.sh # 同时写出脚本
"""
import os, re, sys, json
from pathlib import Path
from collections import defaultdict

SKIP_DIRS = {'.git', 'node_modules', '.next', 'dist', 'build', '.venv', 'venv',
             '__pycache__', '.cache', 'target', 'out', '.obsidian', '.trash'}

# 归类规则：(目标层 key, 正则, 说明)。从上往下匹配，命中即停。
RULES = [
    ('about-me',  r'(关于我|about\s*-?me|profile|我的介绍|风格|style|偏好|preference|标准|standard|定位|'
                  r'persona|bio|简历|resume|性格|personality|人设|语气|tone|voice|价值观|value|'
                  r'黑名单|blacklist|禁用|forbidden|审稿|review|评估|assessment)',
     '像是在描述你自己或你的标准'),
    ('memory',    r'(记忆|memory|cortex|日记|diary|journal|log\.jsonl)', '像是跨会话记忆'),
    ('protocols', r'(工作流|workflow|流程|sop|复盘|retro|迭代|iteration|方法论|protocol|模板|template)',
     '像是流程或方法'),
    ('garage',    r'(script|脚本|tool|工具|\.py$|\.sh$|\.ts$|\.js$|skill|插件|plugin|automation)',
     '像是脚本或工具'),
    ('vault',     r'(素材|vault|摘录|剪藏|clip|参考|reference|收藏|book|读书|文献|论文|paper|引用|quote)',
     '像是别人的东西、参考资料'),
    ('inbox',     r'(inbox|收件箱|草稿|draft|未命名|untitled|新建|temp|tmp)', '没想好放哪'),
]

TEXT_EXT = {'.md', '.txt', '.markdown', '.org', '.rst'}
DATA_EXT = {'.json', '.jsonl', '.csv', '.yaml', '.yml', '.toml'}
CODE_EXT = {'.py', '.sh', '.ts', '.js', '.rb', '.go', '.rs'}
MEDIA_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.mp4', '.mp3', '.wav', '.pdf'}


def harness_dirs(harness):
    """读 harness 实际的目录名，映射回层 key。不猜命名风格。"""
    out = {}
    for d in sorted(Path(harness).iterdir()):
        if not d.is_dir() or d.name.startswith('.'):
            continue
        n = d.name.lower()
        for key in ('inbox', 'about-me', 'vault', 'memory', 'protocols', 'garage'):
            if key.replace('-', '') in n.replace('-', '').replace(' ', '') or key in n:
                out.setdefault(key, d.name)
        for zh, key in (('收件箱', 'inbox'), ('关于我', 'about-me'), ('素材', 'vault'),
                        ('记忆', 'memory'), ('协议', 'protocols'), ('车库', 'garage')):
            if zh in d.name:
                out.setdefault(key, d.name)
    # 剩下的当产出目录
    outs = [d.name for d in sorted(Path(harness).iterdir())
            if d.is_dir() and not d.name.startswith('.') and d.name not in out.values()]
    return out, outs


def classify(path, rel, layers, outputs):
    """返回 (目标目录, 理由, 把握程度)"""
    hay = rel.lower()
    ext = Path(rel).suffix.lower()

    for key, pat, why in RULES:
        if key in layers and re.search(pat, hay, re.I):
            return layers[key], why, 'high'

    if ext in CODE_EXT and 'garage' in layers:
        return layers['garage'], '是脚本文件', 'high'
    if ext in MEDIA_EXT:
        return (outputs[0] if outputs else layers.get('inbox', 'inbox')), '是媒体文件，多半是产出的配图', 'low'
    if ext in DATA_EXT and 'protocols' in layers:
        return layers['protocols'], '是结构化数据，可能是索引或日志', 'low'
    if ext in TEXT_EXT:
        # 有日期前缀的文本，通常是成稿
        if re.match(r'^\d{4}[-_ ]', Path(rel).name) and outputs:
            return outputs[0], '文件名带日期前缀，像是按时间归档的产出', 'medium'
        return (outputs[0] if outputs else layers.get('inbox', 'inbox')), '是正文类文档', 'low'
    return layers.get('inbox', 'inbox'), '没有明显特征', 'low'


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if len(args) < 2:
        print('用法: migrate.py <来源目录> <harness目录> [-o migrate.sh]'); sys.exit(1)
    src, harness = Path(args[0]).resolve(), Path(args[1]).resolve()
    if not src.exists():
        print(f'来源目录不存在：{src}'); sys.exit(1)
    if not harness.exists():
        print(f'harness 目录不存在：{harness}，先跑 scaffold.py'); sys.exit(1)
    if str(harness) in str(src) or str(src) in str(harness):
        print('来源和 harness 有嵌套关系，拒绝处理，换个来源目录'); sys.exit(1)

    layers, outputs = harness_dirs(harness)
    if not layers:
        print(f'{harness} 看起来不像 star-your-harness 生成的骨架（认不出层目录）'); sys.exit(1)

    plan = defaultdict(list)
    skipped, total, bytes_total = [], 0, 0
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.')]
        for fn in filenames:
            if fn.startswith('.'):
                continue
            p = Path(dirpath) / fn
            rel = str(p.relative_to(src))
            try:
                sz = p.stat().st_size
            except Exception:
                continue
            total += 1
            bytes_total += sz
            dest, why, conf = classify(p, rel, layers, outputs)
            target = harness / dest / Path(rel).name
            if target.exists():
                skipped.append((rel, dest, '目标已有同名文件'))
                continue
            plan[dest].append({'src': str(p), 'rel': rel, 'name': Path(rel).name,
                               'why': why, 'conf': conf, 'kb': round(sz / 1024, 1)})

    print(f'来源：{src}')
    print(f'目标：{harness}')
    print(f'扫到 {total} 个文件，约 {bytes_total/1024/1024:.1f} MB\n')

    conf_n = {'high': 0, 'medium': 0, 'low': 0}
    for dest in sorted(plan):
        items = plan[dest]
        for it in items:
            conf_n[it['conf']] += 1
        print(f'── {dest}/  ({len(items)} 个)')
        for it in items[:8]:
            mark = {'high': '  ', 'medium': ' ?', 'low': ' ??'}[it['conf']]
            print(f'  {mark} {it["rel"][:62]:<64} {it["why"]}')
        if len(items) > 8:
            print(f'      … 另外 {len(items)-8} 个')
        print()

    if skipped:
        print(f'跳过 {len(skipped)} 个（目标已有同名文件，不覆盖）：')
        for r, d, why in skipped[:8]:
            print(f'   {r} → {d}/  {why}')
        print()

    print(f'把握程度：确定 {conf_n["high"]} · 大概 {conf_n["medium"]} · 拿不准 {conf_n["low"]}')
    print('标 ? 和 ?? 的一定要人过目，规则是按文件名猜的，猜错很正常。\n')

    if '-o' in sys.argv:
        out = Path(sys.argv[sys.argv.index('-o') + 1])
        lines = ['#!/bin/bash',
                 '# 由 star-your-harness/migrate.py 生成，执行前请逐行过目。',
                 '# 用的是 cp 不是 mv：先复制，确认没问题再自己删来源。',
                 f'# 来源: {src}',
                 f'# 目标: {harness}',
                 'set -e', '']
        for dest in sorted(plan):
            lines.append(f'# ── {dest}/ ─────────────────────────────')
            for it in plan[dest]:
                flag = '' if it['conf'] == 'high' else f'   # {it["conf"]}: {it["why"]}'
                lines.append(f'cp -n "{it["src"]}" "{harness / dest}/"{flag}')
            lines.append('')
        out.write_text('\n'.join(lines), encoding='utf-8')
        os.chmod(out, 0o755)
        print(f'搬运脚本 → {out}')
        print('用的是 cp -n（不覆盖），确认无误后自己执行。这个脚本不会被自动运行。')


if __name__ == '__main__':
    main()

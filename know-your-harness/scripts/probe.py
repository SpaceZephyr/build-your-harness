#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
know-your-harness 探测器：看这台机器上有哪些工具能拿到「关于你」的数据。

只做三件事：命令在不在、自检过不过、环境里有哪些像密钥的变量名。
铁律：只读变量名，永远不读、不打印变量的值。

用法：
  python3 probe.py                 # 打印结果 + 一段可贴进 TOOLS.md 的表格
  python3 probe.py -o probe.json   # 同时写 JSON
  python3 probe.py --tools my-tools.json   # 追加你自己的工具

内置清单只放了最常见的几个。每个人用的平台不一样，自己的工具写进一个 JSON 追加：
  [{"tool": "mycli", "use": "拉我的博客数据", "check": "mycli whoami", "gives": "文章和阅读数"}]
"""
import json, os, re, shutil, subprocess, sys
from pathlib import Path

# (命令, 用途, 自检命令, 能拿到什么)
TOOLS = [
    ('gh',          'GitHub：仓库、star、Issue、PR',      ['gh', 'auth', 'status'],        '仓库列表和 star 数'),
    ('git',         '版本管理',                            ['git', '--version'],            '提交历史'),
    ('glab',        'GitLab：仓库、Issue、MR',             ['glab', 'auth', 'status'],      '仓库列表'),
    ('obsidian',    'Obsidian CLI',                        ['obsidian', '--version'],       '笔记库'),
    ('notion',      'Notion CLI',                          ['notion', '--version'],         '页面和数据库'),
    ('linear',      'Linear CLI',                          ['linear', '--version'],         '任务和项目'),
    ('gcloud',      'Google Cloud CLI',                    ['gcloud', '--version'],         ''),
    ('twitter',     'X：自己的帖子和数据（twitter-cli）',   ['twitter', 'status'],           '帖子、浏览、点赞'),
    ('lark-cli',    '飞书：文档、知识库、多维表格',         ['lark-cli', 'auth', 'status'],  '文档和表格'),
    ('yt-dlp',      '视频平台元数据和字幕',                 ['yt-dlp', '--version'],         '自己频道的视频数据'),
    ('node',        'Node 运行时（不少数据工具依赖它）',    ['node', '--version'],           ''),
    ('uv',          'Python 包运行器',                     ['uv', '--version'],             ''),
]
KEY_PAT = re.compile(r'(TOKEN|API_?KEY|SECRET|ACCESS_KEY|_KEY)$', re.I)
# 这些是系统或工具自己的，不算数据源凭证
KEY_IGNORE = re.compile(r'^(SSH_|GPG_|npm_|HOMEBREW_|TERM_|XPC_|LC_|COLOR|__)', re.I)


def check(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        return r.returncode == 0
    except Exception:
        return False


def main():
    rows = []
    tools = list(TOOLS)
    if '--tools' in sys.argv:          # 用户自己的工具清单
        import shlex
        for t in json.loads(Path(sys.argv[sys.argv.index('--tools') + 1]).read_text(encoding='utf-8')):
            tools.append((t['tool'], t.get('use', ''), shlex.split(t.get('check') or f"{t['tool']} --version"),
                          t.get('gives', '')))
    for name, use, selfcheck, gives in tools:
        path = shutil.which(name)
        if not path:
            rows.append(dict(tool=name, use=use, installed=False, ok=False, check=' '.join(selfcheck), gives=gives))
            continue
        rows.append(dict(tool=name, use=use, installed=True, ok=check(selfcheck),
                         check=' '.join(selfcheck), gives=gives))
    env_names = sorted(k for k in os.environ if KEY_PAT.search(k) and not KEY_IGNORE.search(k))
    # shell 配置里 export 了、但当前进程没继承到的变量名（Agent 的 shell 常常不加载 rc 文件）
    rc_names = set()
    for rc in ('.zshrc', '.zprofile', '.bashrc', '.bash_profile', '.profile'):
        p = Path.home() / rc
        if p.exists():
            for line in p.read_text(encoding='utf-8', errors='ignore').splitlines():
                m = re.match(r'\s*export\s+([A-Za-z_][A-Za-z0-9_]*)=', line)   # 只取等号左边
                if m and KEY_PAT.search(m.group(1)) and not KEY_IGNORE.search(m.group(1)):
                    rc_names.add(m.group(1))
    not_loaded = sorted(rc_names - set(env_names))

    out = dict(tools=rows, env_names=env_names, env_names_in_rc_not_loaded=not_loaded)
    if '-o' in sys.argv:
        Path(sys.argv[sys.argv.index('-o') + 1]).write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')

    ok = [r for r in rows if r['ok']]
    bad = [r for r in rows if r['installed'] and not r['ok']]
    print(f'可用 {len(ok)} 个 · 装了但自检没过 {len(bad)} 个 · 没装 {len(rows) - len(ok) - len(bad)} 个\n')
    print('| 工具 | 用途 | 命令 | 自检 | 状态 |')
    print('|------|------|------|------|------|')
    for r in rows:
        if not r['installed']:
            continue
        print(f"| {r['tool']} | {r['use']} | `{r['tool']}` | `{r['check']}` | {'可用' if r['ok'] else '自检没过，可能要重新登录'} |")
    print('\n环境里像密钥的变量名（只列名字，值没有读）：')
    print('  ' + ('、'.join(env_names) if env_names else '无'))
    if not_loaded:
        print('写在 shell 配置里、但当前进程没加载到的：')
        print('  ' + '、'.join(not_loaded))
        print('  （Agent 的 shell 经常不读 rc 文件。要用时让用户确认后再单独加载这一个变量）')
    print('\n没装的：' + '、'.join(r['tool'] for r in rows if not r['installed']))
    print('上面的表格可以直接贴进 TOOLS.md 的「连接状态」。脚本不认识的工具，让用户自己补。')


if __name__ == '__main__':
    main()

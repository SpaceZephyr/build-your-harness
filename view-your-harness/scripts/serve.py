#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
view-your-harness 本地工作台服务。

零依赖（只用标准库），只绑 127.0.0.1，**只读**：
  GET  /                 工作台页面
  GET  /api/index        索引 JSON
  GET  /api/file?path=   读一个文件的文本内容（限文本类型 + 限大小）
  POST /api/open         用系统默认程序打开文件 / 在访达中定位

没有任何写、改、删接口。所有路径都必须落在 root 之内，越界返回 403。

用法：python3 serve.py <目录> [--port 7799] [--no-open] [--reindex]
"""
import os, io, sys, json, time, argparse, subprocess, threading, webbrowser
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
TEXT_EXT = {'.md', '.markdown', '.txt', '.rst', '.org', '.json', '.jsonl', '.csv',
            '.tsv', '.yml', '.yaml', '.toml', '.ini', '.cfg', '.conf', '.py', '.js',
            '.ts', '.tsx', '.jsx', '.sh', '.zsh', '.rb', '.go', '.rs', '.java',
            '.c', '.h', '.cpp', '.swift', '.lua', '.php', '.sql', '.html', '.css',
            '.gitignore', ''}
MAX_PREVIEW = 300_000
IMAGE_CT = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.gif': 'image/gif', '.webp': 'image/webp', '.svg': 'image/svg+xml',
            '.avif': 'image/avif', '.bmp': 'image/bmp'}
MAX_IMAGE = 12_000_000

STATE = {'root': None, 'index': None, 'index_path': None}


def build_index(root, index_path, no_usage=False):
    cmd = [sys.executable, str(HERE / 'index.py'), str(root), '-o', str(index_path)]
    if no_usage:
        cmd.append('--no-usage')
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        raise SystemExit('索引失败')
    return json.loads(Path(index_path).read_text(encoding='utf-8'))


def safe_join(root, rel):
    """把相对路径解析到 root 之内。任何越界（含符号链接指向外部）返回 None。"""
    if rel is None:
        return None
    rel = rel.lstrip('/')
    try:
        p = (Path(root) / rel).resolve()
        root_r = Path(root).resolve()
    except Exception:
        return None
    if p != root_r and root_r not in p.parents:
        return None
    return p


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        pass  # 别把每个静态请求都刷到终端上

    # ---- 回包 ----
    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _err(self, code, msg):
        self._json({'error': msg}, code)

    def _resolve(self, rel):
        """
        请求里的路径 → 磁盘路径。这是本服务唯一的安全边界，只此一份。

        相对路径按 root 解析；Skill 卡片给的是绝对路径（Skill 常装在 ~/.claude/skills
        而不在 root 里），额外放行 ~/.claude 和 ~/.codex。其余一律 None。
        """
        if not rel:
            return None
        if str(rel).startswith('/') or str(rel).startswith('~'):
            try:
                p = Path(rel).expanduser().resolve()
            except Exception:
                return None
            allowed = [Path(STATE['root']).resolve(),
                       Path.home() / '.claude', Path.home() / '.codex']
            return p if any(a == p or a in p.parents for a in allowed) else None
        return safe_join(STATE['root'], rel)

    # ---- 路由 ----
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        root = STATE['root']

        if u.path in ('/', '/index.html'):
            html = (HERE / 'ui.html').read_text(encoding='utf-8')
            return self._send(200, html, 'text/html; charset=utf-8')

        if u.path == '/api/index':
            return self._json(STATE['index'])

        if u.path == '/api/reindex':
            STATE['index'] = build_index(root, STATE['index_path'])
            return self._json({'ok': True, 'generated_at': STATE['index']['generated_at']})

        if u.path == '/api/raw':
            # 只给图片用。其他二进制不吐字节，避免这个只读服务变成任意文件下载器。
            rel = (q.get('path') or [None])[0]
            p = self._resolve(rel)
            if p is None:
                return self._err(403, '路径越界')
            if not p.exists() or p.is_dir():
                return self._err(404, '文件不存在')
            ct = IMAGE_CT.get(p.suffix.lower())
            if not ct:
                return self._err(415, '只支持图片预览')
            if p.stat().st_size > MAX_IMAGE:
                return self._err(413, '图片过大')
            return self._send(200, p.read_bytes(), ct)

        if u.path == '/api/file':
            p = self._resolve((q.get('path') or [None])[0])
            if p is None:
                return self._err(403, '路径越界')
            if not p.exists():
                return self._err(404, '文件不存在')
            if p.is_dir():
                return self._err(400, '这是一个目录')
            if p.suffix.lower() not in TEXT_EXT:
                return self._json({'binary': True, 'path': str(p),
                                   'bytes': p.stat().st_size, 'text': ''})
            try:
                txt = p.read_text('utf-8', errors='ignore')
            except Exception as e:
                return self._err(500, f'读取失败：{e}')
            return self._json({
                'path': str(p), 'bytes': p.stat().st_size,
                'mtime': int(p.stat().st_mtime),
                'truncated': len(txt) > MAX_PREVIEW,
                'text': txt[:MAX_PREVIEW],
            })

        return self._err(404, 'no route')

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != '/api/open':
            return self._err(404, 'no route')
        try:
            n = int(self.headers.get('Content-Length') or 0)
            body = json.loads(self.rfile.read(n) or b'{}')
        except Exception:
            return self._err(400, 'bad json')

        mode = body.get('mode', 'open')
        p = self._resolve(body.get('path'))
        if p is None:
            return self._err(403, '路径越界')
        if not p.exists():
            return self._err(404, '文件不存在')

        if sys.platform == 'darwin':
            cmd = ['open', '-R', str(p)] if mode == 'reveal' else ['open', str(p)]
        elif sys.platform.startswith('win'):
            cmd = ['explorer', '/select,' + str(p)] if mode == 'reveal' else ['cmd', '/c', 'start', '', str(p)]
        else:
            cmd = ['xdg-open', str(p.parent if mode == 'reveal' else p)]
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            return self._err(500, f'打开失败：{e}')
        return self._json({'ok': True, 'opened': str(p), 'mode': mode})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root')
    ap.add_argument('--port', type=int, default=7799)
    ap.add_argument('--no-open', action='store_true', help='不自动打开浏览器')
    ap.add_argument('--no-usage', action='store_true', help='跳过会话日志统计，索引更快')
    a = ap.parse_args()

    # 这个脚本常被丢到后台跑，非 tty 下 Python 默认全缓冲，
    # 端口和路径要等进程退出才吐出来——那时候已经没用了。
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    root = Path(a.root).expanduser().resolve()
    if not root.is_dir():
        sys.exit(f'不是一个目录：{root}')

    idx_path = Path(f'/tmp/harness-view/{root.name}-index.json')
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    STATE['root'] = str(root)
    STATE['index_path'] = str(idx_path)
    STATE['index'] = build_index(root, idx_path, a.no_usage)

    port = a.port
    for _ in range(20):          # 端口占用就顺延，别让用户自己找空位
        try:
            srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
            break
        except OSError:
            port += 1
    else:
        sys.exit('找不到可用端口')

    url = f'http://127.0.0.1:{port}'
    print(f'\n  工作台 → {url}')
    print(f'  盘的是 {root}')
    print('  只读模式：能看能搜能打开，不改你任何文件。Ctrl-C 停止。\n')
    if not a.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n  已停止。')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
know-your-harness 排名器：给任意平台导出的 JSON，算出什么内容表现好、什么表现差。

不认平台，只认结构：在 JSON 里找到「一组内容」，自动识别标题字段、指标字段、时间字段。
X、小红书、公众号、GitHub、B 站……只要是一个数组，每项带数字指标，就能排。

铁律：画像里出现的每一个数字都必须来自这个脚本的输出，Agent 不许自己估。

用法：
  python3 rank.py posts.json                      # 自动识别
  python3 rank.py posts.json --metric views       # 指定按哪个指标排
  python3 rank.py posts.json --title text --top 10 -o rank.json
  python3 rank.py posts.json --keep-reposts       # 默认会剔掉转发，加这个保留
"""
import json, re, statistics, sys
from collections import Counter
from pathlib import Path

# 指标字段的常见叫法，按「越靠前越适合当主指标」排
METRIC_NAMES = ['views', 'view', 'view_count', 'viewcount', 'impressions', 'read', 'read_num', 'reads', '阅读',
                'play', 'play_count', 'stargazercount', 'stars', 'likes', 'like', 'like_count', 'liked_count',
                'favorite_count', '点赞', 'collected', 'collected_count', 'bookmarks', '收藏', 'shares', 'share',
                'share_count', 'retweets', '转发', 'comments', 'comment_count', 'replies', '评论', 'forkcount', 'quotes']
TITLE_NAMES = ['title', 'text', 'name', 'desc', 'description', 'content', 'full_text', '标题']
DATE_NAMES = ['createdatiso', 'created_at', 'createdat', 'create_time', 'publish_time', 'pushedat',
              'date', 'time', 'timestamp', '发布时间']
URL_NAMES = ['url', 'link', 'share_url', 'permalink']


def flatten(d, prefix=''):
    out = {}
    for k, v in d.items():
        key = f'{prefix}{k}'
        if isinstance(v, dict):
            out.update(flatten(v, key + '.'))
        else:
            out[key] = v
    return out


def find_items(o, depth=0):
    """找 JSON 里最大的那个「对象数组」。"""
    best = []
    if isinstance(o, list) and o and all(isinstance(x, dict) for x in o[:5]):
        best = o
    if depth < 4:
        kids = o.values() if isinstance(o, dict) else (o if isinstance(o, list) and not best else [])
        for v in kids:
            if isinstance(v, (dict, list)):
                c = find_items(v, depth + 1)
                if len(c) > len(best):
                    best = c
    return best


def num(v):
    """'1.2万' '3,456' '12k' 都转成数。转不了返回 None。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    s = v.strip().replace(',', '').replace('+', '')
    m = re.fullmatch(r'(-?\d+(?:\.\d+)?)\s*(万|w|k|千|亿|m)?', s, re.I)
    if not m:
        return None
    mult = {'万': 1e4, 'w': 1e4, 'k': 1e3, '千': 1e3, '亿': 1e8, 'm': 1e6}.get((m.group(2) or '').lower(), 1)
    return float(m.group(1)) * mult


def pick(keys, names):
    low = {k.lower().split('.')[-1]: k for k in reversed(keys)}
    for n in names:
        if n in low:
            return low[n]
    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    def opt(flag, default=None):
        return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default
    for flag in ('--metric', '--title', '--top', '-o'):
        v = opt(flag)
        if v in args:
            args.remove(v)
    if not args:
        print(__doc__); sys.exit(1)
    path = Path(args[0])
    raw = path.read_text(encoding='utf-8', errors='ignore')
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:                      # 可能是 jsonl
        data = [json.loads(l) for l in raw.splitlines() if l.strip().startswith('{')]
    items = [flatten(x) for x in find_items(data)]
    # 转发别人的内容不算你的表现。带 isRetweet / is_repost 之类标记且为真的，默认剔掉
    RT = ('isretweet', 'is_retweet', 'isrepost', 'is_repost', 'retweeted')
    n_all = len(items)
    if '--keep-reposts' not in sys.argv:
        items = [it for it in items if not any(k.lower() in RT and v is True for k, v in it.items())]
    n_rt = n_all - len(items)
    if not items:
        print('没在这个文件里找到「一组内容」。它需要是一个对象数组，或者某个字段是对象数组。'); sys.exit(1)
    keys = list(dict.fromkeys(k for it in items[:50] for k in it))

    # 哪些字段是数字指标
    metrics = [k for k in keys if k.lower().split('.')[-1] in METRIC_NAMES
               and sum(num(it.get(k)) is not None for it in items) >= len(items) * 0.5]
    metric = opt('--metric')
    if metric:
        metric = next((k for k in keys if k == metric or k.split('.')[-1] == metric), None)
    else:
        metric = pick(metrics, METRIC_NAMES)
        # 主指标全是 0（比如平台不给浏览量）就换下一个
        ordered = sorted(metrics, key=lambda k: METRIC_NAMES.index(k.lower().split('.')[-1]))
        for k in ordered:
            if any((num(it.get(k)) or 0) > 0 for it in items):
                metric = k; break
    if not metric:
        print('没认出指标字段。可选字段：' + '、'.join(keys[:40]))
        print('用 --metric <字段名> 指定。'); sys.exit(1)
    title = opt('--title') or pick(keys, TITLE_NAMES)
    title = next((k for k in keys if k == title or k.split('.')[-1] == title), title)
    date_k, url_k = pick(keys, DATE_NAMES), pick(keys, URL_NAMES)
    top_n = int(opt('--top', 10))

    rows = []
    for it in items:
        v = num(it.get(metric))
        if v is None:
            continue
        t = str(it.get(title) or '').replace('\n', ' ').strip()
        rows.append(dict(value=v, title=t[:80], date=str(it.get(date_k) or '')[:10], url=it.get(url_k) or '',
                         others={k.split('.')[-1]: num(it.get(k)) for k in metrics if k != metric}))
    if not rows:
        print(f'字段 {metric} 没有可用的数字。'); sys.exit(1)
    rows.sort(key=lambda r: -r['value'])
    vals = [r['value'] for r in rows]
    med = statistics.median(vals)
    top_share = sum(vals[:max(1, len(vals) // 10)]) / sum(vals) if sum(vals) else 0
    months = Counter(r['date'][:7] for r in rows if re.match(r'\d{4}-\d{2}', r['date']))

    summary = dict(file=path.name, items=len(rows), reposts_excluded=n_rt, metric=metric, title_field=title, date_field=date_k,
                   total=sum(vals), mean=round(statistics.mean(vals), 1), median=med, max=vals[0], min=vals[-1],
                   top_vs_median=round(vals[0] / med, 1) if med else None,
                   top10pct_share=round(top_share, 3),
                   per_month=dict(sorted(months.items())), other_metrics=[k for k in metrics if k != metric])
    out = dict(summary=summary, top=rows[:top_n], bottom=rows[-top_n:][::-1])
    if opt('-o'):
        Path(opt('-o')).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')

    f = lambda x: f'{x:,.0f}'
    print(f'{path.name}：{len(rows)} 条，按 {metric} 排' + (f'（已剔除 {n_rt} 条转发）' if n_rt else ''))
    print(f'合计 {f(sum(vals))} · 平均 {f(summary["mean"])} · 中位数 {f(med)} · 最高 {f(vals[0])} · 最低 {f(vals[-1])}')
    if med:
        print(f'最高那条是中位数的 {summary["top_vs_median"]} 倍；前 10% 的内容拿走了 {top_share:.0%} 的{metric.split(".")[-1]}')
    if months:
        print('每月条数：' + ' · '.join(f'{m} {n}' for m, n in sorted(months.items())[-6:]))
    for label, part in (('表现最好', out['top']), ('表现最差', out['bottom'])):
        print(f'\n{label}的 {len(part)} 条')
        print(f'| # | {metric.split(".")[-1]} | 日期 | 内容 |\n|---|---|---|---|')
        for i, r in enumerate(part, 1):
            print(f'| {i} | {f(r["value"])} | {r["date"]} | {r["title"][:60]} |')
    print('\n规律要 Agent 读完这两张表之后自己归纳，并且每条规律后面要注明依据的是哪几条。')


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""Поиск через раннер: DDG-html качается fetch_url'ом с РФ-адреса, разбирается тут.
Ловушка В13: задания идут строго по одному (последовательно), id = ts+pid.
Использование: python3 ddg.py "запрос" [имя]
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import html as _h

DIR = os.path.dirname(os.path.abspath(__file__))


def search(q, tag=None, page=0):
    tag = tag or ('q%d' % int(time.time()))
    url = 'https://html.duckduckgo.com/html/?q=' + urllib.parse.quote(q)
    if page:
        url += '&s=%d&dc=%d' % (page * 30, page * 30 + 1)
    name = 'ddg-%s.html' % tag
    args = json.dumps({'url': url, 'name': name, 'timeout': 60}, ensure_ascii=False)
    r = subprocess.run([sys.executable, os.path.join(DIR, 'run_on_server.py'),
                        'fetch_url', args], capture_output=True, text=True, cwd=DIR)
    try:
        res = json.loads(r.stdout)
    except Exception:
        return {'error': 'bad runner output', 'raw': r.stdout[-500:], 'stderr': r.stderr[-300:]}
    d = res.get('data') or {}
    if not d.get('ok'):
        return {'error': d.get('error') or res.get('error') or 'fetch failed', 'res': res}
    blob = subprocess.run(['bash', '/home/user/avto/seo-texts/server/drop_client.sh',
                           'down', name, os.path.join(DIR, name)],
                          capture_output=True, text=True).returncode
    t = open(os.path.join(DIR, name), encoding='utf-8', errors='replace').read()
    out = {'query': q, 'html_len': len(t), 'file': name, 'results': []}
    # счётчик/признак применения запроса
    out['query_echoed'] = bool(re.search(re.escape(q.split()[0][:8]), t, re.I))
    out['no_results_banner'] = ('No results' in t or 'не дал результатов' in t)
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', t, re.S):
        href, txt = m.group(1), m.group(2)
        txt = re.sub(r'\s+', ' ', _h.unescape(re.sub(r'<[^>]+>', '', txt))).strip()
        mm = re.search(r'uddg=([^&]+)', href)
        real = urllib.parse.unquote(mm.group(1)) if mm else href
        out['results'].append({'title': txt, 'url': real})
    # сниппеты
    sn = [re.sub(r'\s+', ' ', _h.unescape(re.sub(r'<[^>]+>', '', x))).strip()
          for x in re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', t, re.S)]
    for i, s in enumerate(sn):
        if i < len(out['results']):
            out['results'][i]['snippet'] = s
    return out


if __name__ == '__main__':
    q = sys.argv[1]
    tag = sys.argv[2] if len(sys.argv) > 2 else None
    pg = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    r = search(q, tag, pg)
    print(json.dumps(r, ensure_ascii=False, indent=1))

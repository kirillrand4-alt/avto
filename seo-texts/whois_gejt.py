# -*- coding: utf-8 -*-
"""Второй шлюз WHOIS (who.is) для тех же 70 доменов.

Зачем: шлюзы отвечают РАЗНО на один и тот же домен. whois.com отдал
`org: PJSC "KUIBYSHEVAZOT"` по kuazot.ru, а who.is и api.whois.vu по тому же
домену — пустой org; по acron.ru наоборот: who.is отдал org, whois.com тоже.
То есть «org пуст» у одного шлюза НЕ доказывает приватность домена.
"""
import json
import os
import re
import html
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

D = '/tmp/claude-0/-home-user-avto/520847fd-7699-5483-869b-cf6d49851f67/scratchpad/pr3'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
MULTI = ('spb.ru', 'msk.ru', 'com.ru', 'org.ru', 'net.ru')


def reg_dom(d):
    p = d.split('.')
    if len(p) <= 2:
        return d
    if '.'.join(p[-2:]) in MULTI:
        return '.'.join(p[-3:])
    return '.'.join(p[-2:])


def one(dom):
    rd = reg_dom(dom)
    r = subprocess.run(['curl', '-sS', '-A', UA, '--max-time', '40',
                        f'https://who.is/whois/{rd}'], capture_output=True)
    t = r.stdout.decode('utf-8', 'replace')
    # who.is печатает сырой whois внутри html с экранированными \n
    t2 = html.unescape(t).replace('\\n', '\n')
    o = {'domain': dom, 'sprosili': rd, 'stranica': len(t)}
    for k, rx in (('org', r'(?im)^[ \t]*org:[ \t]*(\S.*)$'),
                  ('inn', r'(?im)^[ \t]*taxpayer-id:[ \t]*(\S.*)$'),
                  ('org2', r'(?im)^[ \t]*Registrant Organization:[ \t]*(\S.*)$')):
        m = re.search(rx, t2)
        if m:
            v = m.group(1).strip()[:150]
            if v and not v.startswith(('<', '\\')):
                o[k] = v
    o['est_whois'] = bool(re.search(r'(?i)registrar:|nserver:|Registry Domain ID', t2))
    return o


def main():
    """Вход: файл со списком доменов (json-список либо по одному в строке).
    Использование: python3 whois_gejt.py domeny.json [сколько]"""
    put = sys.argv[1] if len(sys.argv) > 1 else D + '/domeny.json'
    t = open(put, encoding='utf-8-sig').read().strip()
    if t.startswith('['):
        raw = json.loads(t)
        doms = [x['domain'] if isinstance(x, dict) else x for x in raw]
    else:
        doms = [l.strip() for l in t.splitlines() if l.strip()]
    if len(sys.argv) > 2:
        doms = doms[:int(sys.argv[2])]
    out = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        for i, o in enumerate(ex.map(one, doms)):
            out.append(o)
            print(i, o['domain'], '->', o['sprosili'], '|', o.get('org') or o.get('org2') or '—',
                  '|', o.get('inn', '—'), '| whois есть:', o['est_whois'], file=sys.stderr)
    json.dump(out, open(os.environ.get('WHOIS_OUT', D + '/whois4.json'), 'w'),
              ensure_ascii=False, indent=1)
    print('с org:', sum(1 for o in out if o.get('org') or o.get('org2')))
    print('с ИНН:', sum(1 for o in out if o.get('inn')))
    print('ответ whois получен:', sum(1 for o in out if o['est_whois']))


main()

# -*- coding: utf-8 -*-
"""Совпадает ли домен источника номера с сайтом компании (company.sayt)."""
import collections
import io
import sqlite3

KAT = r'C:\centro2\data\meyer_baza1.db'


def domen(u):
    u = str(u or '').strip().lower()
    if not u:
        return ''
    if '//' in u:
        u = u.split('//', 1)[1]
    d = u.split('/', 1)[0].split('?', 1)[0].split(':', 1)[0]
    d = d[4:] if d.startswith('www.') else d
    try:
        d = d.encode('idna').decode('ascii') if any(ord(ch) > 127 for ch in d) else d
    except Exception:
        pass
    return d


def odin(a, b):
    return bool(a and b and (a == b or a.endswith('.' + b) or b.endswith('.' + a)))


k = sqlite3.connect(KAT)
out = []
sayt = dict(k.execute('select inn, sayt from company'))
out.append('компаний с сайтом: %d из %d; примеры %r' % (sum(1 for v in sayt.values() if v), len(sayt), list(sayt.values())[:5]))
for tabl in ('contact', 'person'):
    c = collections.Counter()
    primery = collections.defaultdict(list)
    for inn, url, src in k.execute('select inn, source_url, source from "%s"' % tabl):
        ds, dk = domen(url), domen(sayt.get(inn))
        flag = 'сторон' in (src or '')
        if not ds:
            kl = 'без ссылки'
        elif not dk:
            kl = 'у компании сайта нет'
        elif odin(ds, dk):
            kl = 'совпал с сайтом компании' + (' (но флаг «сторонний»)' if flag else '')
        else:
            kl = 'НЕ совпал' + (' (флаг «сторонний»)' if flag else '')
        c[kl] += 1
        if len(primery[kl]) < 12:
            primery[kl].append('%s: %s | сайт %s' % (inn, ds, dk))
    out.append('')
    out.append('%s: %s' % (tabl, dict(c.most_common())))
    for kl, pr in primery.items():
        if kl.startswith('НЕ') or 'флаг' in kl or 'нет' in kl:
            out.append('  %s:' % kl)
            out += ['     ' + p for p in pr]
out.append('')
out.append('company_source.field_name: %s' % collections.Counter(
    (r[0] or '').split(':')[0] for r in k.execute('select field_name from company_source')).most_common())
t = '\n'.join(out)
io.open(r'C:\seostat\drop\drop-storage\centro2-sayt-probe.txt', 'w', encoding='utf-8').write(t)
print(t[-5500:])

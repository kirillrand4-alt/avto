# -*- coding: utf-8 -*-
"""ГДЕ лежит база Atlas Copco и сколько в ней чего. Печатаю в КОНЦЕ — хвост раннера режет начало."""
import json, os, sqlite3

nayd = []
for koren in (r'C:\sender', r'C:\seostat', r'C:\ClaudeProjects'):
    if not os.path.isdir(koren):
        continue
    for dp, dn, fn in os.walk(koren):
        dn[:] = [d for d in dn if d not in ('.git', 'node_modules', '__pycache__')]
        for f in fn:
            if f.lower().endswith('.db') and ('atlas' in f.lower() or 'copco' in f.lower()):
                p = os.path.join(dp, f)
                nayd.append((p, os.path.getsize(p)))

svod = {}
for p, n in sorted(nayd, key=lambda x: -x[1]):
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % p.replace('\\', '/'), uri=True)
        t = {}
        for (nm,) in cx.execute("select name from sqlite_master where type='table'"):
            try:
                t[nm] = cx.execute('select count(*) from "%s"' % nm).fetchone()[0]
            except Exception:
                pass
        # сколько уникальных ИНН и сколько строк с контактом
        for tab, pole in (('tenders', 'inn'), ('eis2', 'inn'), ('b2b_stroki', 'firma_inn')):
            if tab in t:
                try:
                    t['%s: разных ИНН' % tab] = cx.execute(
                        'select count(distinct "%s") from "%s" where "%s" is not null'
                        ' and "%s"<>""' % (pole, tab, pole, pole)).fetchone()[0]
                except Exception:
                    pass
        for tab in ('tenders', 'eis2'):
            if tab in t:
                try:
                    t['%s: строк с телефоном' % tab] = cx.execute(
                        'select count(*) from "%s" where phone is not null and phone<>""'
                        % tab).fetchone()[0]
                    t['%s: строк с почтой' % tab] = cx.execute(
                        'select count(*) from "%s" where email is not null and email<>""'
                        % tab).fetchone()[0]
                    t['%s: строк с ФИО' % tab] = cx.execute(
                        'select count(*) from "%s" where fio is not null and fio<>""'
                        % tab).fetchone()[0]
                except Exception:
                    pass
        if 'tenders' in t:
            t['площадки'] = dict(cx.execute(
                'select platform, count(*) from tenders group by platform order by 2 desc'))
            t['ключи запросов'] = dict(list(cx.execute(
                'select query, count(*) from tenders group by query order by 2 desc'))[:12])
        svod[p] = {'байт': n, 'таблицы': t}
        cx.close()
    except Exception as e:
        svod[p] = {'ошибка': str(e)[:120]}

print('\n\n########## ИТОГОВАЯ КАРТА')
for p, d in svod.items():
    print('\n=== %s   %s байт' % (p, d.get('байт')))
    for k, v in (d.get('таблицы') or {}).items():
        print('   %-30s %s' % (k, json.dumps(v, ensure_ascii=False)[:300]
                               if isinstance(v, dict) else v))
print('\nИТОГ ' + json.dumps({'баз': len(svod), 'пути': list(svod)}, ensure_ascii=False))

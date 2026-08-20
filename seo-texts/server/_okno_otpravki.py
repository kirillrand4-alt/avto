# -*- coding: utf-8 -*-
r"""Что сейчас в окне подтверждения и могут ли эти письма уйти."""
import json, sqlite3
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
итог = {}
табл = [r[0] for r in c.execute(
    "select name from sqlite_master where type='table' and "
    "(name like '%setting%' or name like '%config%')")]
итог['таблицы_настроек'] = табл
for т in табл:
    try:
        кол = [x[1] for x in c.execute('pragma table_info("%s")' % т)]
        k = 'key' if 'key' in кол else кол[0]
        v = 'value' if 'value' in кол else (кол[1] if len(кол) > 1 else кол[0])
        итог.setdefault('настройки', {})[т] = {
            str(r[0]): str(r[1])[:60] for r in c.execute(
                'select "%s", "%s" from "%s"' % (k, v, т))
            if any(x in str(r[0]).lower() for x in
                   ('send', 'probe', 'auto', 'live', 'confirm'))}
    except Exception as e:
        итог.setdefault('настройки', {})[т] = str(e)[:70]
ждут = [dict(r) for r in c.execute(
    "select id, email, inn, status, kind, created_at, "
    "coalesce(manual_email_ts,'') ручной from confirm_reviews "
    "where status in ('pending','edited') order by created_at desc limit 40")]
проба = {}
for e, v, s in c.execute('select lower(email), verdict, coalesce(source,"") from addr_probe'):
    проба[e] = (v, s)
для = []
свод = {}
for r in ждут:
    в, ист = проба.get(str(r['email']).lower(), (None, None))
    ключ = в or 'вердикта нет'
    свод[ключ] = свод.get(ключ, 0) + 1
    для.append({'id': r['id'], 'адрес': r['email'], 'статус': r['status'],
                'вердикт': ключ, 'создано': (r['created_at'] or '')[:16]})
итог['ждут_подтверждения'] = len(ждут)
итог['по_вердикту'] = свод
итог['список'] = для[:14]
c.close()
итог.pop('список', None)
print(json.dumps(итог, ensure_ascii=False, indent=1))
print(json.dumps({'ИТОГ': {'ждут': итог.get('ждут_подтверждения'),
                           'по_вердикту': итог.get('по_вердикту')}}, ensure_ascii=False))

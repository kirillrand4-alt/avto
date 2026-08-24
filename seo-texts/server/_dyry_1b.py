# -*- coding: utf-8 -*-
"""Хвост разведки: остаток схемы + файлы + кэш + журнал стадий."""
import json

d = json.load(open(r'C:\sender\_tmp\dyry-shema.json', encoding='utf-8'))
s = d['shema']
kratko = {t: s[t].get('strok') for t in sorted(s)}
print('строки:', json.dumps(kratko, ensure_ascii=False))
for t in ('phone_contacts', 'site_facts', 'stage_log', 'site_text', 'qc_site',
          'vne_bazy', 'signals', 'requisites'):
    if t in s:
        print(t, '->', json.dumps(s[t], ensure_ascii=False)[:900])
print('ФАЙЛЫ', json.dumps(d['fajly'], ensure_ascii=False))
print('КЭШ', json.dumps(d['kesh'], ensure_ascii=False))
print('СТАДИИ', json.dumps(d['stage_top'], ensure_ascii=False)[:2500])

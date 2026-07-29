# -*- coding: utf-8 -*-
"""Добивка: хвост SMTP, имена вне people, и подмена признака в MX-сегментации."""
import io
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_db as EDB  # noqa: E402

db = EDB.EnrichDB()
e = db.cx
out = {}

# ---------- 1. что реально записала схема + хвост SMTP ----------
out['1_записано_схемой'] = [dict(zip(('inn', 'email', 'person', 'source_url'), r))
                            for r in e.execute(
    "select inn, email, person, source_url from emails "
    "where source like '%схема%'")]
п = r'C:\seostat\drop\email_schema.jsonl'
итоги, домены = {}, {}
if os.path.exists(п):
    for s in io.open(п, encoding='utf-8'):
        try:
            d = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        итоги[d.get('итог', '?')] = итоги.get(d.get('итог', '?'), 0) + 1
        if d.get('итог') == 'catch-all':
            домены[d.get('дом')] = 'catch-all'
        elif d.get('адрес'):
            домены.setdefault(d['адрес'].split('@')[-1], d.get('итог'))
out['1_jsonl_итоги'] = итоги
out['1_jsonl_доменов'] = len(домены)
out['1_jsonl_catch_all_доменов'] = sum(1 for v in домены.values() if v == 'catch-all')

# ---------- 2. ИМЕНА ВНЕ people: emails.person и phone_contacts.person ----------
_К = re.compile(r'^([А-ЯЁ][а-яё\-]{2,})\s+([А-ЯЁ])\.\s?([А-ЯЁ])\.?$')
_П = re.compile(r'^([А-ЯЁ][а-яё\-]{2,})\s+([А-ЯЁ][а-яё]{1,})\s+([А-ЯЁ][а-яё]{1,})$')
источники = {}
имена = {}      # inn -> [(таблица, фио)]
for т, q in (('people', 'select inn, person from people where person<>""'),
             ('emails', 'select inn, person from emails where person<>""'),
             ('phone_contacts',
              'select inn, person from phone_contacts where person<>""')):
    к = п2 = 0
    for inn, ф in e.execute(q):
        ф = (ф or '').strip()
        имена.setdefault(inn, []).append((т, ф))
        if _К.match(ф):
            к += 1
        elif _П.match(ф):
            п2 += 1
    источники[т] = {'кратких_ФИО_ИО': к, 'полных_ФИО': п2}
out['2_формы_по_таблицам'] = источники

# межтабличные пары (короткая в одной таблице, полная в другой)
меж, всего_пар = [], 0
for inn, сп in имена.items():
    кр = [(m, т, ф) for т, ф in сп for m in [_К.match(ф)] if m]
    пл = [(m, т, ф) for т, ф in сп for m in [_П.match(ф)] if m]
    for mk, тк, фк in кр:
        for mp, тп, фп in пл:
            if (mp.group(1).lower() == mk.group(1).lower()
                    and mp.group(2)[0] == mk.group(2)
                    and mp.group(3)[0] == mk.group(3)):
                всего_пар += 1
                if тк != тп and len(меж) < 15:
                    меж.append({'инн': inn, 'кратко': f'{фк} ({тк})',
                                'полно': f'{фп} ({тп})'})
                break
out['2_пар_по_ВСЕМ_таблицам'] = всего_пар
out['2_из_них_межтабличных'] = len(меж)
out['2_примеры_межтабличных'] = меж

# ---------- 3. ПОДМЕНА ПРИЗНАКА: корпоративный домен на Яндекс/Mail.ru ----------
ПУБЯЩ = ('mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'bk.ru', 'inbox.ru',
         'list.ru', 'rambler.ru', 'internet.ru', 'yahoo.com', 'icloud.com',
         'mail.com', 'outlook.com', 'hotmail.com', 'narod.ru', 'yandex.com')
плч = ','.join("'%s'" % x for x in ПУБЯЩ)
out['3_домены_корп_по_классу_MX'] = {r[0]: r[1] for r in e.execute(
    f'select provider, count(*) from mx_domains where domain not in ({плч}) '
    'group by provider order by 2 desc')}
out['3_домены_публичных_ящиков_по_классу'] = {r[0]: r[1] for r in e.execute(
    f'select provider, count(*) from mx_domains where domain in ({плч}) '
    'group by provider order by 2 desc')}

# ЧЕСТНАЯ сегментация: есть ли у компании адрес на СВОЁМ (не публичном) домене
res = e.execute(f"""
  with a as (select inn, lower(substr(email, instr(email,'@')+1)) d
             from emails where email like '%@%'),
  c2 as (select distinct a.inn i,
           max(case when a.d not in ({плч}) then 1 else 0 end) корп
         from a group by a.inn)
  select корп, count(*), sum(case when cast(c.revenue_rub as real)>=1000000000
       then 1 else 0 end),
       sum(case when c.revenue_rub is not null and cast(c.revenue_rub as real)>0
       then 1 else 0 end), avg(cast(c.revenue_rub as real))
  from c2 join companies c on c.inn=c2.i group by корп""").fetchall()
out['3_честно_корп_домен_vs_публичный_ящик'] = [
    {'корп_домен': r[0], 'компаний': r[1], 'от_1млрд': r[2],
     'с_выручкой': r[3], 'средняя_млн': round((r[4] or 0) / 1e6, 1),
     'доля_среди_известных_%': round(100.0 * r[2] / r[3], 1) if r[3] else None}
    for r in res]

# что потерял бы фильтр «только корпоративный домен»
out['3_фильтр_корп_домен'] = dict(zip(
    ('крупных_всего', 'сохранил', 'потерял'), e.execute(f"""
  with a as (select inn, lower(substr(email, instr(email,'@')+1)) d
             from emails where email like '%@%'),
  корп as (select distinct inn from a where d not in ({плч})),
  big as (select inn from companies where cast(revenue_rub as real)>=1000000000
          and inn in (select inn from a))
  select (select count(*) from big),
         (select count(*) from big where inn in (select inn from корп)),
         (select count(*) from big where inn not in (select inn from корп))
""").fetchone()))

# сколько КОМПАНИЙ имеют корп-домен, чей MX держит Яндекс/Mail.ru
out['3_компаний_корп_домен_на_яндексе_или_мейле'] = e.execute(f"""
  with a as (select distinct inn, lower(substr(email, instr(email,'@')+1)) d
             from emails where email like '%@%')
  select count(distinct a.inn) from a join mx_domains m on m.domain=a.d
  where a.d not in ({плч}) and m.provider in ('Яндекс','Mail.ru')""").fetchone()[0]

out['3_примеры_нет_MX'] = [r[0] for r in e.execute(
    "select domain from mx_domains where provider='нет MX' limit 12")]
out['3_компаний_всего_с_адресом'] = e.execute(
    "select count(distinct inn) from emails where email like '%@%'").fetchone()[0]
out['3_компаний_в_базе'] = e.execute('select count(*) from companies').fetchone()[0]
out['3_компаний_с_выручкой'] = e.execute(
    'select count(*) from companies where revenue_rub is not null and '
    'cast(revenue_rub as real)>0').fetchone()[0]
out['3_компаний_от_1млрд_в_базе'] = e.execute(
    'select count(*) from companies where cast(revenue_rub as real)>=1000000000'
).fetchone()[0]

print(json.dumps(out, ensure_ascii=False, indent=1)[:15000])
print('ИТОГ ' + json.dumps({k: v for k, v in out.items()
                            if k.startswith('3_') or k.startswith('2_пар')
                            or k == '1_jsonl_итоги'}, ensure_ascii=False))

# -*- coding: utf-8 -*-
"""Адверсариальная перепроверка утверждения №3: сегментация по MX."""
import json
import sys

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_db as EDB  # noqa: E402

db = EDB.EnrichDB()
e = db.cx
out = {}

cols = {t: [r[1] for r in e.execute(f'PRAGMA table_info({t})')]
        for t in ('companies', 'emails', 'people', 'mx_domains')}
out['колонки'] = cols
out['счётчики'] = {t: e.execute(f'select count(*) from {t}').fetchone()[0]
                   for t in ('companies', 'emails', 'people', 'mx_domains')}

rev = 'revenue_rub' if 'revenue_rub' in cols['companies'] else None
out['есть_revenue_rub'] = bool(rev)
if rev:
    out['компаний_с_выручкой'] = e.execute(
        'select count(*) from companies where revenue_rub is not null '
        'and cast(revenue_rub as real) > 0').fetchone()[0]
    out['компаний_от_1млрд_всего'] = e.execute(
        'select count(*) from companies where cast(revenue_rub as real) '
        '>= 1000000000').fetchone()[0]

# ---- 1. ТОЧНОЕ ВОСПРОИЗВЕДЕНИЕ запроса автора (как в ops/mx_scan.py) ----
авт = {}
for пров, n, ср, дол in e.execute("""
    with dom as (
      select distinct lower(substr(em.email, instr(em.email,'@')+1)) d, em.inn
      from emails em where em.email like '%@%'),
    j as (
      select m.provider p, c.inn, cast(c.revenue_rub as real) v
      from dom join mx_domains m on m.domain = dom.d
      join companies c on c.inn = dom.inn)
    select p, count(distinct inn), avg(v),
           sum(case when v >= 1000000000 then 1 else 0 end)
    from j group by p order by 2 desc"""):
    авт[пров] = {'компаний_distinct': n, 'средняя_млн': round((ср or 0) / 1e6, 1),
                 'от_1млрд_СТРОК': дол,
                 'доля_%': round(100.0 * (дол or 0) / n, 1) if n else None}
out['А_запрос_автора_как_есть'] = авт

# ---- 2. ЧЕСТНЫЙ пересчёт: числитель и знаменатель — РАЗНЫЕ КОМПАНИИ ----
чест = {}
for пров, n, n1, nrev, ср in e.execute("""
    with dom as (
      select distinct lower(substr(em.email, instr(em.email,'@')+1)) d, em.inn
      from emails em where em.email like '%@%'),
    j as (
      select distinct m.provider p, c.inn i, cast(c.revenue_rub as real) v
      from dom join mx_domains m on m.domain = dom.d
      join companies c on c.inn = dom.inn)
    select p, count(*), sum(case when v >= 1000000000 then 1 else 0 end),
           sum(case when v is not null and v > 0 then 1 else 0 end), avg(v)
    from j group by p order by 2 desc"""):
    чест[пров] = {'компаний': n, 'от_1млрд': n1, 'с_известной_выручкой': nrev,
                  'средняя_млн': round((ср or 0) / 1e6, 1),
                  'доля_от_всех_%': round(100.0 * (n1 or 0) / n, 1) if n else None,
                  'доля_среди_известных_%': (round(100.0 * (n1 or 0) / nrev, 1)
                                             if nrev else None)}
out['Б_честный_пересчёт_по_компаниям'] = чест

# ---- 3. Насколько группы ПЕРЕСЕКАЮТСЯ (одна компания в двух классах) ----
пере = e.execute("""
    with dom as (
      select distinct lower(substr(em.email, instr(em.email,'@')+1)) d, em.inn
      from emails em where em.email like '%@%'),
    j as (
      select distinct m.provider p, dom.inn i
      from dom join mx_domains m on m.domain = dom.d)
    select k, count(*) from (select i, count(distinct p) k from j group by i)
    group by k order by k""").fetchall()
out['компаний_по_числу_классов'] = {str(k): v for k, v in пере}

# сколько компаний со «своей» имеют ТАКЖЕ публичную и наоборот
out['пересечение_своя_и_публичная'] = e.execute("""
    with dom as (
      select distinct lower(substr(em.email, instr(em.email,'@')+1)) d, em.inn
      from emails em where em.email like '%@%'),
    j as (select distinct m.provider p, dom.inn i
          from dom join mx_domains m on m.domain = dom.d)
    select count(*) from (
      select i from j where p='своя' intersect
      select i from j where p in ('Яндекс','Mail.ru'))""").fetchone()[0]

# ---- 4. ЧТО БЫ ПОТЕРЯЛ фильтр «только своя почта» ----
out['фильтр_только_своя'] = e.execute("""
    with dom as (
      select distinct lower(substr(em.email, instr(em.email,'@')+1)) d, em.inn
      from emails em where em.email like '%@%'),
    j as (select distinct m.provider p, dom.inn i, cast(c.revenue_rub as real) v
          from dom join mx_domains m on m.domain = dom.d
          join companies c on c.inn = dom.inn),
    big as (select distinct i, v from j where v >= 1000000000),
    own as (select distinct i from j where p='своя')
    select (select count(*) from big) крупных_всего,
           (select count(*) from big where i in (select i from own)) сохранил,
           (select count(*) from big where i not in (select i from own)) потерял
    """).fetchone()
out['фильтр_только_своя'] = dict(zip(('крупных_всего', 'сохранил_бы', 'потерял_бы'),
                                     out['фильтр_только_своя']))

# ---- 5. распределение провайдеров по ДОМЕНАМ (а не компаниям) ----
out['доменов_по_классам'] = {r[0]: r[1] for r in e.execute(
    'select provider, count(*) from mx_domains group by provider order by 2 desc')}
out['доменов_непроверенных'] = e.execute("""
    select count(*) from (
      select distinct lower(substr(email, instr(email,'@')+1)) d from emails
      where email like '%@%')
    where d not in (select domain from mx_domains)""").fetchone()[0]

print(json.dumps(out, ensure_ascii=False, indent=1))
print('ИТОГ ' + json.dumps({'авт': авт, 'чест': чест,
                            'фильтр': out['фильтр_только_своя'],
                            'пересеч': out['пересечение_своя_и_публичная']},
                           ensure_ascii=False))

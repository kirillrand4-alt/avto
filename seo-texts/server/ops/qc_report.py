# -*- coding: utf-8 -*-
"""Свод по проверкам качества. ТОЛЬКО ЧТЕНИЕ базы — ничего не пишет и не удаляет.

Каждая цифра снабжена формулировкой того, ЧТО она считает: правило проекта после
подмены признака 29.07 — сперва назвать величину, потом печатать число.
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

db = EDB.EnrichDB()
e = db.cx
R = {}
print(json.dumps({'ГОЛОВА': 'qc_report старт'}, ensure_ascii=False))
sys.stdout.flush()


def норм(с):
    ц = re.sub(r'\D', '', с or '')
    if len(ц) == 11 and ц[0] in '78':
        ц = ц[1:]
    return ц if len(ц) == 10 else ''


# ============ 1. SMTP ============
s = {}
s['_что_меряем'] = ('доля адресов, на которые почтовый сервер домена принял '
                    'конверт в RCPT TO с нашего IP; письмо не отправлялось')
s['доменов_в_базе'] = e.execute(
    "select count(distinct lower(substr(email,instr(email,'@')+1))) "
    "from emails where email like '%@%.%'").fetchone()[0]
s['доменов_опрошено'] = e.execute('select count(*) from smtp_domains').fetchone()[0]
s['состояния_доменов'] = {r[0]: r[1] for r in e.execute(
    'select state, count(*) from smtp_domains group by 1 order by 2 desc')}
s['вердикты_адресов'] = {r[0]: r[1] for r in e.execute(
    'select verdict, count(*) from email_smtp group by 1 order by 2 desc')}
s['адресов_опрошено'] = e.execute('select count(*) from email_smtp').fetchone()[0]

# catch-all: доля ДОМЕНОВ и доля АДРЕСОВ (это РАЗНЫЕ величины)
дост = e.execute("select count(*) from smtp_domains where state in "
                 "('probed','catchall')").fetchone()[0]
ca = e.execute('select count(*) from smtp_domains where catchall=1').fetchone()[0]
s['доменов_доступных_для_суждения'] = дост
s['доменов_catchall'] = ca
s['доля_catchall_среди_доступных_ДОМЕНОВ'] = round(ca / дост, 3) if дост else None
ca_ad = e.execute("select count(*) from email_smtp where verdict='catchall'").fetchone()[0]
суд_ад = e.execute("select count(*) from email_smtp where verdict in "
                   "('catchall','ok','reject','tempfail','unknown')").fetchone()[0]
s['адресов_на_catchall_доменах'] = ca_ad
s['доля_catchall_среди_опрошенных_АДРЕСОВ'] = round(ca_ad / суд_ад, 3) if суд_ад else None

# ДОМЕНЫ, КОТОРЫЕ ДОКАЗАННО РАЗЛИЧАЮТ АДРЕСА: фальшивый отвергнут И хоть один
# настоящий принят. Только на них «reject» значит «ящика нет», а не «нас не любят».
e.execute('DROP TABLE IF EXISTS _tmp_disc')
e.execute("""CREATE TEMP TABLE _tmp_disc AS
  SELECT domain FROM smtp_domains
  WHERE catchall=0 AND state='probed' AND n_ok>0""")
s['_что_такое_различающий_домен'] = (
    'фальшивый ящик отвергнут И хотя бы один настоящий адрес принят — сервер '
    'доказал, что отвечает по-разному, значит его 550 на другой адрес '
    'означает «ящика нет», а не «блокирует наш IP»')
s['доменов_различающих'] = e.execute('select count(*) from _tmp_disc').fetchone()[0]
s['доменов_probed_без_единого_ok'] = e.execute(
    "select count(*) from smtp_domains where catchall=0 and state='probed' "
    'and n_ok=0 and n_probed>0').fetchone()[0]
s['_оговорка_к_ним'] = ('домен, где НИ ОДИН адрес не принят, неотличим от '
                        'домена с глухим отказом нашему IP — по таким адресам '
                        'приговор «ящика нет» НЕ выносим')
s['на_различающих_доменах'] = {r[0]: r[1] for r in e.execute(
    'select verdict, count(*) from email_smtp where domain in '
    '(select domain from _tmp_disc) group by 1 order by 2 desc')}
ок = e.execute("select count(*) from email_smtp where verdict='ok' and domain in "
               '(select domain from _tmp_disc)').fetchone()[0]
рж = e.execute("select count(*) from email_smtp where verdict='reject' and domain in "
               '(select domain from _tmp_disc)').fetchone()[0]
s['на_различающих_ok'] = ок
s['на_различающих_reject'] = рж
s['доля_мёртвых_среди_проверяемых'] = round(рж / (ок + рж), 3) if (ок + рж) else None
s['_как_читать_долю_мёртвых'] = (
    'знаменатель — адреса на доменах, которые доказанно различают ящики; '
    'это ЕДИНСТВЕННАЯ выборка, где проверка что-то значит')
R['1_smtp'] = s

# ============ 2. phone_mismatch ============
p = {'_что_меряем': ('доля компаний, у которых НИ ОДИН телефон исходной выгрузки '
                     'не встретился среди телефонов, найденных нами на скачанных '
                     'страницах её сайта')}
ряды = list(e.execute("""
  select c.inn, coalesce(b.phones,''), q.nbytes, q.n_phones, coalesce(q.phones,''),
         coalesce(c.verified,'')
  from companies c
  join base_ref b on b.inn=c.inn
  left join qc_site q on q.inn=c.inn
  where coalesce(b.phones,'')<>''"""))
p['компаний_с_телефоном_в_выгрузке'] = len(ряды)
св = {'сравнимо_совпало': 0, 'сравнимо_НЕ_совпало': 0,
      'сайт_скачан_но_телефонов_на_нём_нет': 0, 'сайт_не_скачался': 0,
      'сайта_нет_в_базе': 0}
по_вер = {}
примеры = []
for inn, bph, nb, nph, sph, ver in ряды:
    базы = {норм(x) for x in bph.split('|')}
    базы.discard('')
    if nb is None:
        св['сайта_нет_в_базе'] += 1
        continue
    if not nb:
        св['сайт_не_скачался'] += 1
        continue
    сайта = {x for x in (sph or '').split('|') if x}
    if not сайта:
        св['сайт_скачан_но_телефонов_на_нём_нет'] += 1
        continue
    совп = bool(базы & сайта)
    св['сравнимо_совпало' if совп else 'сравнимо_НЕ_совпало'] += 1
    k = ver or '(не подтверждён)'
    d = по_вер.setdefault(k, {'совпало': 0, 'не_совпало': 0})
    d['совпало' if совп else 'не_совпало'] += 1
    if not совп and len(примеры) < 12:
        примеры.append({'inn': inn, 'база': sorted(базы)[:3],
                        'сайт': sorted(сайта)[:4], 'verified': ver})
p['разбивка'] = св
срав = св['сравнимо_совпало'] + св['сравнимо_НЕ_совпало']
p['сравнимых_компаний'] = срав
p['доля_несовпадений_на_сравнимых'] = round(
    св['сравнимо_НЕ_совпало'] / срав, 3) if срав else None
p['по_подтверждённости_сайта'] = по_вер
p['_оговорка_verified_phone'] = (
    "verified='phone' поставлен ПРЕЖНИМ прогоном ровно по факту совпадения "
    'телефона базы с телефоном сайта — на этой группе несовпадение почти '
    'невозможно по построению, она служит контролем нормализации, а не замером')
p['_оговорка_охвата'] = (
    'телефоны сайта собраны максимум с ДВУХ страниц (главная + контакты). '
    'Номер, стоящий на третьей странице, даёт ЛОЖНОЕ несовпадение — то есть '
    'доля несовпадений это ВЕРХНЯЯ граница доли протухших номеров')
p['примеры_несовпадений'] = примеры
R['2_phone_mismatch'] = p

# ============ 3. публичный почтовый сервис ============
f = {'_что_меряем': ('доля адресов, чей ДОМЕН (строка после «@») входит в список '
                     'публичных бесплатных сервисов; MX не участвует')}
f['классы_адресов'] = {r[0]: r[1] for r in e.execute(
    "select coalesce(addr_class,'(нет)'), count(*) from emails group by 1 order by 2 desc")}
f['компаний_с_почтой'] = e.execute(
    'select count(distinct inn) from email_class').fetchone()[0]
f['компаний_все_адреса_публичные'] = e.execute("""
  select count(*) from (select inn from email_class group by inn
  having sum(case when addr_class='публичный' then 1 else 0 end)=count(*))""").fetchone()[0]
f['из_них_у_кого_ЕСТЬ_сайт'] = e.execute("""
  select count(*) from (select ec.inn from email_class ec group by ec.inn
  having sum(case when ec.addr_class='публичный' then 1 else 0 end)=count(*)) x
  join companies c on c.inn=x.inn where coalesce(c.site,'')<>''""").fetchone()[0]
f['публичных_адресов_у_компаний_где_есть_и_свой'] = e.execute("""
  select count(*) from email_class a where a.addr_class='публичный'
  and exists(select 1 from email_class b where b.inn=a.inn and b.addr_class='свой')
  """).fetchone()[0]
f['_оговорка'] = ('класс «прочий» раздут отсутствием сайта: у 2062 адресов '
                  'компания без сайта в базе, и сравнивать домен не с чем')
R['3_публичный_домен'] = f

# ============ 4. свежесть сайта по копирайту ============
c4 = {'_что_меряем': ('максимальный год в окне ±60 символов вокруг знака '
                      'копирайта на скачанных страницах сайта')}
c4['компаний_с_сайтом_обойдено'] = e.execute('select count(*) from qc_site').fetchone()[0]
c4['страница_скачалась'] = e.execute(
    'select count(*) from qc_site where nbytes>0').fetchone()[0]
c4['год_прочитан'] = e.execute(
    'select count(*) from qc_site where cr_year is not null').fetchone()[0]
c4['маркер_копирайта_есть_а_года_нет'] = e.execute(
    'select count(*) from qc_site where cr_marker=1 and cr_year is null').fetchone()[0]
c4['год_рисуется_скриптом_getFullYear'] = e.execute(
    'select count(*) from qc_site where js_year=1').fetchone()[0]
c4['год_рисуется_скриптом_И_статически_не_прочитан'] = e.execute(
    'select count(*) from qc_site where js_year=1 and cr_year is null').fetchone()[0]
c4['распределение_года'] = {str(r[0]): r[1] for r in e.execute(
    'select cr_year, count(*) from qc_site where cr_year is not null '
    'group by 1 order by 1 desc')}
c4['_база_для_долей'] = 'компании, где год РЕАЛЬНО прочитан статически'
чит = c4['год_прочитан']
for порог, имя in ((2026, 'год_2026_текущий'), (2025, 'год_2025'),
                   (2023, 'год_2023_и_старше_то_есть_3+_года')):
    if имя.startswith('год_2023'):
        n = e.execute('select count(*) from qc_site where cr_year<=2023').fetchone()[0]
    else:
        n = e.execute('select count(*) from qc_site where cr_year=?', (порог,)).fetchone()[0]
    c4[имя] = n
    c4['доля_' + имя] = round(n / чит, 3) if чит else None
c4['_оговорка'] = (
    'признак применим только к сайтам, где год выведен в разметке. У '
    'половины сайтов год подставляет скрипт — там наш статический забор '
    'ничего не видит, и такие сайты НЕЛЬЗЯ считать заброшенными')

# связь свежести сайта с ответом почты — только на различающих доменах
пары = list(e.execute("""
  select q.cr_year, es.verdict
  from qc_site q join emails em on em.inn=q.inn
  join email_smtp es on es.email=lower(trim(em.email))
  where q.cr_year is not null and es.verdict in ('ok','reject')
    and es.domain in (select domain from _tmp_disc)"""))
св4 = {}
for год, в in пары:
    k = 'сайт_2024_и_свежее' if год >= 2024 else 'сайт_2023_и_старше'
    d = св4.setdefault(k, {'ok': 0, 'reject': 0})
    d[в] += 1
for k, d in св4.items():
    т = d['ok'] + d['reject']
    d['доля_мёртвых'] = round(d['reject'] / т, 3) if т else None
c4['почта_против_свежести_сайта'] = св4
c4['_оговорка_связи'] = ('выборка = адреса на доменах, доказанно различающих '
                         'ящики, у компаний с прочитанным годом; если она '
                         'мала, цифру не использовать')
R['4_свежесть_сайта'] = c4

# ============ 5. спасённые ингестером ============
R['5_спасённые_лиды'] = {'состояние': 'НЕ ИЗМЕРЕНО — прогон не запускался'}

print(json.dumps(R, ensure_ascii=False, indent=1))
print(json.dumps({'ХВОСТ': 'qc_report готов'}, ensure_ascii=False))
sys.stdout.flush()
import os
os._exit(0)

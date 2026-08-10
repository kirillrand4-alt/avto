# -*- coding: utf-8 -*-
"""Приём контактов, добытых штатным конвейером обогащения, в park.db.

Главное правило, ради которого этот скрипт не однострочник: **owner_match**.
Конвейер сам проверяет, принадлежит ли найденный сайт этой компании, и пишет в поле
`verified`. Замер на первых 90 предприятиях:

    mismatch 42 | provider 18 | нет ответа 29 | inn 3

То есть у почти половины найденный сайт ЧУЖОЙ (пример: АО «ВТЗ» -> vtz.ru, а почта
support@budohost.ru — это хостер). Такие контакты брать нельзя, иначе продавец позвонит
не туда и сошлётся на нас. Берём только verified in ('provider', 'inn').

Провенанс есть у каждого контакта, и он поштучный:
  contact_src.phones[<цифры>] = {url, ctx}   — страница и цитата вокруг номера
  emails[] = {email, person, role, source_url, source}
Это ровно то, что требует владелец: контакт доказывается ссылкой, и цитата видна.
"""
import sqlite3, json, os, re, importlib.util, collections

D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()
FAYL = os.path.join(D, 'park_obogashchenie_potok.jsonl')
if not os.path.exists(FAYL):
    raise SystemExit('нет %s — сначала скачать поток с сервера через дроп' % FAYL)

MOZHNO = {'provider', 'inn'}
vs = tel = mail = 0
pri = collections.Counter()
inny = set()
for ln in open(FAYL, encoding='utf-8', errors='replace'):
    if not ln.strip():
        continue
    try:
        x = json.loads(ln)
    except Exception:
        pri['строка не разобралась'] += 1
        continue
    vs += 1
    inn = str(x.get('inn') or '').strip()
    if not re.fullmatch(r'\d{10}|\d{12}', inn):
        pri['ИНН не разобран'] += 1
        continue
    if x.get('is_competitor'):
        pri['это наш конкурент — контакты не берём'] += 1
        continue
    ver = x.get('verified')
    if ver not in MOZHNO:
        pri['сайт компании не подтверждён (%s)' % (ver or 'нет ответа')] += 1
        continue
    src = (x.get('contact_src') or {})
    # ---- телефоны: у каждого своя страница и цитата -------------------------
    for cifry, meta in (src.get('phones') or {}).items():
        c = re.sub(r'\D', '', cifry)[-10:]
        if len(c) != 10:
            continue
        url = (meta or {}).get('url') or ''
        raz = pb.razbor_url(url)
        if not raz:
            pri['телефон без пригодной ссылки'] += 1
            continue
        cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                    'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto) '
                    'values (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (inn, 'telefon', c, '', '', raz[1], url, raz[0], raz[2], '',
                     ((meta or {}).get('ctx') or '')[:300],
                     '1-я сессия, штатный конвейер обогащения (сайт компании)'))
        tel += 1
    # ---- почты: у них есть человек и роль ------------------------------------
    for e in (x.get('emails') or []):
        if not isinstance(e, dict):
            continue
        adres = (e.get('email') or '').strip()
        if '@' not in adres:
            continue
        url = e.get('source_url') or ''
        raz = pb.razbor_url(url)
        if not raz:
            pri['почта без пригодной ссылки'] += 1
            continue
        cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                    'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto) '
                    'values (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (inn, 'email', adres, (e.get('person') or '')[:200],
                     (e.get('role') or '')[:120], raz[1], url, raz[0], raz[2], '',
                     ((src.get('emails') or {}).get(adres, {}).get('ctx') or '')[:300],
                     '1-я сессия, штатный конвейер обогащения (сайт компании)'))
        mail += 1
    inny.add(inn)

p.commit()
print('записей на входе %d | предприятий принято %d' % (vs, len(inny)))
print('  наблюдений: телефонов %d, почт %d' % (tel, mail))
print('  отказы:', dict(pri))
print('\nПересобираю свод контактов (kontakt) из наблюдений...')
p.close()


# ---------- пересборка свода контактов и ролей -------------------------------
# kontakt строится из наблюдений целиком, иначе новые телефоны в выдачу не попадут.
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()
import time
cur.execute('delete from kontakt')
cur.execute("""
  insert into kontakt(inn,vid,znachenie,person,dolzhnost,ssylok,ssylok_pervoistochnik,
                      imen,innov,lichnyy,mobilnyy,ts)
  select cs.inn, cs.vid, cs.znachenie,
         (select person from contact_source x where x.inn=cs.inn and x.vid=cs.vid
            and x.znachenie=cs.znachenie and x.person!='' order by length(x.person) desc limit 1),
         (select dolzhnost from contact_source x where x.inn=cs.inn and x.vid=cs.vid
            and x.znachenie=cs.znachenie and x.dolzhnost!='' limit 1),
         count(distinct case when cs.source_url like 'http%' then cs.source_url end),
         count(distinct case when cs.pervoistochnik=1 and cs.source_url like 'http%'
               then cs.source_url end),
         count(distinct case when cs.person!='' then lower(cs.person) end),
         (select count(distinct y.inn) from contact_source y
            where y.vid=cs.vid and y.znachenie=cs.znachenie),
         0, 0, ?
  from contact_source cs group by cs.inn, cs.vid, cs.znachenie""",
            (time.strftime('%Y-%m-%d %H:%M:%S'),))
cur.execute("update kontakt set lichnyy = case when imen=1 and ssylok_pervoistochnik>=1 "
            "and innov=1 then 1 else 0 end")
cur.execute("update kontakt set mobilnyy = case when vid='telefon' and "
            "substr(znachenie,1,1)='9' then 1 else 0 end")

ROL = [
    (r'(?i)машинист\s+компрессор|аппаратчик\s+воздухораздел|оператор\s+компрессорн|'
     r'аппаратчик\s+кислородн|моторист\s+.*азотн', 'рабочий-эксплуатант', 1),
    (r'(?i)главн\w+\s+(инженер|механик|энергетик)|техническ\w+\s+директор|'
     r'директор\s+по\s+техн', 'главный инженер/механик/энергетик', 1),
    (r'(?i)начальник\s+(компрессорн|энергоцех|энергетическ)', 'начальник компрессорного/энергоцеха', 1),
    (r'(?i)начальник\s+(цеха|производств)|главн\w+\s+технолог|начальник\s+(асу|кипиа|кип)',
     'начальник цеха/производства', 2),
    (r'(?i)инженер|механик|энергетик|мастер|техник|слесар', 'инженер/механик', 2),
    (r'(?i)снабжен|закупк|мто|тендер|коммерческ', 'снабжение/закупки', 3),
    (r'(?i)директор|руководител|генеральн|президент', 'руководство', 4),
]
n = 0
for kid, dolzh in cur.execute("select id, coalesce(dolzhnost,'') from kontakt").fetchall():
    rol, krug = next(((r, k) for sh, r, k in ROL if re.search(sh, dolzh)),
                     ('не определена', 5) if dolzh else ('должность не названа', 5))
    cur.execute('update kontakt set rol=?, rang=? where id=?', (rol, krug, kid))
    n += 1
p.commit()
q = lambda s: cur.execute(s).fetchone()[0]
print('свод пересобран: %d контактов, роль проставлена %d' % (q('select count(*) from kontakt'), n))
print('  ИНН с телефоном и ссылкой:', q("select count(distinct inn) from kontakt where vid='telefon' and ssylok>0"))
print('  ИНН с почтой и ссылкой:  ', q("select count(distinct inn) from kontakt where vid='email' and ssylok>0"))
print('  круг 1:', q('select count(distinct inn) from kontakt where rang=1'))
p.close()

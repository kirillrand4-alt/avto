# -*- coding: utf-8 -*-
"""Принимает ВСЕ контактные каналы 3-й сессии одним прибором, с реестром принятого.

Владелец спросил «это всё влил в базу?» — сверил опись `VLIV-3S-OPIS.json` (27 файлов) со
своим реестром `prinyatye_potoki` и ответил честно: **принято 9, не принято 18**. Непринятое
— почти целиком каналы КОНТАКТОВ: обратный ход по базе, карточки организации ЕИС, обход
сайтов предприятий, контактная база. Около 16 000 строк, каждая со ссылкой.

Мимо они прошли по той же причине, что и в записи 129: мой прежний приёмник знал только
потоки МАШИН (`park_ingest_*`, `PARK-EIS-TIK*`), а контактные каналы под его отбор не
подпадали и молча оставались лежать.

Имена полей у каналов разные — это уже четвёртый случай того же класса (Росэлторг слал
`zakupka` вместо `predmet`, ingest_3b — `nazvanie_zakupki`). Поэтому здесь поле ищется
СПИСКОМ синонимов, а если не нашлось ни одного — прибор печатает список полей потока, а не
пишет «пусто»:

    человек   chelovek | imya | kontaktnoe_lico
    номер     nomer | telefon | znachenie(при vid_nomera)
    почта     pochta | email

Правило владельца про ссылки соблюдается буквально: строка без `http`-ссылки в базу не идёт,
а несколько источников раскладываются ОТДЕЛЬНЫМИ наблюдениями, а не склейкой через « | » —
склейка теряет, какая ссылка что доказывает.

Запуск: python3 park_1s_prinyat_kontaktnye_kanaly.py [--pisat]
"""
import hashlib, json, os, re, shutil, sqlite3, subprocess, sys, time

D = os.path.dirname(os.path.abspath(__file__))
PISAT = '--pisat' in sys.argv
KLIENT = '/home/user/avto/seo-texts/server/drop_client.sh'
KANALY = [
    'PARK-KONTAKTY-3S-CHESTNO.jsonl', 'PARK-OBRATNYY-BAZA-PROVERENO-3S.jsonl',
    'PARK-OBRATNYY-PROVERENO-3S.jsonl', 'PARK-OBRATNYY-1S-PROVERENO-3S.jsonl',
    'PARK-OBRATNYY-2S-PROVERENO-3S.jsonl', 'PARK-OBRATNYY-2S-NOVYE-PROVERENO-3S.jsonl',
    'PARK-OBRATNYY-STARYY-PROVERENO-3S.jsonl', 'PARK-OBRATNYY-STARYY2-PROVERENO-3S.jsonl',
    'PARK-EIS-ORG-OCHERED-3S.jsonl', 'PARK-EIS-ORG-KONTAKTY-3S.jsonl',
    'PARK-EIS-ORG-KONTAKTY-1S-3S.jsonl', 'PARK-SAYTY-TELEFONY-3S.jsonl',
    'PARK-SAYTY-LICA-3S.jsonl', 'PARK-OTKAZY-RAZOBRANY-3S.jsonl',
]
CHELOVEK = ('chelovek', 'imya', 'kontaktnoe_lico', 'fio')
NOMER = ('nomer', 'telefon', 'phone')
POCHTA = ('pochta', 'email', 'mail')
# часть каналов шлёт СПИСКОМ: «pochty»: ["a@b.ru", "c@d.ru"], «telefony»: [...]
SPISKI_POCHT = ('pochty', 'emails', 'pochta_vse')
SPISKI_NOMEROV = ('telefony', 'nomera', 'phones')


def pole(r, imena):
    for k in imena:
        v = str(r.get(k) or '').strip()
        if v:
            return v
    return ''


def telefon(t):
    c = re.sub(r'\D', '', str(t or ''))
    if len(c) == 11 and c[0] in '78':
        return '7' + c[1:]
    return c if len(c) == 10 else ''


p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=180)
c = p.cursor()
c.execute("""create table if not exists prinyatye_potoki(
    imya text, sha256 text, strok integer, prinyato integer, ts text,
    primary key(imya, sha256))""")
vydacha = {r[0] for r in c.execute("""select distinct inn from fakt where v_parke=1
             and coalesce(v_obzvone,0)=0 and coalesce(posrednik,0)=0""")}
est = {(r[0], r[1], r[2]) for r in c.execute('select inn, vid, znachenie from contact_source')}
uzhe = {(r[0], r[1]) for r in c.execute('select imya, sha256 from prinyatye_potoki')}
bylo = c.execute('select count(*) from contact_source').fetchone()[0]

svod = []
for imya in KANALY:
    put = os.path.join(D, imya)
    if not os.path.exists(put):
        subprocess.run(['bash', KLIENT, 'down', imya], capture_output=True, timeout=600, cwd=D)
    if not os.path.exists(put):
        print('  %-42s НЕ СКАЧАЛСЯ' % imya[:42])
        continue
    sha = hashlib.sha256(open(put, 'rb').read()).hexdigest()
    if (imya, sha) in uzhe:
        print('  %-42s уже принят' % imya[:42])
        continue
    strok = prin = bez_ssylki = vne = 0
    polya_ne_nashlis = set()
    for ln in open(put, encoding='utf-8', errors='replace'):
        if not ln.strip():
            continue
        strok += 1
        try:
            r = json.loads(ln)
        except Exception:
            continue
        inn = str(r.get('inn') or '').strip()
        if not re.fullmatch(r'\d{10}|\d{12}', inn):
            continue
        if inn not in vydacha:
            vne += 1
            continue
        chel = pole(r, CHELOVEK)
        dolzh = str(r.get('dolzhnost') or '').strip()
        nomer = telefon(pole(r, NOMER) or (r.get('znachenie') if r.get('vid_nomera') else ''))
        pochta = pole(r, POCHTA).lower()
        # списки раскладываем в отдельные значения — иначе канал сайтов даёт ноль,
        # хотя почты в нём есть (322 строки с полем «pochty»)
        prochie_pochty = [str(x).strip().lower() for k in SPISKI_POCHT
                          for x in (r.get(k) or []) if '@' in str(x)]
        prochie_nomera = [telefon(x) for k in SPISKI_NOMEROV for x in (r.get(k) or [])]
        prochie_nomera = [x for x in prochie_nomera if x]
        if not pochta and prochie_pochty:
            pochta = prochie_pochty[0]
        if not nomer and prochie_nomera:
            nomer = prochie_nomera[0]
        if not nomer and not pochta:
            polya_ne_nashlis |= set(list(r)[:8])
            continue
        ssylki = [u.strip() for u in str(r.get('istochniki') or '').split('|')
                  if u.strip().startswith('http')]
        if not ssylki:
            bez_ssylki += 1
            continue
        citata = str(r.get('citata') or '')[:300]
        vid = str(r.get('vid_nomera') or '')
        pary = [('telefon', nomer), ('email', pochta)]
        pary += [('email', x) for x in prochie_pochty[1:3]]
        pary += [('telefon', x) for x in prochie_nomera[1:3]]
        for vid_k, znach in pary:
            if not znach or (inn, vid_k, znach) in est:
                continue
            for u in ssylki[:3]:
                c.execute("""insert into contact_source(inn, vid, znachenie, person, dolzhnost,
                                 istochnik, source_url, domen, pervoistochnik,
                                 data_nablyudeniya, quote, kto)
                             values (?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (inn, vid_k, znach, chel, dolzh,
                           '%s: %s' % (imya.replace('.jsonl', ''), vid or ''), u,
                           re.sub(r'^https?://(www\.)?([^/]+).*', r'\2', u), 0,
                           time.strftime('%Y-%m-%d'), citata, '3-я сессия'))
                prin += 1
            est.add((inn, vid_k, znach))
    print('  %-42s строк %-6d принято %-6d вне выдачи %-5d без ссылки %d'
          % (imya[:42], strok, prin, vne, bez_ssylki))
    if polya_ne_nashlis:
        print('        ПОЛЯ КОНТАКТА НЕ НАЙДЕНЫ, поля потока: %s'
              % ','.join(sorted(polya_ne_nashlis)[:8]))
    svod.append((imya, sha, strok, prin))

print()
print('строк принято всего: %d' % sum(s[3] for s in svod))
if not PISAT:
    print('сухой прогон, база не тронута; писать — с ключом --pisat')
    p.rollback()
    p.close()
    raise SystemExit
for imya, sha, strok, prin in svod:
    c.execute('insert or replace into prinyatye_potoki values (?,?,?,?,?)',
              (imya, sha, strok, prin, time.strftime('%Y-%m-%d %H:%M:%S')))
c.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
          (time.strftime('%Y-%m-%d %H:%M:%S'), 'КОНТАКТНЫЕ КАНАЛЫ 3-й СЕССИИ (14 файлов)',
           sum(s[2] for s in svod), sum(s[3] for s in svod), 0,
           'поле ищется списком синонимов; строка без http-ссылки не принимается'))
p.commit()
stalo = c.execute('select count(*) from contact_source').fetchone()[0]
print('contact_source: было %d, стало %d, ПРИБЫЛО %d' % (bylo, stalo, stalo - bylo))
p.close()

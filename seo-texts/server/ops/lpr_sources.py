# -*- coding: utf-8 -*-
"""Технические ЛПР из внешних источников: ЕИС (реестр + карточки) и hh-вакансии.

Владелец 29.07: «очень важны инженеры». Оба источника дают то, чего нет на
сайте компании — ДОЛЖНОСТЬ рядом с телефоном:
  * ЕИС: в извещении 44-ФЗ есть «Ответственное должностное лицо» с должностью,
    а карточка организации в реестре отдаёт контакты даже когда активных
    закупок нет (раньше ходили только в RSS по извещениям — компания без
    свежих процедур давала ноль);
  * hh: в вакансии «главный энергетик» контактным лицом часто идёт сам технарь,
    а комментарий к телефону прямо называет роль. Страницу вакансии конвейер
    не открывал ни разу.

Пишем в phone_contacts/emails с канон-ролью и ЖИВОЙ ссылкой на источник
(карточка закупки, карточка организации, страница вакансии).
Резюмируемо: lpr_sources_stream.jsonl; строки с ошибкой в резюм НЕ попадают,
чтобы разовый таймаут ЕИС не закрывал компанию навсегда.

Запуск: python lpr_sources.py [бюджет_сек] [потоков] [--only sales] [--src eis,hh]
"""
import io
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB          # noqa: E402
import enrich_contacts as EC     # noqa: E402

_поз = [a for a in sys.argv[1:] if not a.startswith('--')]
БЮДЖЕТ = float(_поз[0]) if _поз else 600.0
ПОТОКОВ = int(_поз[1]) if len(_поз) > 1 else 5
ТОЛЬКО = (sys.argv[sys.argv.index('--only') + 1]
          if '--only' in sys.argv else 'sales')
ИСТОЧНИКИ = set((sys.argv[sys.argv.index('--src') + 1]
                 if '--src' in sys.argv else 'eis,hh').split(','))
НАЧАЛО = time.time()
ПОТОК = r'C:\seostat\drop\lpr_sources_stream.jsonl'

db = EDB.EnrichDB()
e = db.cx
e.execute("""CREATE TABLE IF NOT EXISTS phone_contacts(
    inn TEXT, phone TEXT, person TEXT, role TEXT,
    source TEXT, source_url TEXT, updated_at TEXT,
    PRIMARY KEY (inn, phone, source_url))""")
e.commit()

цели = []
БАЗА = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
for строки in БАЗА.values():
    for x in строки:
        i = str(x.get('inn') or '').strip()
        if i and i not in [c[0] for c in цели]:
            цели.append((i, str(x.get('name') or '')))
if ТОЛЬКО != 'sales':
    for ln in io.open(r'C:\seostat\drop\drop-storage\centrifugal-core-inns.txt',
                      encoding='utf-8', errors='replace'):
        m = re.search(r'\b(\d{10}|\d{12})\b', ln)
        if m and m.group(1) not in [c[0] for c in цели]:
            цели.append((m.group(1), ''))

# имя компании: из базы продажников оно есть не всегда, добираем из enrich.db
имена = {r[0]: r[1] for r in e.execute(
    "select inn, name from companies where coalesce(name,'')<>''")}
цели = [(i, n or имена.get(i, '')) for i, n in цели]

сделано = set()
if os.path.exists(ПОТОК):
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            j = json.loads(ln)
            # ошибочные строки НЕ считаем сделанными: один таймаут ЕИС раньше
            # закрывал компанию навсегда
            if not j.get('err'):
                сделано.add(str(j['inn']))
        except Exception:  # noqa: BLE001
            continue
todo = [(i, n) for i, n in цели if i not in сделано]

замок = threading.Lock()
ф = io.open(ПОТОК, 'a', encoding='utf-8')
out = {'целей': len(todo), 'обработано': 0, 'ошибок': 0,
       'еис_карточек': 0, 'еис_людей': 0, 'еис_реестр': 0,
       'hh_вакансий': 0, 'hh_контактов': 0,
       'тел': 0, 'почт': 0, 'техЛПР': 0, 'примеры': []}

_ЦИФРЫ = re.compile(r'\D')


def _ключ(ном):
    return _ЦИФРЫ.sub('', str(ном or ''))[-10:]


def записать(inn, тел, почта, фио, должность, источник, урл):
    """Один контакт в базу: роль по канону, ссылка на страницу-источник."""
    роль = EDB.EnrichDB._canon_role(должность) if должность else ''
    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    if тел and len(_ключ(тел)) == 10:
        стар = e.execute('SELECT rowid, phone, person, role, source_url '
                         'FROM phone_contacts WHERE inn=?', (inn,)).fetchall()
        своя = next((r for r in стар if _ключ(r[1]) == _ключ(тел)), None)
        if своя:
            # непустое новое значение выигрывает, пустое не стирает старое;
            # роль-заглушку настоящая роль вытесняет
            стар_роль = своя[3] or ''
            нов_роль = (роль if роль and стар_роль in (
                '', 'общий', 'с сайта (обход)', 'общий (со страницы)',
                'контакты компании (чеко)', 'общий (чеко)') else (стар_роль or роль))
            e.execute('UPDATE phone_contacts SET person=?, role=?, source=?, '
                      'source_url=?, updated_at=? WHERE rowid=?',
                      (фио or своя[2] or '', нов_роль or '', источник,
                       урл or своя[4] or '', ts, своя[0]))
        else:
            e.execute('INSERT INTO phone_contacts'
                      '(inn,phone,person,role,source,source_url,updated_at) '
                      'VALUES (?,?,?,?,?,?,?)',
                      (inn, str(тел).strip(), фио or '', роль or '',
                       источник, урл or '', ts))
        out['тел'] += 1
        if роль in EDB.EnrichDB.TECH_ROLES:
            out['техЛПР'] += 1
            if len(out['примеры']) < 12:
                out['примеры'].append({'инн': inn, 'тел': тел, 'фио': фио,
                                       'должность': должность, 'роль': роль,
                                       'источник': источник})
    if почта:
        db.add_email(inn, почта, role=должность or '', person=фио or '',
                     source=источник, source_url=урл or '')
        out['почт'] += 1


def работа(t):
    inn, имя = t
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return
    итог = {'inn': inn}
    try:
        if 'eis' in ИСТОЧНИКИ:
            орг = EC.find_zakupki_org(inn)
            if орг and орг.get('people'):
                with замок:
                    out['еис_реестр'] += 1
                    for ч in орг['people']:
                        записать(inn, ч.get('phone'), ч.get('email'),
                                 ч.get('person'), ч.get('post'),
                                 'zakupki:реестр', орг.get('url'))
                итог['реестр'] = len(орг['people'])
            z = EC.find_zakupki_contacts(inn, max_cards=8)
            if z and z.get('error'):
                итог['err'] = z['error'][:90]
            for c in ((z or {}).get('cards') or []):
                люди = c.get('people') or []
                with замок:
                    out['еис_карточек'] += 1
                    out['еис_людей'] += len(люди)
                    for ч in люди:
                        # если должности в карточке нет — контакт всё равно
                        # закупочный, роль ставим честно
                        записать(inn, ч.get('phone'), ч.get('email'),
                                 ч.get('person'),
                                 ч.get('post') or 'снабжение/закупки',
                                 'zakupki:eis', c.get('url'))
                итог['карточек'] = итог.get('карточек', 0) + 1
        if 'hh' in ИСТОЧНИКИ and имя:
            h = EC.hh_lpr_contacts({'name': имя, 'inn': inn})
            if h:
                with замок:
                    out['hh_вакансий'] += len(h.get('vacancies') or [])
                    for c in (h.get('contacts') or []):
                        out['hh_контактов'] += 1
                        записать(inn, c.get('phone'), c.get('email'),
                                 c.get('person'), c.get('post'),
                                 'hh:вакансия', c.get('url'))
                итог['hh'] = len(h.get('contacts') or [])
    except Exception as ex:  # noqa: BLE001
        итог['err'] = f'{type(ex).__name__}: {str(ex)[:70]}'
        with замок:
            out['ошибок'] += 1
    with замок:
        e.commit()
        out['обработано'] += 1
        ф.write(json.dumps(итог, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())


with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
    list(пул.map(работа, todo))
ф.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
# Chromium при teardown отдаёт rc255, хотя данные уже записаны: у
# browser_probe своя защита через os._exit, но она работает только когда
# он запущен процессом, а не импортирован. Отсюда «упавшие» прогоны с
# полным результатом в базе — выходим чисто сами.
sys.stdout.flush()
os._exit(0)

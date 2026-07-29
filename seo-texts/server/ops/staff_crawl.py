# -*- coding: utf-8 -*-
"""ШТАТНЫЙ обходчик рассыльщика (crawl_contacts) по обеим базам: он уже умеет
staff-страницы (сотрудники/команда/руководство), закупки/снабжение,
кириллические слаги, роли и ФИО, JS-рендер. Пишем в phone_contacts/emails с
source_url. Резюмируемо: staff_roles_stream.jsonl. Потоков 12 (внутри есть
собственные паузы pace). Запуск: python staff_crawl.py [бюджет_сек] [потоков]"""
import io
import json
import os
import re
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB
import enrich_contacts as EC

БЮДЖЕТ = float(sys.argv[1]) if len(sys.argv) > 1 else 480.0
ПОТОКОВ = int(sys.argv[2]) if len(sys.argv) > 2 else 40
НАЧАЛО = time.time()
ПОТОК = r'C:\seostat\drop\staff_roles_stream.jsonl'

db = EDB.EnrichDB()
e = db.cx

цели = {}
БАЗА = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
for строки in БАЗА.values():
    for x in строки:
        i = str(x.get('inn') or '').strip()
        if i and i not in цели:
            цели[i] = None
for ln in io.open(r'C:\seostat\drop\drop-storage\centrifugal-core-inns.txt',
                  encoding='utf-8', errors='replace'):
    m = re.search(r'\b(\d{10}|\d{12})\b', ln)
    if m:
        цели.setdefault(m.group(1), None)
for i in list(цели):
    r0 = e.execute('SELECT site FROM companies WHERE inn=?', (i,)).fetchone()
    цели[i] = (r0[0] if r0 else '') or ''
цели = {i: s for i, s in цели.items() if s}

сделано = set()
if os.path.exists(ПОТОК):
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            сделано.add(str(json.loads(ln)['inn']))
        except Exception:  # noqa: BLE001
            continue
todo = [(i, s) for i, s in цели.items() if i not in сделано]

замок = threading.Lock()
ф = io.open(ПОТОК, 'a', encoding='utf-8')
out = {'целей': len(todo), 'обработано': 0, 'почт': 0, 'тел': 0,
       'именных': 0, 'ошибок': 0, 'чужой_сайт': 0,
       'activity_обновлено': 0, 'конкурентов': 0}



_СТОП_ИМЯ = {
    'телефон', 'телефоны', 'почта', 'email', 'отдел', 'представители',
    'реализация', 'мастер', 'флеш', 'адрес', 'факс', 'приёмная', 'приемная',
    'контакты', 'контакт', 'директор', 'менеджер', 'снабжение', 'закупки',
    'продажи', 'сайт', 'россия', 'москва', 'офис', 'склад', 'бухгалтерия',
    'служба', 'секретарь', 'компания', 'группа', 'завод', 'филиал'}
_ОТЧ = ('ович', 'евич', 'ьич', 'овна', 'евна', 'ична', 'инична')


def _чистое_фио(текст):
    """ФИО из контекста или '' — режем товарные/служебные слова.
    Принимаем: «Фамилия Имя Отчество» или «Фамилия Имя»/«Имя Фамилия»,
    где ни одно слово не из стоп-листа и хотя бы одно похоже на имя."""
    if not текст:
        return ''
    слова = [w for w in текст.split()
             if w and w[0].isupper() and len(w) > 2
             and w.lower() not in _СТОП_ИМЯ and w.isalpha()]
    if len(слова) < 2:
        return ''
    хвост = слова[-3:] if len(слова) >= 3 else слова[-2:]
    if any(w.lower() in _СТОП_ИМЯ for w in хвост):
        return ''
    есть_отч = any(w.lower().endswith(_ОТЧ) for w in хвост)
    похоже = есть_отч or all(len(w) >= 3 for w in хвост[:2])
    return ' '.join(хвост) if похоже else ''


def валиден(с):
    ц = re.sub(r'\D', '', str(с))
    if len(ц) == 11 and ц[0] in '78':
        ц = ц[1:]
    return (len(ц) == 10 and ц[0] != '0' and ц[:3] != '000'
            and len(set(ц)) > 2 and len(set(ц[3:])) > 1)


def работа(t):
    inn, сайт = t
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return
    try:
        # контракт штатного обходчика: (текст, страницы, None, источники)
        текст, страницы, _x, csrc = EC.crawl_contacts(сайт, pace=(0.8, 2.0))
    except Exception as ex:  # noqa: BLE001
        with замок:
            out['ошибок'] += 1
            ф.write(json.dumps({'inn': inn, 'err': repr(ex)[:70]},
                               ensure_ascii=False) + '\n')
            ф.flush()
        return
    # ШТАТНОЕ извлечение ролей: провайдер (роли/ФИО/отделы/владение сайтом),
    # regex — фолбэк внутри самой функции
    имя = (e.execute('SELECT name FROM companies WHERE inn=?', (inn,)).fetchone()
           or [''])[0]
    try:
        роли = EC.extract_roles(текст or '', {'inn': inn, 'name': имя})
    except Exception as ex:  # noqa: BLE001
        with замок:
            out['ошибок'] += 1
            ф.write(json.dumps({'inn': inn, 'err': 'roles:' + repr(ex)[:60]},
                               ensure_ascii=False) + '\n')
            ф.flush()
        return
    роли = роли or {}
    # сайт не этой компании — контакты НЕ берём (иначе чужие данные в базе)
    if роли.get('owner_match') is False:
        with замок:
            ф.write(json.dumps({'inn': inn, 'skip': 'сайт не компании'},
                               ensure_ascii=False) + '\n')
            ф.flush()
            out['чужой_сайт'] += 1
            out['обработано'] += 1
        return
    урл_по_почте = {k: (v or {}).get('url') or сайт
                    for k, v in ((csrc or {}).get('emails') or {}).items()}
    почты = [{'email': (em.get('email') or '').lower(),
              'role': em.get('role') or '',
              'person': em.get('person') or '',
              'url': урл_по_почте.get((em.get('email') or '').lower(), сайт)}
             for em in (роли.get('emails') or []) if em.get('email')]
    телефоны = [{'phone': str(p), 'role': '', 'person': '',
                 'url': (страницы[0] if страницы else сайт)}
                for p in (роли.get('phones') or [])]
    активность = (роли.get('activity') or '').strip()
    конкурент = bool(роли.get('is_compressor_maker'))
    with замок:
        ts = time.strftime('%Y-%m-%dT%H:%M:%S')
        for em in почты:
            адрес = (em.get('email') if isinstance(em, dict) else em) or ''
            if not адрес:
                continue
            роль = (em.get('role') if isinstance(em, dict) else '') or ''
            перс = (em.get('person') if isinstance(em, dict) else '') or ''
            урл = (em.get('url') or em.get('source_url')
                   if isinstance(em, dict) else '') or сайт
            e.execute("INSERT OR IGNORE INTO emails(inn,email,role,person,"
                      "source,source_url,updated_at) VALUES(?,?,?,?,?,?,?)",
                      (inn, адрес.lower(), роль, перс, 'сайт:обход', урл, ts))
            out['почт'] += 1
            if перс:
                out['именных'] += 1
        for ph in телефоны:
            ном = (ph.get('phone') if isinstance(ph, dict) else ph) or ''
            if not ном or not валиден(ном):
                continue
            роль = (ph.get('role') if isinstance(ph, dict) else '') or ''
            перс = (ph.get('person') if isinstance(ph, dict) else '') or ''
            урл = (ph.get('url') or ph.get('source_url')
                   if isinstance(ph, dict) else '') or сайт
            e.execute('INSERT OR REPLACE INTO phone_contacts VALUES '
                      '(?,?,?,?,?,?,?)',
                      (inn, str(ном).strip(), перс,
                       роль or 'с сайта (обход)', 'сайт:обход', урл, ts))
            out['тел'] += 1
            if перс:
                out['именных'] += 1
        if активность:
            e.execute("UPDATE companies SET activity=? WHERE inn=? "
                      "AND COALESCE(activity,'')=''", (активность[:200], inn))
            out['activity_обновлено'] += 1
        if конкурент:
            e.execute("UPDATE companies SET is_competitor=1 WHERE inn=?", (inn,))
            out['конкурентов'] += 1
        e.commit()
        ф.write(json.dumps({'inn': inn, 'почт': len(почты),
                            'тел': len(телефоны)}, ensure_ascii=False) + '\n')
        ф.flush()
        out['обработано'] += 1


with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
    list(пул.map(работа, todo))
ф.close()
print(json.dumps(out, ensure_ascii=False, indent=1))

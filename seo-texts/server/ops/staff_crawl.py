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
# --no-browser выставляем ДО импорта: enrich_contacts читает NO_BROWSER на
# старте модуля. Нужен, чтобы отделить обычный обход от рендера браузером —
# прогон умирал без вывода, и подозрение первым делом на Chromium.
if '--no-browser' in sys.argv:
    os.environ['NO_BROWSER'] = '1'
import enrich_db as EDB
import enrich_contacts as EC

_поз = [a for a in sys.argv[1:] if not a.startswith('--')]
БЮДЖЕТ = float(_поз[0]) if len(_поз) > 0 else 480.0
ПОТОКОВ = int(_поз[1]) if len(_поз) > 1 else 40
НАЧАЛО = time.time()
# --only sales — только база продажников (555 ИНН), без ядра центробежных;
# --stream ИМЯ — свой файл резюма: у прогона с НОВЫМИ ролями старый чекпоинт
# отметил бы все компании обработанными и обход не пошёл бы вовсе
ТОЛЬКО = 'sales' if '--only' in sys.argv and sys.argv[
    sys.argv.index('--only') + 1:sys.argv.index('--only') + 2] == ['sales'] else ''
_имя = (sys.argv[sys.argv.index('--stream') + 1]
        if '--stream' in sys.argv else 'staff_roles_stream.jsonl')
ПОТОК = r'C:\seostat\drop' + '\\' + _имя
# кэш скачанных страниц: <ИНН>.json.gz со всеми HTML и склеенным текстом
КЭШ = r'C:\seostat\drop\pagecache'

db = EDB.EnrichDB()
e = db.cx

цели = {}
БАЗА = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
for строки in БАЗА.values():
    for x in строки:
        i = str(x.get('inn') or '').strip()
        if i and i not in цели:
            цели[i] = None
if ТОЛЬКО != 'sales':
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


_ДОБ = re.compile(r'(?:доб|вн|внутр|ext)\.?\s*[:№]?\s*(\d{1,5})', re.I)
_НОМЕР = re.compile(
    r'(?:\+?7|8)?[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}')
# заглушки, которые встречаются в шаблонах сайтов
_ПУСТЫШКИ = {'0000000000', '1234567890', '9999999999', '1111111111'}


def валиден(с):
    """Годен ли НОМЕР (без добавочного). Правило «в хвосте больше одной разной
    цифры» убрано: оно выбрасывало 8-800-555-55-55 и 495-777-77-77 — как раз
    номера крупных компаний. Отсекаем только явные заглушки."""
    ц = re.sub(r'\D', '', str(с))
    if len(ц) == 11 and ц[0] in '78':
        ц = ц[1:]
    return (len(ц) == 10 and ц[0] != '0' and ц[:3] != '000'
            and len(set(ц)) > 1 and ц not in _ПУСТЫШКИ)


def разобрать(с):
    """Строка со страницы -> [(номер, добавочный)].

    Зачем: старая проверка считала цифры во ВСЕЙ строке, поэтому
    «+7 495 123-45-67 доб. 205» давало 14 цифр и номер выбрасывался целиком —
    а добавочный это и есть прямой телефон конкретного человека. Две подряд
    записанные строки («…-67, …-68») тоже терялись обе.
    """
    с = str(с or '')
    из = []
    for m in _НОМЕР.finditer(с):
        осн = m.group(0).strip(' ,;')
        if not валиден(осн):
            continue
        d = _ДОБ.search(с[m.end():m.end() + 26])
        из.append((осн, d.group(1) if d else ''))
    return из


def _ключ_тел(строка):
    """Ключ дедупа: последние 10 цифр номера + добавочный (если он в строке)."""
    s = str(строка or '')
    d = _ДОБ.search(s)
    доб = d.group(1) if d else ''
    цифры = re.sub(r'\D', '', s[:d.start()] if d else s)[-10:]
    return цифры + (f'x{доб}' if доб else '')


def _записать(inn, ном, ключ, перс, роль_к, урл, ts):
    """Дописать телефон, не плодя дублей.

    У phone_contacts первичный ключ (inn, phone, source_url) — по СЫРОЙ строке
    и странице, поэтому один номер в трёх написаниях давал три строки, а
    «INSERT OR REPLACE» при совпадении затирал уже добытые роль и ФИО пустыми.
    Ищем свою строку по нормализованному ключу и ДОПОЛНЯЕМ её: непустое новое
    значение выигрывает, пустое — не стирает старое.
    """
    стар = e.execute(
        'SELECT rowid, phone, person, role, source_url FROM phone_contacts '
        'WHERE inn=?', (inn,)).fetchall()
    своя = next((r for r in стар if _ключ_тел(r[1]) == ключ), None)
    if своя:
        # заглушку «с сайта (обход)» настоящая роль вытесняет, обратно — нет
        стар_роль = (своя[3] or '')
        роль_нов = роль_к or (стар_роль if стар_роль else 'с сайта (обход)')
        if роль_к and стар_роль in ('', 'с сайта (обход)', 'общий',
                                    'общий (со страницы)'):
            роль_нов = роль_к
        elif not роль_к:
            роль_нов = стар_роль or 'с сайта (обход)'
        e.execute(
            'UPDATE phone_contacts SET phone=?, person=?, role=?, source=?, '
            'source_url=?, updated_at=? WHERE rowid=?',
            (ном if len(ном) >= len(своя[1] or '') else своя[1],
             перс or своя[2] or '', роль_нов,
             'сайт:обход', урл or своя[4] or '', ts, своя[0]))
    else:
        e.execute('INSERT INTO phone_contacts'
                  '(inn,phone,person,role,source,source_url,updated_at) '
                  'VALUES (?,?,?,?,?,?,?)',
                  (inn, ном, перс, роль_к or 'с сайта (обход)',
                   'сайт:обход', урл, ts))
    out['тел'] += 1
    if роль_к:
        out['с_ролью'] = out.get('с_ролью', 0) + 1
    if перс:
        out['именных'] += 1


def работа(t):
    inn, сайт = t
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return
    try:
        # контракт штатного обходчика: (текст, страницы, None, источники)
        # cache_dir: скачанный HTML ложится на дроп-сервер, чтобы переразметку
        # ролей можно было прогнать по сохранённым страницам, не обходя сайты
        # заново (владелец 29.07)
        текст, страницы, _x, csrc = EC.crawl_contacts(
            сайт, pace=(0.8, 2.0), cache_dir=КЭШ, cache_key=inn)
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
        # extract_roles возвращает ПАРУ (данные, способ) — 'provider' или
        # 'regex…'. Раньше пара присваивалась целиком, и следующая же строка
        # звала .get у кортежа: AttributeError вылетал ВНЕ try, а pool.map
        # перевыбрасывал его наружу и ронял весь прогон на первой компании.
        роли, способ = EC.extract_roles(текст or '', {'inn': inn, 'name': имя})
        роли = роли or {}
        # сайт не этой компании — контакты НЕ берём (иначе чужие данные в базе)
        чужой = роли.get('owner_match') is False
    except Exception as ex:  # noqa: BLE001
        with замок:
            out['ошибок'] += 1
            ф.write(json.dumps({'inn': inn, 'err': 'roles:' + repr(ex)[:60]},
                               ensure_ascii=False) + '\n')
            ф.flush()
        return
    out[f'способ_{способ}'] = out.get(f'способ_{способ}', 0) + 1
    if чужой:
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
    # Телефоны: роль/ФИО из ответа модели (phone_roles), страница-источник —
    # по самому номеру из csrc['phones'], а НЕ «страницы[0]» на всю компанию.
    # Раньше роль и ФИО были жёстко пустыми, а ссылка у всех номеров одна —
    # первая обойденная страница; «читать источник» вело не туда, где номер.
    урл_по_тел = {k: (v or {}).get('url') or сайт
                  for k, v in ((csrc or {}).get('phones') or {}).items()}
    запас_урл = (страницы[0] if страницы else сайт)
    телефоны = []
    for p in (роли.get('phone_roles') or роли.get('phones') or []):
        if isinstance(p, dict):
            ном, роль_т = str(p.get('phone') or ''), (p.get('role') or '')
            перс_т, отдел = (p.get('person') or ''), (p.get('dept') or '')
        else:
            ном, роль_т, перс_т, отдел = str(p), '', '', ''
        if not ном:
            continue
        ключ = re.sub(r'\D', '', ном)[-10:]
        # отдел как подпись роли, когда должности модель не увидела: «отдел
        # главного энергетика» на сайте пишут чаще, чем должность человека
        телефоны.append({'phone': ном, 'role': роль_т or отдел, 'person': перс_т,
                         'url': урл_по_тел.get(ключ, запас_урл)})
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
            # через add_email, а не INSERT OR IGNORE: у метода есть ON CONFLICT,
            # который ДОПИСЫВАЕТ роль/ФИО/ссылку к уже известному адресу и
            # приводит роль к канону. С «OR IGNORE» повторный обход не мог
            # улучшить запись — новая роль «гл.энергетик» молча терялась.
            db.add_email(inn, адрес.lower(), role=роль, person=перс,
                         source='сайт:обход', source_url=урл)
            out['почт'] += 1
            if перс:
                out['именных'] += 1
        for ph in телефоны:
            сырое = (ph.get('phone') if isinstance(ph, dict) else ph) or ''
            роль = (ph.get('role') if isinstance(ph, dict) else '') or ''
            перс = (ph.get('person') if isinstance(ph, dict) else '') or ''
            урл = (ph.get('url') or ph.get('source_url')
                   if isinstance(ph, dict) else '') or сайт
            # роль телефона — по тому же канону, что и у почт
            роль_к = EDB.EnrichDB._canon_role(роль) if роль else ''
            for осн, доб in разобрать(сырое):
                ном = f'{осн} доб.{доб}' if доб else осн
                # ключ дедупа с добавочным: «доб.205» — ОТДЕЛЬНЫЙ человек,
                # схлопывать его с общим номером приёмной нельзя
                ключ = re.sub(r'\D', '', осн)[-10:] + (f'x{доб}' if доб else '')
                _записать(inn, ном, ключ, перс, роль_к, урл, ts)
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

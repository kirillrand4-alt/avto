# -*- coding: utf-8 -*-
"""Переразметка ролей провайдером по УЖЕ СКАЧАННЫМ страницам.

Структурный перечёт кэша (pagecache_reparse) забрал то, что лежит в блоке
человека: ФИО, должность, его номер. Но замер показал, что новая регулярка
видит на тех же страницах 720 номеров, а в блоках людей их всего несколько
десятков. Остальное — ОТДЕЛЫ: «отдел материально-технического снабжения
+7 (34764) 6 42 26». Роль такого номера живёт в соседней ячейке таблицы, и
надёжно её снимает только модель.

Почему это не повтор старой работы: умная обрезка (_contact_cap) строит окна
вокруг НАЙДЕННЫХ телефонов, а старая регулярка номера с кодом из 4-5 цифр не
находила вовсе. Значит окна вокруг них не ставились, и в 24000 символов,
которые видит модель, целые куски справочника не попадали. Теперь попадут.

Тяжёлая работа идёт через провайдерский API (правило владельца), обход не
делается вовсе — страницы уже на диске. Резюмируемо: pagecache_roles.jsonl,
компания с ошибкой в резюм не попадает. По умолчанию СУХОЙ ПРОГОН.

Запуск: python pagecache_roles.py [бюджет_сек] [потоков] [--apply] [--limit N]
"""
import gzip
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
БЮДЖЕТ = float(_поз[0]) if _поз else 900.0
ПОТОКОВ = int(_поз[1]) if len(_поз) > 1 else 4
ПРИМЕНИТЬ = '--apply' in sys.argv
ЛИМИТ = int(sys.argv[sys.argv.index('--limit') + 1]
            if '--limit' in sys.argv else 100000)
КЭШ = r'C:\seostat\drop\pagecache'
ПОТОК = r'C:\seostat\drop\pagecache_roles.jsonl'
НАЧАЛО = time.time()

db = EDB.EnrichDB()
e = db.cx
замок = threading.Lock()


def _норм(с):
    ц = re.sub(r'\D', '', с or '')
    if len(ц) == 11 and ц[0] in '78':
        ц = ц[1:]
    return ц[:10] if len(ц) >= 10 else ''


def читать(имя):
    п = os.path.join(КЭШ, имя)
    try:
        if имя.endswith('.gz'):
            with gzip.open(п, 'rt', encoding='utf-8', errors='replace') as f:
                return json.load(f)
        return json.load(io.open(п, encoding='utf-8', errors='replace'))
    except Exception:  # noqa: BLE001
        return None


def инн_по_страницам(j, имя):
    """ИНН владельца кэша: ИМЯ ФАЙЛА, затем поле в кэше, домен — в последнюю
    очередь и только точным единственным совпадением.

    Поиск по домену подстрокой дал 12 чужих привязок на 211 файлов: «ozm.ru»
    вошёл в «ao-ozm.ru» и телефоны «Микрона» уехали «Механику». А на
    halopolymer.ru и europlast.ru честно сидят по два разных юрлица, и по
    домену их не разделить в принципе — там правильный ответ «не знаю».
    """
    m = re.match(r'(\d{10}|\d{12})', имя or '')
    if m:
        return m.group(1)
    if j.get('inn'):
        return str(j['inn'])
    for p in (j.get('pages') or [])[:4]:
        d = EC._domain((p or {}).get('url') or '')
        if not d:
            continue
        нашли = [r[0] for r in e.execute(
            'SELECT inn FROM companies WHERE lower(site)=? OR lower(site)=?',
            (d, 'www.' + d))]
        if len(нашли) == 1:
            return нашли[0]
    return ''


сделано = set()
if os.path.exists(ПОТОК):
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            x = json.loads(ln)
            if not x.get('err'):
                сделано.add(x['файл'])
        except Exception:  # noqa: BLE001
            continue

файлы = [x for x in sorted(os.listdir(КЭШ))[:ЛИМИТ]
         if x not in сделано] if os.path.isdir(КЭШ) else []
ф = io.open(ПОТОК, 'a', encoding='utf-8')
out = {'файлов': len(файлы), 'обработано': 0, 'ошибок': 0, 'без_инн': 0,
       'провайдер_ок': 0, 'фолбэк': 0, 'телефонов_ново': 0,
       'телефонов_с_ролью': 0, 'почт_ново': 0,
       'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой прогон (--apply)',
       'примеры': []}


def работа(имя):
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return
    итог = {'файл': имя}
    try:
        j = читать(имя)
        if not j:
            итог['err'] = 'нечитаемый кэш'
            raise RuntimeError(итог['err'])
        inn = инн_по_страницам(j, имя)
        if not inn:
            with замок:
                out['без_инн'] += 1
            итог['err'] = 'инн не сопоставлен'
            raise RuntimeError(итог['err'])
        итог['inn'] = inn
        имя_к = (e.execute('SELECT name FROM companies WHERE inn=?',
                           (inn,)).fetchone() or [''])[0]
        куски = [EC._текст(p.get('html') or '')
                 for p in (j.get('pages') or []) if isinstance(p, dict)]
        текст = EC._contact_cap('\n'.join(x for x in куски if x))
        if not текст.strip():
            итог['err'] = 'пустой текст'
            raise RuntimeError(итог['err'])
        data, how = EC.extract_roles(текст, {'name': имя_к, 'inn': inn})
        итог['разбор'] = how
        with замок:
            if str(how).startswith('regex'):
                out['фолбэк'] += 1
            else:
                out['провайдер_ок'] += 1
        роли, _голые = EC._norm_phone_roles(data.get('phone_roles')
                                            or data.get('phones'))
        было_тел = {_норм(r[0]) for r in e.execute(
            'SELECT phone FROM phone_contacts WHERE inn=?', (inn,))}
        было_почт = {(r[0] or '').lower() for r in e.execute(
            'SELECT email FROM emails WHERE inn=?', (inn,))}
        адрес = ((j.get('pages') or [{}])[0] or {}).get('url') or ''
        for p in роли:
            н = _норм(p['phone'])
            if not н or н in было_тел:
                continue
            было_тел.add(н)
            роль = EDB.EnrichDB._canon_role(p.get('role') or p.get('dept') or '')
            with замок:
                out['телефонов_ново'] += 1
                if роль:
                    out['телефонов_с_ролью'] += 1
                if len(out['примеры']) < 14:
                    out['примеры'].append(
                        {'инн': inn, 'тел': p['phone'], 'роль': роль,
                         'кто': p.get('person') or p.get('dept')})
                if ПРИМЕНИТЬ:
                    e.execute(
                        'INSERT OR IGNORE INTO phone_contacts'
                        '(inn, phone, person, role, source, source_url,'
                        ' updated_at) VALUES(?,?,?,?,?,?,datetime("now"))',
                        (inn, p['phone'], p.get('person') or '', роль or '',
                         'сайт компании', адрес))
        for em in (data.get('emails') or []):
            а = (em.get('email') or '').lower().strip()
            if not а or а in было_почт:
                continue
            было_почт.add(а)
            with замок:
                out['почт_ново'] += 1
                if ПРИМЕНИТЬ:
                    db.add_email(inn, а, role=em.get('role') or '',
                                 person=em.get('person') or '',
                                 source='сайт компании', source_url=адрес)
        итог['телефонов'] = len(роли)
    except Exception as ex:  # noqa: BLE001
        итог.setdefault('err', f'{type(ex).__name__}: {str(ex)[:70]}')
        with замок:
            out['ошибок'] += 1
    with замок:
        if ПРИМЕНИТЬ:
            e.commit()
        out['обработано'] += 1
        ф.write(json.dumps(итог, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())


with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
    list(пул.map(работа, файлы))
ф.close()
print(json.dumps(out, ensure_ascii=False, indent=1)[:5000])
print(json.dumps({k: v for k, v in out.items() if k != 'примеры'},
                 ensure_ascii=False))
sys.stdout.flush()
os._exit(0)

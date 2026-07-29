# -*- coding: utf-8 -*-
"""Гриф «УТВЕРЖДАЮ» в документации закупок (способ А5).

Техническую документацию закупки утверждает ГЛАВНЫЙ ИНЖЕНЕР, и его должность
с ФИО стоят на титульном листе. Работает даже там, где состав закупочной
комиссии не публикуется, а извещение 44-ФЗ даёт лишь контрактного управляющего.
Приёма не было ни в одной из четырнадцати линз разбора — он нашёлся только при
работе с живыми документами.

Путь: RSS ЕИС по ИНН -> карточка извещения -> вкладка документов -> файлы.
Читаем docx, rtf и PDF. Приоритет файлов: техническое задание и документация о
закупке, извещение последним.

ВАЖНО ПРО ПЕРВЫЙ ЗАМЕР. Прогон 29.07 дал 29 человек и лишь ОДНОГО технического
ЛПР — и этот результат надо считать недействительным: тогда PDF пропускались,
а техническое задание в ЕИС выкладывают в PDF чаще, чем в docx. То есть мерили
не источник, а нашу неспособность его прочесть. После появления разбора PDF
способ нужно перемерить с нуля.

Пишем в people с должностью и ссылкой НА ДОКУМЕНТ, чтобы можно было проверить
глазами. Резюмируемо: utverzhdayu_stream.jsonl, ошибки в резюм не попадают.

Запуск: python utverzhdayu.py [бюджет_сек] [потоков] [--only sales] [--inn ИНН]
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
ПОТОКОВ = int(_поз[1]) if len(_поз) > 1 else 4
ТОЛЬКО = (sys.argv[sys.argv.index('--only') + 1]
          if '--only' in sys.argv else 'sales')
ОДИН = (sys.argv[sys.argv.index('--inn') + 1] if '--inn' in sys.argv else '')
_имя = (sys.argv[sys.argv.index('--stream') + 1]
        if '--stream' in sys.argv else 'utverzhdayu_stream.jsonl')
ПОТОК = r'C:\seostat\drop' + '\\' + _имя
НАЧАЛО = time.time()

db = EDB.EnrichDB()
e = db.cx

# сколько карточек и файлов смотреть на компанию: гриф печатают на КАЖДОМ
# документе, поэтому первых обычно хватает, а ЕИС ходим вежливо
КАРТОЧЕК = int(os.environ.get('UTV_CARDS', '3'))
ФАЙЛОВ = int(os.environ.get('UTV_FILES', '3'))


def цели():
    из, было = [], set()
    БАЗА = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
    for строки in БАЗА.values():
        for x in строки:
            i = str(x.get('inn') or '').strip()
            if i and i not in было:
                было.add(i)
                из.append(i)
    if ТОЛЬКО != 'sales':
        for ln in io.open(r'C:\seostat\drop\drop-storage\centrifugal-core-inns.txt',
                          encoding='utf-8', errors='replace'):
            m = re.search(r'\b(\d{10}|\d{12})\b', ln)
            if m and m.group(1) not in было:
                было.add(m.group(1))
                из.append(m.group(1))
    return из


сделано = set()
if os.path.exists(ПОТОК):
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            j = json.loads(ln)
            if not j.get('err'):
                сделано.add(str(j['inn']))
        except Exception:  # noqa: BLE001
            continue
todo = [ОДИН] if ОДИН else [i for i in цели() if i not in сделано]

замок = threading.Lock()
ф = io.open(ПОТОК, 'a', encoding='utf-8')
out = {'целей': len(todo), 'обработано': 0, 'ошибок': 0, 'карточек': 0,
       'файлов_прочитано': 0, 'pdf_пропущено': 0, 'грифов': 0, 'людей': 0,
       'техЛПР': 0, 'примеры': []}


def _вес(имя):
    """Порядок чтения файлов: техзадание и документация раньше извещения."""
    н = (имя or '').lower()
    if 'техническ' in н or 'тз' in н:
        return 0
    if 'документац' in н or 'требован' in н:
        return 1
    if 'извещен' in н:
        return 3
    return 2


def работа(inn):
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return
    итог = {'inn': inn}
    try:
        z = EC.find_zakupki_contacts(inn, max_cards=КАРТОЧЕК)
        if z and z.get('error'):
            итог['err'] = str(z['error'])[:90]
            raise RuntimeError(итог['err'])
        нашли = 0
        for c in ((z or {}).get('cards') or [])[:КАРТОЧЕК]:
            if time.time() - НАЧАЛО > БЮДЖЕТ:
                break
            файлы = EC.eis_documents(c.get('url') or '')
            with замок:
                out['карточек'] += 1
            файлы = [f for f in файлы if EC._ДОК_ФОРМАТ.search(f[0] or '')]
            файлы.sort(key=lambda f: _вес(f[0]))
            for имя, url in файлы[:ФАЙЛОВ]:
                if time.time() - НАЧАЛО > БЮДЖЕТ:
                    break
                txt = EC.doc_text(url)
                with замок:
                    if txt:
                        out['файлов_прочитано'] += 1
                    else:
                        out['pdf_пропущено'] += 1
                if not txt:
                    continue
                for ч in EC.utverzhdayu(txt):
                    if not ч.get('person'):
                        continue
                    роль = EDB.EnrichDB._canon_role(ч.get('post') or '')
                    with замок:
                        out['грифов'] += 1
                        db.add_person(inn, ч['person'], post=ч.get('post') or '',
                                      source='zakupki:утверждаю', source_url=url)
                        out['людей'] += 1
                        нашли += 1
                        if роль in EDB.EnrichDB.TECH_ROLES:
                            out['техЛПР'] += 1
                            if len(out['примеры']) < 12:
                                out['примеры'].append(
                                    {'инн': inn, 'фио': ч['person'],
                                     'должность': ч.get('post'), 'роль': роль,
                                     'файл': (имя or '')[:48]})
                time.sleep(0.6)
        итог['людей'] = нашли
    except Exception as ex:  # noqa: BLE001
        итог.setdefault('err', f'{type(ex).__name__}: {str(ex)[:70]}')
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
sys.stdout.flush()
os._exit(0)

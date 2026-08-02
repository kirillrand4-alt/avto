# -*- coding: utf-8 -*-
"""Поиск сайта по 1089 целям без сайта — параллельно, с тем же двойным рубежом.

Чем отличается от `sayty_dlya_celey`: тот идёт строго по одной компании, и
при бюджете 1100 секунд успевает около сотни. На 1089 целях это одиннадцать
кругов, то есть ночь целиком. Здесь внешний цикл в пуле: сам запрос в выдачу
всё равно ограничен семафором `_SEM_XMLRIVER` (каналы аккаунта, их 4), но
проверка ИНН на странице — девять параллельных загрузок на компанию — идёт
одновременно у нескольких целей, и время перестаёт быть суммой ожиданий.

Рубеж привязки НЕ ослаблен и повторяет исходный оп дословно:
  * `_is_own_site` внутри `find_site_via_xmlriver` отсекает агрегаторы;
  * страница качается, и на ней ищется ИНН; совпал — в `site`, не совпал —
    только в `cand_site`. Молча в `site` не пишем никогда.

Имя для запроса берём ИЗ БАЗЫ на момент обращения, а не из файла целей: файл
собран из CSV, где имена обрезаны до 60 символов, а dadata дописывает полные
прямо сейчас. Обрезанное имя — это гарантированный промах выдачи, поэтому
цель с обрезанным именем и без полного в базе ПРОПУСКАЕТСЯ, а не отправляется
в выдачу «как есть»: пустой ответ на обрубке мы бы записали в журнал и больше
никогда не переспросили.

Durable: журнал `sayty_massovo.jsonl` с flush+fsync на каждую цель, запись в
`companies` через `upsert_company`. Резюмируемо: пройденное берётся из
журнала И из журнала прежнего опа, чтобы не переспрашивать одно и то же.

Запуск: python sayty_massovo.py [--targets ФАЙЛ] [--lim N] [--potokov N]
                                [--budget СЕК] [--dry]
"""
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\server\ops')
import enrich_db as EDB       # noqa: E402
import enrich_contacts as EC  # noqa: E402
import sayty_dlya_celey as SDC  # noqa: E402  — берём его `инн_на_странице`

СУХОЙ = '--dry' in sys.argv


def арг(имя, поум):
    return sys.argv[sys.argv.index(имя) + 1] if имя in sys.argv else поум


ЦЕЛИ = арг('--targets', r'C:\seostat\drop\celi-1486.jsonl')
ЛИМ = int(арг('--lim', '1200'))
ПОТОКОВ = int(арг('--potokov', '8'))
БЮДЖЕТ = float(арг('--budget', '1100'))
ЖУРНАЛ = r'C:\sender\server\sayty_massovo.jsonl'
ЖУРНАЛ_СТАРЫЙ = r'C:\sender\server\sayty_dlya_celey.jsonl'

_ЗАМОК = threading.Lock()


def _прочитать_журнал(путь, куда):
    if not os.path.exists(путь):
        return
    with open(путь, encoding='utf-8', errors='replace') as ж:
        for строка in ж:
            try:
                и = json.loads(строка).get('инн')
            except Exception:  # noqa: BLE001
                continue
            if и:
                куда.add(и)


def main():
    цели = []
    with open(ЦЕЛИ, encoding='utf-8') as ф:
        for строка in ф:
            try:
                цели.append(json.loads(строка))
            except Exception:  # noqa: BLE001
                continue

    db = EDB.EnrichDB()
    q = db.cx.execute
    имена = {}
    есть_сайт = set()
    for и, н, с in q("SELECT inn,COALESCE(name,''),COALESCE(site,'') "
                     "FROM companies"):
        имена[и] = н
        if с.strip():
            есть_сайт.add(и)
    опрошены = set()
    _прочитать_журнал(ЖУРНАЛ, опрошены)
    _прочитать_журнал(ЖУРНАЛ_СТАРЫЙ, опрошены)

    работа, без_имени = [], 0
    for c in цели:
        if c['inn'] in есть_сайт or c['inn'] in опрошены:
            continue
        имя = (имена.get(c['inn']) or '').strip()
        if not имя:
            имя = (c.get('poln') or '').strip()
            if c.get('imya_obrezano'):
                # обрубок в выдачу не отправляем: промах записался бы в
                # журнал и цель больше не переспросили бы никогда
                без_имени += 1
                continue
        работа.append((c['inn'], имя, c.get('region') or ''))
    работа = работа[:ЛИМ]

    print(f'целей в файле: {len(цели)}; уже с сайтом: {len(есть_сайт & {c["inn"] for c in цели})}; '
          f'уже опрошены: {len(опрошены)}', flush=True)
    print(f'ждут полного имени (обрезано, в ЕГРЮЛ ещё не добрано): {без_имени}',
          flush=True)
    print(f'в работу: {len(работа)}, потоков {ПОТОКОВ}, бюджет {БЮДЖЕТ:.0f}с',
          flush=True)
    if not работа:
        print('искать нечего')
        return

    было_с = q("SELECT COUNT(*) FROM companies WHERE COALESCE(site,'')<>''"
               ).fetchone()[0]
    начало = time.time()
    стоп = threading.Event()

    def одна(зад):
        инн, имя, регион = зад
        if стоп.is_set():
            return None
        try:
            сайт, откуда, _ = EC.find_site_via_xmlriver(
                {'name': имя, 'city': регион})
        except Exception as e:  # noqa: BLE001
            return {'инн': инн, 'имя': имя[:70], 'сайт': '',
                    'откуда': f'ошибка:{str(e)[:50]}', 'инн_на_странице': False}
        if not сайт:
            return {'инн': инн, 'имя': имя[:70], 'сайт': '', 'откуда': откуда,
                    'инн_на_странице': False}
        try:
            совпал, где = SDC.инн_на_странице(сайт, инн)
        except Exception:  # noqa: BLE001
            совпал, где = False, ''
        return {'инн': инн, 'имя': имя[:70], 'сайт': сайт, 'откуда': откуда,
                'инн_на_странице': совпал, 'где': где}

    подтв = канд = пусто = ошибок = сделано = 0
    with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
        будущие = {пул.submit(одна, з): з for з in работа}
        for ф in as_completed(будущие):
            if time.time() - начало > БЮДЖЕТ:
                стоп.set()
            зап = ф.result()
            if зап is None:
                continue
            сделано += 1
            with _ЗАМОК:
                with open(ЖУРНАЛ, 'a', encoding='utf-8') as ж:
                    ж.write(json.dumps(зап, ensure_ascii=False) + '\n')
                    ж.flush()
                    os.fsync(ж.fileno())
            if зап['откуда'].startswith(('ошибка:', 'xmlriver-err')) or \
                    зап['откуда'] == 'no-xmlriver-key':
                ошибок += 1
                if ошибок <= 3:
                    print(f'  {зап["инн"]}: {зап["откуда"]}', flush=True)
                continue
            if not зап['сайт']:
                пусто += 1
                continue
            if not СУХОЙ:
                with _ЗАМОК:
                    if зап['инн_на_странице']:
                        db.upsert_company(зап['инн'], site=зап['сайт'])
                    else:
                        db.upsert_company(зап['инн'], cand_site=зап['сайт'])
            подтв += 1 if зап['инн_на_странице'] else 0
            канд += 0 if зап['инн_на_странице'] else 1
            if сделано % 50 == 0:
                print(f'  … {сделано}/{len(работа)}: подтв {подтв}, канд {канд}, '
                      f'пусто {пусто}, ошибок {ошибок}, '
                      f'{time.time() - начало:.0f}с', flush=True)

    стало_с = q("SELECT COUNT(*) FROM companies WHERE COALESCE(site,'')<>''"
                ).fetchone()[0]
    print()
    print('=== ИЗ БАЗЫ (не из счётчиков прогона) ===')
    print(f'  компаний с подтверждённым сайтом: было {было_с} → стало {стало_с} '
          f'(+{стало_с - было_с})')
    print(f'ИТОГ {json.dumps({"обработано": сделано, "подтверждено": подтв, "кандидатов": канд, "выдача_пуста": пусто, "ошибок": ошибок, "секунд": round(time.time() - начало)}, ensure_ascii=False)}')


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""P25: реквизиты ЕГРЮЛ по 491 покупателю через DaData → enrich.db и p25.db.

ЧТО ЭТО ЗАКРЫВАЕТ. Пункт ТЗ моей части: «DaData по 491 ИНН: ОГРН, статус ЕГРЮЛ,
адрес, ОКВЭД, руководитель. Ликвидированные — пометить, но НЕ выбрасывать».
ОГРН нужен ещё и как КЛЮЧ К ЧЕКО: чеко открывается по ОГРН, и из-за этого на
центробежке 33 карточки молчали, пока ключ не нашли.

НЕ ПИШУ ВТОРОЙ РАЗБОР. Запрос и разбор ответа DaData уже обкатаны в
`dadata_rekvizity.py` — импортирую их оттуда. Две копии одного разбора однажды
разойдутся, и заметит это продавец, а не мы.

ГДЕ ЧТО ЛЕЖИТ:
  enrich.db.requisites — общий справочник ЕГРЮЛ по ИНН, он и так общий на обе
        задачи (там уже 2 392 ИНН). Реквизиты — объективные данные из реестра,
        а не наши выводы, поэтому «сбор с нуля» их не касается: правило про
        людей и доказательства, которые несут НАШИ ошибки;
  p25.db.company — то, что видит продавец: регион, адрес, директор, статус,
        ОКВЭД основной и все;
  p25_dadata.jsonl — поток с fsync, переживает рестарт.

ЛИКВИДИРОВАННЫЕ НЕ ВЫБРАСЫВАЮТСЯ: статус пишется как есть, а строка остаётся —
они покупали, значит платил кто-то и правопреемник существует.

Резюмируемо: уже опрошенные ИНН пропускаются, прогон можно бить на куски.
Запуск: python p25_dadata.py [--lim N] [--potok N] [--vse]
"""
import io
import json
import os
import re
import sqlite3
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\server\ops')
import enrich_db as EDB  # noqa: E402

P25 = r'C:\seostat\data\p25.db'
ПОТОК = r'C:\seostat\drop\p25_dadata.jsonl'
ВСЕ = '--vse' in sys.argv
_замок = threading.Lock()


def арг(имя, поум):
    try:
        return int(sys.argv[sys.argv.index(имя) + 1])
    except (ValueError, IndexError):
        return поум


ЛИМ = арг('--lim', 600)
ПОТОКОВ = арг('--potok', 6)

try:
    import dadata_rekvizity as DR
except Exception as ex:  # noqa: BLE001
    print('не импортируется dadata_rekvizity:', str(ex)[:200])
    raise SystemExit(1)

DR.ТОКЕН = os.environ.get('DADATA_TOKEN', '') or getattr(DR, 'ТОКЕН', '')
if not DR.ТОКЕН:
    print('НЕТ DADATA_TOKEN в окружении раннера')
    raise SystemExit(1)


def регион_из_адреса(адрес):
    """Регион — первая часть адреса до города. DaData отдаёт его строкой."""
    а = str(адрес or '')
    м = re.match(r'^\s*([^,]+(?:обл|край|респ|Респ|АО|округ|город|г\.)[^,]*)', а)
    if м:
        return м.group(1).strip()
    части = [ч.strip() for ч in а.split(',') if ч.strip()]
    return части[0] if части else ''


def main():
    db = EDB.EnrichDB()
    цб = sqlite3.connect(P25, timeout=30)
    цели = [str(r[0]) for r in цб.execute(
        'SELECT inn FROM company ORDER BY COALESCE(mesto_po_summe, 999999)')]
    кол = {r[1] for r in цб.execute('PRAGMA table_info(company)')}
    уже = {}
    for и, о, ст in цб.execute(
            "SELECT inn, COALESCE(istochnik_rekvizitov,''), "
            "COALESCE(status_egrul,'') FROM company"):
        уже[str(и)] = bool(str(о).strip() or str(ст).strip())
    цб.close()
    todo = [и for и in цели if ВСЕ or not уже.get(и)][:ЛИМ]
    print(f'целей всего {len(цели)}, к опросу {len(todo)}, потоков {ПОТОКОВ}')

    стат = Counter()
    правки = []

    def один(инн):
        try:
            д = DR.спросить(инн)
        except Exception as ex:  # noqa: BLE001
            with _замок:
                стат['СБОЙ запроса'] += 1
            return {'inn': инн, 'err': f'{type(ex).__name__}: {str(ex)[:120]}'}
        if not д:
            with _замок:
                стат['DaData не знает ИНН'] += 1
            return {'inn': инн, 'err': 'нет данных'}
        поля = DR.разобрать(д)
        with _замок:
            стат['получено'] += 1
            if поля.get('ogrn'):
                стат['  с ОГРН (ключ к чеко)'] += 1
            ст = str(поля.get('status') or '').upper()
            if ст and ст != 'ACTIVE':
                стат[f'  статус {ст}'] += 1
            правки.append((инн, поля))
        return {'inn': инн, **{к: поля.get(к, '') for к in
                               ('ogrn', 'status', 'director', 'okved_main')}}

    записи = []
    with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
        for з in пул.map(один, todo):
            записи.append(з)

    # 1) СЕРВЕРНОЕ ХРАНИЛИЩЕ: общий справочник ЕГРЮЛ
    в_req = 0
    for инн, поля in правки:
        try:
            есть = {r[1] for r in db.cx.execute('PRAGMA table_info(requisites)')}
            зн = {к: v for к, v in поля.items() if к in есть}
            зн['inn'] = инн
            зн['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
            имена = list(зн)
            db.cx.execute(
                f"INSERT INTO requisites ({','.join(имена)}) "
                f"VALUES ({','.join('?' * len(имена))}) "
                f"ON CONFLICT(inn) DO UPDATE SET "
                + ', '.join(f'{к}=excluded.{к}' for к in имена if к != 'inn'),
                [зн[к] for к in имена])
            в_req += 1
        except Exception as ex:  # noqa: BLE001
            print('requisites:', инн, str(ex)[:100])
            break
    db.cx.commit()

    # 2) КАРТОЧКА ПРОДАВЦА
    цб = sqlite3.connect(P25, timeout=30)
    до = цб.total_changes
    for инн, поля in правки:
        зн = {
            'region': регион_из_адреса(поля.get('address')),
            'adres': поля.get('address', ''),
            'direktor': ' '.join(x for x in (поля.get('director', ''),
                                             поля.get('director_post', '')) if x),
            'status_egrul': поля.get('status', ''),
            'okved': поля.get('okved_main', ''),
            'okvedy_vse': поля.get('okved_all', ''),
            'ssch': poluchit(поля, 'employees'),
            'istochnik_rekvizitov': 'ЕГРЮЛ через DaData findById/party',
        }
        зн = {к: v for к, v in зн.items() if к in кол and str(v).strip()}
        if not зн:
            continue
        цб.execute(f"UPDATE company SET {', '.join(f'{к}=?' for к in зн)} "
                   f"WHERE inn=?", list(зн.values()) + [инн])
    цб.commit()
    изменено = цб.total_changes - до
    с_огрн = 0
    for инн, поля in правки:
        if поля.get('ogrn'):
            с_огрн += 1
    заполнено = цб.execute(
        "SELECT COUNT(*) FROM company WHERE COALESCE(status_egrul,'')<>''").fetchone()[0]
    цб.close()

    with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
        for з in записи:
            ф.write(json.dumps(з, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())

    print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
    print(f'в requisites записано: {в_req}')
    print(f'строк карточек изменено: {изменено}')
    print(f'ОГРН получен у: {с_огрн} (это ключ к чеко)')
    print(f'предприятий со статусом ЕГРЮЛ в базе: {заполнено} из 491')


def poluchit(поля, ключ):
    return str(поля.get(ключ) or '')


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""Добрать реквизиты ЕГРЮЛ по нашим ИНН через DaData и положить в enrich.db.

ЗАЧЕМ. После заливки реквизитов остались редкими ровно официальные поля:
адрес 231, статус ЕГРЮЛ 230, директор 198, выручка 266 из 1573. Их не знает ни
наш обогатитель, ни база обзвона (она про другие 161k юрлиц). Их знает ЕГРЮЛ, а
дешёвый вход в ЕГРЮЛ у нас есть: DaData findById/party, БЕСПЛАТНО 10k/день,
токен уже лежит в окружении раннера. Чеко через Дельфин для этого не нужен —
это дороже и медленнее ровно за те же поля.

ЧТО БЕРЁМ, кроме очевидного: `okveds` — СПИСОК ВСЕХ ОКВЭДов С НАЗВАНИЯМИ.
Владелец просил именно все с подписями; словарь из базы обзвона подписывает
только те коды, что там встречались, а DaData отдаёт название всегда и от
первоисточника. Основной ОКВЭД помечен флагом `main`.

DURABILITY. Ответ пишется в СЕРВЕРНОЕ хранилище: таблица `requisites` в
enrich.db (upsert по ИНН) плюс журнал `dadata_rekvizity.jsonl` с fsync. Прогон
резюмируемый: уже опрошенные ИНН пропускаются, поэтому его можно бить на куски
и пережить рестарт. Возвращаемый JSON хранилищем НЕ считается.

Ничего не выдумываем: чего DaData не отдала, остаётся пустым.

Запуск: python dadata_rekvizity.py [--lim N] [--potok N] [--vse]
        --vse — опрашивать всех, а не только тех, у кого поля пусты.
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

API = 'https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party'
ТОКЕН = os.environ.get('DADATA_TOKEN', '')
ЖУРНАЛ = r'C:\sender\server\dadata_rekvizity.jsonl'
ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ВСЕ = '--vse' in sys.argv
_замок = threading.Lock()
_стат = Counter()


def арг(имя, поум):
    try:
        return int(sys.argv[sys.argv.index(имя) + 1])
    except (ValueError, IndexError):
        return поум


def спросить(инн, попыток=3):
    тело = json.dumps({'query': str(инн)}).encode('utf-8')
    for н in range(попыток):
        try:
            зпр = urllib.request.Request(API, data=тело, method='POST', headers={
                'Content-Type': 'application/json', 'Accept': 'application/json',
                'Authorization': f'Token {ТОКЕН}'})
            with urllib.request.urlopen(зпр, timeout=30) as о:
                д = json.loads(о.read())
            сг = д.get('suggestions') or []
            return (сг[0].get('data') or {}) if сг else {}
        except urllib.error.HTTPError as e:
            # 429 — упёрлись в темп, ждём и повторяем; 403 — кончился лимит дня
            if e.code == 429:
                time.sleep(2 + н * 3)
                continue
            with _замок:
                _стат[f'HTTP {e.code}'] += 1
            return None
        except Exception:  # noqa: BLE001
            time.sleep(1 + н)
    with _замок:
        _стат['не ответила'] += 1
    return None


def разобрать(д):
    """DaData party -> поля таблицы requisites. Пустое остаётся пустым."""
    адрес = ((д.get('address') or {}).get('unrestricted_value')
             or (д.get('address') or {}).get('value') or '')
    рук = д.get('management') or {}
    имя = д.get('name') or {}
    сост = д.get('state') or {}
    оквэды = д.get('okveds') or []
    все = ' | '.join(
        f"{o.get('code', '')} {o.get('name', '')}".strip()
        for o in оквэды if o.get('code'))
    осн = next((f"{o.get('code','')} {o.get('name','')}".strip()
                for o in оквэды if o.get('main')), '')
    if not осн and д.get('okved'):
        осн = str(д['okved'])
    return {
        'ogrn': д.get('ogrn') or '', 'kpp': д.get('kpp') or '',
        'okpo': д.get('okpo') or '',
        'opf': ((д.get('opf') or {}).get('short') or ''),
        'opf_full': ((д.get('opf') or {}).get('full') or ''),
        'status': сост.get('status') or '',
        'reg_date': _дата(сост.get('registration_date')),
        'liq_date': _дата(сост.get('liquidation_date')),
        'name_short': имя.get('short_with_opf') or имя.get('short') or '',
        'name_full': имя.get('full_with_opf') or имя.get('full') or '',
        'address': адрес,
        'director': рук.get('name') or '',
        'director_post': рук.get('post') or '',
        'okved_main': осн, 'okved_all': все,
        'employees': str(д.get('employee_count') or ''),
        'branch_count': str(д.get('branch_count') or ''),
        'capital': str(((д.get('capital') or {}) or {}).get('value') or ''),
        'src': 'dadata:findById',
    }


def _дата(мс):
    try:
        return time.strftime('%Y-%m-%d', time.gmtime(int(мс) / 1000)) if мс else ''
    except Exception:  # noqa: BLE001
        return ''


def сделанные():
    из = set()
    if os.path.exists(ЖУРНАЛ):
        for стр in open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(стр)
            except Exception:  # noqa: BLE001
                continue
            if з.get('inn'):
                из.add(str(з['inn']))
    return из


def main():
    if not ТОКЕН:
        raise SystemExit('нет DADATA_TOKEN в окружении раннера')
    ЛИМ, ПОТОК = арг('--lim', 1600), арг('--potok', 6)
    import sqlite3
    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    наши = []
    for инн, адр, дир, ст in цб.execute(
            "SELECT inn, COALESCE(adres,''), COALESCE(direktor,''), "
            "COALESCE(status_egrul,'') FROM company"):
        if ВСЕ or not (адр and дир and ст):
            наши.append(str(инн))
    цб.close()
    было = сделанные()
    очередь = [и for и in наши if и not in было][:ЛИМ]
    print(f'наших без полного набора реквизитов: {len(наши)}; '
          f'уже спрошено ранее: {len(наши) - len([и for и in наши if и not in было])}; '
          f'в этот прогон: {len(очередь)}')
    sys.stdout.flush()
    if not очередь:
        return

    db = EDB.EnrichDB()
    ж = open(ЖУРНАЛ, 'a', encoding='utf-8')
    поля = ('ogrn kpp okpo opf opf_full status reg_date liq_date name_short '
            'name_full address director director_post okved_main okved_all '
            'employees branch_count capital src').split()

    def один(инн):
        д = спросить(инн)
        if д is None:
            return
        if not д:
            with _замок:
                _стат['не найдено в ЕГРЮЛ'] += 1
                ж.write(json.dumps({'inn': инн, 'пусто': True},
                                   ensure_ascii=False) + '\n')
            return
        з = разобрать(д)
        with _замок:
            _стат['получено'] += 1
            for п in ('address', 'director', 'status', 'okved_all', 'employees'):
                if з.get(п):
                    _стат['есть ' + п] += 1
            try:
                db.cx.execute(
                    'INSERT INTO requisites (inn, ' + ','.join(поля) + ', updated_at)'
                    ' VALUES (?' + ',?' * len(поля) + ',?)'
                    ' ON CONFLICT(inn) DO UPDATE SET ' +
                    ', '.join(f'{п}=excluded.{п}' for п in поля) +
                    ', updated_at=excluded.updated_at',
                    [инн] + [з.get(п, '') for п in поля] +
                    [time.strftime('%Y-%m-%dT%H:%M:%S')])
            except Exception as e:  # noqa: BLE001
                _стат['запись не легла'] += 1
                if _стат['запись не легла'] < 3:
                    print('  запись:', str(e)[:110])
            ж.write(json.dumps({'inn': инн, **з}, ensure_ascii=False) + '\n')

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=ПОТОК) as п:
        for i, _ in enumerate(п.map(один, очередь), 1):
            if i % 200 == 0:
                with _замок:
                    db.cx.commit()
                    ж.flush()
                    os.fsync(ж.fileno())
                print(f'  {i}/{len(очередь)}, {int(time.time()-t0)} с, '
                      f'получено {_стат["получено"]}')
                sys.stdout.flush()
    db.cx.commit()
    ж.flush()
    os.fsync(ж.fileno())
    ж.close()
    всего = db.cx.execute('SELECT COUNT(*) FROM requisites').fetchone()[0]
    с_адр = db.cx.execute(
        "SELECT COUNT(*) FROM requisites WHERE COALESCE(address,'')<>''").fetchone()[0]
    print(json.dumps({'итог': dict(_стат), 'строк_в_requisites': всего,
                      'из_них_с_адресом': с_адр, 'секунд': int(time.time() - t0)},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()

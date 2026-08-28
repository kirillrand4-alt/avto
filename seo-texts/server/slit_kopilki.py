# -*- coding: utf-8 -*-
r"""Слить копилки в базу вручную, не дожидаясь конвейеров.

Владелец 28.08: «копилка живучая? если не сольётся, утром сможем вручную
долить?» Живучая — да: обе пишутся с fsync и переписываются атомарно, лежат на
сервере и переживают падение процесса, перезапуск сервера и рестарт песочницы.
А вот долить было нечем: слив вызывался ТОЛЬКО в начале очередной пачки, и при
остановленных конвейерах копилку разгребать некому. Эта команда закрывает дыру.

Ждёт свободного окна: сверки приговоров и лидов по расписанию держат enrich.db
по четверти часа, и попытка в занятую минуту не значит ничего. По умолчанию
ждём до пятнадцати минут, проверяя раз в полминуты.

    python slit_kopilki.py                 слить обе, ждать до 15 минут
    python slit_kopilki.py --skolko 40     ждать сорок минут
    python slit_kopilki.py --posmotret     только показать, что накопилось
"""
import json
import os
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
os.environ.setdefault('NO_BROWSER', '1')

БД = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')


def _строк(п):
    if not os.path.exists(п):
        return 0
    with open(п, encoding='utf-8', errors='replace') as f:
        return sum(1 for s in f if s.strip())


def _свободна(секунд=3):
    """Пускает ли база писать прямо сейчас."""
    try:
        c = sqlite3.connect(БД, timeout=секунд)
        c.execute('PRAGMA busy_timeout=%d' % (секунд * 1000))
        c.execute('BEGIN IMMEDIATE')
        c.execute('ROLLBACK')
        c.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def что_накопилось():
    import poisk_saytov as PS
    import site_facts as SF
    return {'поиск': {'файл': PS.ОЖИДАЮТ, 'записей': _строк(PS.ОЖИДАЮТ)},
            'паспорта': {'файл': SF.OZHIDAYUT, 'записей': _строк(SF.OZHIDAYUT)},
            'база_свободна': _свободна()}


def слить(ждать_минут=15):
    import poisk_saytov as PS
    import site_facts as SF

    итог = {'до': {'поиск': _строк(PS.ОЖИДАЮТ), 'паспорта': _строк(SF.OZHIDAYUT)}}
    if not (итог['до']['поиск'] or итог['до']['паспорта']):
        итог['итог'] = 'копилки пусты, лить нечего'
        return итог

    t0 = time.time()
    ждали = 0
    while time.time() - t0 < ждать_минут * 60:
        if _свободна():
            break
        ждали += 1
        time.sleep(30)
    итог['ждали_проб'] = ждали
    if not _свободна():
        итог['итог'] = ('база занята все %d минут — ничего не лили, копилки целы'
                        % ждать_минут)
        return итог

    c = sqlite3.connect(БД, timeout=60)
    c.execute('PRAGMA busy_timeout=30000')
    итог['поиск'] = PS._слить_копилку(c) or {'из_копилки_легло': 0}
    итог['паспорта'] = SF._slit_kopilku(c) or {'из_копилки_легло': 0}
    c.close()

    итог['после'] = {'поиск': _строк(PS.ОЖИДАЮТ), 'паспорта': _строк(SF.OZHIDAYUT)}
    c = sqlite3.connect('file:%s?mode=ro' % БД.replace('\\', '/'), uri=True)
    итог['теперь_в_базе'] = {
        'компаний_с_сайтом': c.execute(
            "select count(*) from companies where coalesce(site,'')<>'' "
            "or coalesce(cand_site,'')<>''").fetchone()[0],
        'паспортов': c.execute(
            "select count(*) from site_facts where coalesce(facts_json,'')<>''"
        ).fetchone()[0]}
    c.close()
    return итог


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    if '--posmotret' in a:
        print(json.dumps(что_накопилось(), ensure_ascii=False, indent=1))
        return 0
    минут = 15
    if '--skolko' in a:
        try:
            минут = int(a[a.index('--skolko') + 1])
        except Exception:  # noqa: BLE001
            pass
    print(json.dumps(слить(минут), ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())

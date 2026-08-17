# -*- coding: utf-8 -*-
r"""Одна команда — всё ли живо и всё ли движется.

Владелец 17.08: «проверь нормально ли идёт». Раньше на такой вопрос я собирал
ответ из пяти разных проверок, каждый раз заново. Здесь всё вместе, и главное —
не «процесс запущен», а ДВИЖЕТСЯ ЛИ РАБОТА: очередь убывает, карточки прибывают,
поиск сайтов пишет находки. Живой процесс, который ничего не делает, — это тоже
поломка, и её видно только по счётчикам во времени.

    python zdorovie.py
"""
import io
import json
import os
import re
import subprocess
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
ZENNO = os.environ.get('ZENNO_DIR', r'C:\seostat\drop\zenno')
BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
ЖДЁМ = (('мост Зенки', 'zenno_most.py'), ('цикл фактов', 'fakty_cikl.py'),
        ('поиск сайтов', 'poisk_saytov.py'), ('годность', 'godnost.py'))


def цели_поиска_остались():
    """Поиск сайтов не запущен — это поломка или он доделал работу?"""
    try:
        sys.path.insert(0, DIR)
        import poisk_saytov as PS
        цели, _порог, _всего = PS.цели(1)
        return bool(цели)
    except Exception:  # noqa: BLE001
        return True          # не смогли спросить — считаем, что работа есть


def процессы():
    p = subprocess.run(['wmic', 'process', 'where', "name='python.exe'",
                        'get', 'ProcessId,CommandLine'], capture_output=True, text=True)
    строки = p.stdout.splitlines()
    из = {}
    for имя, кусок in ЖДЁМ:
        живой = [s for s in строки if кусок in s]
        из[имя] = ('идёт, pid ' + живой[0].split()[-1]) if живой else 'НЕ ИДЁТ'
    return из


def кэш_по_часам(часов=6):
    сейчас = time.time()
    по = [0] * часов
    for имя in os.listdir(KESH):
        if not имя.endswith('.json.gz'):
            continue
        ч = int((сейчас - os.path.getmtime(os.path.join(KESH, имя))) // 3600)
        if 0 <= ч < часов:
            по[ч] += 1
    return по


def факты_по_часам():
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    по = {}
    for (ts,) in c.execute("select ts from site_facts where coalesce(facts_json,'')<>'' "
                           'and ts > ?', (time.strftime('%Y-%m-%dT00:00:00'),)):
        по[str(ts)[11:13]] = по.get(str(ts)[11:13], 0) + 1
    ждут = c.execute("select count(*) from site_facts where coalesce(facts_json,'')<>'' "
                     'and coalesce(format,0)<2').fetchone()[0]
    готово = c.execute('select count(*) from site_facts where coalesce(format,0)>=2'
                       ).fetchone()[0]
    c.close()
    return dict(sorted(по.items())[-6:]), готово, ждут


def очередь():
    p = os.path.join(ZENNO, 'ochered.txt')
    if not os.path.exists(p):
        return {'нет файла': p}
    n = sum(1 for s in io.open(p, encoding='utf-8', errors='replace') if s.strip())
    return {'строк': n, 'изменена': time.strftime('%d.%m %H:%M',
                                                  time.localtime(os.path.getmtime(p)))}


def хвост(путь, строк=3, знаков=160):
    if not os.path.exists(путь):
        return ['(нет файла)']
    т = io.open(путь, encoding='utf-8', errors='replace').read().splitlines()
    return [s[:знаков] for s in т[-строк:]]


def сторож():
    p = r'C:\sender\storozh.jsonl'
    из = []
    for s in хвост(p, 3, 400):
        try:
            d = json.loads(s)
            из.append('%s очередь %s, %s' % (d['ts'][11:16], d['очередь'],
                                             json.dumps(d['подняли'], ensure_ascii=False)[:60]))
        except Exception:  # noqa: BLE001
            из.append(s[:100])
    return из


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    по_часам_ф, готово, ждут = факты_по_часам()
    обходы = кэш_по_часам()
    итог = {
        'процессы': процессы(),
        'очередь_Зенки': очередь(),
        'обходов_по_часам_назад': обходы,
        'паспортов_по_часам_сегодня': по_часам_ф,
        'паспортов_готово': готово, 'паспортов_ждут_переразбора': ждут,
        'сторож_последние': сторож(),
        'поиск_сайтов_лог': хвост(r'C:\sender\poisk_saytov.out', 2),
        'цикл_фактов_лог': хвост(os.path.join(DIR, 'fakty_cikl.log'), 2),
    }
    # вывод: сперва подробности, потом короткий вердикт — раннер отдаёт хвост
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    # «не идёт» — ещё не поломка: поиск сайтов честно кончает работу, когда цели
    # исчерпаны, и поднимать его незачем. Первая версия отчёта этого не различала
    # и звала разбираться там, где всё правильно.
    беды = []
    for k, v in итог['процессы'].items():
        if v != 'НЕ ИДЁТ' or k == 'годность':
            continue
        if k == 'поиск сайтов':
            if цели_поиска_остались():
                беды.append('поиск сайтов лежит, а цели есть')
            else:
                итог['процессы'][k] = 'доделал: цели кончились'
            continue
        беды.append(k)
    if not обходы[0] and не_ноль(обходы[1:]):
        беды.append('обход встал: за последний час ноль страниц')
    print(json.dumps({'вердикт': ('всё движется' if not беды else 'разобраться: ' +
                                  '; '.join(беды))}, ensure_ascii=False))
    return 0


def не_ноль(сп):
    return any(сп)


if __name__ == '__main__':
    sys.exit(main())

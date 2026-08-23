# -*- coding: utf-8 -*-
r"""Проверка всей цепочки распознавания сайтов: Зенка → мост → кэш → паспорт.

Смотрим не «процесс жив», а движение на каждом стыке: очередь, готовые файлы,
кэш, разбор фактов. И отдельно — кого сайт не пустил: их надо вернуть в очередь,
иначе компания навсегда останется без паспорта.

    svodka()      — что происходит сейчас
    kandidaty()   — кого возвращать в очередь и почему
"""
import gzip
import json
import os
import sqlite3
import subprocess
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, r'C:\sender', r'C:\sender\server'):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ZENNO = os.environ.get('ZENNO_DIR', r'C:\seostat\drop\zenno')
GOTOVO = os.path.join(ZENNO, 'gotovo')
RAZOBRANO = os.path.join(ZENNO, 'razobrano')
OCHERED = os.path.join(ZENNO, 'ochered.txt')
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')


def _скольк(п, свежее_мин=None):
    порог = time.time() - (свежее_мин or 0) * 60
    n = 0
    try:
        with os.scandir(п) as it:
            for e in it:
                if not e.is_file():
                    continue
                if свежее_мин is None:
                    n += 1
                else:
                    try:
                        if e.stat().st_mtime >= порог:
                            n += 1
                    except OSError:
                        pass
    except OSError:
        return -1
    return n


def _процессы():
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "Get-CimInstance Win32_Process | Where-Object {$_.Name -match "
         "'zenno|python' } | %{ '{0}|{1}' -f $_.Name, $_.CommandLine }"],
        capture_output=True, text=True, timeout=120)
    живые = {'зенка': 0, 'мост': 0, 'факты': 0, 'роли': 0, 'прочие_питоны': 0}
    for стр in (out.stdout or '').splitlines():
        н = стр.lower()
        if 'zenno' in н and 'python' not in н:
            живые['зенка'] += 1
        elif 'zenno_most' in н:
            живые['мост'] += 1
        elif 'fakty_cikl' in н:
            живые['факты'] += 1
        elif 'roli_telefonov' in н:
            живые['роли'] += 1
        elif 'python' in н:
            живые['прочие_питоны'] += 1
    return живые


def _строк_очереди():
    if not os.path.exists(OCHERED):
        return 0, set()
    инн = set()
    n = 0
    with open(OCHERED, encoding='utf-8', errors='replace') as f:
        for s in f:
            s = s.strip()
            if not s:
                continue
            n += 1
            инн.add(s.split(';')[0].strip())
    return n, инн


def _кэш_разбор(предел=None):
    """По каждому файлу кэша: сколько страниц и были ли отказы."""
    пусто, с_отказами, всего, страниц = [], 0, 0, 0
    with os.scandir(KESH) as it:
        for e in it:
            if not e.name.endswith('.json.gz'):
                continue
            инн = e.name.split('.')[0]
            всего += 1
            if предел and всего > предел:
                break
            try:
                with gzip.open(e.path, 'rb') as f:
                    д = json.loads(f.read().decode('utf-8', 'replace'))
            except Exception:  # noqa: BLE001
                пусто.append((инн, 'битый файл'))
                continue
            стр = [p for p in (д.get('pages') or []) if (p.get('html') or '').strip()]
            страниц += len(стр)
            отк = д.get('otkazy') or []
            if отк:
                с_отказами += 1
            if not стр:
                причина = (отк[0][:60] if отк else 'страниц нет')
                пусто.append((инн, причина))
    return {'файлов': всего, 'страниц': страниц, 'пустых': len(пусто),
            'с_отказами': с_отказами, 'пустые': пусто}


def svodka():
    d = {'процессы': _процессы()}
    очередь, _ = _строк_очереди()
    d['зенка'] = {
        'очередь_строк': очередь,
        'gotovo': _скольк(GOTOVO), 'gotovo_за_10мин': _скольк(GOTOVO, 10),
        'razobrano': _скольк(RAZOBRANO),
        'кэш_файлов': _скольк(KESH), 'кэш_за_час': _скольк(KESH, 60),
    }
    для = os.path.join(ZENNO, 'demon.out')
    if os.path.exists(для):
        хв = [s.strip()[:150] for s in
              open(для, encoding='utf-8', errors='replace')][-3:]
        d['зенка']['последние_круги'] = хв

    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True,
                        timeout=60)
    d['паспорта'] = {
        'записей': c.execute('select count(*) from site_facts').fetchone()[0],
        'с_фактами': c.execute(
            "select count(*) from site_facts where coalesce(facts_json,'')<>''"
        ).fetchone()[0],
        'ГОТОВЫХ_формат2': c.execute(
            "select count(*) from site_facts where coalesce(facts_json,'')<>'' "
            'and coalesce(format,0)>=2').fetchone()[0],
        'ПОЛНЫХ_с_продукцией': c.execute(
            "select count(*) from site_facts where coalesce(format,0)>=2 "
            "and facts_json like '%\"продукция\": [\"%'").fetchone()[0],
        'за_час': c.execute(
            "select count(*) from site_facts where ts > ? "
            "and coalesce(facts_json,'')<>''",
            (time.strftime('%Y-%m-%dT%H:%M:%S',
                           time.localtime(time.time() - 3600)),)).fetchone()[0],
    }
    d['причины_без_паспорта'] = {r[0][:48]: r[1] for r in c.execute(
        "select coalesce(note,'(пусто)') n, count(*) k from site_facts "
        "where coalesce(facts_json,'')='' group by n order by k desc limit 8")}
    c.close()
    return d


if __name__ == '__main__':
    print(json.dumps(svodka(), ensure_ascii=False, indent=1))

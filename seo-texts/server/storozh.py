# -*- coding: utf-8 -*-
r"""Сторож: держит конвейер живым, пока владельца нет за компьютером.

Владелец 16.08: «а я через пару часов прихожу и всё стоит». Так и было: процессы
доходят до конца своей порции и завершаются, а перезапускать их некому — я в
диалоге, а не на сервере. Сторож решает это на стороне сервера.

Что проверяет и чинит:
  * мост Зенки (zenno_most.py --demon) — умер, поднимаем;
  * поиск сайтов (poisk_saytov.py --vse) — умер, а цели остались, поднимаем;
  * сбор фактов (site_facts.py) — умер, а страницы в кэше не разобраны, поднимаем;
  * очередь Зенки короче порога — дописываем переобходом.

Ставится в планировщик Windows на каждые десять минут:
    schtasks /create /tn Storozh /tr "python storozh.py" /sc minute /mo 10 /f
"""
import json
import os
import subprocess
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
PY311 = r'C:\Program Files\Python311\python.exe'
ZENNO = r'C:\seostat\drop\zenno'
LOG = r'C:\sender\storozh.jsonl'
ФЛАГИ = 0x08 | 0x200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def _живые():
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
         'Select-Object -ExpandProperty CommandLine'],
        capture_output=True, text=True, timeout=120).stdout
    return [s.strip() for s in out.splitlines() if s.strip()]


def _крутится(живые, *куски):
    return any(all(k in s for k in куски) for s in живые)


def _поднять(имя, аргументы, лог):
    f = open(лог, 'a', encoding='utf-8')
    f.write('\n=== сторож поднял %s %s ===\n' % (имя, time.strftime('%Y-%m-%d %H:%M:%S')))
    f.flush()
    p = subprocess.Popen([PY311, os.path.join(DIR, имя)] + аргументы,
                         stdout=f, stderr=subprocess.STDOUT, cwd=DIR, creationflags=ФЛАГИ)
    return p.pid


def _длина_очереди():
    p = os.path.join(ZENNO, 'ochered.txt')
    if not os.path.exists(p):
        return 0
    with open(p, encoding='utf-8', errors='replace') as f:
        return sum(1 for s in f if s.strip())


def _цели_поиска_остались():
    try:
        sys.path.insert(0, DIR)
        import poisk_saytov as PS
        цели, _порог, _всего = PS.цели(1)
        return bool(цели)
    except Exception:  # noqa: BLE001
        return False


def _факты_недоразобраны():
    try:
        import sqlite3
        c = sqlite3.connect(r'C:\sender\enrich.db')
        n = c.execute("select count(*) from site_facts where coalesce(facts_json,'')='' "
                      'and coalesce(popytok,0) < 3').fetchone()[0]
        c.close()
        return n > 0
    except Exception:  # noqa: BLE001
        return False


def обход():
    живые = _живые()
    сделано = {}
    if not _крутится(живые, 'zenno_most.py', '--demon'):
        сделано['мост'] = _поднять('zenno_most.py', ['--demon', '120'],
                                   os.path.join(ZENNO, 'demon.out'))
    if not _крутится(живые, 'poisk_saytov.py') and _цели_поиска_остались():
        сделано['поиск_сайтов'] = _поднять('poisk_saytov.py', ['--vse', '500', '8'],
                                           r'C:\sender\poisk_saytov.out')
    if not _крутится(живые, 'site_facts.py') and _факты_недоразобраны():
        сделано['факты'] = _поднять('site_facts.py', ['--peresprosit', '200'],
                                    r'C:\sender\perespros_faktov.out')
    длина = _длина_очереди()
    if длина < 150:
        try:
            sys.path.insert(0, DIR)
            import zenno_most as Z
            сделано['очередь_дописана'] = Z.pereobhod(500)
        except Exception as e:  # noqa: BLE001
            сделано['очередь_сбой'] = str(e)[:120]
    итог = {'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'очередь': длина,
            'подняли': сделано or 'ничего не требовалось'}
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(итог, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return итог


if __name__ == '__main__':
    print(json.dumps(обход(), ensure_ascii=False)[:600])

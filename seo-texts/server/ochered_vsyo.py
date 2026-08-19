# -*- coding: utf-8 -*-
r"""Очередь Зенки по ВСЕЙ базе: каждая компания, у которой известен сайт.

Владелец 19.08: «запусти зенку по остальным сайтам… по всей базе (160к) где сайт
известен». Штатный наполнитель (zenno_most.ochered) берёт узкий срез — только
тех, у кого НЕТ контактов: он писался под задачу «дожать заслон». Здесь берём
всех, потому что цель другая — собрать материалы сайтов впрок.

Два источника сайтов, и второй крупнее первого:
  enrich.companies.site / cand_site   — 44 236 компаний;
  обзвон obzvon.sites                 — 35 119 (частью те же, частью новые).

Не отдаём: уже отданных (otdano.txt), уже обойденных (файл в кэше), площадки и
справочники (мерка ploshchadki + enrich_contacts._is_own_site).

Провайдер и XMLRiver здесь не участвуют вовсе: это только скачивание страниц.

    python ochered_vsyo.py            посчитать, ничего не записывая
    python ochered_vsyo.py --pisat [сколько]   дописать в очередь
"""
import json
import os
import re
import sqlite3
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
ZENNO = os.environ.get('ZENNO_DIR', r'C:\seostat\drop\zenno')
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
ENRICH = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
OBZVON = r'C:\sender\obzvon-index.db'
OCHERED = os.path.join(ZENNO, 'ochered.txt')
OTDANO = os.path.join(ZENNO, 'otdano.txt')


def _отданные():
    if not os.path.exists(OTDANO):
        return set()
    with open(OTDANO, encoding='utf-8', errors='replace') as f:
        return {l.strip() for l in f if l.strip()}


def _обойденные():
    return {n.split('.')[0] for n in os.listdir(KESH) if n.endswith('.json.gz')}


def _мерки():
    свой = (lambda u: True)
    площадка = (lambda u: '')
    try:
        import enrich_contacts as _E
        свой = _E._is_own_site
    except Exception:  # noqa: BLE001
        pass
    try:
        import ploshchadki as _PL
        площадка = _PL.из_списка
    except Exception:  # noqa: BLE001
        pass
    return свой, площадка


def _первый_сайт(строка):
    """В обзвоне сайты идут списком через запятую/точку с запятой."""
    for кусок in re.split(r'[;,|\s]+', str(строка or '')):
        к = кусок.strip().strip('"\'')
        if k_годен(к):
            return к
    return ''


def k_годен(u):
    return bool(u) and '.' in u and not u.lower().startswith(('mailto:', 'tel:'))


def собрать(предел=0):
    отдано, обойдено = _отданные(), _обойденные()
    свой, площадка = _мерки()
    видели = set(отдано) | set(обойдено)
    из, свод = [], {'из_enrich': 0, 'из_обзвона': 0, 'уже_обойдены': 0,
                    'уже_отдавали': 0, 'площадки': 0, 'без_сайта': 0}
    e = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    for inn, s, cs in e.execute(
            "select inn, coalesce(site,''), coalesce(cand_site,'') from companies "
            "where coalesce(site,'')<>'' or coalesce(cand_site,'')<>''"):
        inn = str(inn)
        u = (s or cs).strip()
        if inn in обойдено:
            свод['уже_обойдены'] += 1
            continue
        if inn in видели:
            свод['уже_отдавали'] += 1
            continue
        if not k_годен(u):
            свод['без_сайта'] += 1
            continue
        if площадка(u) or not свой(u if u.startswith('http') else 'http://' + u):
            свод['площадки'] += 1
            continue
        видели.add(inn)
        из.append('%s;%s;oba' % (inn, u))
        свод['из_enrich'] += 1
        if предел and len(из) >= предел:
            e.close()
            return из, свод
    e.close()
    if os.path.exists(OBZVON):
        o = sqlite3.connect('file:%s?mode=ro' % OBZVON.replace('\\', '/'), uri=True)
        for inn, сайты in o.execute(
                "select inn, coalesce(sites,'') from obzvon where coalesce(sites,'')<>''"):
            inn = ''.join(c for c in str(inn or '') if c.isdigit())
            if not inn or inn in видели:
                свод['уже_отдавали' if inn in отдано else 'уже_обойдены'] += 1
                continue
            u = _первый_сайт(сайты)
            if not k_годен(u):
                свод['без_сайта'] += 1
                continue
            if площадка(u) or not свой(u if u.startswith('http') else 'http://' + u):
                свод['площадки'] += 1
                continue
            видели.add(inn)
            из.append('%s;%s;oba' % (inn, u))
            свод['из_обзвона'] += 1
            if предел and len(из) >= предел:
                break
        o.close()
    return из, свод


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    писать = '--pisat' in sys.argv
    числа = [int(a) for a in sys.argv[1:] if a.isdigit()]
    предел = числа[0] if числа else 0
    строки, свод = собрать(предел)
    свод['готово_к_отдаче'] = len(строки)
    if писать and строки:
        for путь, данные in ((OCHERED, строки),
                             (OTDANO, [s.split(';')[0] for s in строки])):
            with open(путь, 'a', encoding='utf-8') as f:
                f.write('\n'.join(данные) + '\n')
                f.flush()
                os.fsync(f.fileno())
        свод['дописано_в_очередь'] = len(строки)
        свод['длина_очереди'] = sum(1 for l in open(OCHERED, encoding='utf-8',
                                                    errors='replace') if l.strip())
    print(json.dumps(свод, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())

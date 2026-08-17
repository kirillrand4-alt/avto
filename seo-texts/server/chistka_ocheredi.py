# -*- coding: utf-8 -*-
r"""Чистка ОЧЕРЕДИ Зенки: площадки и общие домены не должны в неё попадать.

Владелец 17.08 прислал лог Зенки: «мусор всё так же есть, дзен, б2б». Так и есть,
и это моя недоделка: фильтр площадок 16.08 я применил к базе (companies), а
ОЧЕРЕДЬ собрана раньше и живёт своей жизнью — 38 тысяч строк с адресами, часть
которых мы уже признали справочниками.

Плюс два дырявых места в самих сборщиках:
  * ochered() фильтрует меркой enrich_contacts (_NE_SAYT), а там 22 домена и нет
    ни dzen.ru (яндекс переименовал zen.yandex.ru), ни b2b.house, ни банковских
    проверок контрагентов;
  * pereobhod() не фильтрует вовсе — он берёт всех, кого когда-либо обходили,
    включая тех, кого мы обошли ошибочно.

Здесь: показать, чем забита очередь, и вычистить её тем же правилом, что и базу —
список площадок плюс «один домен на много ИНН = справочник».

    python chistka_ocheredi.py            что в очереди (ничего не меняя)
    python chistka_ocheredi.py --primenit вычистить (со снимком старой очереди)
"""
import json
import os
import sys
import time
from collections import defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import ploshchadki as PL          # noqa: E402
import obshchie_domeny as OD      # noqa: E402

ZENNO = os.environ.get('ZENNO_DIR', r'C:\seostat\drop\zenno')
ОЧЕРЕДЬ = os.path.join(ZENNO, 'ochered.txt')
ЛОГ = os.path.join(DIR, 'chistka_ocheredi.jsonl')
ПОРОГ = 3                        # столько разных ИНН на домене — уже справочник


def разобрать():
    строки = []
    if not os.path.exists(ОЧЕРЕДЬ):
        return строки
    with open(ОЧЕРЕДЬ, encoding='utf-8', errors='replace') as f:
        for s in f:
            s = s.rstrip('\n')
            if not s.strip():
                continue
            части = s.split(';')
            inn = части[0].strip()
            url = части[1].strip() if len(части) > 1 else ''
            строки.append({'строка': s, 'inn': inn, 'url': url, 'домен': PL.домен(url)})
    return строки


def решить(строки, имена=None):
    """Кого оставить, кого убрать и почему."""
    по_домену = defaultdict(set)
    for r in строки:
        if r['домен']:
            по_домену[r['домен']].add(r['inn'])
    оставить, убрать = [], []
    for r in строки:
        п = PL.из_списка(r['url'])
        if п:
            убрать.append(dict(r, причина='площадка: ' + п))
            continue
        сколько = len(по_домену.get(r['домен'], ()))
        if сколько >= ПОРОГ:
            имя = (имена or {}).get(r['inn'], '')
            # своё имя в домене спасает привязку так же, как при чистке базы:
            # холдинг с общим сайтом — не справочник
            if имя and OD._свой_домен(имя, r['домен']):
                оставить.append(r)
            else:
                убрать.append(dict(r, причина='общий домен: %d ИНН' % сколько))
            continue
        оставить.append(r)
    return оставить, убрать


def _имена(инны):
    import sqlite3
    bd = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
    c = sqlite3.connect('file:%s?mode=ro' % bd.replace('\\', '/'), uri=True)
    из = {}
    сп = list(инны)
    for i in range(0, len(сп), 400):
        часть = сп[i:i + 400]
        q = ','.join('?' * len(часть))
        for inn, имя in c.execute(
                "select inn, coalesce(name,'') from companies where inn in (%s)" % q, часть):
            из[str(inn)] = имя
    c.close()
    return из


def отчёт():
    строки = разобрать()
    имена = _имена({r['inn'] for r in строки})
    оставить, убрать = решить(строки, имена)
    по_причинам, по_доменам = {}, {}
    for r in убрать:
        к = r['причина'].split(':')[0]
        по_причинам[к] = по_причинам.get(к, 0) + 1
        по_доменам[r['домен']] = по_доменам.get(r['домен'], 0) + 1
    return {'в_очереди': len(строки), 'останется': len(оставить), 'убрать': len(убрать),
            'по_причинам': по_причинам,
            'верх_мусорных_доменов': sorted(по_доменам.items(), key=lambda x: -x[1])[:20]}


def применить():
    строки = разобрать()
    имена = _имена({r['inn'] for r in строки})
    оставить, убрать = решить(строки, имена)
    if not убрать:
        return {'чисто': True, 'в_очереди': len(строки)}
    снимок = ОЧЕРЕДЬ + '.do-chistki-' + time.strftime('%d%H%M')
    os.replace(ОЧЕРЕДЬ, снимок)
    with open(ОЧЕРЕДЬ, 'w', encoding='utf-8') as f:
        for r in оставить:
            f.write(r['строка'] + '\n')
        f.flush()
        os.fsync(f.fileno())
    with open(ЛОГ, 'a', encoding='utf-8') as f:
        for r in убрать:
            f.write(json.dumps({'inn': r['inn'], 'url': r['url'],
                                'причина': r['причина']}, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return {'было': len(строки), 'осталось': len(оставить), 'убрано': len(убрать),
            'снимок_старой_очереди': снимок}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    if a and a[0] == '--primenit':
        print(json.dumps(применить(), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(отчёт(), ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())

# -*- coding: utf-8 -*-
r"""Что Зенка делает прямо сейчас: очередь, скорость, отказы и десять свежих обходов.

Владелец 16.08: «доложи по зенке, что там смотрит она, сколько осталось, посмотри
10 рандомных, правильно ли всё работает».

Проверяем не «работает ли процесс», а сходится ли результат:
  * очередь — сколько строк и в каких режимах (контакты / факты / оба);
  * скорость — сколько файлов кэша написано за последний час и за сутки, отсюда
    видно, когда очередь кончится;
  * отказы — страницы, куда Зенка не смогла зайти;
  * десять случайных свежих обходов ЦЕЛИКОМ: домен привязки против домена
    скачанных страниц, сколько страниц и знаков, нашлись ли почты, собрался ли
    паспорт. Если Зенка ходит не туда или тащит пустые страницы, это видно здесь,
    а не в счётчиках.

    python zenka_dozor.py [сколько_примеров]
"""
import gzip
import json
import os
import random
import re
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import ploshchadki as PL          # noqa: E402

KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
ZENNO = os.environ.get('ZENNO_DIR', r'C:\seostat\drop\zenno')
BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')


def очередь():
    p = os.path.join(ZENNO, 'ochered.txt')
    итог = {'файл': p, 'строк': 0, 'по_режимам': {}}
    if not os.path.exists(p):
        итог['нет файла'] = True
        return итог
    with open(p, encoding='utf-8', errors='replace') as f:
        for s in f:
            s = s.strip()
            if not s:
                continue
            итог['строк'] += 1
            части = s.split(';')
            режим = (части[2].strip() if len(части) > 2 and части[2].strip() else 'контакты')
            итог['по_режимам'][режим] = итог['по_режимам'].get(режим, 0) + 1
    итог['изменён'] = time.strftime('%d.%m %H:%M', time.localtime(os.path.getmtime(p)))
    return итог


def скорость():
    сейчас = time.time()
    за_час = за_сутки = всего = 0
    свежие = []
    for имя in os.listdir(KESH):
        if not имя.endswith('.json.gz'):
            continue
        всего += 1
        м = os.path.getmtime(os.path.join(KESH, имя))
        if сейчас - м < 3600:
            за_час += 1
        if сейчас - м < 86400:
            за_сутки += 1
            свежие.append((м, имя))
    свежие.sort(reverse=True)
    return {'файлов_в_кэше': всего, 'за_последний_час': за_час, 'за_сутки': за_сутки,
            'последний_обход': (time.strftime('%d.%m %H:%M', time.localtime(свежие[0][0]))
                                if свежие else 'сутки тишины')}, [и for _м, и in свежие]


def отказы():
    n, примеры = 0, []
    if not os.path.isdir(ZENNO):
        return {'нет папки': ZENNO}
    сейчас = time.time()
    for имя in os.listdir(ZENNO):
        if not имя.endswith('.otkaz.txt'):
            continue
        путь = os.path.join(ZENNO, имя)
        if сейчас - os.path.getmtime(путь) > 86400:
            continue
        n += 1
        if len(примеры) < 5:
            try:
                примеры.append({'инн': имя.split('.')[0],
                                'причина': open(путь, encoding='utf-8',
                                                errors='replace').read()[:120].strip()})
            except Exception:  # noqa: BLE001
                pass
    return {'отказов_за_сутки': n, 'примеры': примеры}


def _страницы(путь):
    try:
        d = json.loads(gzip.open(путь, 'rb').read().decode('utf-8', 'replace'))
    except Exception as e:  # noqa: BLE001
        return [], 0, 'не читается: %s' % str(e)[:60]
    урлы, знаков = [], 0
    for pg in (d.get('pages') or []):
        h = pg.get('html') or ''
        знаков += len(h)
        урлы.append(pg.get('url') or '')
    return урлы, знаков, ''


def примеры(свежие, сколько=10):
    random.seed()
    выбор = random.sample(свежие[:400], min(сколько, len(свежие[:400])))
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    из = []
    for имя in выбор:
        inn = имя.split('.')[0]
        r = c.execute("select coalesce(name,'') name, coalesce(nullif(site,''),nullif(cand_site,''),'') site, "
                      "coalesce(verified,'') verified, coalesce(best_email,'') pochta, "
                      "coalesce(site_source,'') istochnik from companies where inn=?",
                      (inn,)).fetchone()
        f = c.execute("select coalesce(facts_json,'') f, coalesce(format,0) fmt, "
                      "coalesce(note,'') note from site_facts where inn=?", (inn,)).fetchone()
        урлы, знаков, беда = _страницы(os.path.join(KESH, имя))
        дом_кэша = PL.домен(урлы[0]) if урлы else ''
        дом_привязки = PL.домен(r['site']) if r else ''
        паспорт = ''
        if f and f['f']:
            try:
                d = json.loads(f['f'])
                паспорт = '; '.join((d.get('продукция') or [])[:3])[:90] or '(поля пустые)'
            except Exception:  # noqa: BLE001
                паспорт = '(json не читается)'
        elif f:
            паспорт = 'нет: %s' % (f['note'][:60] or 'ещё не разбирали')
        из.append({
            'инн': inn, 'имя': (r['name'][:40] if r else '(нет в базе)'),
            'привязка': дом_привязки or '—', 'откуда_привязка': (r['istochnik'] if r else ''),
            'домен_страниц': дом_кэша or '—',
            'сходится': (дом_кэша == дом_привязки) if (дом_кэша and дом_привязки) else None,
            'страниц': len(урлы), 'знаков': знаков,
            'почта': (r['pochta'] if r and r['pochta'] else 'нет'),
            'паспорт': паспорт or 'карточки нет',
            'первые_адреса': [u[:70] for u in урлы[:3]], 'беда': беда})
    c.close()
    return из


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 10
    оч = очередь()
    ск, свежие = скорость()
    пр = примеры(свежие, n)
    print(json.dumps({'примеры': пр}, ensure_ascii=False, indent=1))
    осталось = ''
    if ск['за_последний_час']:
        осталось = '%.1f ч при нынешней скорости' % (оч['строк'] / ск['за_последний_час'])
    print(json.dumps({'очередь': оч, 'скорость': ск, 'отказы': отказы(),
                      'очередь_кончится_через': осталось or 'скорость нулевая'},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())

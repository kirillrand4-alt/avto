# -*- coding: utf-8 -*-
r"""Найти хозяина чужого сайта и отдать факты ему.

Владелец 16.08, увидев чистку: «а хозяина мы нашли этих доменов? чтобы отдать
факты хозяину». Вопрос по делу — выкидывать скачанный сайт жалко. Он кому-то
принадлежит, и этот кто-то с большой вероятностью тоже наш лид: страницы уже
скачаны, контакты на них есть, паспорт по ним собирается.

Что уже было. В обогащении такой перенос есть для КОНТАКТОВ (r['perenos'],
r['vne_bazy']), и он опирается на сильную улику: ИНН в подвале самой страницы.
Замер по 600 чужим сайтам: ИНН на странице нашёлся у 215 (36%), а закрепление
домена в реестровой выгрузке — лишь у 17. Но работает это ТОЛЬКО в момент
обогащения и только с контактами. Страницы, которые мы 16.08 увели в карантин
(1160 файлов), никто не разбирал на предмет хозяина, и паспорта по ним пропали
бы вместе с ними.

Здесь мы проходим по карантину и решаем судьбу каждой пачки страниц:
  * ИНН со страницы есть в нашей базе — отдаём домен и страницы ЕМУ: ставим сайт
    (если у него пусто) и кладём файл под его ИНН, чтобы разбор собрал паспорт;
  * ИНН есть, но компании у нас нет — пишем в hozyaeva_vne_bazy.jsonl: живая
    компания с сайтом и контактами, прицепится при расширении базы без обхода;
  * ИНН на страницах нет или их много (справочник) — оставляем в карантине.

    python hozyain_domena.py --stat       посчитать, ничего не трогая
    python hozyain_domena.py --primenit   раздать хозяевам
"""
import gzip
import json
import os
import re
import shutil
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import ploshchadki as PL          # noqa: E402

KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
ОТСТОЙНИК = os.environ.get('PAGECACHE_OTKLONENO',
                           os.path.join(os.path.dirname(KESH), 'pagecache_otkloneno'))
BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
ВНЕ_БАЗЫ = os.path.join(DIR, 'hozyaeva_vne_bazy.jsonl')
ЛОГ = os.path.join(DIR, 'hozyain_domena.jsonl')
_ИНН = re.compile(r'(?<!\d)(\d{10}|\d{12})(?!\d)')


def _инн_верно(s):
    """Контрольные цифры ИНН: без них в улику попадёт любой десятизначный номер."""
    if len(s) == 10:
        k = (2, 4, 10, 3, 5, 9, 4, 6, 8)
        return int(s[9]) == sum(int(s[i]) * k[i] for i in range(9)) % 11 % 10
    if len(s) == 12:
        k1 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
        k2 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
        return (int(s[10]) == sum(int(s[i]) * k1[i] for i in range(10)) % 11 % 10
                and int(s[11]) == sum(int(s[i]) * k2[i] for i in range(11)) % 11 % 10)
    return False


def _разобрать(путь):
    """Текст страниц, домен и заголовок из файла кэша."""
    try:
        d = json.loads(gzip.open(путь, 'rb').read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        return '', '', ''
    куски, домен, заголовок = [], '', ''
    for pg in (d.get('pages') or []):
        h = pg.get('html') or ''
        if not домен and pg.get('url'):
            домен = PL.домен(pg['url'])
        if not заголовок:
            m = re.search(r'<title[^>]*>(.{3,120}?)</title>', h, re.S | re.I)
            if m:
                заголовок = re.sub(r'\s+', ' ', m.group(1)).strip()
        h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
        куски.append(re.sub(r'<[^>]+>', ' ', h))
    return re.sub(r'\s+', ' ', ' '.join(куски)), домен, заголовок


def найти():
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    в_базе = {str(r['inn']): (r['name'] or '', r['site'] or '')
              for r in c.execute("select inn, coalesce(name,'') name, "
                                 "coalesce(site,'') site from companies")}
    есть_кэш = {n.split('.')[0] for n in os.listdir(KESH) if n.endswith('.json.gz')}
    c.close()
    из = []
    if not os.path.isdir(ОТСТОЙНИК):
        return из
    for имя in os.listdir(ОТСТОЙНИК):
        if not имя.endswith('.json.gz'):
            continue
        чей_был = имя.split('.')[0]
        путь = os.path.join(ОТСТОЙНИК, имя)
        текст, домен, заголовок = _разобрать(путь)
        if not текст:
            continue
        if PL.из_списка(домен):
            из.append({'файл': имя, 'домен': домен, 'итог': 'площадка'})
            continue
        свои = [x for x in dict.fromkeys(_ИНН.findall(текст[:120000]))
                if x != чей_был and _инн_верно(x)]
        if not свои:
            из.append({'файл': имя, 'домен': домен, 'итог': 'ИНН на страницах нет'})
            continue
        if len(свои) > 3:
            из.append({'файл': имя, 'домен': домен, 'итог': 'много ИНН — справочник',
                       'сколько_инн': len(свои)})
            continue
        хозяин = свои[0]
        имя_х, сайт_х = в_базе.get(хозяин, (None, None))
        из.append({'файл': имя, 'домен': домен, 'заголовок': заголовок[:80],
                   'был_у': чей_был, 'хозяин': хозяин,
                   'итог': ('хозяин в базе' if имя_х is not None else 'хозяина нет в базе'),
                   'имя_хозяина': имя_х or '', 'сайт_хозяина': сайт_х or '',
                   'кэш_хозяина_уже_есть': хозяин in есть_кэш})
    return из


def применить():
    находки = найти()
    c = sqlite3.connect(BD, timeout=60)
    итог = {'разобрано_файлов': len(находки), 'отдали_хозяину': 0,
            'проставили_сайт': 0, 'вернули_страницы': 0, 'вне_базы': 0,
            'площадки': 0, 'без_инн': 0, 'справочники': 0}
    вне = []
    for н in находки:
        если = н.get('итог')
        if если == 'площадка':
            итог['площадки'] += 1
            continue
        if если == 'ИНН на страницах нет':
            итог['без_инн'] += 1
            continue
        if если == 'много ИНН — справочник':
            итог['справочники'] += 1
            continue
        if если == 'хозяина нет в базе':
            итог['вне_базы'] += 1
            вне.append({'inn': н['хозяин'], 'домен': н['домен'],
                        'заголовок': н.get('заголовок', ''),
                        'найден': 'инн-на-странице', 'ts': time.strftime('%Y-%m-%dT%H:%M:%S')})
            continue
        # хозяин в базе: домен и страницы уезжают ему
        итог['отдали_хозяину'] += 1
        if not н['сайт_хозяина']:
            итог['проставили_сайт'] += c.execute(
                "UPDATE companies SET site=?, site_source='инн-на-странице', updated_at=? "
                "WHERE inn=? AND coalesce(site,'')=''",
                (н['домен'], time.strftime('%Y-%m-%dT%H:%M:%S'), н['хозяин'])).rowcount
        if not н['кэш_хозяина_уже_есть']:
            try:
                shutil.copy(os.path.join(ОТСТОЙНИК, н['файл']),
                            os.path.join(KESH, '%s.json.gz' % н['хозяин']))
                итог['вернули_страницы'] += 1
            except Exception as e:  # noqa: BLE001
                н['сбой'] = str(e)[:100]
    c.commit()
    c.close()
    if вне:
        with open(ВНЕ_БАЗЫ, 'a', encoding='utf-8') as f:
            for в in вне:
                f.write(json.dumps(в, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
    with open(ЛОГ, 'a', encoding='utf-8') as f:
        for н in находки:
            f.write(json.dumps(н, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return итог


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    if not a or a[0] == '--stat':
        находки = найти()
        по = {}
        for н in находки:
            по[н['итог']] = по.get(н['итог'], 0) + 1
        примеры = [н for н in находки if н['итог'] == 'хозяин в базе'][:6]
        print(json.dumps({'примеры': примеры}, ensure_ascii=False, indent=1))
        print(json.dumps({'файлов_в_карантине': len(находки), 'по_итогам': по},
                         ensure_ascii=False, indent=1))
    elif a[0] == '--primenit':
        print(json.dumps(применить(), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())

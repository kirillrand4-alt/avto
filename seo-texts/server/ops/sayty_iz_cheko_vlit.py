# -*- coding: utf-8 -*-
"""Сайты С КАРТОЧЕК ЧЕКО в пустые клетки карточек — с заслоном от мусора.

ПОЧЕМУ ЭТО ЛУЧШЕ ПОИСКА. Вопрос владельца: «из чеко ты брал сайты? там сессии
сайты не могут подтвердить». Не брал — лил только поисковые файлы, где
принадлежность доказывается близостью названия в выдаче. Чеко печатает сайт НА
КАРТОЧКЕ КОНКРЕТНОГО ИНН: связь даёт сам источник, а не наше сопоставление.

ПОЧЕМУ ВСЁ РАВНО НЕЛЬЗЯ ЛИТЬ ВСЛЕПУЮ. Замер по живой базе показал, что в это
поле чеко кладёт и не сайты предприятия:

    2705090529  → vk.ru                      соцсеть
    7714626332  → globas.credinform.ru       домен самого агрегатора
    740400188249 → …gosweb.gosuslugi.ru      портал госуслуг

Поэтому заслон по классам, а не «домен непустой»:
  * соцсети и мессенджеры — это не сайт предприятия;
  * домены агрегаторов выписок — это карточка о предприятии, а не его сайт;
  * госпорталы и бесплатные хостинги — сайт есть, но обхода не выдержит;
  * почтовые службы — там вообще не сайт, а адрес почты, попавший в поле.

ЧТО ПИШЕТСЯ. Только в ПУСТУЮ клетку `sayt`: занятую не трогаю, там может стоять
домен с первоисточника. Источник записывается как «чеко: карточка компании» со
ссылкой — в карточке продавца он получит пометку «вторые руки: агрегатор», как
и остальные данные оттуда.

Запуск: python sayty_iz_cheko_vlit.py [--baza p25|centro|obe] [--apply]
"""
import io
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ПОТОК = r'C:\seostat\drop\sayty_iz_cheko.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
БАЗА = 'obe'
for i, а in enumerate(sys.argv):
    if а == '--baza' and i + 1 < len(sys.argv):
        БАЗА = sys.argv[i + 1]

_МУСОР = (
    ('соцсеть', r'(?:^|\.)(?:vk\.(?:com|ru)|ok\.ru|facebook|instagram|twitter|'
                r'x\.com|t\.me|telegram|youtube|rutube|dzen\.ru|livejournal)'),
    ('агрегатор выписок', r'(?:credinform|rusprofile|checko|list-org|sbis\.ru|'
                          r'zachestnyibiznes|audit-it|b2b(?:ook|\.house)|'
                          r'companium|inndex|star-pro|ofcheck|rbc\.ru)'),
    ('госпортал', r'(?:gosuslugi\.ru|gosweb|\.gov\.ru|bus\.gov|zakupki\.gov)'),
    ('почтовая служба', r'(?:^|\.)(?:mail\.ru|yandex\.(?:ru|com)|gmail\.com|'
                        r'bk\.ru|inbox\.ru|list\.ru|rambler\.ru)$'),
    ('бесплатный хостинг', r'(?:narod\.ru|ucoz|wixsite|tilda\.ws|nethouse|'
                           r'jimdo|wordpress\.com|blogspot)'),
)
МУСОР = [(имя, re.compile(п, re.I)) for имя, п in _МУСОР]


def домен(з):
    д = str(з or '').strip().lower()
    д = re.sub(r'^https?://', '', д)
    д = re.sub(r'^www\.', '', д).split('/')[0].split('?')[0].strip()
    return д if re.match(r'^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$', д) else ''


def почему_мусор(д):
    for имя, п in МУСОР:
        if п.search(д):
            return имя
    return ''


def main():
    db = EDB.EnrichDB()
    поля = {r[1] for r in db.cx.execute('PRAGMA table_info(companies)')}
    кол = [к for к in ('site', 'cand_site') if к in поля]
    if not кол:
        print('в companies нет колонки сайта — лить нечего')
        return
    ист_есть = 'source' in поля
    сайты = {}
    for р in db.cx.execute(
            f"SELECT inn, {', '.join(кол)}" +
            (", COALESCE(source,'')" if ист_есть else ", ''") + " FROM companies"):
        и = str(р[0])
        for зн in р[1:-1]:
            д = домен(зн)
            if д:
                сайты.setdefault(и, (д, str(р[-1])))
                break

    цели = []
    if БАЗА in ('p25', 'obe'):
        цели.append(('P25', r'C:\seostat\data\p25.db'))
    if БАЗА in ('centro', 'obe'):
        цели.append(('центробежка', os.getenv('CENTRIFUGAL_DB')
                     or r'C:\seostat\data\centrifugal.db'))

    стат = Counter()
    к_записи = []
    примеры = []
    for имя, путь in цели:
        if not os.path.exists(путь):
            continue
        цб = sqlite3.connect(f'file:{путь}?mode=ro', uri=True)
        поля_c = {r[1] for r in цб.execute('PRAGMA table_info(company)')}
        поле = 'sayt' if 'sayt' in поля_c else ('site' if 'site' in поля_c else '')
        if not поле:
            цб.close()
            continue
        for и, с in цб.execute(f"SELECT inn, COALESCE({поле},'') FROM company"):
            и = str(и)
            if str(с).strip() or и not in сайты:
                continue
            д, ист = сайты[и]
            бяка = почему_мусор(д)
            if бяка:
                стат[f'{имя}: ОТСЕЯНО — {бяка}'] += 1
                if len(примеры) < 10:
                    примеры.append(f'{имя} {и} ✗ {д[:34]:34} [{бяка}]')
                continue
            стат[f'{имя}: К ЗАПИСИ'] += 1
            к_записи.append({'baza': имя, 'put': путь, 'pole': поле,
                             'inn': и, 'domen': д, 'istochnik': ист})
            if len(примеры) < 10:
                примеры.append(f'{имя} {и} ✓ {д[:34]}')
        цб.close()

    for п in примеры:
        print('  ', п)

    if not ПРИМЕНИТЬ:
        print()
        print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
        print('СУХОЙ ПРОГОН, ничего не записано')
        return

    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    по_базам = Counter()
    for имя, путь in цели:
        мои = [з for з in к_записи if з['put'] == путь]
        if not мои:
            continue
        цб = sqlite3.connect(путь, timeout=30)
        поля_c = {r[1] for r in цб.execute('PRAGMA table_info(company)')}
        до = цб.total_changes
        for з in мои:
            наборы = [f"{з['pole']}=?"]
            зн = [з['domen']]
            if 'istochnik_sayta' in поля_c:
                наборы.append('istochnik_sayta=?')
                зн.append('чеко: карточка компании')
            цб.execute(f"UPDATE company SET {', '.join(наборы)} WHERE inn=? "
                       f"AND COALESCE({з['pole']},'')=''", зн + [з['inn']])
        цб.commit()
        по_базам[имя] = цб.total_changes - до
        с_сайтом = цб.execute(
            f"SELECT COUNT(*) FROM company WHERE COALESCE({мои[0]['pole']},'')<>''"
        ).fetchone()[0]
        всего = цб.execute('SELECT COUNT(*) FROM company').fetchone()[0]
        по_базам[f'{имя}: с сайтом стало'] = с_сайтом
        по_базам[f'{имя}: предприятий всего'] = всего
        цб.close()

    with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
        for з in к_записи:
            ф.write(json.dumps({**з, 'ts': ts}, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())

    print()
    print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
    for к, v in sorted(по_базам.items()):
        print(f'{к:36} {v:6}')


if __name__ == '__main__':
    main()

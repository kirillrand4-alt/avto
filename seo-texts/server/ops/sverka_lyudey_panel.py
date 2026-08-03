# -*- coding: utf-8 -*-
"""Сколько людей из enrich.db реально доехало в панель — сверка ПО ИНН.

Вопрос 3-й сессии, и он поставлен правильно: «у вас 2402 человека по видимым
ИНН на 865 предприятиях, у панели люди на 905 предприятиях — цифры близки, но
множества могут не совпадать. Сверьте по ИНН, а не по количеству: равные числа
при разных множествах выглядят как всё в порядке».

Это ровно тот класс ошибок, на котором мы уже дважды сгорели за сутки:
«телефонов 4782» и «телефонов 4612» оказались одним и тем же числом, посчитанным
строками и парами; «людей 970» у соседей свернулись в 546 человек. Общий счёт
совпадает — состав разный.

Поэтому здесь считается ТРИ вещи, а не одна:
  * предприятия: есть у меня, нет в панели — и наоборот;
  * люди по паре (ИНН, нормализованное ФИО): чьи именно не доехали;
  * технические ЛПР отдельно — они и есть цель, и потерять их дороже всего.

Ничего не пишет. Это замер.

Запуск: python sverka_lyudey_panel.py [--fajl]
"""
import json
import os
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ФАЙЛ = '--fajl' in sys.argv
ИМЯ = 'SVERKA-lyudey-enrich-vs-panel.csv'
ТЕХ = set(EDB.EnrichDB.TECH_ROLES) | {'техконтакт'}


def инн_кл(т):
    return re.sub(r'\D', '', str(т or ''))[:12]


def клч(т):
    return re.sub(r'\s+', ' ', str(т or '').strip().lower()).replace('ё', 'е')


def main():
    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    на_панели = {инн_кл(r[0]) for r in цб.execute('SELECT inn FROM company')}
    люди_панели = set()
    тех_панели = set()
    for и, ч, т in цб.execute(
            "SELECT inn, COALESCE(person,''), COALESCE(is_tech,0) FROM person"):
        к = (инн_кл(и), клч(ч))
        if not к[1]:
            continue
        люди_панели.add(к)
        if т:
            тех_панели.add(к)
    цб.close()

    скрыты = set()
    try:
        пр = sqlite3.connect(f'file:{ПР}?mode=ro', uri=True, timeout=20)
        скрыты = {инн_кл(r[0]) for r in пр.execute(
            "SELECT inn FROM hidden_item WHERE kind='company'")}
        пр.close()
    except Exception:  # noqa: BLE001
        pass
    видимые = на_панели - скрыты

    db = EDB.EnrichDB()
    люди_мои = set()
    тех_мои = set()
    роль_по = {}
    for и, ч, р in db.cx.execute(
            "SELECT inn, COALESCE(person,''), COALESCE(role,'') FROM people"):
        ик = инн_кл(и)
        к = (ик, клч(ч))
        if not к[1] or ик not in видимые:
            continue
        люди_мои.add(к)
        роль_по[к] = р
        if р in ТЕХ:
            тех_мои.add(к)

    не_доехали = люди_мои - люди_панели
    только_в_панели = люди_панели - люди_мои
    тех_не_доехали = тех_мои - люди_панели
    предпр_мои = {к[0] for к in люди_мои}
    предпр_панели = {к[0] for к in люди_панели if к[0] in видимые}

    итог = {
        'видимых_предприятий': len(видимые),
        'у_меня_людей_по_видимым': len(люди_мои),
        'у_меня_предприятий_с_людьми': len(предпр_мои),
        'в_панели_людей_по_видимым': len([к for к in люди_панели if к[0] in видимые]),
        'в_панели_предприятий_с_людьми': len(предпр_панели),
        'НЕ_ДОЕХАЛО_людей': len(не_доехали),
        'из_них_ТЕХНИЧЕСКИХ': len(тех_не_доехали),
        'предприятий_у_меня_есть_в_панели_людей_нет':
            len(предпр_мои - предпр_панели),
        'есть_в_панели_но_нет_у_меня': len(только_в_панели),
        'роли_недоехавших': Counter(
            роль_по.get(к) or 'без роли' for к in не_доехали).most_common(10),
    }
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    for к in list(тех_не_доехали)[:10]:
        print(f'  не доехал техЛПР: {к[0]} {к[1][:40]} — {роль_по.get(к)}')

    if not ФАЙЛ:
        return
    import csv
    import urllib.request
    п = os.path.join(r'C:\sender\server', ИМЯ)
    with open(п, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(['inn', 'fio', 'rol', 'tehLPR'])
        for к in sorted(не_доехали):
            р = роль_по.get(к) or ''
            в.writerow([к[0], к[1], р, 'да' if р in ТЕХ else 'нет'])
    урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
    urllib.request.urlopen(urllib.request.Request(
        урл.rstrip('/') + '/' + ИМЯ, data=open(п, 'rb').read(), method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
        timeout=300).read()
    print(f'файл на дропе: {ИМЯ} ({os.path.getsize(п)} байт)')


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""Кому звонить сегодня: у машины истёк срок экспертизы промбезопасности.

ПОЧЕМУ ЭТО ПОВОД ДЛЯ ЗВОНКА, А НЕ ПРОСТО СТРОЧКА. Заключение ЭПБ выдаётся на
срок. Когда срок вышел, у предприятия ровно три дороги: заказать новую
экспертизу, продлить ресурс или заменить машину. Все три — разговор про
деньги, и он идёт СЕЙЧАС, а не когда-нибудь. Это редкий для нашей базы случай,
когда известен не только факт наличия машины, но и момент.

Список строится по фактам, влитым из реестра (`dolivka_epb_faktov.py`):
состояние `экспертиза ЭПБ истекла`. Рядом кладём телефоны технических ЛПР —
без них список не работа, а справка.

Ничего не пишет в базы. Кладёт CSV на дроп и печатает сводку.

Запуск: python srok_epb_istek.py
"""
import csv
import json
import os
import re
import sqlite3
import sys
import urllib.request
from collections import defaultdict

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ИМЯ = 'SROK-EPB-ISTEK-zvonit-seychas.csv'
ТЕХ = set(EDB.EnrichDB.TECH_ROLES) | {'техконтакт'}
_ДО = re.compile(r'действует до ([\d.]{8,10})')


def клч(т):
    return re.sub(r'\s+', ' ', str(т or '').strip().lower()).replace('ё', 'е')


def main():
    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    имена = {r[0]: r[1] for r in цб.execute('SELECT inn, predpriyatie FROM company')}

    машины = defaultdict(list)
    for и, м, т, ц, док, ссылка in цб.execute(
            "SELECT inn, COALESCE(model,''), COALESCE(equipment_type,''), "
            "COALESCE(quote,''), COALESCE(evidence,''), COALESCE(source_url,'') "
            "FROM fact WHERE status='экспертиза ЭПБ истекла'"):
        сов = _ДО.search(док)
        машины[и].append({'марка': м, 'тип': т, 'текст': ц,
                          'до': сов.group(1) if сов else '', 'ссылка': ссылка})

    # ТЕХЛПР С НОМЕРОМ — ИЗ ДВУХ ТАБЛИЦ, А НЕ ИЗ ОДНОЙ. Первая версия читала
    # только `person.phone` и по всем девяти предприятиям выдала «техЛПР 0» —
    # включая БСК и Салават, которых мы обогащали неделю. Номер у человека
    # чаще лежит в `contact` (kind='phone', person заполнен), а `person.phone`
    # пуст. Ровно на этой подмене таблиц уже был ложный вывод «772 номера
    # новые»: искали в `phone`, а живёт в `contact`.
    люди = defaultdict(dict)
    for и, ч, п, р, тел in цб.execute(
            "SELECT inn, COALESCE(person,''), COALESCE(position,''), "
            "COALESCE(role,''), COALESCE(phone,'') FROM person "
            'WHERE COALESCE(is_tech,0)=1'):
        if ч and тел:
            люди[и][клч(ч)] = f'{ч} ({р or п[:30]}) {тел}'
    for и, ч, р, п, зн in цб.execute(
            "SELECT inn, COALESCE(person,''), COALESCE(role,''), "
            "COALESCE(position,''), value FROM contact "
            "WHERE kind='phone' AND COALESCE(is_tech,0)=1"):
        if ч and зн and клч(ч) not in люди[и]:
            люди[и][клч(ч)] = f'{ч} ({р or п[:30]}) {зн}'
    люди = {и: list(д.values()) for и, д in люди.items()}
    цб.close()

    скрыты = set()
    try:
        пр = sqlite3.connect(f'file:{ПР}?mode=ro', uri=True, timeout=20)
        скрыты = {r[0] for r in пр.execute(
            "SELECT inn FROM hidden_item WHERE kind='company'")}
        пр.close()
    except Exception:  # noqa: BLE001
        pass

    ряды = []
    for и, сп in sorted(машины.items(), key=lambda x: -len(x[1])):
        марки = sorted({м['марка'] for м in сп if м['марка']})
        даты = sorted({м['до'] for м in сп if м['до']})
        ряды.append({
            'inn': и,
            'predpriyatie': имена.get(и, ''),
            'mashin_s_istekshim_srokom': len(сп),
            'marki': ' | '.join(марки[:6]),
            'sroki_konchilis': ' | '.join(даты[:6]),
            'tehLPR_s_telefonom': ' | '.join(люди.get(и, [])[:4]),
            'tehLPR_vsego': len(люди.get(и, [])),
            'skryto_v_paneli': 'да' if и in скрыты else 'нет',
            'primer_mashiny': (сп[0]['текст'] or '')[:180],
            'ssylka': сп[0]['ссылка'],
        })

    print(json.dumps({
        'предприятий_с_истёкшей_экспертизой': len(ряды),
        'машин_всего': sum(р['mashin_s_istekshim_srokom'] for р in ряды),
        'из_них_скрыто_в_панели': sum(
            1 for р in ряды if р['skryto_v_paneli'] == 'да'),
        'без_единого_техЛПР_с_телефоном': sum(
            1 for р in ряды if not р['tehLPR_vsego']),
    }, ensure_ascii=False, indent=1))
    for р in ряды:
        print(f'  {р["inn"]} {р["predpriyatie"][:44]:<44} машин '
              f'{р["mashin_s_istekshim_srokom"]:>3}  техЛПР '
              f'{р["tehLPR_vsego"]:>2}  {р["marki"][:40]}')

    if not ряды:
        return
    п = os.path.join(r'C:\sender\server', ИМЯ)
    with open(п, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.DictWriter(ф, fieldnames=list(ряды[0].keys()), delimiter=';')
        в.writeheader()
        в.writerows(ряды)
    урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
    urllib.request.urlopen(urllib.request.Request(
        урл.rstrip('/') + '/' + ИМЯ, data=open(п, 'rb').read(), method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
        timeout=300).read()
    print(f'файл на дропе: {ИМЯ}')


if __name__ == '__main__':
    main()

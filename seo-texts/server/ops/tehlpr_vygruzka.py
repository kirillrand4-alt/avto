# -*- coding: utf-8 -*-
"""Выгрузка ВСЕХ технических ЛПР с телефонами и провенансом.

Общая база центробежников покрывает только 700 предприятий с доказанным
фактом «центробежная + воздух». Технических руководителей в enrich.db больше,
и по остальным предприятиям они тоже нужны: у части факт не доказан, но
машина есть, а у части предприятие пришло из другого канала.

Здесь один файл на всех: человек, роль, должность как в источнике, его личный
номер (если есть), номера предприятия, ссылка на страницу-источник и дата
наблюдения. Плюс признак «предприятие в доказанном ядре» — чтобы продажник
видел, звонит он по подтверждённому поводу или по вероятному.

Порядок строк: сперва те, у кого есть ЛИЧНЫЙ номер, затем те, у кого есть
номер предприятия, затем остальные. Внутри — доказанное ядро выше.

Ничего не пишет в базу. Запуск: python tehlpr_vygruzka.py
"""
import csv
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'
ИМЯ = 'TEHLPR-VSE-s-provenansom.csv'
ТЕХ = set(EDB.EnrichDB.TECH_ROLES)


def д10(т):
    ц = re.sub(r'\D', '', т or '')
    if len(ц) == 11 and ц[0] in '78':
        ц = ц[1:]
    return ц if len(ц) == 10 else ''


def мобильный(ц):
    return bool(ц) and ц[0] == '9'


def main():
    csv.field_size_limit(10 ** 7)
    cx = EDB.EnrichDB().cx

    ядро = set()
    п = os.path.join(ДРОП, 'BAZA-CENTROBEZHNIKI-OBSHCHAYA.csv')
    if os.path.exists(п):
        for r in csv.DictReader(io.StringIO(
                open(п, encoding='utf-8-sig', errors='replace').read()),
                delimiter=';'):
            ядро.add((r.get('inn') or '').strip())

    комп = {}
    for и, н, к, р, с in cx.execute(
            "SELECT inn,COALESCE(name,''),COALESCE(short_name,''),"
            "COALESCE(region,''),COALESCE(site,'') FROM companies"):
        комп[и] = {'имя': к.strip() or н, 'регион': р, 'сайт': с}
    статус = dict(cx.execute(
        "SELECT inn,detail FROM stage_log WHERE stage='ЕГРЮЛ статус'"))

    тел_комп = defaultdict(list)
    for и, т in cx.execute("SELECT inn,phone FROM phone_contacts"):
        ц = д10(т)
        if ц and ц not in тел_комп[и]:
            тел_комп[и].append(ц)

    строки = []
    for и, чел, пост, роль, тел, ист, урл, набл in cx.execute(
            "SELECT inn,person,COALESCE(post,''),COALESCE(role,''),"
            "COALESCE(phone,''),COALESCE(source,''),COALESCE(source_url,''),"
            "COALESCE(observed_at,'') FROM people"):
        if роль not in ТЕХ:
            continue
        c = комп.get(и, {})
        личный = д10(тел)
        номера = тел_комп.get(и, [])
        строки.append({
            'inn': и,
            'predpriyatie': (c.get('имя') or '')[:70],
            'region': (c.get('регион') or '')[:28],
            'v_dokazannom_yadre': 'да' if и in ядро else 'нет',
            'status_yurlica': статус.get(и, 'ЕГРЮЛ не спрашивали'),
            'fio': чел,
            'dolzhnost_kak_v_istochnike': пост[:90],
            'rol': роль,
            'lichnyy_nomer': личный,
            'vid_lichnogo': ('мобильный' if мобильный(личный)
                             else ('городской' if личный else '')),
            'nomera_predpriyatiya': ' | '.join(номера[:4]),
            'istochnik': ист[:60],
            'ssylka_na_istochnik': урл[:160],
            'data_nablyudeniya': (набл or '')[:10],
            'sayt': (c.get('сайт') or '')[:60],
        })

    def ключ(с):
        есть_личн = 1 if с['lichnyy_nomer'] else 0
        есть_комп = 1 if с['nomera_predpriyatiya'] else 0
        ядро_ = 1 if с['v_dokazannom_yadre'] == 'да' else 0
        return (-есть_личн, -есть_комп, -ядро_, с['predpriyatie'])
    строки.sort(key=ключ)

    путь = os.path.join(r'C:\sender\server', ИМЯ)
    поля = list(строки[0]) if строки else ['inn']
    with open(путь, 'w', encoding='utf-8-sig', newline='') as ф:
        w = csv.DictWriter(ф, fieldnames=поля, delimiter=';')
        w.writeheader()
        w.writerows(строки)
        ф.flush()
        os.fsync(ф.fileno())

    # числа — ПЕРЕЧИТЫВАНИЕМ файла
    вс = личн = комп_н = ядро_н = без = 0
    роли = Counter()
    ист = Counter()
    инн_вс = set()
    with open(путь, encoding='utf-8-sig', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            вс += 1
            инн_вс.add(r['inn'])
            роли[r['rol']] += 1
            ист[r['istochnik'][:32]] += 1
            if r['lichnyy_nomer']:
                личн += 1
            elif r['nomera_predpriyatiya']:
                комп_н += 1
            else:
                без += 1
            if r['v_dokazannom_yadre'] == 'да':
                ядро_н += 1

    try:
        import urllib.request
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        urllib.request.urlopen(urllib.request.Request(
            урл.rstrip('/') + '/' + ИМЯ, data=open(путь, 'rb').read(),
            method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
            timeout=300).read()
        куда = ИМЯ
    except Exception as e:  # noqa: BLE001
        куда = 'НЕ легло: ' + str(e)[:70]

    print(json.dumps({
        'файл': куда,
        'технических_людей': вс, 'предприятий': len(инн_вс),
        'с_ЛИЧНЫМ_номером': личн,
        'без_личного_но_с_номером_предприятия': комп_н,
        'вообще_без_номера': без,
        'из_доказанного_ядра': ядро_н,
        'роли': роли.most_common(),
        'источники': ист.most_common(8),
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()

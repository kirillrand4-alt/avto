# -*- coding: utf-8 -*-
"""Сведение всего добытого в один список обзвона, ранжированный.

Зачем. За день контакты накопились в трёх разных файлах с разными колонками:
`contacts-accumulator.csv` (ранний накопитель), `centro/telefony-vozdushnye.csv` (заводы,
основной), `centro/telefony-vodokanaly.csv` (новый сегмент). Продавцу нужен **один файл,
отсортированный по тому, кому звонить первым**, а не три разных.

Порядок звонка. Он строится из четырёх множителей, и каждый — измеренный признак, а не
догадка:

1. **Роль.** Технический ЛПР выше снабженца. По итогам дня это самый дефицитный признак:
   технический руководитель по должности нашёлся только на страницах «Руководство».
2. **Уровень доказательства.** `verified=inn` (ИНН напечатан на странице) выше, чем
   совпадение домена: у АО «ННК» гейт подтвердил домен `nnk.ru`, а это оказалась
   «Национальная нерудная» — щебень и карьеры. Двенадцать телефонов пришлось выбросить.
3. **Тип телефона.** Прямой и добавочный выше приёмной: приёмная — это ещё один барьер,
   а не контакт.
4. **Оборудование.** Число воздушных машин и наличие истекающего срока: там, где машин
   больше и срок кончается, разговор предметнее.

Использование:
    python3 svesti_obzvon.py <out.csv>
"""
import csv
import os
import re
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
LENS = os.path.join(DIR, 'engineers-lens')

# Роли: вес по убыванию влияния на решение о покупке машины. Порядок задан владельцем.
ROLI = [
    (r'главн\w+ инженер|технический директор', 5.0, 'главный инженер'),
    (r'главн\w+ механик|главн\w+ энергетик', 4.5, 'главный механик/энергетик'),
    (r'начальник\w*\s+(управлени|отдел\w*)\s+главн', 4.0, 'служба главного инженера'),
    (r'компрессорн|воздухоразделени|кислородн\w+ цех', 4.0, 'компрессорное хозяйство'),
    (r'начальник\w*\s+(цеха|производств|участка)|директор по производств', 3.5, 'производство'),
    (r'главн\w+ технолог', 3.0, 'технолог'),
    (r'снабжени|закупк|материально-техническ|МТО|тендер', 2.0, 'снабжение'),
    (r'директор|руководител', 1.5, 'руководство'),
    (r'при[её]мная|секретар|канцеляр', 0.5, 'приёмная'),
]


def rol_ves(dolzhnost, razdel=''):
    """Роль ищется в должности И в разделе страницы.

    Почему в разделе. У Северстали должность записана как «Начальник управления», а то,
    какого именно управления, стоит заголовком раздела — «Управление главного энергетика».
    По одной должности человек уходил в «не определена», хотя это ровно наша целевая роль.
    Технический признак у крупных предприятий часто лежит **в заголовке блока, а не в
    строке должности**.
    """
    d = ((dolzhnost or '') + ' | ' + (razdel or '')).lower()
    for pat, ves, imya in ROLI:
        if re.search(pat, d):
            return ves, imya
    return 1.0, 'не определена'


def dokaz_ves(row):
    """Уровень доказательства привязки человека к ИНН."""
    v = ' '.join(str(row.get(k) or '') for k in ('proverka_V12', 'svyaz_s_inn', 'proof_level'))
    v = v.lower()
    if 'inn' in v or 'инн на странице' in v or 'карточк' in v:
        return 2.0, 'ИНН на странице или карточка реестра'
    if 'домен' in v or 'provider' in v:
        return 1.0, 'совпадение домена — мнение, не проверка'
    return 0.7, 'уровень не указан'


def tel_ves(row):
    t = ' '.join(str(row.get(k) or '') for k in ('tip', 'phone_type')).lower()
    dob = str(row.get('dobavochny') or '').strip()
    nomer = str(row.get('telefon_polnyy') or row.get('phone') or '').strip()
    if not nomer:
        return 0.3, 'номера нет'
    if 'мобил' in t or 'сотов' in t or re.match(r'\+?7\s*9', nomer):
        return 3.0, 'мобильный'
    if dob:
        return 2.2, 'с добавочным'
    if 'при[её]мн' in t or 'приемн' in t:
        return 1.2, 'приёмная'
    return 2.0, 'прямой'


def oborud_ves(n_mashin, est_istekayushchie):
    try:
        n = int(float(n_mashin or 0))
    except (TypeError, ValueError):
        n = 0
    ves = 1.0 + min(n, 120) ** 0.5 / 4.0
    if est_istekayushchie:
        ves *= 1.4
    return ves


def chitat(path, mapping):
    if not os.path.exists(path):
        print(f'  нет файла: {os.path.basename(path)}', file=sys.stderr)
        return []
    out = []
    for r in csv.DictReader(open(path, encoding='utf-8-sig'), delimiter=';'):
        d = {k: (r.get(v) or '') for k, v in mapping.items()}
        d['_syroy'] = r
        d['istochnik_fajl'] = os.path.basename(path)
        out.append(d)
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit('usage: svesti_obzvon.py <out.csv>')
    out_path = sys.argv[1]

    # истекающие сроки по ИНН — из воздушной выгрузки
    istek = set()
    mashin = {}
    vozd = os.path.join(LENS, 'centro', 'epb-vozdushnye.csv')
    if os.path.exists(vozd):
        for r in csv.DictReader(open(vozd, encoding='utf-8-sig'), delimiter=';'):
            i = (r.get('inn_zakazchika') or '').strip()
            if not i:
                continue
            mashin[i] = mashin.get(i, 0) + 1
            if r.get('srok') == 'expiring':
                istek.add(i)

    zapisi = []
    zapisi += chitat(os.path.join(LENS, 'centro', 'telefony-vozdushnye.csv'),
                     {'inn': 'inn', 'organizaciya': 'zakazchik', 'fio': 'fio',
                      'dolzhnost': 'dolzhnost_so_stranicy', 'telefon': 'telefon_polnyy',
                      'email': 'email', 'ssylka': 'istochnik_url', 'data': 'data_snyatiya'})
    zapisi += chitat(os.path.join(LENS, 'centro', 'telefony-vodokanaly.csv'),
                     {'inn': 'inn', 'organizaciya': 'zakazchik', 'fio': 'fio',
                      'dolzhnost': 'dolzhnost_so_stranicy', 'telefon': 'telefon_polnyy',
                      'email': 'email', 'ssylka': 'istochnik_url', 'data': 'data_snyatiya'})
    # Грифы «УТВЕРЖДАЮ» и «Инициатор мероприятия» из закупочных документов.
    # Единственный источник дня, где техническая должность приходит из документа,
    # а не с сайта: 27 главных инженеров с ФИО, и фрагмент выдачи РосТендера отдаёт
    # их без скачивания файла.
    zapisi += chitat(os.path.join(LENS, 'centro', 'iniciatory-i-grify.csv'),
                     {'inn': 'inn', 'organizaciya': 'predpriyatie', 'fio': 'fio',
                      'dolzhnost': 'dolzhnost_doslovno', 'telefon': '', 'email': '',
                      'ssylka': 'ssylka', 'data': 'data_dokumenta_ili_snyatiya'})
    # Назначения из поиска по фразе: технические роли с датой, но без телефонов.
    # Ценность не в номере, а в имени — секретарь переключает на человека по фамилии.
    zapisi += chitat(os.path.join(LENS, 'centro', 'naznacheniya.csv'),
                     {'inn': 'inn', 'organizaciya': 'predpriyatie_v_istochnike',
                      'fio': 'fio', 'dolzhnost': 'dolzhnost_doslovno',
                      'telefon': 'telefon', 'email': '',
                      'ssylka': 'ssylka', 'data': 'data_istochnika'})
    zapisi += chitat(os.path.join(LENS, 'contacts-accumulator.csv'),
                     {'inn': 'inn', 'organizaciya': 'organization', 'fio': 'person',
                      'dolzhnost': 'role', 'telefon': 'phone', 'email': 'email',
                      'ssylka': 'source_url', 'data': 'observed_at'})
    print(f'записей прочитано: {len(zapisi)}', file=sys.stderr)

    # дедупликация: один человек в одной организации — одна строка, берётся с лучшим счётом
    luchshie = {}
    for d in zapisi:
        syroy = d.pop('_syroy')
        rv, rimya = rol_ves(d['dolzhnost'] or syroy.get('role') or '',
                            syroy.get('razdel_stranicy') or syroy.get('note') or '')
        dv, dimya = dokaz_ves(syroy)
        tv, timya = tel_ves(syroy)
        inn = d['inn'].strip()
        ov = oborud_ves(mashin.get(inn, syroy.get('mashin_vozduh')), inn in istek)
        d.update({'rol_gruppa': rimya, 'uroven_dokazatelstva': dimya, 'tip_telefona': timya,
                  'mashin_vozduh': mashin.get(inn, syroy.get('mashin_vozduh') or ''),
                  'srok_istekaet': 'да' if inn in istek else '',
                  'ochered': round(rv * dv * tv * ov, 2)})
        klyuch = (inn, re.sub(r'\W+', '', (d['fio'] or d['dolzhnost']).lower()))
        if klyuch not in luchshie or d['ochered'] > luchshie[klyuch]['ochered']:
            luchshie[klyuch] = d

    rows = sorted(luchshie.values(), key=lambda x: -x['ochered'])
    cols = ['ochered', 'inn', 'organizaciya', 'fio', 'dolzhnost', 'rol_gruppa', 'telefon',
            'tip_telefona', 'email', 'mashin_vozduh', 'srok_istekaet',
            'uroven_dokazatelstva', 'ssylka', 'data', 'istochnik_fajl']
    with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    print(f'после дедупликации: {len(rows)} → {out_path}', file=sys.stderr)
    for d in rows[:12]:
        print(f"  {d['ochered']:6.1f}  {d['rol_gruppa']:<26} {(d['fio'] or '—')[:24]:<24} "
              f"{d['telefon'][:22]:<22} {d['organizaciya'][:26]}", file=sys.stderr)


if __name__ == '__main__':
    main()

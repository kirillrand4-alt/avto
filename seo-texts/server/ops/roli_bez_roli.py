# -*- coding: utf-8 -*-
"""Доопределить роль там, где человек есть, а роль не установлена.

201 предприятие из 1573 имеет названных людей, но ни одного технического. У
этих людей ЕСТЬ должность — значит роль выводима, и это дешевле, чем искать
новых людей: человек уже найден, телефон часто есть, не хватает только ответа
«он ли решает по компрессорам».

Сначала штатный канон (`EnrichDB._canon_role`) — он бесплатный и отлажен.
Что канон не взял, идёт к модели, но НЕ к `claude-fable-5`: правило владельца
от 02.08 — свободный текст разбирает `deepseek-v4-pro`, он в 35 раз дешевле
при том же результате. Fable оставлен на спорные случаи.

ЧЕГО ЗДЕСЬ НЕТ НАМЕРЕННО: выдумывания роли по имени или по названию
предприятия. Если должность пустая или невнятная — роль остаётся пустой. Мы
сегодня уже дважды получали «технического ЛПР», который оказывался судовым
механиком; третьего раза не надо.

По умолчанию СУХОЙ ПРОГОН. Запись — с --apply.
"""
import csv
import io
import json
import os
import re
import sys
import urllib.request
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\seostat')
import enrich_db as EDB  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'
ИМЯ = 'ROLI-doopredeleny.csv'
ПРИМЕНИТЬ = '--apply' in sys.argv
МОДЕЛЬ = 'deepseek-v4-pro'


def арг(имя, поум):
    return sys.argv[sys.argv.index(имя) + 1] if имя in sys.argv else поум


def провайдер(пачка):
    """Спросить модель про пачку должностей. Возвращает {должность: роль}."""
    ключ = os.environ.get('PROVIDER_API_KEY', '')
    база = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
    if not ключ:
        return {}
    роли = ('гл.инженер, гл.энергетик, гл.механик, гл.технолог, гл.конструктор, '
            'техдиректор, нач.производства, нач.цеха, АСУ/КИПиА, техконтакт, '
            'снабжение/закупки, директор, продажи, кадры, бухгалтерия, '
            'приёмная, общий')
    вопрос = (
        'Ты классифицируешь должности сотрудников российских промышленных '
        'предприятий. Компания продаёт компрессоры, ей нужен тот, кто РЕШАЕТ '
        'по компрессорному хозяйству.\n\n'
        f'Верни СТРОГО JSON-объект вида {{"должность": "роль"}}. Роль — одна '
        f'из списка: {роли}.\n\n'
        'Важные правила:\n'
        '1. «Судовой механик», «механик транспортного цеха», «автомеханик», '
        'механик гаража — это НЕ технические роли по компрессорам, ставь '
        '«общий».\n'
        '2. Машинист компрессорных установок, слесарь КИПиА, приборист — '
        'работают на машине, но НЕ решают: ставь «общий».\n'
        '3. Если должность невнятная или пустая — ставь «общий», не угадывай.\n'
        '4. «Начальник компрессорного цеха», «начальник энергослужбы» — '
        'это «нач.цеха» и «гл.энергетик» соответственно.\n\n'
        'Должности:\n' + '\n'.join(f'- {д}' for д in пачка))
    тело = json.dumps({
        'model': МОДЕЛЬ,
        'messages': [{'role': 'user', 'content': вопрос}],
        'max_tokens': 4000,
    }).encode()
    зпр = urllib.request.Request(
        база + '/v1/chat/completions', data=тело, method='POST',
        headers={'Authorization': 'Bearer ' + ключ,
                 'Content-Type': 'application/json',
                 'User-Agent': 'curl/8.5.0'})
    try:
        with urllib.request.urlopen(зпр, timeout=300) as о:
            д = json.loads(о.read().decode('utf-8', 'replace'))
        т = д['choices'][0]['message']['content']
        м = re.search(r'\{.*\}', т, re.S)
        return json.loads(м.group(0)) if м else {}
    except Exception as e:  # noqa: BLE001
        print(f'    провайдер не ответил: {str(e)[:120]}')
        return {}


def main():
    csv.field_size_limit(10 ** 7)
    п = os.path.join(ДРОП, 'BAZA-CENTROBEZHNIKI-OBSHCHAYA.csv')
    ряды = list(csv.DictReader(io.StringIO(
        open(п, encoding='utf-8-sig', errors='replace').read()), delimiter=';'))
    цель = [r for r in ряды
            if (r.get('fio') or '').strip()
            and not (r.get('rol_kanon') or '').strip()
            and (r.get('dolzhnost') or '').strip()]
    print(f'строк в базе: {len(ряды)}')
    print(f'людей БЕЗ роли, но С должностью: {len(цель)} '
          f'на {len({r["inn"] for r in цель})} предприятиях')
    if not цель:
        print('доопределять нечего')
        return

    # 1) штатный канон — бесплатно и отлажено
    каноном = {}
    остаток = []
    for r in цель:
        роль = EDB.EnrichDB._canon_role(r['dolzhnost'])
        if роль and роль != 'общий':
            каноном[(r['inn'], r['fio'])] = роль
        else:
            остаток.append(r)
    print(f'  канон взял сразу: {len(каноном)}')
    print(f'  осталось модели: {len(остаток)}')

    # 2) остаток — модели, пачками по 40 уникальных должностей
    уник = sorted({r['dolzhnost'].strip() for r in остаток})
    print(f'  уникальных должностей в остатке: {len(уник)}')
    предел = int(арг('--pachek', '6'))
    отмодели = {}
    for i in range(0, min(len(уник), предел * 40), 40):
        пачка = уник[i:i + 40]
        отв = провайдер(пачка)
        отмодели.update(отв)
        print(f'    пачка {i // 40 + 1}: спросил {len(пачка)}, '
              f'ответов {len(отв)}')

    # 3) сборка, с указанием, чем именно определено
    строки = []
    итог = Counter()
    for r in цель:
        к = (r['inn'], r['fio'])
        if к in каноном:
            роль, чем = каноном[к], 'канон по должности'
        else:
            роль = (отмодели.get(r['dolzhnost'].strip()) or '').strip()
            чем = f'модель {МОДЕЛЬ}' if роль else ''
        if not роль or роль == 'общий':
            итог['роль не определена или общая'] += 1
            continue
        итог[роль] += 1
        строки.append({
            'inn': r['inn'], 'predpriyatie': (r.get('predpriyatie') or '')[:70],
            'fio': r['fio'], 'dolzhnost': r['dolzhnost'][:100],
            'rol_novaya': роль, 'chem_opredelena': чем,
            'telefon': (r.get('vse_nomera') or ''),
            'istochnik': (r.get('istochnik') or '')[:70],
            'ssylka': (r.get('ssylka_na_istochnik') or ''),
            'tehLPR': 'да' if роль in (
                set(EDB.EnrichDB.TECH_ROLES) | {'техконтакт'}) else 'нет',
        })

    путь = os.path.join(r'C:\sender\server', ИМЯ)
    поля = ['inn', 'predpriyatie', 'fio', 'dolzhnost', 'rol_novaya',
            'chem_opredelena', 'telefon', 'istochnik', 'ssylka', 'tehLPR']
    with open(путь, 'w', encoding='utf-8-sig', newline='') as ф:
        w = csv.DictWriter(ф, fieldnames=поля, delimiter=';')
        w.writeheader()
        w.writerows(строки)
        ф.flush()
        os.fsync(ф.fileno())

    вс = тех = 0
    предпр_тех = set()
    чем = Counter()
    with open(путь, encoding='utf-8-sig', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            вс += 1
            чем[r['chem_opredelena']] += 1
            if r['tehLPR'] == 'да':
                тех += 1
                предпр_тех.add(r['inn'])
    print()
    print('=== ЧИСЛА ПЕРЕЧИТЫВАНИЕМ ФАЙЛА ===')
    print(f'  ролей доопределено: {вс}')
    print(f'  из них ТЕХНИЧЕСКИХ: {тех} на {len(предпр_тех)} предприятиях')
    for к, n in чем.most_common():
        print(f'    {n:>5}  {к}')
    print('  распределение ролей:')
    for к, n in итог.most_common(12):
        print(f'    {n:>5}  {к}')

    if ПРИМЕНИТЬ and строки:
        db = EDB.EnrichDB()
        for с in строки:
            # add_person роль НЕ принимает — он выводит её каноном из
            # должности сам. Значит модельную роль в базу через него не
            # протащить, и это правильно: один канон, одно место решения.
            # Пишем должность, а модельную роль отдаём отдельным файлом —
            # пусть решает тот, кто держит канон, а не я в обход него.
            db.add_person(с['inn'], с['fio'], post=с['dolzhnost'],
                          phone=с['telefon'],
                          source=(с['istochnik'] or 'роль доопределена')[:90],
                          source_url=с['ssylka'])
        db.cx.commit()
        print('  записано в enrich.db через штатный писатель')

    try:
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        urllib.request.urlopen(urllib.request.Request(
            урл.rstrip('/') + '/' + ИМЯ, data=open(путь, 'rb').read(),
            method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
            timeout=300).read()
        print(f'  на дропе: {ИМЯ}')
    except Exception as e:  # noqa: BLE001
        print(f'  на дроп НЕ легло: {str(e)[:110]}')


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
r"""Полная выгрузка ЦА O2/N2 для загрузки в базу (11.11, владелец: «это разве все контакты компании? мне нужен список,
чтобы я их в базу загрузил, вообще все поля информации, которые у нас есть»).

Лист «Компании» — одна строка на компанию списка ca-spisok.json: реквизиты, ОКВЭД, отрасль, газ, выручка, штат, МСП,
сайт и как он подтверждён, все поля паспорта, признаки газа на сайте и в тендерах, техпроцесс и боли (карточки
ca_boli), все почты и телефоны (сводно), сделки Битрикса, база обзвона, статус обработки.
Лист «Контакты» — одна строка на контакт, все найденные: сайт компании (обход; чужие номера «чей: другая» — вон),
агенты (принятые перепроверкой, ca-glubokiy2.jsonl), чистые ЕИС. ФИО, должность, роль, ЛПР, телефон, доб., почта,
тип почты, источник и страница.
Выход: ca\CA-ENGER-BAZA.xlsx и два CSV (utf-8-sig, «;») — CA-ENGER-BAZA-kompanii.csv, CA-ENGER-BAZA-kontakty.csv
(+ дроп). Персональные данные — только сервер и дроп, не репозиторий.
"""
import collections, csv, io, json, os, re, sqlite3, sys

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
ДРОП = r'C:\seostat\drop\drop-storage'
sys.path.insert(0, DIR)
import ca_cel  # noqa: E402
import ca_vygruzka as V  # noqa: E402  (регионы, ролевые ящики, карточки отраслей)

БЕСПЛАТНЫЕ = re.compile(r'@(?:mail|inbox|list|bk|internet|yandex|ya|gmail|rambler|hotmail|outlook|icloud|lenta|ro)\.(?:ru|com|ua|by|kz)$', re.I)


def тип_почты(п, сайт=''):
    п = (п or '').lower()
    лок, _, дом = п.partition('@')
    ядро_дом = re.sub(r'^www\.', '', дом).split('.')[0]
    ядро_сайт = re.sub(r'^https?://(www\.)?', '', (сайт or '').lower()).split('/')[0].split('.')[0]
    if V.РОЛЕВЫЕ.match(лок):
        if re.match(r'(snab|zakup|supply|tender|ogm|oge|ogt|energ|glavinzh|tech|teh|proizv|production|mehanik|otk|lab|quality|kachestvo)', лок):
            return 'служба (снабжение/техническая)'
        if re.match(r'(sales?|zakaz|order|opt|market|reklama|hr|kadr|buh|account|finance|job|rabota|resume|vacancy|press|smi|noreply|no-reply|roznica|retail|shop|store|dostavka|delivery|logist)', лок):
            return 'служба (продажи/прочие)'
        return 'общая'
    # ящик с названием компании (efti@efti.ru) — общий, не личный
    if лок and (лок == ядро_дом or лок == ядро_сайт or (len(лок) >= 4 and (лок in ядро_дом or ядро_дом in лок))):
        return 'общая (название компании)'
    if re.fullmatch(r'[\d._-]+', лок or ''):
        return 'прочая'
    return 'личная, бесплатный ящик' if БЕСПЛАТНЫЕ.search(п) else 'личная'


def jl(п):
    if os.path.exists(п):
        for s in io.open(п, encoding='utf-8', errors='replace'):
            try:
                yield json.loads(s)
            except ValueError:
                continue


def спис(x, предел=600):
    if isinstance(x, list):
        x = '; '.join(map(str, x))
    elif isinstance(x, dict):
        x = '; '.join('%s: %s' % (k, v) for k, v in x.items() if v)
    x = str(x or '').strip()
    return x if len(x) <= предел else x[:предел].rsplit(' ', 1)[0] + '…'


def main():
    кар = V.карточки()
    сп = json.load(io.open(os.path.join(DIR, 'ca-spisok.json'), encoding='utf-8'))['компании']
    пасп = {str(з.get('inn')): з.get('паспорт') or {} for з in jl(os.path.join(DIR, 'ca-pasport.jsonl'))}
    зап = {з['inn']: з for з in jl(os.path.join(DIR, 'ca-kontakty.jsonl')) if з.get('итог') == 'ok'}
    сайт_чей = {}
    for имя in ('ca-audit.jsonl', 'ca-audit2.jsonl'):
        for з in jl(os.path.join(DIR, имя)):
            if з.get('inn') and з.get('сайт_чей'):
                сайт_чей[з['inn']] = з['сайт_чей']
    модель_сайт = {з['inn']: з.get('итог') for з in jl(os.path.join(DIR, 'ca-sayt-proverka.jsonl')) if з.get('inn')}
    опров = {з['inn']: з.get('итог') for з in jl(os.path.join(DIR, 'ca-oprov.jsonl')) if з.get('inn')}
    агент = {}
    for з in jl(os.path.join(DIR, 'ca-glubokiy2.jsonl')):
        if з.get('inn'):
            агент[з['inn']] = з
    # 11.11: агент «ЛПР при известном сайте» (принятое перепроверкой, ca-lpr-agent2.jsonl) — отдельно, источник свой
    агент_лпр = {з['inn']: з for з in jl(os.path.join(DIR, 'ca-lpr-agent2.jsonl')) if з.get('inn')} \
        if os.path.exists(os.path.join(DIR, 'ca-lpr-agent2.jsonl')) else {}
    еис = collections.defaultdict(list)
    for x in jl(os.path.join(ПАПКА, 'ca-zakupki-chistye.jsonl')):
        еис[x['inn']].append(x)
    сиг = {з['inn']: з for з in jl(os.path.join(ПАПКА, 'ca-signaly.jsonl')) if з.get('inn')}
    сделки = json.load(io.open(os.path.join(ДРОП, 'sdelki-vse-1410.json'), encoding='utf-8'))
    база = {}
    try:
        con = sqlite3.connect('file:C:/sender/obzvon-index.db?mode=ro', uri=True, timeout=120)
        for инн, н in con.execute('select inn, base_label from obzvon'):
            база[str(инн)] = н or ''
        con.close()
    except Exception:  # noqa: BLE001
        pass
    очередь = set(json.load(io.open(os.path.join(ДРОП, 'ca-glubokiy-vhod.json'), encoding='utf-8'))) \
        if os.path.exists(os.path.join(ДРОП, 'ca-glubokiy-vhod.json')) else set()

    компании, контакты = [], []
    for инн, к in сп.items():
        кат = [c for c in (к.get('сегм') or '').split(', ') if c in ca_cel.КАТ]
        гл = sorted(кат, key=lambda c: ('ядро', 'новая', 'по нашим сделкам', 'резерв').index(ca_cel.КАТ[c][1])
                    if ca_cel.КАТ[c][1] in ('ядро', 'новая', 'по нашим сделкам', 'резерв') else 9)[0] if кат else ''
        з = зап.get(инн) or {}
        сайт = з.get('сайт') or к.get('сайт') or ''
        рег = к.get('регион') or ''
        рег = V.РЕГИОНЫ.get(рег, рег) if re.fullmatch(r'\d{2}', рег) else рег
        if not рег and re.fullmatch(r'\d{10}', инн):
            рег = V.РЕГИОНЫ.get(инн[:2], '')
        имя = к.get('имя') or ''
        # ---- контакты ----
        свои = []
        for x in з.get('номера') or []:
            if x.get('чей') == 'другая':
                continue
            свои.append({'ФИО': x.get('фио') or '', 'Должность': x.get('должность') or '', 'Роль': x.get('роль') or '',
                         'ЛПР': x.get('лпр') or '', 'Телефон': x.get('номер') or '', 'Доб.': x.get('доб') or '',
                         'Почта': x.get('почта') or '', 'Источник': 'сайт компании',
                         'Страница': (x.get('страницы') or [''])[0]})
        аг = агент.get(инн) or {}
        for ист, а_ in (('агент (проверен)', аг), ('агент ЛПР по сайту (проверен)', агент_лпр.get(инн) or {})):
            for x in (а_.get('номера') or []) + (а_.get('почты') or []):
                if not isinstance(x, dict) or x.get('чей') == 'другая':
                    continue
                свои.append({'ФИО': x.get('фио') or '', 'Должность': x.get('должность') or '', 'Роль': x.get('класс') or '',
                             'ЛПР': '', 'Телефон': x.get('номер') or '', 'Доб.': '', 'Почта': x.get('почта') or '',
                             'Источник': ист, 'Страница': x.get('url') or ''})
        for x in еис.get(инн, []):
            свои.append({'ФИО': x.get('фио') or '', 'Должность': x.get('должность') or 'контактное лицо закупок',
                         'Роль': 'Закупки / снабжение', 'ЛПР': '', 'Телефон': x.get('телефон') or '', 'Доб.': '',
                         'Почта': x.get('почта') or '', 'Источник': 'закупки ЕИС (%s)' % x.get('вердикт', ''),
                         'Страница': x.get('url') or ''})
        видел = set()
        for ч in свои:
            ключ = (re.sub(r'\D', '', ч['Телефон'])[-10:], ч['Доб.'], ч['Почта'].lower(), ч['ФИО'].lower())
            if ключ in видел or not (ч['Телефон'] or ч['Почта']):
                continue
            видел.add(ключ)
            контакты.append(dict({'ИНН': инн, 'Компания': имя}, **ч,
                                 **{'Тип почты': тип_почты(ч['Почта'], сайт) if ч['Почта'] else ''}))
        почты = list(dict.fromkeys(ч['Почта'].lower() for ч in свои if ч['Почта']))
        тел = list(dict.fromkeys((ч['Телефон'] + (' доб. ' + ч['Доб.'] if ч['Доб.'] else '')) for ч in свои if ч['Телефон']))
        # ---- компания ----
        п = пасп.get(инн) or {}
        п = п if isinstance(п, dict) else {}
        с = сиг.get(инн) or {}
        if з:
            статус = 'обработана, ждёт агента' if (инн in очередь and инн not in агент and (к.get('выручка') or 0) >= 120e6) \
                else 'обработана полностью'
        else:
            статус = 'в очереди обхода'
        компании.append({
            'ИНН': инн, 'Компания': имя, 'Регион': рег, 'Выручка, млн ₽': round((к.get('выручка') or 0) / 1e6),
            'Штат (ССЧ)': к.get('ссч') or '', 'МСП': к.get('мсп') or '', 'ОКВЭД основной': к.get('осн') or '',
            'ОКВЭД все': ', '.join(к.get('все') or []), 'Отрасль': ' | '.join(ca_cel.КАТ[c][2].replace(';', ',') for c in кат),
            'Статус отрасли': ca_cel.КАТ[гл][1] if гл else '', 'Газ': V.ГАЗ[ca_cel.КАТ[гл][0]] if гл else '',
            'Техпроцесс (где нужен газ)': (кар.get(гл) or {}).get('техпроцесс', ''), 'Боли': (кар.get(гл) or {}).get('боли', ''),
            'Сайт': сайт, 'Сайт: ИНН/название на сайте': сайт_чей.get(инн, ''), 'Сайт: проверка моделью': модель_сайт.get(инн, '') or '',
            'Сайт: опровергатель': опров.get(инн, '') or '',
            'Сайт завода (агент)': аг.get('сайт_завода') or '', 'Сайт холдинга (агент)': аг.get('сайт_холдинга') or '',
            'Описание (сайт)': з.get('описание') or '',
            'Продукция': спис(п.get('продукция')), 'Оборудование, линии': спис(п.get('оборудование_линии')),
            'Мощности': спис(п.get('мощности')), 'Сырьё': спис(п.get('сырьё')), 'Упаковка, фасовка': спис(п.get('упаковка_фасовка')),
            'Контроль качества': спис(п.get('контроль_качества')), 'Масштаб': спис(п.get('масштаб')),
            'Год основания': спис(п.get('год_основания')), 'Экспорт': спис(п.get('экспорт')),
            'География поставок': спис(п.get('география_поставок')), 'Клиенты': спис(п.get('клиенты')),
            'Энергохозяйство': спис(п.get('энергохозяйство')), 'Газы (паспорт)': спис(п.get('газы')),
            'Расширение': спис(п.get('расширение')), 'Свежая новость': спис(п.get('свежая_новость')),
            'Признаки газа на сайте': ', '.join(sorted((с.get('кэш') or {}).keys())),
            'Тендеры на газ': '; '.join(t.get('название', '')[:120] for t in (с.get('тендеры_газ') or [])[:3]),
            'Почты (все)': ', '.join(почты), 'Телефоны (все)': ', '.join(тел),
            'Контактов': len(видел),
            'ЛПР найден': 'да' if any(ч['ЛПР'] == 'да' for ч in свои) else 'нет',
            'Сделки Битрикса': '; '.join(sorted({'%s: %s' % (d[0], d[1]) for d in сделки.get(инн) or []})),
            'База обзвона': база.get(инн, ''), 'Статус обработки': статус})
    кол_к = list(компании[0].keys())
    кол_ч = ['ИНН', 'Компания', 'ФИО', 'Должность', 'Роль', 'ЛПР', 'Телефон', 'Доб.', 'Почта', 'Тип почты', 'Источник', 'Страница']
    for имя_, строки, кол in (('CA-ENGER-BAZA-kompanii.csv', компании, кол_к), ('CA-ENGER-BAZA-kontakty.csv', контакты, кол_ч)):
        with io.open(os.path.join(ПАПКА, имя_), 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=кол, delimiter=';', extrasaction='ignore')
            w.writeheader()
            w.writerows(строки)
    import openpyxl
    from openpyxl.styles import Font
    wb = openpyxl.Workbook(write_only=True)
    for лист, строки, кол in (('Компании', компании, кол_к), ('Контакты', контакты, кол_ч)):
        ws = wb.create_sheet(лист)
        ws.append(кол)
        for r in строки:
            # openpyxl не принимает управляющие символы (IllegalCharacterError)
            ws.append([re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', v) if isinstance(v, str) else v for v in (r.get(k, '') for k in кол)])
    вх = os.path.join(ПАПКА, 'CA-ENGER-BAZA.xlsx')
    wb.save(вх)
    import shutil
    for имя_ in ('CA-ENGER-BAZA.xlsx', 'CA-ENGER-BAZA-kompanii.csv', 'CA-ENGER-BAZA-kontakty.csv'):
        shutil.copyfile(os.path.join(ПАПКА, имя_), os.path.join(ДРОП, имя_))
    print('===ИТОГ===', json.dumps({
        'компаний': len(компании), 'контактов': len(контакты),
        'статус': dict(collections.Counter(r['Статус обработки'] for r in компании)),
        'компаний_с_почтой': sum(1 for r in компании if r['Почты (все)']),
        'компаний_с_телефоном': sum(1 for r in компании if r['Телефоны (все)']),
        'тип_почты': dict(collections.Counter(r['Тип почты'] for r in контакты if r['Тип почты'])),
        'источник': dict(collections.Counter(r['Источник'][:14] for r in контакты)),
        'с_ФИО': sum(1 for r in контакты if r['ФИО'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()

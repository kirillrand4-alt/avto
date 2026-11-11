# -*- coding: utf-8 -*-
r"""Выгрузка готовых компаний ЦА O2/N2 для заливки (11.11, владелец: «дай готовые компании файлом для заливки, все поля
должны быть заполнены, включая отрасли и боли, техпроцесс их и под какой газ они нам подходят»).

Строка = один контакт ЛПР. Берутся только строки, где заполнены ВСЕ поля: ИНН, компания, регион, выручка, сайт,
продукция (паспорт), отрасль, газ, техпроцесс и боли (карточка отрасли из ca_boli, физика проверена поиском), ФИО,
должность, личная почта, телефон (свой у того же человека, иначе основной телефон компании — колонка «Чей телефон»).
Контакты — с сайта («лпр: да», не чужой номер) и чистые ЕИС (закупщики).
Исключения уже применены при сборке списка (активные сделки КЦ, запреты панели, гос, конкуренты).
Лист 2 «Компании»: без ЛПР, но с почтой и продукцией, по которым больше ничего не найдём (см. ниже).
Выход: ca\CA-ENGER-ZALIVKA.csv, CA-ENGER-ZALIVKA-kompanii.csv (utf-8-sig, «;») и .xlsx с двумя листами (+ дроп). Персональные данные — только на сервере и в дропе.
"""
import collections, csv, io, json, os, re, sys

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
ДРОП = r'C:\seostat\drop\drop-storage'
sys.path.insert(0, DIR)
import ca_cel  # noqa: E402

РЕГИОНЫ = {'01': 'Республика Адыгея', '02': 'Республика Башкортостан', '03': 'Республика Бурятия', '04': 'Республика Алтай',
           '05': 'Республика Дагестан', '06': 'Республика Ингушетия', '07': 'Кабардино-Балкарская Республика',
           '08': 'Республика Калмыкия', '09': 'Карачаево-Черкесская Республика', '10': 'Республика Карелия', '11': 'Республика Коми',
           '12': 'Республика Марий Эл', '13': 'Республика Мордовия', '14': 'Республика Саха (Якутия)',
           '15': 'Республика Северная Осетия', '16': 'Республика Татарстан', '17': 'Республика Тыва', '18': 'Удмуртская Республика',
           '19': 'Республика Хакасия', '20': 'Чеченская Республика', '21': 'Чувашская Республика', '22': 'Алтайский край',
           '23': 'Краснодарский край', '24': 'Красноярский край', '25': 'Приморский край', '26': 'Ставропольский край',
           '27': 'Хабаровский край', '28': 'Амурская область', '29': 'Архангельская область', '30': 'Астраханская область',
           '31': 'Белгородская область', '32': 'Брянская область', '33': 'Владимирская область', '34': 'Волгоградская область',
           '35': 'Вологодская область', '36': 'Воронежская область', '37': 'Ивановская область', '38': 'Иркутская область',
           '39': 'Калининградская область', '40': 'Калужская область', '41': 'Камчатский край', '42': 'Кемеровская область',
           '43': 'Кировская область', '44': 'Костромская область', '45': 'Курганская область', '46': 'Курская область',
           '47': 'Ленинградская область', '48': 'Липецкая область', '49': 'Магаданская область', '50': 'Московская область',
           '51': 'Мурманская область', '52': 'Нижегородская область', '53': 'Новгородская область', '54': 'Новосибирская область',
           '55': 'Омская область', '56': 'Оренбургская область', '57': 'Орловская область', '58': 'Пензенская область',
           '59': 'Пермский край', '60': 'Псковская область', '61': 'Ростовская область', '62': 'Рязанская область',
           '63': 'Самарская область', '64': 'Саратовская область', '65': 'Сахалинская область', '66': 'Свердловская область',
           '67': 'Смоленская область', '68': 'Тамбовская область', '69': 'Тверская область', '70': 'Томская область',
           '71': 'Тульская область', '72': 'Тюменская область', '73': 'Ульяновская область', '74': 'Челябинская область',
           '75': 'Забайкальский край', '76': 'Ярославская область', '77': 'Москва', '78': 'Санкт-Петербург', '79': 'Еврейская АО',
           '83': 'Ненецкий АО', '86': 'Ханты-Мансийский АО', '87': 'Чукотский АО', '89': 'Ямало-Ненецкий АО', '91': 'Республика Крым',
           '92': 'Севастополь'}
РОЛЕВЫЕ = re.compile(
    r'^(info|office|mail|post|pochta|sales?|zakaz|order|orders|priem\w*|reception|secretar\w*|sekretar\w*|snab\w*|zakup\w*|'
    r'supply|tender\w*|ogm|oge|ogt|energ\w*|mehanik|hr|kadr\w*|buh\w*|account\w*|finance|market\w*|reklama|pr|export|import|'
    r'ved|support|help|admin|director|dir|gendir|ceo|contact\w*|kontakt\w*|feedback|hello|service|servis|manager|managers|'
    r'opt|roznica|retail|shop|store|logist\w*|dostavka|delivery|kanc\w*|general|no-?reply|noreply|webmaster|press|smi|job|'
    r'jobs|rabota|resume|vacancy|personal|otk|lab\w*|quality|kachestvo|tech\w*|teh\w*|proizv\w*|production|glavinzh\w*|ogk|'
    r'ok|yur\w*|legal|ur|security|sb|it|zavod|plant|company|firm\w*)\d*$', re.I)
# 11.11, владелец: «телефон сейчас не нужен» — строки без телефона не отсеиваем
НЕОБЯЗ = {'Телефон', 'Чей телефон'}
ГАЗ = {'O2': 'Кислород (O2): станция Enger PSA, 93±3 %', 'N2': 'Азот (N2): станция Enger PSA, 98–99,999 %'}


def личная(почта):
    лок = (почта or '').split('@')[0].lower()
    return bool(лок) and not РОЛЕВЫЕ.match(лок) and not re.fullmatch(r'[\d._-]+', лок)


def чисто(т, предел=700):
    т = re.sub(r'\*\*|`|^#+\s*', '', т or '', flags=re.M)
    т = re.sub(r'^\s*(?:[-*]|\d+\.)\s+', '• ', т, flags=re.M)
    т = re.sub(r'\s*---\s*$', '', т.strip())
    т = re.sub(r'[ \t]+', ' ', т).replace(' -- ', ' – ').replace('--', '–')
    т = re.sub(r'\n{2,}', '\n', т).strip()
    return т if len(т) <= предел else т[:предел].rsplit(' ', 1)[0] + '…'


def карточки():
    т = io.open(os.path.join(ПАПКА, 'CA-BOLI.md'), encoding='utf-8').read()
    out = {}
    for ч in re.split(r'\n(?=## (?:O2|N2) )', т):
        м = re.match(r'## (?:O2|N2) .*\((\w+), сейчас', ч)
        if not м:
            continue
        def раздел(имя):
            р = re.search(r'\*\*%s[^*\n]*\*\*:?(.*?)(?=\n\*\*[А-ЯЁ]|\nИсточники проверки|\Z)' % имя, ч, re.S)
            return чисто(р.group(1)) if р else ''
        тп = раздел('Где реально нужна станция')
        if м.group(1).startswith('n2_'):  # GO — кислородная серия Enger, азотная — GN (судья путал в карточке РГС)
            тп = re.sub(r'Enger\s+GO\s+N2', 'Enger GN', тп)
        out[м.group(1)] = {'техпроцесс': тп, 'боли': раздел('Топ-3 боли'), 'физика': раздел('Физика')}
    return out


def main():
    кар = карточки()
    сп = json.load(io.open(os.path.join(DIR, 'ca-spisok.json'), encoding='utf-8'))['компании']
    продукция = {}
    for s in io.open(os.path.join(DIR, 'ca-pasport.jsonl'), encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        п = з.get('паспорт') or {}
        if isinstance(п, dict) and п.get('продукция'):
            пр = п['продукция']
            продукция[str(з.get('inn'))] = '; '.join(map(str, пр))[:300] if isinstance(пр, list) else str(пр)[:300]
    зап = {}
    for s in io.open(os.path.join(DIR, 'ca-kontakty.jsonl'), encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('итог') == 'ok':
            зап[з['inn']] = з
    еис = collections.defaultdict(list)
    п = os.path.join(ПАПКА, 'ca-zakupki-chistye.jsonl')
    if os.path.exists(п):
        for s in io.open(п, encoding='utf-8'):
            x = json.loads(s)
            еис[x['inn']].append(x)
    строки, причины = [], collections.Counter()
    for инн, к in сп.items():
        кат = [c for c in (к.get('сегм') or '').split(', ') if c in ca_cel.КАТ]
        if not кат:
            continue
        гл = sorted(кат, key=lambda c: ('ядро', 'новая', 'по нашим сделкам', 'резерв').index(ca_cel.КАТ[c][1])
                    if ca_cel.КАТ[c][1] in ('ядро', 'новая', 'по нашим сделкам', 'резерв') else 9)[0]
        газ_ = ca_cel.КАТ[гл][0]
        з = зап.get(инн) or {}
        рег = к.get('регион') or ''
        рег = РЕГИОНЫ.get(рег, рег) if re.fullmatch(r'\d{2}', рег) else рег
        if not рег and re.fullmatch(r'\d{10}', инн):
            рег = РЕГИОНЫ.get(инн[:2], '')
        общее = {'ИНН': инн, 'Компания': к.get('имя') or '', 'Регион': рег,
                 'Выручка, млн ₽': round((к.get('выручка') or 0) / 1e6) or '', 'Сайт': з.get('сайт') or к.get('сайт') or '',
                 'Отрасль': '; '.join(ca_cel.КАТ[c][2] for c in кат), 'Газ': ГАЗ[газ_],
                 'Техпроцесс (где нужен газ)': (кар.get(гл) or {}).get('техпроцесс', ''),
                 'Боли': (кар.get(гл) or {}).get('боли', ''), 'Продукция': продукция.get(инн, '')}
        люди = []
        ном = [x for x in з.get('номера') or [] if x.get('чей') != 'другая']
        # телефон к почте ЛПР: почта и номер на сайте — разные записи. Свой номер того же человека (по ФИО), иначе
        # основной телефон компании: приёмная/общий, затем любой номер ЛПР, затем любой номер компании
        def тел(x):
            return (x.get('номер') or '').strip() + ((' доб. ' + x['доб']) if x.get('доб') else '')
        тел_по_фио = {(x.get('фио') or '').strip().lower(): тел(x) for x in ном if x.get('номер') and (x.get('фио') or '').strip()}
        общий = next((тел(x) for x in ном if x.get('номер') and 'приём' in (x.get('роль') or '').lower()), '') or \
            next((тел(x) for x in ном if x.get('номер') and x.get('лпр') == 'да'), '') or \
            next((тел(x) for x in ном if x.get('номер')), '')
        for x in ном:
            if x.get('лпр') == 'да' and личная(x.get('почта')):
                фио = (x.get('фио') or '').strip()
                свой = тел(x) if x.get('номер') else тел_по_фио.get(фио.lower(), '')
                люди.append({'ФИО': фио, 'Должность': (x.get('должность') or x.get('роль') or '').strip(),
                             'Почта': x['почта'], 'Телефон': свой or общий,
                             'Чей телефон': 'личный' if свой else ('общий компании' if общий else 'нет'),
                             'Источник контакта': 'сайт компании'})
        for x in еис.get(инн, []):
            if личная(x.get('почта')):
                свой = (x.get('телефон') or '').strip()
                люди.append({'ФИО': (x.get('фио') or '').strip(), 'Должность': (x.get('должность') or 'контактное лицо закупок').strip(),
                             'Почта': x['почта'], 'Телефон': свой or общий,
                             'Чей телефон': 'личный (из закупки)' if свой else 'общий компании',
                             'Источник контакта': 'закупки ЕИС (%s)' % x.get('вердикт', '')})
        if not люди:
            причины['нет ЛПР с личной почтой'] += 1
            continue
        видел = set()
        for ч in люди:
            ключ = (ч['Почта'].lower(), re.sub(r'\D', '', ч['Телефон'])[-10:])
            if ключ in видел:
                continue
            видел.add(ключ)
            r = dict(общее, **ч)
            пустые = [k for k, v in r.items() if not str(v).strip() and k not in НЕОБЯЗ]
            if пустые:
                for k in пустые:
                    причины['пусто: ' + k] += 1
                continue
            строки.append(r)
    строки.sort(key=lambda r: (r['Газ'], r['Отрасль'], -int(r['Выручка, млн ₽'] or 0)))
    # 11.11, владелец: «там, где есть почта (любая) + продукция, но они уже обработаны и больше мы ничего по ним не найдём,
    # тоже в файл». Компании без строки ЛПР: обход пройден (запись ok), паспорт с продукцией, есть почта, и агенты ничего
    # не добавят — агент уже отработал, либо компания не в очереди агентов (сайт подтверждён или выручка < 120 млн)
    с_лпр = {r['ИНН'] for r in строки}
    агент_был = set()
    п = os.path.join(DIR, 'ca-glubokiy.jsonl')
    if os.path.exists(п):
        for s_ in io.open(п, encoding='utf-8', errors='replace'):
            try:
                агент_был.add(json.loads(s_)['inn'])
            except (ValueError, KeyError):
                pass
    п = os.path.join(ДРОП, 'ca-glubokiy-vhod.json')
    очередь_агентов = set(json.load(io.open(п, encoding='utf-8'))) if os.path.exists(п) else set()
    компании = []
    for инн, к in сп.items():
        if инн in с_лпр or инн not in зап or not продукция.get(инн):
            continue
        if инн in очередь_агентов and инн not in агент_был and (к.get('выручка') or 0) >= 120e6:
            причины['компания: ждёт агента'] += 1
            continue
        з = зап[инн]
        ном = [x for x in з.get('номера') or [] if x.get('чей') != 'другая']
        почты = [x['почта'] for x in ном if x.get('почта')] + [x['почта'] for x in еис.get(инн, []) if x.get('почта')]
        if not почты:
            причины['компания: нет почты'] += 1
            continue
        def вес(п_):
            л = п_.split('@')[0].lower()
            if личная(п_):
                return 0
            if re.match(r'(snab|zakup|supply|tender|ogm|oge|ogt|energ|glavinzh|tech|teh|proizv|production|mehanik)', л):
                return 1
            if re.match(r'(info|office|mail|post|priem|reception|secretar|sekretar|general|kontakt|contact|zavod|plant)', л):
                return 2
            if re.match(r'(sales?|zakaz|order|opt|market|reklama|hr|kadr|buh|account|finance|job|rabota|resume|vacancy|press|smi|noreply|no-reply)', л):
                return 4
            return 3
        почта = sorted(dict.fromkeys(почты), key=вес)[0]
        def тел(x):
            return (x.get('номер') or '').strip() + ((' доб. ' + x['доб']) if x.get('доб') else '')
        телефон = next((тел(x) for x in ном if x.get('номер') and 'приём' in (x.get('роль') or '').lower()), '') or \
            next((тел(x) for x in ном if x.get('номер') and x.get('лпр') == 'да'), '') or \
            next((тел(x) for x in ном if x.get('номер')), '')
        кат = [c for c in (к.get('сегм') or '').split(', ') if c in ca_cel.КАТ]
        if not кат:
            continue
        гл = sorted(кат, key=lambda c: ('ядро', 'новая', 'по нашим сделкам', 'резерв').index(ca_cel.КАТ[c][1])
                    if ca_cel.КАТ[c][1] in ('ядро', 'новая', 'по нашим сделкам', 'резерв') else 9)[0]
        рег = к.get('регион') or ''
        рег = РЕГИОНЫ.get(рег, рег) if re.fullmatch(r'\d{2}', рег) else рег
        if not рег and re.fullmatch(r'\d{10}', инн):
            рег = РЕГИОНЫ.get(инн[:2], '')
        r = {'ИНН': инн, 'Компания': к.get('имя') or '', 'Регион': рег,
             'Выручка, млн ₽': round((к.get('выручка') or 0) / 1e6) or '', 'Сайт': з.get('сайт') or к.get('сайт') or '',
             'Отрасль': '; '.join(ca_cel.КАТ[c][2] for c in кат), 'Газ': ГАЗ[ca_cel.КАТ[гл][0]],
             'Техпроцесс (где нужен газ)': (кар.get(гл) or {}).get('техпроцесс', ''), 'Боли': (кар.get(гл) or {}).get('боли', ''),
             'Продукция': продукция.get(инн, ''), 'Почта': почта,
             'Тип почты': ['личная', 'служба (снабжение/техническая)', 'общая', 'прочая', 'продажи/прочие службы'][вес(почта)],
             'Телефон': телефон, 'Почему без ЛПР': 'агент отработал' if инн in агент_был else 'обход и проверки пройдены, агент не нужен'}
        пустые = [k for k, v in r.items() if not str(v).strip() and k not in НЕОБЯЗ]
        if пустые:
            for k in пустые:
                причины['компания пусто: ' + k] += 1
            continue
        компании.append(r)
    компании.sort(key=lambda r: (r['Газ'], r['Отрасль'], -int(r['Выручка, млн ₽'] or 0)))
    кол = ['ИНН', 'Компания', 'Регион', 'Выручка, млн ₽', 'Сайт', 'Отрасль', 'Газ', 'Техпроцесс (где нужен газ)', 'Боли',
           'Продукция', 'ФИО', 'Должность', 'Почта', 'Телефон', 'Чей телефон', 'Источник контакта']
    вых = os.path.join(ПАПКА, 'CA-ENGER-ZALIVKA.csv')
    with io.open(вых, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=кол, delimiter=';')
        w.writeheader()
        w.writerows(строки)
    import openpyxl
    from openpyxl.styles import Alignment, Font
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Заливка'
    ws.append(кол)
    for r in строки:
        ws.append([r[k] for k in кол])
    for c in ws[1]:
        c.font = Font(bold=True)
    ширина = {'ИНН': 13, 'Компания': 38, 'Регион': 22, 'Выручка, млн ₽': 11, 'Сайт': 26, 'Отрасль': 34, 'Газ': 30,
              'Техпроцесс (где нужен газ)': 60, 'Боли': 60, 'Продукция': 45, 'ФИО': 28, 'Должность': 30, 'Почта': 30,
              'Телефон': 20, 'Чей телефон': 16, 'Источник контакта': 22}
    for i, k in enumerate(кол, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = ширина.get(k, 20)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical='top')
    ws.freeze_panes = 'C2'
    ws.auto_filter.ref = ws.dimensions
    кол2 = ['ИНН', 'Компания', 'Регион', 'Выручка, млн ₽', 'Сайт', 'Отрасль', 'Газ', 'Техпроцесс (где нужен газ)', 'Боли',
            'Продукция', 'Почта', 'Тип почты', 'Телефон', 'Почему без ЛПР']
    вых2 = os.path.join(ПАПКА, 'CA-ENGER-ZALIVKA-kompanii.csv')
    with io.open(вых2, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=кол2, delimiter=';')
        w.writeheader()
        w.writerows(компании)
    ws2 = wb.create_sheet('Компании (общая почта)')
    ws2.append(кол2)
    for r in компании:
        ws2.append([r[k] for k in кол2])
    for c in ws2[1]:
        c.font = Font(bold=True)
    for i, k in enumerate(кол2, 1):
        ws2.column_dimensions[openpyxl.utils.get_column_letter(i)].width = ширина.get(k, 24)
    for row in ws2.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical='top')
    ws2.freeze_panes = 'C2'
    ws2.auto_filter.ref = ws2.dimensions
    ws.title = 'ЛПР'
    вх = os.path.join(ПАПКА, 'CA-ENGER-ZALIVKA.xlsx')
    wb.save(вх)
    import shutil
    for ф in (вых, вых2, вх):
        shutil.copyfile(ф, os.path.join(ДРОП, os.path.basename(ф)))
    print('===ИТОГ===', json.dumps({'строк': len(строки), 'компаний': len({r['ИНН'] for r in строки}),
                                     'лист_компании': len(компании),
                                     'лист_компании_тип_почты': dict(collections.Counter(r['Тип почты'] for r in компании)),
                                     'лист_компании_почему': dict(collections.Counter(r['Почему без ЛПР'] for r in компании)),
                                     'по_газу': dict(collections.Counter(r['Газ'][:12] for r in строки)),
                                     'по_отрасли_компаний': dict(collections.Counter(r['Отрасль'].split(';')[0] for r in
                                                                                     {r['ИНН']: r for r in строки}.values())),
                                     'по_источнику': dict(collections.Counter(r['Источник контакта'][:12] for r in строки)),
                                     'чей_телефон': dict(collections.Counter(r['Чей телефон'] for r in строки)),
                                     'отсев': dict(причины.most_common(12)), 'карточек': len(кар)}, ensure_ascii=False))


if __name__ == '__main__':
    main()

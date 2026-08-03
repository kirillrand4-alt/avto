# -*- coding: utf-8 -*-
"""Свести ВСЕХ добытых людей в один список обзвона. Пункт 16 владельца.

ЗАЧЕМ. Обратная проверка показала главный разрыв: людей мы добыли тысячами, а в списке для
продавца (`SPISOK-OBZVONA.csv`) 385 строк. Причина простая — `svesti_obzvon.py` читает ПЯТЬ
файлов из десяти, а список входов зашит в код. Вне свода остались личные номера третьей сессии,
люди Тендер.Про, роли, вложения ЕИС, лица со страниц сайтов и весь обход сайтов.

ПРАВИЛО ВЛАДЕЛЬЦА, которое здесь соблюдается буквально: **провенанс накапливается, а не
заменяется**. Один и тот же человек, найденный в трёх источниках, даёт ОДНУ строку с тремя
источниками и числом 3 — а не три строки и не последний победивший. Подтверждённое трижды
обязано быть отличимо от подтверждённого однажды.

ВТОРОЕ ПРАВИЛО: разделять, а не отсеивать. Ничего не выбрасывается. Вид контакта пишется явно
(личный мобильный, прямой номер, приёмная, отдел, почта), чтобы продавец видел, что берёт.
"""
import csv
import os
import re
import sys

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
LENS = os.path.join(BAZA, 'engineers-lens')

ROLI = [
    (r'главн\w+ инженер|технический директор', 5.0, 'главный инженер'),
    (r'главн\w+ (механик|энергетик)', 4.5, 'главный механик или энергетик'),
    (r'компрессорн|воздухоразделени|кислородн\w+ цех', 4.0, 'компрессорное хозяйство'),
    (r'начальник\w*\s+(цеха|производств|участка)|директор по производств', 3.5, 'производство'),
    (r'главн\w+ технолог', 3.0, 'технолог'),
    (r'снабж|закуп|тендер|мто|мтс|коммерческ', 2.5, 'снабжение или закупки'),
    (r'энергетик|механик|инженер', 2.0, 'инженерная служба'),
    (r'директор|руководител', 1.5, 'первое лицо'),
]


def rol_ves(dolzh, gotovaya=''):
    t = f'{dolzh} {gotovaya}'.lower()
    for rx, ves, imya in ROLI:
        if re.search(rx, t):
            return ves, imya
    return 0.5, (gotovaya or 'роль не установлена')


def nomer(s):
    d = re.sub(r'\D', '', str(s or ''))
    if len(d) == 11 and d[0] in '78':
        d = d[1:]
    return d if len(d) == 10 else ''


def vid_nomera(n, podskazka=''):
    p = (podskazka or '').lower()
    if n.startswith('9'):
        return 'личный мобильный' if 'мобил' in p or 'личн' in p else 'мобильный'
    if 'приём' in p or 'прием' in p:
        return 'приёмная'
    if 'добав' in p or 'доб.' in p:
        return 'добавочный'
    return 'номер предприятия'


OTCHESTVO = re.compile(r'.+(?:ович|евич|ьевич|овна|евна|ьевна|ична|инична)$', re.I)


def fio_ok(s):
    """Похоже ли на ФИО. Заслон против должностей и обрывков, попавших в поле имени."""
    s = (s or '').strip()
    if len(s) < 5 or len(s) > 60:
        return False
    if re.search(r'\d|@|ООО|ОАО|АО\b|предприят|отдел', s, re.I):
        return False
    return bool(re.match(r'^[А-ЯЁ][а-яё\-]+\s+[А-ЯЁ]', s))


def klyuch_imeni(imya):
    """Ключ человека, переживающий разное написание одного и того же имени.

    Разбор 25 «спорных» личных мобильных показал, что спор чаще всего мой собственный:
      «Татаринов Дмитрий ЕвгениЕвич» и «Татаринов Дмитрий ЕвгенЬЕвич» — один человек;
      «ГоловачЁв Алексей» и «Головачев Алексей» — один;
      «Грачев Дмитрий Анатольевич» и «Дмитрий Анатольевич» — один, у второго срезана фамилия.
    Пока они считались разными, номер выглядел привязанным к двоим (ложная тревога), а
    источники по одному человеку не накапливались — то есть терялось главное правило.

    Поэтому: ё сводится к е, отчество приводится к общей форме (-иевич/-ьевич -> -евич),
    имя без фамилии не считается отдельным человеком, а по ключу «имя+отчество» сходится
    с полной записью. Настоящие расхождения — разные фамилии, разные отчества — остаются
    разными, и это правильно: «Чурсина Екатерина Юрьевна» и «Белова Екатерина Юрьевна»
    решать должен человек, а не шаблон.
    """
    t = re.sub(r'\s+', ' ', (imya or '').replace('ё', 'е').replace('Ё', 'Е')).strip().lower()
    ch = t.split()
    ch = [re.sub(r'(и|ь)евич$', 'евич', c) for c in ch]
    ch = [re.sub(r'(и|ь)евна$', 'евна', c) for c in ch]
    return ' '.join(ch)


def dobavit(baza, inn, imya, dolzh, kontakt, tip, vid, istochnik, ssylka=''):
    """Ключ — предприятие + человек + контакт. Источники НАКАПЛИВАЮТСЯ."""
    inn = re.sub(r'\D', '', str(inn or ''))
    if not (kontakt or imya):
        return
    k = (inn, klyuch_imeni(imya), kontakt)
    z = baza.get(k)
    if z is None:
        ves, rol = rol_ves(dolzh)
        baza[k] = {'inn': inn, 'fio': imya or '', 'dolzhnost': dolzh or '', 'rol': rol,
                   'ves_roli': ves, 'kontakt': kontakt, 'tip_kontakta': tip, 'vid': vid,
                   'istochniki': [istochnik], 'ssylki': [ssylka] if ssylka else []}
    else:
        if istochnik not in z['istochniki']:
            z['istochniki'].append(istochnik)
        if ssylka and ssylka not in z['ssylki']:
            z['ssylki'].append(ssylka)
        # Держим САМОЕ ПОЛНОЕ написание: «Грачев Дмитрий Анатольевич» полезнее, чем
        # «Дмитрий Анатольевич», а ключ у них теперь общий.
        if imya and len(imya.split()) > len((z['fio'] or '').split()):
            z['fio'] = imya
        if not z['dolzhnost'] and dolzh:
            z['dolzhnost'] = dolzh
            z['ves_roli'], z['rol'] = rol_ves(dolzh)


def chitat(put, sep=';'):
    if not os.path.exists(put):
        print(f'  НЕТ ФАЙЛА: {put}', file=sys.stderr)
        return []
    raw = open(put, encoding='utf-8-sig', errors='replace').read(2000)
    s = ';' if raw.count(';') > raw.count(',') else ','
    return list(csv.DictReader(open(put, encoding='utf-8-sig', errors='replace'), delimiter=s))


# РЕЕСТР ВХОДОВ. Список источников был зашит внутрь `main()`, и ровно из-за этого прошлый
# свод читал ПЯТЬ файлов из десяти: личные номера третьей сессии, люди Тендер.Про, роли,
# вложения ЕИС и весь обход сайтов в него не попадали, и никто этого не видел — отсутствующий
# вход просто ничего не добавлял. Здесь входы объявлены, и при запуске по КАЖДОМУ печатается
# строка: прочитано N либо НЕТ ФАЙЛА. Молчащий источник теперь виден в отчёте.
VHODY = [
    ('LICHNYE-NOMERA-3-SESSIYA', os.path.join(LENS, 'centro', 'LICHNYE-NOMERA-3-SESSIYA.csv'),
     'личные номера третьей сессии'),
    ('tp-lyudi-dlya-obzvona', os.path.join(LENS, 'centro', 'tenderpro',
                                           'tp-lyudi-dlya-obzvona.csv'),
     'Тендер.Про, люди с телефонами'),
    ('roli-ot-3-sessii', os.path.join(LENS, 'centro', 'roli-ot-3-sessii.csv'),
     'роли, разбор Тендер.Про'),
    ('OBHOD-kontakty-3s', '/home/user/work/OBHOD-kontakty-3s.csv',
     'обход сайтов предприятий'),
    ('contacts-accumulator', os.path.join(LENS, 'contacts-accumulator.csv'),
     'накопитель прошлой сессии'),
    ('eis-zakupka-inn-karta', os.path.join(LENS, 'centro', 'eis-zakupka-inn-karta.csv'),
     'карта закупка -> ИНН (справочник, людей не даёт)'),
    ('vlozheniya-lica.csv', os.path.join(LENS, 'centro', 'eis', 'vlozheniya-lica.csv'),
     'вложения ЕИС'),
    ('vlozheniya-lica-hvosty.csv', os.path.join(LENS, 'centro', 'eis',
                                                'vlozheniya-lica-hvosty.csv'),
     'вложения ЕИС, хвост сверх предела окон'),
    ('tp-inn', os.path.join(LENS, 'centro', 'tenderpro', 'tp-inn.csv'),
     'карта company_id -> ИНН (справочник, людей не даёт)'),
    ('tp-lica-polnye', os.path.join(LENS, 'centro', 'tenderpro', 'tp-lica-polnye.csv'),
     'Тендер.Про по полным комментариям'),
    ('lica-s-sajtov', '/home/user/work/lica-s-sajtov.csv', 'лица со страниц сайтов'),
    ('PATENTY-patenton', '/home/user/work/PATENTY-patenton-3s.csv',
     'изобретатели из патентов'),
    ('lpr-pesochnica', '/home/user/work/lpr-pesochnica.jsonl',
     'поиск человека по должности в выдаче'),
    ('lpr-obratnyy', '/home/user/work/lpr-obratnyy.jsonl',
     'обратный ход: контакт по имени человека'),
]


def proverit_vhody():
    """Печатает состояние КАЖДОГО входа до сбора. Нет файла — сказано вслух."""
    net = 0
    for imya, put, zachem in VHODY:
        if os.path.exists(put):
            n = sum(1 for _ in open(put, encoding='utf-8-sig', errors='replace')) - 1
            print(f'  есть   {imya:<28} {n:>7} строк  — {zachem}', file=sys.stderr)
        else:
            net += 1
            print(f'  НЕТ    {imya:<28} {"":>7}         — {zachem}  [{put}]',
                  file=sys.stderr)
    if net:
        print(f'  ВНИМАНИЕ: входов не найдено {net} — их данные в свод НЕ попадут',
              file=sys.stderr)
    return net


def main():
    baza = {}
    ist = {}
    print('входы свода:', file=sys.stderr)
    proverit_vhody()
    print('', file=sys.stderr)

    def uchest(imya, n):
        ist[imya] = n

    # 1. Личные номера третьей сессии — у них уже есть накопленный провенанс
    r = chitat(os.path.join(LENS, 'centro', 'LICHNYE-NOMERA-3-SESSIYA.csv'))
    for x in r:
        n = nomer(x.get('nomer_10cifr'))
        if n:
            dobavit(baza, x.get('inn'), x.get('fio'), x.get('dolzhnost'), n, 'телефон',
                    vid_nomera(n, 'личный'), x.get('istochniki') or 'свод личных номеров')
    uchest('LICHNYE-NOMERA-3-SESSIYA', len(r))

    # 2. Тендер.Про — люди с телефонами
    r = chitat(os.path.join(LENS, 'centro', 'tenderpro', 'tp-lyudi-dlya-obzvona.csv'))
    for x in r:
        for pole, tip in (('mobilnyy', 'телефон'), ('telefony', 'телефон'), ('pochty', 'почта')):
            for v in re.split(r'[|,;]+', str(x.get(pole) or '')):
                v = v.strip()
                if not v:
                    continue
                if tip == 'телефон':
                    n = nomer(v)
                    if n:
                        dobavit(baza, x.get('inn'), x.get('imya'), x.get('dolzhnost'), n,
                                tip, vid_nomera(n, pole), 'Тендер.Про')
                elif '@' in v:
                    dobavit(baza, x.get('inn'), x.get('imya'), x.get('dolzhnost'), v.lower(),
                            'почта', 'именная почта', 'Тендер.Про')
    uchest('tp-lyudi-dlya-obzvona', len(r))

    # 3. Роли третьей сессии
    r = chitat(os.path.join(LENS, 'centro', 'roli-ot-3-sessii.csv'))
    for x in r:
        n = nomer(x.get('telefon'))
        if n:
            dobavit(baza, x.get('inn'), x.get('imya'), x.get('dolzhnost'), n, 'телефон',
                    vid_nomera(n), 'роли, Тендер.Про')
        p = (x.get('pochta') or '').strip().lower()
        if '@' in p:
            dobavit(baza, x.get('inn'), x.get('imya'), x.get('dolzhnost'), p, 'почта',
                    'именная почта', 'роли, Тендер.Про')
    uchest('roli-ot-3-sessii', len(r))

    # 4. Обход сайтов третьей сессии
    r = chitat('/home/user/work/OBHOD-kontakty-3s.csv')
    for x in r:
        k = (x.get('kontakt') or '').strip()
        if not k:
            continue
        if x.get('tip') == 'телефон':
            n = nomer(k)
            if n:
                dobavit(baza, x.get('inn'), x.get('chelovek'), x.get('dolzhnost'), n, 'телефон',
                        x.get('vid') or vid_nomera(n), 'обход сайта', x.get('ssylka', ''))
        else:
            dobavit(baza, x.get('inn'), x.get('chelovek'), x.get('dolzhnost'), k.lower(), 'почта',
                    x.get('vid') or 'общая почта', 'обход сайта', x.get('ssylka', ''))
    uchest('OBHOD-kontakty-3s', len(r))

    # 5. Накопитель прошлой сессии
    r = chitat(os.path.join(LENS, 'contacts-accumulator.csv'))
    for x in r:
        n = nomer(x.get('phone'))
        if n:
            dobavit(baza, x.get('inn'), x.get('person'), x.get('role'), n, 'телефон',
                    x.get('phone_type') or vid_nomera(n), 'накопитель 29.07')
        p = (x.get('email') or '').strip().lower()
        if '@' in p:
            dobavit(baza, x.get('inn'), x.get('person'), x.get('role'), p, 'почта',
                    x.get('email_type') or 'почта', 'накопитель 29.07')
    uchest('contacts-accumulator', len(r))

    # 6. Вложения ЕИС: техзадания, протоколы, листы согласования. Людей там называют по
    # должности, и это ровно наша роль. ИНН в файле разбора нет — есть номер закупки,
    # поэтому подставляется по карте `eis-zakupka-inn-karta.csv`. Строки без карты НЕ
    # выбрасываются: пишутся с пустым ИНН и остаются видимыми как «предприятие не привязано».
    karta = {}
    for x in chitat(os.path.join(LENS, 'centro', 'eis-zakupka-inn-karta.csv')):
        if x.get('zakupka'):
            karta[str(x['zakupka']).strip()] = (x.get('inn') or '').strip()
    for fajl, podpis in (('vlozheniya-lica.csv', 'вложения ЕИС'),
                         ('vlozheniya-lica-hvosty.csv', 'вложения ЕИС, хвост сверх предела')):
        r = chitat(os.path.join(LENS, 'centro', 'eis', fajl))
        for x in r:
            inn = karta.get(str(x.get('zakupka') or '').strip(), '')
            ssyl = f"https://zakupki.gov.ru/223/purchase/public/purchase/info/common-info.html?regNumber={x.get('zakupka')}"
            n = nomer(x.get('telefon'))
            # Номер, которого нет во входном тексте, модель могла придумать — такой не берём
            # как телефон, но САМОГО ЧЕЛОВЕКА сохраняем: ФИО с должностью это цель поиска.
            if n and (x.get('telefon_est_v_tekste') or '') == '1':
                dobavit(baza, inn, x.get('imya'), x.get('dolzhnost'), n, 'телефон',
                        vid_nomera(n), podpis, ssyl)
            p = (x.get('pochta') or '').strip().lower()
            if '@' in p:
                dobavit(baza, inn, x.get('imya'), x.get('dolzhnost'), p, 'почта',
                        'именная почта', podpis, ssyl)
            if not n and '@' not in p and fio_ok(x.get('imya')):
                dobavit(baza, inn, x.get('imya'), x.get('dolzhnost'), '', 'без контакта',
                        'ФИО и должность без номера', podpis, ssyl)
        uchest(fajl, len(r))

    # Карта company_id -> ИНН для Тендер.Про. В самом разборе колонка `inn` пуста у ВСЕХ
    # 1 435 строк — площадка её в карточке тендера не показывает, ИНН добывается отдельным
    # проходом по страницам компаний (`tp-inn.csv`, 347 из 384 company_id с ИНН). Без этой
    # карты 641 человек ложился в свод без предприятия: имя и номер есть, звонить некому.
    tp_inn = {}
    for x in chitat(os.path.join(LENS, 'centro', 'tenderpro', 'tp-inn.csv')):
        if x.get('company_id') and (x.get('inn') or '').strip():
            tp_inn[str(x['company_id']).strip()] = x['inn'].strip()

    # 7. Тендер.Про, разбор ПОЛНЫХ комментариев. Отдельно от `tp-lyudi-dlya-obzvona`:
    # тот файл собран по обрезанному на 1 500 знаках тексту, этот — по целому, и в нём
    # есть люди, которых в первом нет вовсе.
    r = chitat(os.path.join(LENS, 'centro', 'tenderpro', 'tp-lica-polnye.csv'))
    bez_inn = 0
    for x in r:
        if not (x.get('inn') or '').strip():
            x['inn'] = tp_inn.get(str(x.get('company_id') or '').strip(), '')
            if not x['inn']:
                bez_inn += 1
        ssyl = f"https://www.tender.pro/tender/{x.get('tender_id')}" if x.get('tender_id') else ''
        n = nomer(x.get('telefon'))
        # Заслон читался наоборот. Колонка принимает '1' («номер есть во входном тексте»)
        # и пустоту («модель его выдумала»), а проверка стояла «не равно '0'» — то есть
        # пустота проходила. Замер 03.08: 11 таких номеров ехало в список обзвона, среди
        # них добавочный, приписанный чужому человеку. Выдуманный контакт хуже пропуска —
        # по нему звонят не туда. Сам ЧЕЛОВЕК при этом сохраняется строкой ниже, без номера:
        # имя и должность добыты честно, теряться они не должны.
        if n and (x.get('telefon_est_v_tekste') or '') == '1':
            dobavit(baza, x.get('inn'), x.get('imya'), x.get('dolzhnost'), n, 'телефон',
                    vid_nomera(n), 'Тендер.Про, полный комментарий', ssyl)
        p = (x.get('pochta') or '').strip().lower()
        if '@' in p:
            dobavit(baza, x.get('inn'), x.get('imya'), x.get('dolzhnost'), p, 'почта',
                    'именная почта', 'Тендер.Про, полный комментарий', ssyl)
        vydumka = bool(n) and (x.get('telefon_est_v_tekste') or '') != '1'
        if (not n or vydumka) and '@' not in p and fio_ok(x.get('imya')):
            dobavit(baza, x.get('inn'), x.get('imya'), x.get('dolzhnost'), '', 'без контакта',
                    'ФИО и должность без номера'
                    + (', номер модели отброшен как отсутствующий в тексте' if vydumka else ''),
                    'Тендер.Про, полный комментарий', ssyl)
    uchest('tp-lica-polnye', len(r))
    if bez_inn:
        print(f'  Тендер.Про: {bez_inn} строк остались без ИНН — company_id нет в tp-inn.csv',
              file=sys.stderr)

    # 8. Лица со страниц сайтов предприятий
    r = chitat('/home/user/work/lica-s-sajtov.csv')
    for x in r:
        ssyl = x.get('sajt') or ''
        n = nomer(x.get('telefon'))
        dob = (x.get('dobavochnyy') or '').strip()
        if n:
            dobavit(baza, x.get('inn'), x.get('imya'), x.get('dolzhnost'), n, 'телефон',
                    vid_nomera(n) + (f', добавочный {dob}' if dob else ''),
                    'страница сайта предприятия', ssyl)
        p = (x.get('pochta') or '').strip().lower()
        if '@' in p:
            dobavit(baza, x.get('inn'), x.get('imya'), x.get('dolzhnost'), p, 'почта',
                    'именная почта', 'страница сайта предприятия', ssyl)
        if not n and '@' not in p and fio_ok(x.get('imya')):
            dobavit(baza, x.get('inn'), x.get('imya'), x.get('dolzhnost'), '', 'без контакта',
                    'ФИО и должность без номера', 'страница сайта предприятия', ssyl)
    uchest('lica-s-sajtov', len(r))

    # 9. Изобретатели из патентов. Три оговорки, и все три в самой записи, а не в памяти:
    #   * патентообладателя выдача не показывает, доказано лишь УПОМИНАНИЕ имени предприятия
    #     в тексте патента — беру только строки, где имя реально попало в отрывок;
    #   * советские патенты (SU, 3 415 строк из 9 935) отброшены: инженер оттуда как минимум
    #     тридцать пять лет в профессии, звонить по нему некому;
    #   * контакта нет вовсе. Это не контакт, это ИМЯ ДЛЯ ПОИСКА номера, и вид записи так и
    #     назван. Выбрасывать нельзя — 3 916 пар «предприятие + инженер» по 212 предприятиям
    #     это готовый вход для поиска по должности.
    r = chitat('/home/user/work/PATENTY-patenton-3s.csv')
    FIO_PAT = re.compile(r'[А-ЯЁ][а-яё\-]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?')
    npat = 0
    for x in r:
        if x.get('imya_v_citate') != '1' or not (x.get('nomer') or '').startswith('RU'):
            continue
        for chast in re.split(r'\s*,\s*', x.get('izobretateli') or ''):
            fio = re.sub(r'\s*\([A-Z]{2}\)', '', chast).strip()
            if not FIO_PAT.fullmatch(fio):
                continue
            # ПОРЯДОК ИМЕНИ ОПРЕДЕЛЯЕТСЯ, А НЕ ПРЕДПОЛАГАЕТСЯ. Я сначала записала, что
            # в патенте имя идёт «Имя Отчество Фамилия», и переставила все — вышло
            # «Шамилевич Валиев Рафаил». Порядок оказался разный у разных входов: Google
            # Patents отдаёт «Рафаил Шамилевич Валиев», patenton.ru — «Валиев Рафаил
            # Шамилевич». Различаю по отчеству: где стоит слово на -ович/-евич/-овна/-ична,
            # там и третья позиция.
            ch = fio.split()
            if len(ch) == 3 and OTCHESTVO.match(ch[1]) and not OTCHESTVO.match(ch[2]):
                fio = f'{ch[2]} {ch[0]} {ch[1]}'
            dobavit(baza, x.get('inn'), fio, '', '', 'без контакта',
                    'ФИО из патента, контакта нет — имя для поиска номера',
                    'патент (упоминание предприятия в тексте, патентообладатель не проверен)',
                    x.get('ssylka', ''))
            npat += 1
    uchest('PATENTY-patenton (RU, имя в отрывке)', npat)

    # 10. Поиск человека ПО ДОЛЖНОСТИ в выдаче (`lpr_pesochnica.py`). Единственный
    # источник, который ищет не предприятие и не событие, а самого технического
    # руководителя: «"<компания>" ("главный инженер" OR ...)». Контакта тут нет — есть имя
    # и должность, и по ним потом идёт обратный ход, добирающий телефон.
    # Строка «фамилия с инициалами» сохраняется наравне с полным ФИО: у обратного хода
    # запрос всё равно строится по имени плюс компании, а «Иванов И.И.» это уже адрес.
    import json as _json
    put = '/home/user/work/lpr-pesochnica.jsonl'
    nlpr = 0
    if os.path.exists(put):
        for ln in open(put, encoding='utf-8'):
            if not ln.strip():
                continue
            try:
                z = _json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            for ch in z.get('lyudi') or []:
                dobavit(baza, z.get('inn'), ch.get('fio'), ch.get('dolzhnost'), '',
                        'без контакта',
                        'ФИО и должность из выдачи, контакта нет — цель обратного хода',
                        'поиск по должности в выдаче (xmlriver)', ch.get('ssylka', ''))
                nlpr += 1
    uchest('lpr-pesochnica (поиск по должности)', nlpr)

    # 11. Обратный ход: контакт, найденный по ИМЕНИ человека. Это уже не имя, а контакт,
    # и ценность его выше всех «без контакта» — искали конкретного человека и нашли его
    # страницу. Расстояние до фамилии несём в вид записи: контакт в двадцати знаках от
    # фамилии и контакт в трёхстах — разной надёжности, и решать должен человек.
    put_o = '/home/user/work/lpr-obratnyy.jsonl'
    nobr = 0
    if os.path.exists(put_o):
        for ln in open(put_o, encoding='utf-8'):
            if not ln.strip():
                continue
            try:
                z = _json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            for k in z.get('kontakty') or []:
                zn = (k.get('znachenie') or '').strip()
                d = k.get('znakov_do_familii')
                if k.get('tip') == 'телефон':
                    n = nomer(zn)
                    if not n:
                        continue
                    dobavit(baza, z.get('inn'), z.get('fio'), z.get('dolzhnost'), n,
                            'телефон', f'{vid_nomera(n)}, найден по имени человека '
                                       f'({d} знаков до фамилии)',
                            'обратный ход по имени (xmlriver)', k.get('ssylka', ''))
                else:
                    dobavit(baza, z.get('inn'), z.get('fio'), z.get('dolzhnost'),
                            zn.lower(), 'почта',
                            f'именная почта, найдена по имени человека '
                            f'({d} знаков до фамилии)',
                            'обратный ход по имени (xmlriver)', k.get('ssylka', ''))
                nobr += 1
    uchest('lpr-obratnyy (контакт по имени)', nobr)

    zapisi = list(baza.values())

    # СЛИЯНИЕ СОВМЕСТИМЫХ ЗАПИСЕЙ ОДНОГО ЧЕЛОВЕКА. Ключ вставки не может знать, что
    # «Чикуров В.В.» и «Чикуров Владимир Васильевич» — один человек: имена приходят из
    # разных источников в разное время. Поэтому сливаем ПОСЛЕ сбора, внутри одной пары
    # предприятие+контакт, где спорить может только написание.
    #
    # Разбор 23 «спорных» личных мобильных: одно и то же имя пришло как «Рябышев Е.»,
    # «Рябышев Евгений» и «Рябышев Евгений Иванович»; как «Ботвинко Надежда» и «Надежда
    # Ботвинко» (порядок слов); как «Галкова Наталия» и «Галкова Наталья»; как «Шаповалова
    # Елена Александрова» и «...Александровна» (опечатка в отчестве). Настоящих расхождений
    # среди 23 всего четыре — «Белова Екатерина Юрьевна» против «Чурсина Екатерина Юрьевна»
    # и подобные. Пока разные написания считались разными людьми, номер выглядел
    # привязанным к нескольким (ложная тревога), а источники по человеку НЕ накапливались —
    # то есть нарушалось главное правило владельца.
    def _tokeny(imya):
        t = re.sub(r'\s+', ' ', (imya or '').replace('ё', 'е').replace('Ё', 'Е')).strip().lower()
        return [x for x in re.split(r'[\s.]+', t) if x]

    def _sovmestimy(a, b):
        """Одно ли это имя. Инициал совпадает с полным словом по первой букве."""
        ta, tb = _tokeny(a), _tokeny(b)
        if not ta or not tb:
            return False
        # порядок слов бывает обратный: «Ботвинко Надежда» и «Надежда Ботвинко»
        for tb2 in (tb, tb[::-1]):
            dlin = min(len(ta), len(tb2))
            if all(x[0] == y[0] and (len(x) < 3 or len(y) < 3 or x[:3] == y[:3])
                   for x, y in zip(ta[:dlin], tb2[:dlin])):
                return True
        # фамилия совпала целиком, остальное — инициалы: «Чикуров В.В.» и «Чикуров Владимир
        # Васильевич». Совпадение по одной фамилии без инициалов НЕ считаем: однофамильцы.
        if ta[0] == tb[0] and len(ta) > 1 and len(tb) > 1 and ta[1][0] == tb[1][0]:
            return True
        # У одной записи срезана фамилия: «Дмитрий Анатольевич» и «Грачев Дмитрий
        # Анатольевич». Короткое имя должно идти ПОДРЯД внутри длинного и быть не короче
        # двух слов — «Дмитрий» в одиночку сходился бы с любым Дмитрием предприятия.
        korot, dlin = (ta, tb) if len(ta) < len(tb) else (tb, ta)
        if len(korot) >= 2:
            for i in range(len(dlin) - len(korot) + 1):
                if dlin[i:i + len(korot)] == korot:
                    return True
        return False

    po_pare = {}
    for z in zapisi:
        po_pare.setdefault((z['inn'], z['kontakt']), []).append(z)
    slito = 0
    for (_inn, kont), gr in po_pare.items():
        if not kont or len(gr) < 2:
            continue
        gr.sort(key=lambda z: -len((z['fio'] or '').split()))   # полное имя ведущее
        ubrat = set()
        for i, glavnyy in enumerate(gr):
            if id(glavnyy) in ubrat or not glavnyy['fio']:
                continue
            for drugoy in gr[i + 1:]:
                if id(drugoy) in ubrat or not drugoy['fio']:
                    continue
                if _sovmestimy(glavnyy['fio'], drugoy['fio']):
                    for ist in drugoy['istochniki']:
                        if ist not in glavnyy['istochniki']:
                            glavnyy['istochniki'].append(ist)
                    for ss in drugoy.get('ssylki') or []:
                        if ss not in glavnyy['ssylki']:
                            glavnyy['ssylki'].append(ss)
                    if not glavnyy['dolzhnost'] and drugoy['dolzhnost']:
                        glavnyy['dolzhnost'] = drugoy['dolzhnost']
                        glavnyy['ves_roli'], glavnyy['rol'] = rol_ves(drugoy['dolzhnost'])
                    ubrat.add(id(drugoy))
                    slito += 1
        if ubrat:
            for z in gr:
                if id(z) in ubrat:
                    z['__ubrat'] = True
    zapisi = [z for z in zapisi if not z.get('__ubrat')]
    print(f'  слито записей одного человека, различавшихся написанием: {slito}',
          file=sys.stderr)

    # СКОЛЬКО ЛЮДЕЙ ЧИСЛИТСЯ ЗА ОДНИМ НОМЕРОМ. Замер 03.08: из 1 002 телефонов с именем
    # 132 привязаны больше чем к одному человеку, и 35 из них — ЛИЧНЫЕ МОБИЛЬНЫЕ. Для
    # приёмной или общего номера отдела это нормально (8352735555 — пять человек, это
    # коммутатор). Для личного мобильного — нет: он принадлежит одному, значит на части
    # строк имя приписано чужому номеру, и звонок пойдёт не тому.
    # Отсеивать нельзя (какая из строк верна — решать по источникам), поэтому считаю и
    # называю: `lyudey_na_nomere`, а у личного мобильного с двумя и более именами вид
    # прямо говорит, что привязка спорная.
    #
    # Перед подсчётом схлопываю короткую запись имени в полную: «Резник Алексей» и
    # «Резник Алексей Александрович» это один человек, а не двое, и считать их спором
    # значит поднять ложную тревогу.
    po_nomeru = {}
    for z in zapisi:
        if z['tip_kontakta'] == 'телефон' and z['fio']:
            po_nomeru.setdefault(z['kontakt'], set()).add(klyuch_imeni(z['fio']))

    def _szhat(imena):
        polnye = [i for i in imena if len(i.split()) >= 3]
        out = set()
        for i in imena:
            ch = i.split()
            if len(ch) < 3:
                nashli = [p for p in polnye if p.startswith(' '.join(ch[:2]))]
                if len(nashli) == 1:
                    out.add(nashli[0])
                    continue
            out.add(i)
        return out

    # ОДИН НОМЕР У НЕСКОЛЬКИХ ПРЕДПРИЯТИЙ — это не спор имён, а другой сорт находки.
    # Разбор: номер 9609184197 (Грачев Дмитрий Анатольевич, коммерческий директор) стоит
    # у СЕМИ разных ИНН. Человек не работает на семи заводах — он посредник, дилер или
    # представитель поставщика, публикующий закупки за других. Владелец продаёт заводам,
    # значит такой контакт не цель, а шум, и попасть в верх обзвона он не должен.
    # Не выбрасываю (правило «разделять, а не отсеивать»): 11 номеров, 42 строки, из них
    # 2 личных мобильных — называю прямо и опускаю в приоритете.
    predpr_na_nomere = {}
    for z in zapisi:
        if z['tip_kontakta'] == 'телефон' and z['inn'] and z['kontakt']:
            predpr_na_nomere.setdefault(z['kontakt'], set()).add(z['inn'])

    for z in zapisi:
        n = len(_szhat(po_nomeru.get(z['kontakt'], set()))) if z['kontakt'] else 0
        z['lyudey_na_nomere'] = n if n > 1 else ''
        p = len(predpr_na_nomere.get(z['kontakt'], ()))
        z['predpriyatiy_na_nomere'] = p if p > 2 else ''
        if p > 2:
            z['vid'] = (f'{z["vid"]}, НЕ ЗАВОДСКОЙ: номер стоит у {p} разных предприятий, '
                        f'похоже на посредника')
        elif n > 1 and z['vid'] in ('личный мобильный', 'мобильный'):
            z['vid'] = f'{z["vid"]}, СПОРНО: за номером {n} разных человека'

    # ПЕРЕКРЁСТНАЯ ОТМЕТКА. Ключ склейки — предприятие + человек + КОНТАКТ, поэтому запись без
    # контакта (имя из патента) никогда не сольётся с записью, где номер есть, и провенанс по
    # ним не накопится сам. А совпадение важно: человек, известный по закупке И названный
    # изобретателем на том же предприятии, почти наверняка настоящий технический сотрудник,
    # а не однофамилец. Поэтому не ломаю ключ, а ставлю отдельную отметку.
    v_patente = {(z['inn'], klyuch_imeni(z['fio']))
                 for z in zapisi if 'патент' in ' '.join(z['istochniki'])}
    for z in zapisi:
        z['takzhe_v_patente'] = (
            'да' if (z['kontakt'] and z['fio']
                     and (z['inn'], klyuch_imeni(z['fio'])) in v_patente) else '')
    for z in zapisi:
        z['istochnikov'] = len(z['istochniki'])
        z['istochniki'] = ' | '.join(z['istochniki'])[:300]
        z['ssylka'] = (z['ssylki'] or [''])[0]
        z['imya_est'] = 'да' if fio_ok(z['fio']) else 'нет'
        # Приоритет: роль важнее, личный номер важнее, подтверждение несколькими источниками важнее
        z['prioritet'] = round(z['ves_roli'] * 10
                               + (8 if z['vid'] in ('личный мобильный', 'мобильный') else 0)
                               - (10 if 'СПОРНО' in z['vid'] else 0)
                               - (20 if 'НЕ ЗАВОДСКОЙ' in z['vid'] else 0)
                               + (5 if z['imya_est'] == 'да' else 0)
                               + min(z['istochnikov'], 3) * 3
                               + (6 if z.get('takzhe_v_patente') else 0), 1)
        z.pop('ssylki', None)
    zapisi.sort(key=lambda z: -z['prioritet'])
    kol = ['inn', 'fio', 'imya_est', 'dolzhnost', 'rol', 'kontakt', 'tip_kontakta', 'vid',
           'prioritet', 'lyudey_na_nomere', 'predpriyatiy_na_nomere', 'takzhe_v_patente',
           'istochniki', 'istochnikov', 'ssylka']
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(LENS, 'SPISOK-OBZVONA-POLNYY.csv')
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=kol, delimiter=';', extrasaction='ignore')
        w.writeheader()
        w.writerows(zapisi)
    import collections
    print('прочитано из источников:', ist)
    print(f'\nВСЕГО строк в своде: {len(zapisi)}')
    print(f'предприятий: {len(set(z["inn"] for z in zapisi if z["inn"]))}')
    print(f'строк с ФИО: {sum(1 for z in zapisi if z["imya_est"] == "да")}')
    print(f'подтверждено 2+ источниками: {sum(1 for z in zapisi if z["istochnikov"] > 1)}')
    print('по видам контакта:', dict(collections.Counter(z['vid'] for z in zapisi).most_common(8)))
    print('по ролям:', dict(collections.Counter(z['rol'] for z in zapisi).most_common(6)))
    print('→', out)


if __name__ == '__main__':
    main()

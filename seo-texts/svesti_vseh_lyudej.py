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


def dobavit(baza, inn, imya, dolzh, kontakt, tip, vid, istochnik, ssylka=''):
    """Ключ — предприятие + человек + контакт. Источники НАКАПЛИВАЮТСЯ."""
    inn = re.sub(r'\D', '', str(inn or ''))
    if not (kontakt or imya):
        return
    k = (inn, (imya or '').strip().lower(), kontakt)
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
        if not z['fio'] and imya:
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


def main():
    baza = {}
    ist = {}

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

    zapisi = list(baza.values())
    # ПЕРЕКРЁСТНАЯ ОТМЕТКА. Ключ склейки — предприятие + человек + КОНТАКТ, поэтому запись без
    # контакта (имя из патента) никогда не сольётся с записью, где номер есть, и провенанс по
    # ним не накопится сам. А совпадение важно: человек, известный по закупке И названный
    # изобретателем на том же предприятии, почти наверняка настоящий технический сотрудник,
    # а не однофамилец. Поэтому не ломаю ключ, а ставлю отдельную отметку.
    v_patente = {(z['inn'], (z['fio'] or '').strip().lower())
                 for z in zapisi if 'патент' in ' '.join(z['istochniki'])}
    for z in zapisi:
        z['takzhe_v_patente'] = (
            'да' if (z['kontakt'] and z['fio']
                     and (z['inn'], z['fio'].strip().lower()) in v_patente) else '')
    for z in zapisi:
        z['istochnikov'] = len(z['istochniki'])
        z['istochniki'] = ' | '.join(z['istochniki'])[:300]
        z['ssylka'] = (z['ssylki'] or [''])[0]
        z['imya_est'] = 'да' if fio_ok(z['fio']) else 'нет'
        # Приоритет: роль важнее, личный номер важнее, подтверждение несколькими источниками важнее
        z['prioritet'] = round(z['ves_roli'] * 10
                               + (8 if z['vid'] in ('личный мобильный', 'мобильный') else 0)
                               + (5 if z['imya_est'] == 'да' else 0)
                               + min(z['istochnikov'], 3) * 3
                               + (6 if z.get('takzhe_v_patente') else 0), 1)
        z.pop('ssylki', None)
    zapisi.sort(key=lambda z: -z['prioritet'])
    kol = ['inn', 'fio', 'imya_est', 'dolzhnost', 'rol', 'kontakt', 'tip_kontakta', 'vid',
           'prioritet', 'takzhe_v_patente', 'istochniki', 'istochnikov', 'ssylka']
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

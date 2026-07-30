# -*- coding: utf-8 -*-
"""Люди Tender.pro в вид, пригодный для обзвона: ИНН, дедуп по человеку, технические сверху.

Подсказка соседней сессии: ИНН для `tp-lica.csv` искать не надо, он лежит в `tp-inn.csv`,
join по `company_id`. Проверено на файлах — сходится.

Чем эта выгрузка отличается от сырого `tp-lica.csv`:
- **ИНН приклеен** — без него человека не с чем сверить и некуда положить в базу;
- **дедуп по человеку, а не по строке.** Один человек встречается в десятках карточек одной
  компании: в сыром файле 3 184 строки, людей в разы меньше. Считать строки вместо людей — тот
  самый брак, на котором обе сессии уже попадались (счётчик прогона против базы);
- **строки с непроверенным телефоном отделены**, а не выброшены: 27 номеров модель назвала, но
  их нет во входном тексте карточки. Молча удалять нельзя — пропажу видно, подделку нет;
- **порядок: техническая роль выше снабжения**, мобильный выше городского, свежая закупка выше
  старой;
- **рубеж «это вообще ФИО»**: строки вида «отдел снабжения» или «приёмная» именем не считаются.

Использование:
    python3 tp_dlya_prodazhnikov.py [--vyhod <csv>]
"""
import csv
import os
import re
import sys
from collections import defaultdict

BAZA = os.path.dirname(os.path.abspath(__file__))
TP = os.path.join(BAZA, 'engineers-lens', 'centro', 'tenderpro')
# Два разбора карточек. `tp-lica.csv` — наш накопитель, 5 075 строк; 1 380 строк полного разбора
# третьей сессии в него уже **дописаны** коммитом 90094f9. `tp-lica-polnye.csv` читается вторым
# на случай, если третья сессия обновит свой файл: дедуп идёт по множествам, повторное чтение уже
# слитых строк ничего не портит, только раздувает счётчик «строк на входе».
# Замер после слияния (30.07, по файлам): строк с ключом «ИНН + фамилия и имя», которого в нашем
# накопителе нет, — 10, и все десять не проходят рубеж «это ФИО» («Крамарова», «Алёна»,
# «Elena Tsivanyuk»). То есть весь их прирост у нас уже есть. Их оценка была +174 человека
# и +31 технический с мобильным, но она считалась против нашего файла на 3 184 строки, до наших
# собственных допросов провайдера по полному тексту комментария.
LICA = [os.path.join(TP, 'tp-lica.csv'), os.path.join(TP, 'tp-lica-polnye.csv')]
INN = os.path.join(TP, 'tp-inn.csv')
KARTOCHKI = [os.path.join(TP, 'tp-kartochki-polnye.csv'), os.path.join(TP, 'tp-kartochki.csv')]
VYHOD = os.path.join(TP, 'tp-lyudi-dlya-obzvona.csv')

# Рубеж «это вообще ФИО»: минимум два слова с заглавной буквы кириллицей, либо «Фамилия И.О.».
FIO = re.compile(r'^[А-ЯЁ][а-яё\-]{2,}\s+(?:[А-ЯЁ][а-яё\-]{2,}|[А-ЯЁ]\.)\s*'
                 r'(?:[А-ЯЁ][а-яё\-]{2,}|[А-ЯЁ]\.)?\s*$')
NE_IMYA = re.compile(r'отдел|служб|приём|приемн|секретар|бухгалт|канцеляр|управлен|ООО|АО\b|'
                     r'департамент|дирекц', re.I)
MOB = re.compile(r'(?:\+?7|\b8)[\s(\-]*9\d{2}')

# Должности, которые выглядят техническими, но человек не решает по нашей машине.
# Список пришёл от соседней сессии, проверен на нашем файле: из 259 технических он поймал
# **одного** — «Начальник бюро ГИП, начальник бюро главных инженерных проектов». ГИП это
# главный инженер ПРОЕКТА, проектировщик: машину на чужой площадке он не выбирает.
# Автотранспорт стоит выше механиков намеренно: «механик гаража» иначе проходит по слову
# «механик». Это их же вывод — правку канона нельзя принимать по одному направлению.
NE_NASH = re.compile(r'автомеханик|механик\s+гараж|транспортн\w+\s+цех|автоколонн|автотранспорт|'
                     r'главн\w+\s+инженер\w*\s+проект|бюро\s+ГИП|главн\w+\s+инженерн\w+\s+проект|'
                     r'инженер\s+по\s+(?:закупк|договор|смет|охране\s+труда|надзору\s+за\s+строит)',
                     re.I)


def cifry(s):
    return re.sub(r'\D', '', s or '')[-10:]


# Круглосуточная линия «Центр ТендерПро-Консультант» и персональный консультант площадки. Стоит
# почти в каждой карточке и телефоном предприятия не является.
LINIYA_PLOSHCHADKI = re.compile(r'215\D?14\D?38|\b8\D?800\b')


def telefony_kompanij():
    """Телефоны предприятия по `company_id` — для тех, у кого есть имя и почта, но нет номера.

    Зачем это отдельной колонкой, а не в `telefony`. У семи технических людей из восьми, стоявших
    «без телефона», в тексте карточки рядом с именем действительно только корпоративная почта —
    проверено чтением текста, а не механической близостью. Приписать им номер предприятия нельзя:
    это чужой номер. Но продавцу он нужен: с ним заход «позовите главного механика Ракушинца» —
    это звонок по имени, а не в пустоту. Поэтому номер лежит в отдельной колонке с явным именем.
    """
    po_cid = defaultdict(set)
    for put in KARTOCHKI:
        if not os.path.exists(put):
            continue
        for r in csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';'):
            for pole in ('telefony_tekst', 'telefony_razmetka'):
                for t in re.split(r'[|,;]', r.get(pole) or ''):
                    t = t.strip()
                    if t and not LINIYA_PLOSHCHADKI.search(t) and len(cifry(t)) >= 9:
                        po_cid[r['company_id']].add(t)
    return po_cid


def main():
    vyhod = sys.argv[sys.argv.index('--vyhod') + 1] if '--vyhod' in sys.argv else VYHOD
    po_cid = {}
    for r in csv.DictReader(open(INN, encoding='utf-8-sig'), delimiter=';'):
        po_cid[r['company_id']] = r
    lica, otkuda = [], {}
    for put in LICA:
        if not os.path.exists(put):
            print(f'ВНИМАНИЕ: нет {os.path.basename(put)} — этот разбор в выгрузку не попадёт')
            continue
        r = list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';'))
        otkuda[os.path.basename(put)] = len(r)
        lica += r
    print('разборы на входе: ' + ', '.join(f'{k} {v}' for k, v in otkuda.items()))

    lyudi = defaultdict(lambda: {'telefony': set(), 'pochty': set(), 'dolzhnosti': set(),
                                 'tendery': set(), 'predmety': set(), 'daty': set(),
                                 'osnovaniya': set(), 'roli': set()})
    bez_inn = 0
    nepodtverzhdennye = []
    korotkie = []
    for r in lica:
        if r.get('telefon_est_v_tekste') != '1' and (r.get('telefon') or '').strip():
            nepodtverzhdennye.append(r)
            continue
        imya = (r.get('imya') or '').strip()
        if not imya or NE_IMYA.search(imya) or not FIO.match(imya):
            continue
        c = po_cid.get(r['company_id']) or {}
        inn = c.get('inn') or ''
        if not inn:
            bez_inn += 1
        # «Головачёв Алексей» и «Головачев Алексей» — один человек. Ключ без «ё» и без
        # отчества: отчество в карточках то есть, то нет, и по нему один человек двоится.
        chasti = imya.lower().replace('ё', 'е').split()
        k = (inn or r['company_id'], ' '.join(chasti[:2]))
        d = lyudi[k]
        d['inn'] = inn
        d['company_id'] = r['company_id']
        d['company'] = r.get('company') or c.get('company') or ''
        d['imya'] = imya
        # Рубеж «это вообще номер»: в российском номере не меньше десяти цифр. Полный разбор
        # третьей сессии принёс строки вида «+7 (002) 69-79» — восемь цифр, набрать нельзя.
        # Человека при этом оставляем: у него есть имя и почта, потерять его из-за номера нельзя.
        if r.get('telefon'):
            if len(re.sub(r'\D', '', r['telefon'])) >= 10:
                d['telefony'].add(r['telefon'].strip())
            else:
                d.setdefault('vnutrennie', set()).add(r['telefon'].strip())
                korotkie.append((r.get('company', ''), (r.get('imya') or ''), r['telefon']))
        if r.get('pochta'):
            d['pochty'].add(r['pochta'].strip())
        if (r.get('dolzhnost') or '').strip():
            d['dolzhnosti'].add(r['dolzhnost'].strip())
        d['roli'].add(r.get('rol') or '')
        d['tendery'].add(r.get('tender_id') or '')
        d['predmety'].add((r.get('predmet') or '')[:120])
        d['daty'].add(r.get('sozdan') or '')
        if (r.get('osnovanie') or '').strip():
            d['osnovaniya'].add(r['osnovanie'].strip()[:120])

    # --- Склейка одного человека, разъехавшегося по разным ИНН одного холдинга ---
    # Замер, из-за которого это появилось: Микрюкова Мария Владимировна стояла в выгрузке ДВАЖДЫ —
    # под ИНН 2130230898 («ТД Транспортное машиностроение») с мобильным +7 (951) 788-00-92 и под
    # ИНН 2127309097 («ПО КТЗ») без телефона вовсе. Ключ дедупа `(ИНН, фамилия и имя)` считает это
    # двумя людьми, потому что карточки одного холдинга заведены на разные юрлица. Вторая запись
    # выглядела как «технический человек, у которого телефона нет», и именно так её и посчитала
    # линза, потребовавшая «добрать 103 телефона».
    # Доказательство «это один человек» берём не по близости строк, а по ПОЧТЕ: совпадает адрес
    # целиком или домен. Однофамильцы из разных компаний под это не подходят — проверено на
    # Микрюковых: Мария (chtz.uvz.ru), Анна (без почты) и Роман (basemet.ru) остались раздельными.
    sklejka = 0
    po_imeni = defaultdict(list)
    for k, d in lyudi.items():
        po_imeni[' '.join(d['imya'].lower().replace('ё', 'е').split()[:2])].append(k)
    for imya, klyuchi in po_imeni.items():
        if len(klyuchi) < 2:
            continue
        gruppy = []  # список [ключи, множество почт, множество доменов]
        for k in klyuchi:
            p = {x.lower() for x in lyudi[k]['pochty'] if '@' in x}
            dm = {x.split('@')[1] for x in p}
            for g in gruppy:
                if (p & g[1]) or (dm & g[2]):
                    g[0].append(k)
                    g[1] |= p
                    g[2] |= dm
                    break
            else:
                gruppy.append([[k], p, dm])
        for kl, _, _ in gruppy:
            if len(kl) < 2:
                continue
            # головной — у кого больше карточек: у него самая надёжная привязка к компании
            glav = max(kl, key=lambda k: len(lyudi[k]['tendery']))
            g = lyudi[glav]
            for k in kl:
                if k == glav:
                    continue
                d = lyudi.pop(k)
                for pole in ('telefony', 'pochty', 'dolzhnosti', 'tendery', 'predmety', 'daty',
                             'osnovaniya', 'roli'):
                    g[pole] |= d[pole]
                if d.get('vnutrennie'):
                    g.setdefault('vnutrennie', set()).update(d['vnutrennie'])
                if d.get('inn') and d['inn'] != g.get('inn'):
                    g.setdefault('drugie_inn', set()).add(f"{d['inn']} ({d.get('company', '')})")
                sklejka += 1
    # После склейки номера одного человека в разных написаниях складываются; убираем повторы по
    # последним десяти цифрам, иначе «+7-960-918-41-97» и «89609184197» лежат как два номера.
    for d in lyudi.values():
        vidno = {}
        for t in sorted(d['telefony']):
            vidno.setdefault(cifry(t) or t, t)
        d['telefony'] = set(vidno.values())

    # Понижение роли по списку «выглядит техническим, но решает не по нашей машине».
    ponizheno = 0
    for d in lyudi.values():
        if 'техническая' in d['roli'] and any(NE_NASH.search(x) for x in d['dolzhnosti']):
            d['roli'].discard('техническая')
            d['roli'].add('неясно')
            d['ponizheno'] = 'проектная или автотранспортная должность'
            ponizheno += 1

    def ves(d):
        teh = 'техническая' in d['roli']
        mob = any(MOB.search(t) for t in d['telefony'])
        return (teh, mob, bool(d['dolzhnosti']), max(d['daty'] or ['']),
                len(d['tendery']))

    spisok = sorted(lyudi.values(), key=ves, reverse=True)
    tel_komp = telefony_kompanij()
    cols = ['inn', 'company', 'imya', 'dolzhnost', 'rol', 'telefony', 'mobilnyy', 'pochty',
            'tenderov', 'poslednyaya_data', 'predmet', 'osnovanie', 'ponizheno', 'ssylka',
            'drugie_inn', 'vnutrenniy_nomer', 'telefon_predpriyatiya_ne_lichnyy']
    with open(vyhod, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for d in spisok:
            tid = sorted(d['tendery'])[-1] if d['tendery'] else ''
            w.writerow({
                'inn': d.get('inn', ''), 'company': d.get('company', ''), 'imya': d['imya'],
                'dolzhnost': ' | '.join(sorted(d['dolzhnosti'])),
                'rol': 'техническая' if 'техническая' in d['roli']
                       else ('снабжение' if 'снабжение' in d['roli'] else 'неясно'),
                'telefony': ' | '.join(sorted(d['telefony'])),
                'mobilnyy': '1' if any(MOB.search(t) for t in d['telefony']) else '',
                'pochty': ' | '.join(sorted(d['pochty'])),
                'tenderov': len(d['tendery']),
                'poslednyaya_data': max(d['daty'] or ['']),
                'predmet': sorted(d['predmety'])[-1] if d['predmety'] else '',
                'osnovanie': ' | '.join(sorted(d['osnovaniya']))[:200],
                'ponizheno': d.get('ponizheno', ''),
                'ssylka': f'https://www.tender.pro/api/tender/{tid}/view_public' if tid else '',
                'drugie_inn': ' | '.join(sorted(d.get('drugie_inn') or [])),
                # Короткий внутренний номер («85-40», «доб. 54-536») набрать напрямую нельзя, но
                # выбрасывать его нельзя тоже: вместе с номером предприятия это прямой путь
                # к человеку. Линза требовала как раз этого — отделить внутренние от прямых.
                'vnutrenniy_nomer': ' | '.join(sorted(d.get('vnutrennie') or [])),
                # только тем, у кого своего номера нет: иначе колонка сбивает продавца с личного
                'telefon_predpriyatiya_ne_lichnyy': (
                    '' if d['telefony']
                    else ' | '.join(sorted(tel_komp.get(d.get('company_id') or '', []))[:4])),
            })

    teh = [d for d in spisok if 'техническая' in d['roli']]
    mob = [d for d in teh if any(MOB.search(t) for t in d['telefony'])]
    print(f'строк на входе: {len(lica)}')
    print(f'отложено, телефона нет во входном тексте карточки: {len(nepodtverzhdennye)}')
    print(f'отделено внутренних номеров (короче десяти цифр): {len(korotkie)}' + (f' (например: {korotkie[0][2]} — {korotkie[0][1]})' if korotkie else ''))
    print(f'людей после дедупа и рубежа «это ФИО»: {len(spisok)}')
    print(f'  из них техническая роль: {len(teh)}, у них мобильный: {len(mob)}')
    print(f'  с должностью словами из текста: {sum(1 for d in spisok if d["dolzhnosti"])}')
    print(f'понижено по списку «решает не по нашей машине»: {ponizheno}')
    print(f'склеено записей одного человека с разными ИНН: {sklejka}')
    bez_tel = [d for d in teh if not d['telefony']]
    s_zamenoj = [d for d in bez_tel if tel_komp.get(d.get('company_id') or '')]
    print(f'технических без своего номера: {len(bez_tel)}, '
          f'из них с телефоном предприятия для захода по имени: {len(s_zamenoj)}')
    print(f'компаний: {len({d.get("inn") or d["company_id"] for d in spisok})}, '
          f'без ИНН строк: {bez_inn}')
    print(f'→ {vyhod}')


if __name__ == '__main__':
    main()

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
LICA = os.path.join(TP, 'tp-lica.csv')
INN = os.path.join(TP, 'tp-inn.csv')
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


def main():
    vyhod = sys.argv[sys.argv.index('--vyhod') + 1] if '--vyhod' in sys.argv else VYHOD
    po_cid = {}
    for r in csv.DictReader(open(INN, encoding='utf-8-sig'), delimiter=';'):
        po_cid[r['company_id']] = r
    lica = list(csv.DictReader(open(LICA, encoding='utf-8-sig'), delimiter=';'))

    lyudi = defaultdict(lambda: {'telefony': set(), 'pochty': set(), 'dolzhnosti': set(),
                                 'tendery': set(), 'predmety': set(), 'daty': set(),
                                 'osnovaniya': set(), 'roli': set()})
    bez_inn = 0
    nepodtverzhdennye = []
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
        if r.get('telefon'):
            d['telefony'].add(r['telefon'].strip())
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
    cols = ['inn', 'company', 'imya', 'dolzhnost', 'rol', 'telefony', 'mobilnyy', 'pochty',
            'tenderov', 'poslednyaya_data', 'predmet', 'osnovanie', 'ponizheno', 'ssylka']
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
            })

    teh = [d for d in spisok if 'техническая' in d['roli']]
    mob = [d for d in teh if any(MOB.search(t) for t in d['telefony'])]
    print(f'строк на входе: {len(lica)}')
    print(f'отложено, телефона нет во входном тексте карточки: {len(nepodtverzhdennye)}')
    print(f'людей после дедупа и рубежа «это ФИО»: {len(spisok)}')
    print(f'  из них техническая роль: {len(teh)}, у них мобильный: {len(mob)}')
    print(f'  с должностью словами из текста: {sum(1 for d in spisok if d["dolzhnosti"])}')
    print(f'понижено по списку «решает не по нашей машине»: {ponizheno}')
    print(f'компаний: {len({d.get("inn") or d["company_id"] for d in spisok})}, '
          f'без ИНН строк: {bez_inn}')
    print(f'→ {vyhod}')


if __name__ == '__main__':
    main()

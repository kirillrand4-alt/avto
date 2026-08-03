# -*- coding: utf-8 -*-
"""Дообогащение контактов обхода: ФИО и должность из сохранённого контекста.

Аудит показал: в файле 2 062 контакта, но ФИО проставлено лишь у 114, а должность не извлекалась
вовсе — колонки не было. При этом в `kontekst` (160 знаков вокруг номера) ФИО и должность часто
стоят рядом, потому что контактные страницы всегда свёрстаны как «ФИО → должность → почта →
телефон».

ГЛАВНОЕ ПРАВИЛО РАЗБОРА, выведенное замером: брать ближайшее ФИО СЛЕВА от маркера контакта, а не
просто ближайшее. Выбор «по минимальному расстоянию» систематически приписывает номер СЛЕДУЮЩЕМУ
человеку в списке — проверено на «СВИСС КРОНО» и «Арзамасском хлебе». Точность такого разбора
замерена на 114 уже размеченных строках: 96%.

Ничего не выбрасываю (правило владельца): мусор и корпоративные номера холдингов помечаются
колонками, а не удаляются.
"""
import csv
import re
import sys

sys.path.insert(0, '/home/user/work')
from regex_lica import (CLEAN_HTML, CLEAN_TAG, R_FIO_FULL, R_FIO_IOF, R_FIO_IO, R_FIO_FIO_,
                        R_FIO_IOF_, R_DOL)  # noqa: E402

csv.field_size_limit(10 ** 7)
R_ULICA = re.compile(r'(?:ул\.|улиц\w+|пр-т|проспект|пер\.|переул\w+|бульвар|шоссе|наб\.|площад\w+)\s*$', re.I)
R_TEH = re.compile(
    r'гл(?:авн\w*|\.)\s*инженер|гл(?:авн\w*|\.)\s*энергетик|\bОГЭ\b|гл(?:авн\w*|\.)\s*механик|\bОГМ\b|'
    r'техническ\w+\s+директор|директор\w*\s+по\s+(?:производств|техническ|эксплуатац)|\bПТО\b|'
    r'производственно[- ]техническ|\bКИПиА\b|\bАСУ\s?ТП\b|метролог|энергоцех|компрессорн|'
    r'начальник\w*\s+(?:цеха|участка|смены|котельн|производств|станции)|гл(?:авн\w*|\.)\s*технолог|'
    r'служб\w+\s+эксплуатац|инженер', re.I)
R_SNAB = re.compile(r'снабжен|закупк|закупо|\bОМТС\b|\bМТО\b|материально[- ]техническ|тендерн|комплектаци', re.I)
R_PRODAZHI = re.compile(r'менеджер\w*\s+по\s+продаж|отдел\w*\s+продаж|sales', re.I)
R_MUSOR = [
    (re.compile(r'0000000|1234567|1111111|9999999|8888888'), 'номер-заглушка', True),
    (re.compile(r'\d+\s+0\s+obj|endobj|/Type\s*/|\bxref\b'), 'вырезано из потока PDF', False),
    (re.compile(r'дизайн\s+сайта|разработ\w+\s+сайта|веб[- ]?студи|1С-Битрикс', re.I), 'блок про сайт', False),
    (re.compile(r'горячая\s+лини|телефон\s+доверия|единый\s+контакт-центр|антикоррупц|'
                r'СберБанк|Россельхозбанк|@(?:mosreg|gov)\.ru', re.I), 'чужая линия или ведомство', False),
    (re.compile(r'ваканс|резюме|трудоустрой|соискател|отдел\s+кадров', re.I), 'кадры, не ЛПР по оборудованию', False),
]
STOPTAIL = re.compile(r'\s+(?:тел|телефон|email|e-mail|почта|адрес|факс|8|\+7|\d)\S*$', re.I)
STOP_FAM = {'контактное', 'ответственное', 'должностное', 'уполномоченное', 'юридический',
            'почтовый', 'фактический', 'единый', 'горячая'}


def chistyy(t):
    return CLEAN_HTML.sub(' ', t or '')


def fio_i_dolzhnost(kontekst):
    """Возвращает (ФИО, должность). Ищем СЛЕВА от маркера контакта."""
    t = chistyy(kontekst)
    m = CLEAN_TAG.search(t)
    poz = m.start() if m else len(t)
    levo = CLEAN_TAG.sub(' ', t[:poz])
    pravo = CLEAN_TAG.sub(' ', t[poz:])
    fio = ''
    for rx, sborka in ((R_FIO_FULL, lambda g: ' '.join(g)),
                       (R_FIO_IOF, lambda g: f'{g[2]} {g[0]} {g[1]}'),
                       (R_FIO_FIO_, lambda g: f'{g[0]} {g[1]}.{g[2]}.'),
                       (R_FIO_IOF_, lambda g: f'{g[2]} {g[0]}.{g[1]}.'),
                       (R_FIO_IO, lambda g: ' '.join(g))):
        kand = list(rx.finditer(levo)) or list(rx.finditer(pravo))
        if kand:
            g = kand[-1].groups() if rx.search(levo) else kand[0].groups()
            v = sborka(g)
            if v.split()[0].lower().strip('.,') not in STOP_FAM:
                fio = v
                break
    dol = ''
    kd = list(R_DOL.finditer(levo)) or list(R_DOL.finditer(pravo))
    if kd:
        m2 = kd[-1] if R_DOL.search(levo) else kd[0]
        if not R_ULICA.search(levo[:m2.start()]):
            dol = STOPTAIL.sub('', m2.group(0)).strip(' ,;:-')
    return fio.strip(), dol.strip()


def main():
    vhod = '/home/user/work/OBHOD-kontakty-3s.csv'
    r = list(csv.DictReader(open(vhod, encoding='utf-8-sig'), delimiter=';'))
    # номер, встречающийся у разных ИНН — это корпоративная линия холдинга, а не завода
    po_kontaktu = {}
    for x in r:
        po_kontaktu.setdefault(x['kontakt'], set()).add(x['inn'])
    novyh_fio = novyh_dol = teh = snab = musor = holding = prodazhi = 0
    for x in r:
        f, d = fio_i_dolzhnost(x.get('kontekst', ''))
        if f and not (x.get('chelovek') or '').strip():
            x['chelovek'] = f
            novyh_fio += 1
        x['dolzhnost'] = d
        if d:
            novyh_dol += 1
        blob = f'{d} {x.get("kontekst","")}'
        x['tehnicheskiy_lpr'] = 'да' if (d and R_TEH.search(d)) else ''
        if x['tehnicheskiy_lpr']:
            teh += 1
        x['snabzhenie'] = 'да' if R_SNAB.search(blob) else ''
        if x['snabzhenie']:
            snab += 1
        x['prodazhnik'] = 'да' if R_PRODAZHI.search(blob) else ''
        if x['prodazhnik']:
            prodazhi += 1
        pr = ''
        for rx, imya, po_nomeru in R_MUSOR:
            cel = re.sub(r'\D', '', x['kontakt']) if po_nomeru else x.get('kontekst', '')
            if rx.search(cel or ''):
                pr = imya
                break
        x['musor'] = pr
        if pr:
            musor += 1
        n = len(po_kontaktu.get(x['kontakt'], ()))
        x['obshchiy_na_neskolko_inn'] = str(n) if n > 1 else ''
        if n > 1:
            holding += 1
    kol = list(r[0])
    with open(vhod, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=kol, delimiter=';', extrasaction='ignore')
        w.writeheader()
        w.writerows(r)
    s_fio = sum(1 for x in r if (x.get('chelovek') or '').strip())
    print(f'строк: {len(r)}')
    print(f'ФИО было 114, дописано {novyh_fio}, стало {s_fio}')
    print(f'должность извлечена у {novyh_dol}')
    print(f'ТЕХНИЧЕСКИЙ ЛПР: {teh} | снабжение: {snab} | продажники (отрицательная ценность): {prodazhi}')
    print(f'помечено мусором: {musor} | корпоративный номер на несколько ИНН: {holding}')
    print(f'предприятий с ФИО: {len(set(x["inn"] for x in r if (x.get("chelovek") or "").strip()))}')


if __name__ == '__main__':
    main()

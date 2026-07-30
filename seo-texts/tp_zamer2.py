# -*- coding: utf-8 -*-
"""Замер-2 по отсечённым карточкам Tender.pro: проверка самих признаков отсечения.

Правило 1 («ноль — своя неисправность, пока не доказано обратное») применяю к ПРИЗНАКАМ,
по которым карточки отсекались, а не только к результату. Два признака:
  telefony_* пусто  → но регулярка `TEL_TXT` из harvest может номер не поймать;
  est_teh пусто     → но `TEH` из harvest не покрывает часть должностей.
Здесь оба признака перепроверяю своим, более широким набором, и считаю расхождение.
"""
import csv
import os
import re
import sys

BAZA = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BAZA, 'engineers-lens', 'centro', 'tenderpro')
KART = os.path.join(OUT, 'tp-kartochki.csv')

# ровно та регулярка, которой отсекали (tenderpro_harvest.py)
TEL_HARVEST = re.compile(r'(?:\+7|\b8)[\s(\-]*\d{3,5}[\s)\-]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}\b')
TEH_HARVEST = re.compile(r'тех\w*\s+(?:вопрос|характер|част)|техническ|главн\w+\s+(?:инженер|механик|'
                         r'энергетик|технолог)|гл\.?\s*(?:инженер|механик|энергетик)|начальник\s+'
                         r'(?:цеха|управлен|отдела\s+глав|компрессорн|энерго|производств)|'
                         r'механик|энергетик|инженер|КИПиА|ОГМ|ОГЭ|УГЭ|УГМ', re.I)

# широкий ловец: «тел./моб./т.» ИЛИ 10-11 цифр с разделителями любой раскладки
TEL_SHIROKO = re.compile(
    r'(?:\+7|\b8|\b7)[\s()\-.]*\d{3,5}[\s()\-.]*\d{2,4}[\s\-.]*\d{2,4}(?:[\s\-.]*\d{2})?'
    r'|(?:тел|моб|факс|т\.)[^0-9]{0,12}(\d[\d\s()\-.]{8,18}\d)', re.I)

FIO_INIC = re.compile(r'([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ])\.\s?([А-ЯЁ])\.')
INIC_FIO = re.compile(r'([А-ЯЁ])\.\s?([А-ЯЁ])\.\s*([А-ЯЁ][а-яё]{2,})')
# три слова с заглавной подряд — сильный признак ФИО, отчество почти всегда на -ович/-евна и т.п.
TRI = re.compile(r'[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}')
DVA = re.compile(r'[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}')
# отчество: надёжный маркер человека
OTCH = re.compile(r'\b[А-ЯЁ][а-яё]+(?:ович|евич|ьевич|овна|евна|ична|ьевна|инична)\b')
POCHTA = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')

# слово о должности любого рода (шире, чем «техническая»)
DOLZH = re.compile(
    r'главн\w*\s+(?:инженер|механик|энергетик|метролог|технолог)|'
    r'инженер|механик|энергетик|метролог|технолог|начальник|заместител|\bзам\.|'
    r'директор|руководител|мастер\b|специалист|менеджер|куратор|диспетчер|'
    r'снабжен|закупк|ОМТС|ОГМ|ОГЭ|КИПиА|ТОиР|энергоцентр|компрессорн', re.I)

# наши целевые роли — узко
CEL = re.compile(
    r'главн\w*\s+(?:инженер|механик|энергетик|метролог)|гл\.?\s*(?:инженер|механик|энергетик)|'
    r'\bинженер|\bмеханик|\bэнергетик|начальник\s+(?:цеха|участка|компрессорн|энерго|производств|'
    r'отдела\s+глав|управлен|смены|котельн|ремонт)|ОГМ|ОГЭ|КИПиА|ТОиР|энергоцентр|'
    r'тех\w*\s+(?:вопрос|характер|част|специалист)|эксплуатац', re.I)

MUSOR = re.compile(
    r'^(?:Российск|Гражданск|Федеральн|Обществ|Закрыт|Открыт|Публичн|Акционерн|Ограничен|'
    r'Единый|Электронн|Торгов|Запрос|Коммерческ|Техническ|Приложен|Договор|Заказчик|'
    r'Организатор|Участник|Победител|Комисси|Республик|Област|Настоящ|Данн|Указан|Извещен|'
    r'Документ|Протокол|Поставк|Услуг|Работ|Товар|Налогов|Деловые|Крайнего|Город|Правил|'
    r'Кодекс|Отдел|Служб|Управлен|Центр|Завод|Комбинат|Группа|Компан|Фирм|Дирекц|Филиал|'
    r'Стоимост|Условия|Требован|Гарант|Оплат|Срок|Цена|Внимание|Просьб|Прош|Все|Любые)',
    re.I)


def kandidaty_fio(c):
    """Кандидаты в люди, от сильных признаков к слабым."""
    silno, slabo = [], []
    for m in OTCH.finditer(c):                       # есть отчество → почти наверняка человек
        silno.append(m.group(0))
    for m in FIO_INIC.finditer(c):
        if not MUSOR.match(m.group(1)):
            silno.append(m.group(0))
    for m in INIC_FIO.finditer(c):
        if not MUSOR.match(m.group(3)):
            silno.append(m.group(0))
    for m in TRI.finditer(c):
        if not MUSOR.match(m.group(0).split()[0]):
            slabo.append(m.group(0))
    for m in DVA.finditer(c):
        if not MUSOR.match(m.group(0).split()[0]):
            slabo.append(m.group(0))
    return silno, slabo


def main():
    vse = otsech = 0
    st = {k: 0 for k in ('com_pusto', 'com_est', 'tel_propushchen', 'teh_propushchen',
                         'silno', 'slabo', 'lyuboy', 'dolzh', 'cel', 'pochta',
                         'silno_i_dolzh', 'silno_i_cel', 'silno_bez_tel')}
    komp = {'vse': set(), 'silno': set(), 'silno_i_cel': set()}
    prim_tel, prim_teh, prim_fio = [], [], []
    otobrat = []                       # что имеет смысл отдать провайдеру

    for r in csv.DictReader(open(KART, encoding='utf-8-sig'), delimiter=';'):
        vse += 1
        tel_kol = (r.get('telefony_razmetka') or '') + (r.get('telefony_tekst') or '')
        if tel_kol or r.get('est_teh'):
            continue
        otsech += 1
        komp['vse'].add(r.get('company_id'))
        c = (r.get('comment') or '').replace('&nbsp;', ' ').replace('&ndash;', '-')
        # «Комментарий:» — префикс, который harvest ставит всегда; без него пусто
        golyy = re.sub(r'^\s*Комментарий:\s*', '', c).strip()
        if not golyy:
            st['com_pusto'] += 1
            continue
        st['com_est'] += 1

        # перепроверка признаков отсечения
        mt = TEL_SHIROKO.search(golyy)
        if mt and not TEL_HARVEST.search(golyy):
            st['tel_propushchen'] += 1
            if len(prim_tel) < 6:
                prim_tel.append((r['tender_id'], r['company'], mt.group(0).strip(), golyy[:260]))
        mh = CEL.search(golyy)
        if mh and not TEH_HARVEST.search(golyy):
            st['teh_propushchen'] += 1
            if len(prim_teh) < 6:
                prim_teh.append((r['tender_id'], r['company'], mh.group(0), golyy[:260]))

        silno, slabo = kandidaty_fio(golyy)
        d = DOLZH.search(golyy)
        cl = CEL.search(golyy)
        p = POCHTA.findall(golyy)
        if silno:
            st['silno'] += 1
            komp['silno'].add(r.get('company_id'))
        if slabo and not silno:
            st['slabo'] += 1
        if silno or slabo:
            st['lyuboy'] += 1
        if d:
            st['dolzh'] += 1
        if cl:
            st['cel'] += 1
        if p:
            st['pochta'] += 1
        if silno and d:
            st['silno_i_dolzh'] += 1
        if silno and cl:
            st['silno_i_cel'] += 1
            komp['silno_i_cel'].add(r.get('company_id'))
            if len(prim_fio) < 8:
                prim_fio.append((r['tender_id'], r['company'], silno[:3], cl.group(0), golyy[:300]))
        if silno:
            st['silno_bez_tel'] += 1
            otobrat.append(r['tender_id'])

    n = otsech
    print(f'карточек в файле: {vse};  отсечено: {n}')
    print(f'знаменатель дальше — {n} отсечённых карточек, {len(komp["vse"])} компаний\n')
    print(f'комментарий пуст (только префикс «Комментарий:»): {st["com_pusto"]:5d} / {n}'
          f'  ({100 * st["com_pusto"] / n:.1f}%)')
    print(f'комментарий с текстом:                           {st["com_est"]:5d} / {n}'
          f'  ({100 * st["com_est"] / n:.1f}%)')
    m = st['com_est'] or 1
    print(f'\n--- перепроверка самих признаков отсечения (знаменатель {m} с текстом) ---')
    print(f'номер есть, но регулярка harvest его НЕ поймала: {st["tel_propushchen"]:5d}'
          f'  ({100 * st["tel_propushchen"] / m:.1f}%)')
    print(f'целевая роль есть, но TEH harvest НЕ поймал:     {st["teh_propushchen"]:5d}'
          f'  ({100 * st["teh_propushchen"] / m:.1f}%)')
    print(f'\n--- что в тексте (знаменатель {m}) ---')
    print(f'сильный признак человека (отчество / Фамилия И.О.): {st["silno"]:5d}'
          f'  ({100 * st["silno"] / m:.1f}%)')
    print(f'только слабый (два-три слова с заглавной):          {st["slabo"]:5d}'
          f'  ({100 * st["slabo"] / m:.1f}%)')
    print(f'слово о должности любой:                            {st["dolzh"]:5d}'
          f'  ({100 * st["dolzh"] / m:.1f}%)')
    print(f'слово о ЦЕЛЕВОЙ (технической) роли:                 {st["cel"]:5d}'
          f'  ({100 * st["cel"] / m:.1f}%)')
    print(f'почта:                                              {st["pochta"]:5d}'
          f'  ({100 * st["pochta"] / m:.1f}%)')
    print(f'сильное ФИО + должность:                            {st["silno_i_dolzh"]:5d}'
          f'  ({100 * st["silno_i_dolzh"] / m:.1f}%)')
    print(f'сильное ФИО + ЦЕЛЕВАЯ роль:                         {st["silno_i_cel"]:5d}'
          f'  ({100 * st["silno_i_cel"] / m:.1f}%)')
    print(f'\nкомпаний с сильным ФИО: {len(komp["silno"])} из {len(komp["vse"])};'
          f' с ФИО+целевой ролью: {len(komp["silno_i_cel"])}')
    print(f'К РАЗБОРУ ПРОВАЙДЕРОМ (сильный признак человека): {len(otobrat)} карточек')

    print('\n=== ДОКАЗАТЕЛЬСТВО, что отсечение было не всегда верным: номер в отсечённой карточке ===')
    for tid, comp, tel, c in prim_tel:
        print(f'\n[{tid}] {comp}\n  найденный мною номер: {tel}\n  {c}')
    print('\n=== целевая роль в отсечённой карточке (TEH harvest промахнулся) ===')
    for tid, comp, w, c in prim_teh:
        print(f'\n[{tid}] {comp}\n  слово: {w}\n  {c}')
    print('\n=== ФИО + целевая роль без телефона ===')
    for tid, comp, fio, w, c in prim_fio:
        print(f'\n[{tid}] {comp}\n  ФИО: {fio}  роль: {w}\n  {c}')

    with open(os.path.join(OUT, 'tp-otsech-k-razboru.txt'), 'w') as fh:
        fh.write('\n'.join(otobrat))


if __name__ == '__main__':
    main()

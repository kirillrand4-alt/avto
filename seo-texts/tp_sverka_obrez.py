# -*- coding: utf-8 -*-
"""Сверка перевыкачки карточек Tender.pro: что именно вернула снятая обрезка.

Зачем отдельный скрипт. Перевыкачка стоила девять тысяч запросов, и о её пользе надо
отчитываться цифрой ИЗ ФАЙЛА, а не счётчиком прогона (правило 6 из передачи). Сверка читает
старый и новый CSV и печатает ровно то, что изменилось.

Важно понимать, что перевыкачка НЕ меняет: телефоны, почты и признак `est_teh` старый прогон
брал из ПОЛНОГО текста комментария и только потом резал поле `comment` до 2 000 знаков. То есть
номера регулярка не теряла. Терял их провайдер: в `tenderpro_lica.py` уходили первые 1 500
знаков уже обрезанного поля, и заслон «номера нет во входном тексте» сверялся с ним же.

Исключение одно, и его надо замерить: когда конец блока комментария в разметке не находился,
старый сборщик брал запасную границу `i + 4000` знаков РАЗМЕТКИ. Там терялось всё — и телефоны
тоже. Новый предел 60 000 знаков, случаи помечены колонкой `granica_zapasnaya`.

Использование:
    python3 tp_sverka_obrez.py [старый.csv] [новый.csv]
"""
import csv
import os
import re
import sys

csv.field_size_limit(10 ** 7)

BAZA = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BAZA, 'engineers-lens', 'centro', 'tenderpro')
STARYY = os.path.join(OUT, 'tp-kartochki.csv')
NOVYY = os.path.join(OUT, 'tp-kartochki-polnye.csv')

D = re.compile(r'\D+')
TEL = re.compile(r'(?:\+7|\b8)[\s(\-]*\d{3,5}[\s)\-]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}\b')


def cifry(s):
    d = D.sub('', s or '')
    return d[-10:] if len(d) in (10, 11) else ''


def nomera_polya(r):
    """Все номера из полей телефонов карточки, нормализованные до десяти цифр."""
    s = (r.get('telefony_razmetka') or '') + ' | ' + (r.get('telefony_tekst') or '')
    return {c for c in (cifry(t) for t in s.split('|')) if c}


def main():
    staryy = sys.argv[1] if len(sys.argv) > 1 else STARYY
    novyy = sys.argv[2] if len(sys.argv) > 2 else NOVYY
    st = {r['tender_id']: r for r in csv.DictReader(open(staryy, encoding='utf-8-sig'),
                                                   delimiter=';')}
    nv = {r['tender_id']: r for r in csv.DictReader(open(novyy, encoding='utf-8-sig'),
                                                   delimiter=';')}
    print('=== ОБЪЁМ ===')
    print(f'карточек в старом файле: {len(st)}')
    print(f'карточек в новом файле:  {len(nv)}')
    propali = [t for t in st if t not in nv]
    print(f'было и не пришло заново: {len(propali)}'
          + (f' (первые: {propali[:5]})' if propali else ''))

    obshch = [t for t in nv if t in st]
    print(f'сверяется по общим:      {len(obshch)}')

    print('\n=== ДЛИНА КОММЕНТАРИЯ ===')
    st2000 = sum(1 for t in obshch if len(st[t].get('comment') or '') == 2000)
    dlinnee = [t for t in obshch
               if len(nv[t].get('comment') or '') > len(st[t].get('comment') or '')]
    maxlen = max((len(nv[t].get('comment') or '') for t in obshch), default=0)
    print(f'упирались в старый обрез 2000 знаков:   {st2000}')
    print(f'в новом файле текст стал длиннее:       {len(dlinnee)}')
    print(f'самый длинный комментарий теперь:       {maxlen} знаков')
    for p in (2000, 5000, 10000, 20000):
        print(f'  длиннее {p:>5} знаков: '
              f'{sum(1 for t in obshch if len(nv[t].get("comment") or "") > p)}')
    zapas = [t for t in nv if nv[t].get('granica_zapasnaya')]
    print(f'запасная граница блока сработала:       {len(zapas)}')

    print('\n=== ЧТО ПРОВАЙДЕР НЕ ВИДЕЛ (главная потеря) ===')
    # Номер, добытый регуляркой из полного текста, но отсутствующий в сохранённом поле:
    # именно эти карточки уходили провайдеру без номера, и заслон мог назвать номер выдумкой.
    nevidno_st = [t for t in obshch
                  if nomera_polya(st[t]) - {cifry(x) for x in TEL.findall(st[t].get('comment') or '')}]
    nevidno_nv = [t for t in obshch
                  if nomera_polya(nv[t]) - {cifry(x) for x in TEL.findall(nv[t].get('comment') or '')}]
    print(f'было — карточек, где добытый номер не попал в сохранённый текст: {len(nevidno_st)}')
    print(f'стало — таких же карточек:                                      {len(nevidno_nv)}')
    # Провайдеру уходили первые 1500 знаков: номер за этим рубежом он не видел даже там,
    # где поле не упиралось в 2000.
    za1500_st = sum(1 for t in obshch
                    if nomera_polya(st[t]) - {cifry(x) for x in
                                              TEL.findall((st[t].get('comment') or '')[:1500])})
    za1500_nv = sum(1 for t in obshch
                    if nomera_polya(nv[t]) - {cifry(x) for x in
                                              TEL.findall((nv[t].get('comment') or '')[:1500])})
    print(f'было — номер не виден в первых 1500 знаках (что и уходило в запрос): {za1500_st}')
    print(f'стало — при отправке полного текста:                                {za1500_nv}')

    print('\n=== НОВЫЕ ДАННЫЕ, КОТОРЫХ НЕ БЫЛО ВОВСЕ ===')
    nov_tel, nov_teh, ushli_tel = [], [], []
    for t in obshch:
        a, b = nomera_polya(st[t]), nomera_polya(nv[t])
        if b - a:
            nov_tel.append((t, sorted(b - a)))
        if a - b:
            ushli_tel.append((t, sorted(a - b)))
        if nv[t].get('est_teh') and not st[t].get('est_teh'):
            nov_teh.append(t)
    print(f'карточек с НОВЫМИ номерами:              {len(nov_tel)}')
    for t, n in nov_tel[:10]:
        print(f'   {t}: {n} | {(nv[t].get("company") or "")[:40]}')
    print(f'карточек, где номер пропал (проверить!): {len(ushli_tel)}')
    for t, n in ushli_tel[:10]:
        print(f'   {t}: {n} | {(nv[t].get("company") or "")[:40]}')
    print(f'карточек, где техническое слово появилось: {len(nov_teh)}')

    print('\n=== СКОЛЬКО ПЕРЕСПРАШИВАТЬ У ПРОВАЙДЕРА ===')
    sys.path.insert(0, BAZA)
    import tenderpro_lica as L  # noqa: E402  (импорт после csv-настроек, ради za_rubezhom)
    k_razboru = [t for t in nv
                 if ((nv[t].get('telefony_razmetka') or '') + (nv[t].get('telefony_tekst') or '')
                     or nv[t].get('est_teh')) and L.za_rubezhom(nv[t].get('comment'))]
    print(f'карточек с телефоном или тех.словом, где за прежним рубежом 1400 есть номер '
          f'или техническое слово: {len(k_razboru)}')


if __name__ == '__main__':
    main()

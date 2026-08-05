# -*- coding: utf-8 -*-
"""Мобильный, стоящий у ДВУХ разных людей, — не личный номер, а номер бюро.

ОТКУДА ПРАВИЛО. Его прислала 2-я сессия, посмотрев свою панель глазами: у неё нашлось
пять мобильных, поделённых на двоих, — два снабженца ТЯЖМАШа на один номер, две
кадровички Кировпейпера на один номер. Признак «начинается на 79» отличает мобильный от
городского, но НЕ личный от отдельского, а мере ТЗ нужно именно второе: личный номер
человека, принимающего решение.

Это тот же класс, что я весь день ловлю у себя: близость не доказывает принадлежность.
Номер стоит рядом с человеком — значит он его. Не значит. Общий сотовый отдела снабжения
лежит в столе и переходит из рук в руки, и звонок по нему попадает не к тому, к кому
целились.

ЧТО ДЕЛАЕТ ПРИБОР. Считает по каждому номеру, скольким РАЗНЫМ людям он приписан, и
скольким предприятиям. Три исхода, и ни один не выбрасывается:

  * у одного человека и одного предприятия — личный, мера ТЗ его считает;
  * у нескольких людей одного предприятия — «мобильный отдела»: звонить по нему можно и
    нужно, но обещать «это личный номер главного инженера» нельзя;
  * у нескольких ПРЕДПРИЯТИЙ — номер посредника, тендерного агента или справочника,
    и это уже разобрано отдельным правилом.

Разные написания одного имени — не разные люди. «Аксёнов Денис» и «Денис Аксенов» это
один человек, и 2-я сессия на этом же обожглась. Сравниваю по ЯДРУ ИМЕНИ: фамилия и
инициалы, без регистра, без ё/е, без порядка слов.

Без --apply ничего не пишется.
"""
import collections
import json
import re
import sqlite3
import sys

BAZY = (r'C:\seostat\data\centrifugal.db', r'C:\seostat\data\p25.db')
APPLY = '--apply' in sys.argv


def cifry(s):
    c = re.sub(r'\D', '', str(s or ''))
    if len(c) == 11 and c[0] in '78':
        return '7' + c[1:]
    if len(c) == 10 and c[0] == '9':
        return '7' + c
    return ''


def slova(s):
    return [w.lower().replace('ё', 'е')
            for w in re.split(r'[^А-Яа-яЁёA-Za-z]+', str(s or '')) if w]


def sovmestimy(a, b):
    """Одно ли это лицо. Не ключ, а СРАВНЕНИЕ ПАРЫ — потому что ключ здесь не строится.

    Первым заходом я делала ключ «фамилия + инициалы», а фамилией брала самое длинное
    слово. Отчество почти всегда длиннее фамилии: у «Иванов Иван Иванович» фамилией
    оказалось бы «иванович». Ошибка тихая — люди просто не склеились бы, и номер бюро
    сошёл бы за личный. Угадывать, какое слово фамилия, при гуляющем порядке слов нельзя.

    Сравнение обходится без этого. Двое — одно лицо, если у них есть общее ПОЛНОЕ слово
    и ничто не противоречит: остальные полные слова совпадают хотя бы началом, а инициалы
    находят себе слово с той же буквы.

        «Аксёнов Денис» и «Денис Аксенов Не»          -> одно лицо (порядок слов)
        «АКСЕНОВ Д.В.» и «Аксёнов Денис Владимирович» -> одно лицо (инициалы)
        «Иванов Иван»  и «Иванов Пётр»                -> РАЗНЫЕ (общая только фамилия)
    """
    A, B = slova(a), slova(b)
    da = [w for w in A if len(w) >= 3]
    db = [w for w in B if len(w) >= 3]
    ia = [w[0] for w in A if len(w) < 3]
    ib = [w[0] for w in B if len(w) < 3]
    obsh = set(da) & set(db)
    if not obsh:
        return False
    ost_a = [w for w in da if w not in obsh]
    ost_b = [w for w in db if w not in obsh]
    bukvy_a, bukvy_b = {w[0] for w in ost_a}, {w[0] for w in ost_b}
    if ost_a and ost_b and not (bukvy_a & bukvy_b):
        return False
    if ost_b and any(i not in bukvy_b for i in ia):
        return False
    if ost_a and any(i not in bukvy_a for i in ib):
        return False
    return True


def raznyh_lic(imena):
    """Сколько РАЗНЫХ лиц в наборе имён: склеиваем совместимые, считаем группы."""
    gruppy = []
    for im in imena:
        for g in gruppy:
            if any(sovmestimy(im, x) for x in g):
                g.append(im)
                break
        else:
            gruppy.append([im])
    return gruppy


def razobrat(baza):
    b = sqlite3.connect('file:%s?mode=ro' % baza.replace('\\', '/'), uri=True)
    tabl = [r[0] for r in b.execute(
        "select name from sqlite_master where type='table'")]
    nayti = []
    for t in tabl:
        polya = [r[1] for r in b.execute('pragma table_info(%s)' % t)]
        tel = [p for p in polya if re.search(r'phone|telefon|nomer', p, re.I)]
        chel = [p for p in polya if re.search(r'person|fio|contact_name|imya', p, re.I)]
        if tel and chel:
            nayti.append((t, polya, tel[0], chel[0],
                          'inn' if 'inn' in polya else ''))
    return b, nayti


def main():
    itog, primery = collections.Counter(), collections.defaultdict(list)
    pometit = collections.defaultdict(list)   # база -> [(vid, tablica, rowid)]
    for baza in BAZY:
        try:
            b, nayti = razobrat(baza)
        except Exception as e:  # noqa: BLE001
            print('REC база %s не открылась: %s\t1' % (baza, str(e)[:50]))
            continue
        for t, polya, p_tel, p_chel, p_inn in nayti:
            po_nomeru = collections.defaultdict(lambda: {'lyudi': set(), 'inn': set(),
                                                         'rowid': []})
            sql = 'select rowid, %s, %s%s from %s' % (
                p_tel, p_chel, (', ' + p_inn) if p_inn else '', t)
            try:
                stroki = list(b.execute(sql))
            except Exception:  # noqa: BLE001
                continue
            for r in stroki:
                n = cifry(r[1])
                if not n or not n.startswith('79'):     # правило только про мобильные
                    continue
                imya = str(r[2] or '').strip()
                if not slova(imya):
                    continue
                z = po_nomeru[n]
                z['lyudi'].add(imya)
                z['rowid'].append(r[0])
                if p_inn and len(r) > 3:
                    z['inn'].add(str(r[3] or ''))
            for n, z in po_nomeru.items():
                gruppy = raznyh_lic(sorted(z['lyudi']))
                if len(gruppy) <= 1:
                    itog['%s.%s: личный (одно лицо)' % (baza[-14:], t)] += 1
                    continue
                vid = ('мобильный отдела: номер у %d разных лиц' % len(gruppy)
                       if len(z['inn']) <= 1 else
                       'номер у %d лиц и %d предприятий — посредник или справочник'
                       % (len(gruppy), len(z['inn'])))
                itog['%s.%s: %s' % (baza[-14:], t, vid.split(':')[0])] += 1
                for rid in z['rowid']:
                    pometit[(baza, t)].append((vid, rid))
                if len(primery[t]) < 8:
                    primery[t].append((n, [g[0] for g in gruppy][:4], len(z['inn'])))
        b.close()

    for t, sp in primery.items():
        print('\n--- %s: номера, поделённые между людьми' % t)
        for n, lyudi, n_inn in sp:
            print('    %-12s предприятий %-3d  %s' % (n, n_inn, '; '.join(lyudi)[:78]))

    # Запись: вид номера называется прямо в строке, ничего не удаляется.
    zapisano = 0
    if APPLY:
        for (baza, t), spisok in pometit.items():
            try:
                z = sqlite3.connect(baza)
                polya = [r[1] for r in z.execute('pragma table_info(%s)' % t)]
                if 'vid_nomera_po_lyudyam' not in polya:
                    z.execute('alter table %s add column vid_nomera_po_lyudyam text' % t)
                z.executemany('update %s set vid_nomera_po_lyudyam = ? where rowid = ?' % t,
                              spisok)
                z.commit()
                z.close()
                zapisano += len(spisok)
            except Exception as e:  # noqa: BLE001
                print('REC запись в %s.%s не прошла: %s\t1' % (baza[-14:], t, str(e)[:44]))
        itog['СТРОК ПОМЕЧЕНО'] = zapisano
    else:
        itog['будет помечено (сухой прогон)'] = sum(len(v) for v in pometit.values())

    for k, v in itog.most_common():
        print('REC %s\t%d' % (k, v))
    print('ИТОГ ' + json.dumps({
        'режим': 'запись' if APPLY else 'сухой прогон',
        'номеров, поделённых между людьми': sum(len(v) for v in primery.values()),
        'строк помечено': zapisano}, ensure_ascii=False))


if __name__ == '__main__':
    main()

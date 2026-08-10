# -*- coding: utf-8 -*-
"""Пункт очереди: сопоставить формы серий словаря с тем, что написано в записях ЭПБ.

Зачем. Марка стоит у 2 173 фактов из 70 590. Самый большой запас — записи Ростехнадзора
(ЭПБ) и предметы закупок: там наименование пишут целиком, «компрессор поршневой 4ВУ1-5/9»,
но при вливании из текста брали только ТИП, а обозначение оставалось внутри текста.
Словарь (3 731 обозначение) позволяет это обозначение узнать.

ПЕРВЫЙ ЗАХОД БЫЛ НЕТОЧЕН, и это видно только глазами. Совпадение шло по словарю, и в марку
писалась словарная форма: текст «балансировка ротора компрессора 43ВЦ-160/9М2» давал марку
«ВЦ-160/9», текст «компрессоров АК-50Т» — «АК-50». Формально не выдумка, фактически другая
машина: 43ВЦ-160/9М2 и ВЦ-160/9 — разные исполнения. Поэтому теперь словарь работает только
как УЗНАВАНИЕ, а в базу идёт НАСТОЯЩЕЕ написание из текста:

    napisanie — точный кусок исходного текста («43ВЦ-160/9М2»);
    model     — он же, это и есть модель, как её назвал документ;
    marka     — бренд из словаря, если запись каталожная, иначе словарная серия.

Как ищем, чтобы не наловить ложного:
  * сравниваем СЖАТЫЕ формы (без пробелов, верхний регистр, ё→е): в документах пишут и
    «ЗИФ-ПВ-6/1,0», и «ЗИФ ПВ 6/1,0» — это одно обозначение;
  * обозначение короче 5 знаков или без цифры не берём: «АК-50», «ВП» ловятся в числах
    и заводских номерах;
  * при нескольких совпадениях берём самое длинное;
  * границы расширяем ПО ИСХОДНОМУ тексту, а не по сжатому: влево только цифрами (43ВЦ…,
    4ВУ1…), вправо буквами и цифрами не дальше пробела и не более шести знаков. Иначе
    «ТВ 175-1,6 очистных» превратилось бы в «ТВ175-1,6ОЧИСТН».

По умолчанию скрипт НИЧЕГО не пишет — печатает замер и примеры с контекстом для проверки
глазами. Запись: python3 park_1s_serii_v_marki.py --pisat
"""
import collections, csv, os, re, sqlite3, sys, time

D = os.path.dirname(os.path.abspath(__file__))
PISAT = '--pisat' in sys.argv
BUKVOCIFRA = re.compile(r'[0-9A-Za-zА-Яа-яЁё]')
PRODOLZHENIE = re.compile(r'[0-9A-ZА-ЯA-Za-zа-я/,.-]')


def szhat_s_kartoy(t):
    """Сжатая форма + карта: позиция в сжатом -> позиция в исходном."""
    out, karta = [], []
    for i, ch in enumerate(t or ''):
        if ch.isspace():
            continue
        out.append(ch.upper().replace('Ё', 'Е'))
        karta.append(i)
    return ''.join(out), karta


def szhat(t):
    return re.sub(r'\s+', '', (t or '').upper().replace('Ё', 'Е'))


# В словаре 3-й сессии часть обозначений снята вместе с хвостом карточки: «К-1500-62-2,СТ»
# (дальше в документе шло «ст. №4»). С таким ключом в базу уезжает «К-1500-62-2, ст» —
# марка с куском соседнего поля. Чистим ключ на входе, а не после записи.
_HVOST = re.compile(r'[,;]\s*(ст|поз|зав|инв|техн?|№).*$', re.I)


def chistyy_klyuch(ob):
    return _HVOST.sub('', (ob or '').strip()).strip(' .,;:-')


slovar = {}
for x in csv.DictReader(open(os.path.join(D, 'PARK-SLOVAR-EDINYY.csv'), encoding='utf-8-sig'),
                        delimiter=';'):
    ob = chistyy_klyuch(x.get('oboznachenie'))
    s = szhat(ob)
    if len(s) < 5 or not re.search(r'\d', s):
        continue
    if s not in slovar or (not slovar[s][1] and x.get('brend')):
        slovar[s] = (ob, (x.get('brend') or '').strip(), (x.get('vid_mashiny') or '').strip(),
                     (x.get('vid_zapisi') or '').strip())
klyuchi = sorted(slovar, key=len, reverse=True)
print('обозначений в словаре после отсева коротких и бесцифренных: %d' % len(klyuchi))


# «поз. К-1-1-1», «зав. № 95005», «инв.№712103» — это ПОЗИЦИЯ по схеме и номер, а не марка.
# Ловится на общих ключах вида «К-250»: у одного ИНН нашлись и настоящий «32ВЦ-100-9М3»,
# и позиционный «К-1/1-1» из той же записи ЭПБ.
# «позиция по схеме ЦК-402/3» тоже позиция, хотя слова стоят не вплотную: в той же записи
# настоящая марка названа отдельно («компрессор марки АТКП-435-1600»). Поэтому смотрим не
# один предлог, а всё окно слева.
POZICIYA = re.compile(
    r'(поз(иц\w*)?(\s+по\s+схеме)?\.?|ст(анционн\w*)?\.?\s*№?|тех(нологическ\w*|н)?\.?\s*№?|'
    r'зав(одск\w*)?\.?\s*№?|инв(ентарн\w*)?\.?\s*№?|рег(истрационн\w*)?\.?\s*№?|'
    r'(технологическ\w*\s+)?индекс|заключени\w*\s*№?|№)\s*$', re.I)


def nastoyashchee(tekst, i, j):
    """Кусок ИСХОДНОГО текста вокруг совпадения [i,j) сжатой формы + что слева от него."""
    s, karta = szhat_s_kartoy(tekst)
    a, b = karta[i], karta[j - 1] + 1
    # влево — буквы, цифры И ДЕФИСЫ до ближайшего пробела: «43ВЦ…», «4ВУ1…», «ГК-301/302».
    # Ограничение цифрами теряло букву префикса («компрессоров ГК-301/302» -> «К-301/302»),
    # а остановка на дефисе прятала чужую конструкцию: в «Заключение № НЦ-1744-К-2021»
    # ключ «К-202» выглядел маркой, пока слева не подтянулся весь номер заключения.
    while a > 0 and (BUKVOCIFRA.match(tekst[a - 1]) or tekst[a - 1] == '-'):
        a -= 1
    # вправо — буквы/цифры/дробь, не дальше пробела и не более шести знаков
    k = 0
    while b < len(tekst) and k < 6 and PRODOLZHENIE.match(tekst[b]) and not tekst[b].isspace():
        b += 1
        k += 1
    return tekst[a:b].strip(' .,;:)'), tekst[max(0, a - 24):a], a, b


p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()
rows = cur.execute("""select id, inn, tip, chto_naydeno, kto from fakt
                      where v_parke=1 and coalesce(marka,'')='' and coalesce(chto_naydeno,'')<>''
                   """).fetchall()
print('фактов без марки на входе: %d' % len(rows))

nashli = []
istochniki = collections.Counter()
vidy = collections.Counter()
otsev = collections.Counter()
razoshlos = 0
for fid, inn, tip, tekst, kto in rows:
    s, _ = szhat_s_kartoy(tekst)
    if not re.search(r'\d', s):
        continue
    for k in klyuchi:
        i = s.find(k)
        if i < 0:
            continue
        ob, brend, vidm, vidz = slovar[k]
        nast, sleva, a, b = nastoyashchee(tekst, i, i + len(k))
        if POZICIYA.search(sleva):
            otsev['позиция по схеме или заводской номер, а не марка'] += 1
            break
        if sleva.rstrip().endswith('/'):
            # «аммиак и карбамид А-525/К-700» — обозначение агрегата производства,
            # наш ключ тут лишь правая половина чужой пары
            otsev['правая половина чужой пары через дробь'] += 1
            break
        if szhat(nast) != k:
            razoshlos += 1
        nashli.append((fid, inn, tip, ob, brend, vidm, vidz, nast, tekst, kto[:44], a, b))
        istochniki[kto[:44]] += 1
        vidy[vidz] += 1
        break

print('совпало обозначений: %d (%.1f%% входа)'
      % (len(nashli), 100.0 * len(nashli) / max(1, len(rows))))
print('  из них написание в тексте ПОЛНЕЕ словарной формы: %d' % razoshlos)
print('  по виду записи словаря:', dict(vidy))
print('  по источнику факта:')
for k, v in istochniki.most_common(8):
    print('     %-46s %d' % (k, v))
print('  предприятий затронуто: %d' % len({x[1] for x in nashli}))
print('  отсеяно заслонами:')
for k, v in otsev.most_common():
    print('     %-52s %d' % (k, v))
print()
print('=== 25 совпадений с контекстом (проверка глазами, ровный шаг по всей выборке) ===')
shag = max(1, len(nashli) // 25)
for x in nashli[::shag][:25]:
    fid, inn, tip, ob, brend, vidm, vidz, nast, tekst, kto, a, b = x
    okno = tekst[max(0, a - 45):b + 45].replace('\n', ' ')
    print('  факт %-7s ИНН %-12s [%-14s] словарь «%s» -> в базу «%s»%s'
          % (fid, inn, tip, ob, nast, (' /' + brend) if brend else ''))
    print('      …%s…' % okno)

if PISAT:
    n = 0
    for fid, inn, tip, ob, brend, vidm, vidz, nast, tekst, kto, a, b in nashli:
        cur.execute("""update fakt set marka=?, model=?, napisanie=?,
                         chem_rang = case when coalesce(chem_rang,'')='' then ? else chem_rang end
                       where id=? and coalesce(marka,'')=''""",
                    (brend or ob, nast, nast,
                     'C: обозначение узнано словарём в тексте документа', fid))
        n += cur.rowcount
    cur.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
                (time.strftime('%Y-%m-%d %H:%M:%S'),
                 'СЛОВАРЬ СЕРИЙ -> марка/модель из текстов фактов',
                 len(rows), n, len(rows) - n,
                 '{"обозначение из словаря в тексте не найдено": %d}' % (len(rows) - n)))
    p.commit()
    q = lambda s: cur.execute(s).fetchone()[0]
    print()
    print('ЗАПИСАНО: %d фактов' % n)
    print('фактов с маркой в парке стало: %d'
          % q("select count(*) from fakt where v_parke=1 and coalesce(marka,'')<>''"))
p.close()

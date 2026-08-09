# -*- coding: utf-8 -*-
"""Обратный ход дал 96 телефонов на 62 человека. Провожу их через ВСЕ оплаченные заслоны.

Прогон: 558 человек с полным ФИО из 883 найденных, у 62 нашёлся телефон, 96 телефонов,
63 почты, сбой 1. Это ещё не результат — это сырьё. Каждый заслон ниже уже стоил нам
ошибки, и ни один не пропускаю:

1. НОМЕР У НЕСКОЛЬКИХ ПРЕДПРИЯТИЙ — НЕ ЛИЧНЫЙ. Правило поймало больше всех: мой же замер
   личных мобильных прошёл 818 -> 613 -> 249 именно из-за него. Считаю номер по всем ИНН
   всех баз сразу, а не по одному предприятию.
2. БЛИЗОСТЬ К ФАМИЛИИ НЕ ДОКАЗЫВАЕТ ПРИНАДЛЕЖНОСТЬ. Модуль обратного хода пишет расстояние
   между фамилией и номером — беру его и печатаю распределение, а не прячу. Далёкий номер
   помечается «фамилия и номер в разных местах страницы», но не выбрасывается.
3. ССЫЛКА ОБЯЗАТЕЛЬНА. Контакт без первоисточника в счёт цели не идёт.
4. ВИД НОМЕРА НАЗЫВАЕТСЯ ЯВНО: личный мобильный, мобильный без имени, городской, 8-800,
   общий с добавочным. Разделять, а не отсеивать.

И отдельно: 469 человек из 558 остались без телефона. Это НЕ провал канала, а его цена —
называю её числом, чтобы следующий заход считал от неё, а не от нуля.

Только чтение баз. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import sqlite3
import urllib.request

# Тот же прибор гоняю по ДВУМ разным входам: свои найденные люди и люди 1-й сессии.
# Имя входного файла — первым доводом, чтобы не плодить копию скрипта: провенанс у потоков
# разный, а заслоны обязаны быть одни и те же.
import sys as _sys
FAJL = _sys.argv[1] if len(_sys.argv) > 1 else 'PARK-OBRATNYY-3S.jsonl'
VYHOD = (r'C:\sender\_ops\%s' % (_sys.argv[2] if len(_sys.argv) > 2
                                  else 'PARK-OBRATNYY-PROVERENO-3S.jsonl'))
BAZY = [r'C:\sender\enrich.db', r'C:\seostat\drop\drop-storage\atlas_copco.db',
        r'C:\seostat\data\centrifugal.db']
P_INN = re.compile(r'^(inn|company_inn|firma_inn|org_inn)$', re.I)
P_TEL = re.compile(r'phone|tel|mobil', re.I)
URL = re.compile(r'https?://[^\s"\'<>|;,]+')
DOB = re.compile(r'доб\.?\s*\d{1,5}|ext\.?\s*\d{1,5}', re.I)


TELEFON = re.compile(r'(?:\+?7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}'
                     r'|\b9\d{9}\b')
FIO_LYUBOE = re.compile(r'[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё\-]{2,}\s+'
                        r'[А-ЯЁ][а-яё\-]{2,}(?:ович|евич|ич|овна|евна|ична)')


def prinadlezhit(citata, imya, syroy, des):
    """Принадлежит ли номер ИМЕННО этому человеку. Смотрела глазами — в трёх случаях из
    четырёх НЕ принадлежал:

        «Алексеев Константин Анатольевич 9146734735»
          цитата: «Алексеев АНДРЕЙ АЛЕКСАНДРОВИЧ … Олесик Виктор Геннадьевич: тел.: 8 9…»
          -> номер Олесика, совпала одна фамилия

        «Петров Алексей Сергеевич 9272270787»
          цитата: «Петров Алексей ВАЛЕРЬЕВИЧ, Петров Евгений Валерьевич…»
          -> другой человек, совпали фамилия и имя

        «Христич Олег Викторович 9210982344»
          цитата: «Христич Олег Викторович +7 (81366) 94-086»
          -> в цитате ДРУГОЙ номер, значит записанный взят из иного места страницы

    Модуль обратного хода пишет расстояние до фамилии, но в моих строках оно пустое у всех
    двадцати — то есть заслон «близость не доказывает принадлежность» у меня НЕ РАБОТАЛ.
    Делаю проверку по самой цитате, а не по полю, которого нет:

      1. цифры номера обязаны стоять в цитате — иначе это номер с другого места страницы;
      2. в окне ±140 знаков вокруг номера должно стоять ПОЛНОЕ ФИО нашего человека;
      3. если в этом окне есть ЧУЖОЕ полное ФИО ближе к номеру, чем наше — номер не наш.
    """
    if not citata or not des:
        return False, 'цитаты нет'
    # ВТОРАЯ ПОПРАВКА, после того как я посмотрела все четырнадцать выживших глазами.
    #
    # 1. Номер нельзя искать по слитым цифрам всей цитаты. У Потаповой «9502938494»
    #    сложился из обрывков «…Дилерский Комплект 2938494…» и соседних чисел — телефона
    #    в цитате нет вовсе. Ищу телефонный ОБРАЗЕЦ и сверяю его десять цифр.
    # 2. Хозяин номера — ближайшее ФИО, и мерить надо от КОНЦА предшествующего имени, а не
    #    от его начала. У Кошилева цитата: «Технический директор Рузаев Артем Сергеевич
    #    с.т. - 8-903-945-61-63 Главный инженер Кошилев Олег Николаевич» — номер стоит
    #    вплотную к Рузаеву, а прежняя мерка отдавала его Кошилеву.
    obrazcy = [(m.start(), m.end()) for m in TELEFON.finditer(citata)
               if desyat(m.group(0)) == des]
    if not obrazcy:
        return False, 'номера нет в цитате — взят из другого места страницы'
    n_start, n_end = obrazcy[0]
    chasti = imya.split()
    nash = ' '.join(chasti[:3])
    kand = []
    for m in FIO_LYUBOE.finditer(citata):
        d = (n_start - m.end()) if m.end() <= n_start else (m.start() - n_end)
        kand.append((abs(d), m.group(0)))
    if not kand:
        return False, 'в цитате нет ни одного полного ФИО'
    kand.sort()
    if kand[0][1] == nash:
        return True, 'номер стоит вплотную к нашему ФИО'
    if nash and nash in citata:
        return False, 'ближе к номеру стоит другое ФИО: %s' % kand[0][1]
    if len(chasti) >= 2 and ' '.join(chasti[:2]) in citata:
        return False, 'совпали только фамилия и имя, отчество другое'
    if chasti and chasti[0] in citata:
        return False, 'совпала только фамилия — однофамилец'
    return False, 'нашего ФИО в цитате нет'


def desyat(t):
    c = re.sub(r'\D', '', str(t or ''))
    if len(c) == 11 and c[0] in '78':
        c = c[1:]
    return c if len(c) == 10 else ''


op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
rq = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'), FAJL),
                            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
syr = op.open(rq, timeout=300).read().decode('utf-8', 'replace')

# --- номер -> сколько предприятий, по всем базам
nomer_u_inn = collections.defaultdict(set)
for baza in BAZY:
    if not os.path.exists(baza):
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % baza.replace('\\', '/'), uri=True)
        tabl = [r[0] for r in cx.execute("select name from sqlite_master where type='table'")]
    except Exception:  # noqa: BLE001
        continue
    for t in tabl:
        try:
            kol = [r[1] for r in cx.execute('pragma table_info("%s")' % t)]
        except Exception:  # noqa: BLE001
            continue
        k_inn = [k for k in kol if P_INN.match(k)]
        k_tel = [k for k in kol if P_TEL.search(k)]
        if not k_inn or not k_tel:
            continue
        try:
            kur = cx.execute('select %s from "%s"' % (','.join('"%s"' % k for k in k_inn[:1] + k_tel), t))
        except Exception:  # noqa: BLE001
            continue
        for r in kur:
            inn = str(r[0] or '').strip()
            if not inn:
                continue
            for v in r[1:]:
                d = desyat(v)
                if d:
                    nomer_u_inn[d].add(inn)
    cx.close()

lyudi, bez_tel, s_oshibkoy = 0, 0, 0
potok, vidy, rasst = [], collections.Counter(), collections.Counter()
spornye = collections.Counter()
for s in syr.splitlines():
    if not s.strip():
        continue
    try:
        o = json.loads(s)
    except Exception:  # noqa: BLE001
        continue
    lyudi += 1
    if o.get('err'):
        s_oshibkoy += 1
    try:
        kont = json.loads(o.get('kontakty') or '[]') if isinstance(o.get('kontakty'), str) \
            else (o.get('kontakty') or [])
    except Exception:  # noqa: BLE001
        kont = []
    if not kont:
        bez_tel += 1
        continue
    for k in kont:
        syroy = str(k.get('znachenie') or k.get('value') or k.get('telefon') or
                    k.get('phone') or k.get('kontakt') or '')
        ssylka = str(k.get('ssylka') or k.get('url') or '')
        citata = str(k.get('citata') or k.get('okno') or '')[:220]
        r_ = k.get('rasstoyanie')
        des = desyat(syroy)
        if '@' in syroy and not des:
            vid = 'почта'
        elif not des:
            continue
        else:
            u_skolkih = len(nomer_u_inn.get(des, ()))
            if u_skolkih > 1:
                vid = 'номер у %d предприятий — не личный' % u_skolkih
            elif des.startswith('800'):
                vid = '8-800 (линия предприятия)'
            elif DOB.search(syroy):
                vid = 'общий с добавочным'
            elif des[0] == '9':
                vid = 'ЛИЧНЫЙ МОБИЛЬНЫЙ'
            else:
                vid = 'городской'
        svoy, pochemu = (True, 'почта') if vid == 'почта' else prinadlezhit(citata, o.get('fio', ''), syroy, des)
        if vid == 'ЛИЧНЫЙ МОБИЛЬНЫЙ' and not svoy:
            vid = 'мобильный, но принадлежность не доказана'
            spornye[pochemu] += 1
        if isinstance(r_, int):
            rasst['до 100 знаков' if r_ <= 100 else
                  ('100–400' if r_ <= 400 else 'дальше 400 — фамилия и номер в разных местах')] += 1
        vidy[vid] += 1
        potok.append({
            'inn': o.get('inn', ''), 'predpriyatie': o.get('predpriyatie', '')[:120],
            'imya': o.get('fio', ''), 'dolzhnost': o.get('dolzhnost', ''),
            'znachenie': syroy[:60], 'nomer': des, 'vid_nomera': vid,
            'rasstoyanie_do_familii': r_ if isinstance(r_, int) else '',
            'prinadlezhnost': pochemu,
            'istochniki': ssylka, 'istochnikov': 1 if ssylka.startswith('http') else 0,
            'citata': citata,
            'u_skolkih_predpriyatiy': len(nomer_u_inn.get(des, ())) if des else '',
            'kto': '3-я сессия, обратный ход по найденным ЛПР',
        })

# ГЛАЗАМИ ПО ДЕВЯТИ ВЫЖИВШИМ — ещё два дефекта, и оба чинятся здесь.
#
# 1. «Потапова Светлана Евгеньевна 9502938494», цитата: «Адреса и телефоны: Россия и Китай…
#    Потапова Светлана Евгеньевна: 00.00.1960 г.р., адрес… Дилерский Комплект 2938494:
#    тел.: 8 9502938494». Номер принадлежит фирме «Дилерский Комплект», а ФИО стоит выше
#    по другому адресу. Ближайшего ЧУЖОГО ФИО рядом нет, поэтому правило её пропустило.
#    Источник — сайт-сборник утёкших персональных данных (дата рождения, домашний адрес).
#    Такие источники исключаю по существу, а не по точности: это не деловой контакт.
# 2. Один и тот же номер Кошилева стоит у ДВУХ разных ИНН. Правило «номер у нескольких
#    предприятий — не личный» я применяла к базам, а к собственному потоку забыла.
SLIV = re.compile(r'metall\.win|б\d{2,}\.php|адреса\s+и\s+телефоны|г\.р\.,\s*адрес|'
                  r'база\s+данных|слив|утечк', re.I)
for _o in potok:
    if _o['vid_nomera'] == 'ЛИЧНЫЙ МОБИЛЬНЫЙ' and (SLIV.search(_o.get('citata') or '')
                                                   or SLIV.search(_o.get('istochniki') or '')):
        _o['vid_nomera'] = 'мобильный из сборника утёкших данных — не деловой контакт'
        spornye['источник — сборник утёкших персональных данных'] += 1
_po_nomeru = collections.Counter()
for _o in potok:
    if _o['nomer']:
        _po_nomeru[_o['nomer']] += 1
for _o in potok:
    if _o['vid_nomera'] == 'ЛИЧНЫЙ МОБИЛЬНЫЙ' and _po_nomeru[_o['nomer']] > 1:
        _inn = {x['inn'] for x in potok if x['nomer'] == _o['nomer']}
        if len(_inn) > 1:
            _o['vid_nomera'] = 'номер у %d предприятий в моём же потоке — не личный' % len(_inn)
            spornye['номер стоит у нескольких ИНН в собственном потоке'] += 1

# СВЁРТКА. Один и тот же номер Кошилева приехал пятью строками из пяти разных тендеров —
# это не пять контактов, а один с пятью доказательствами. Ключ свёртки канонический:
# ИНН плюс десять цифр номера; ссылки накапливаются, их число и есть сила.
_svern = {}
for _o in potok:
    _k = (_o['inn'], _o['nomer'] or _o['znachenie'])
    if _k in _svern:
        _z = _svern[_k]
        if _o['istochniki'] and _o['istochniki'] not in _z['istochniki']:
            _z['istochniki'] += ' | ' + _o['istochniki']
            _z['istochnikov'] += 1
    else:
        _svern[_k] = _o
potok = list(_svern.values())

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in potok:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')
vylozheno = 'не выкладывала'
try:
    r2 = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                           os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT',
                                headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vylozheno = op.open(r2, timeout=300).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vylozheno = 'не выложено: %s' % str(e)[:90]

lich = [o for o in potok if o['vid_nomera'] == 'ЛИЧНЫЙ МОБИЛЬНЫЙ']
lich_ss = [o for o in lich if o['istochnikov']]
print('\n\n########## ВЕРСИЯ ПРИБОРА: ближайшее ФИО от конца имени + телефонный образец + свёртка')
print('########## ЛИЧНЫЕ, ПО ОДНОМУ')
for o in lich[:10]:
    print('  %-12s %-26s %-24s %s' % (o['inn'], o['imya'][:26], o['dolzhnost'][:24], o['nomer']))
    print('        %s' % (o['istochniki'][:110] or 'ССЫЛКИ НЕТ'))
print('\n########## ЧИСЛА')
print('  людей в файле                %5d' % lyudi)
print('  из них без контакта вовсе    %5d  (цена канала, а не провал)' % bez_tel)
print('  строк контактов              %5d' % len(potok))
print('  ЛИЧНЫХ МОБИЛЬНЫХ             %5d  (со ссылкой %d, предприятий %d)'
      % (len(lich), len(lich_ss), len({o['inn'] for o in lich_ss})))
print('  --- по виду')
for k, v in vidy.most_common(10):
    print('     %-46s %5d' % (k[:46], v))
print('  --- почему мобильный НЕ засчитан личным')
for k, v in spornye.most_common(8):
    print('     %-52s %5d' % (k[:52], v))
print('  --- расстояние «фамилия — номер»')
for k, v in rasst.most_common():
    print('     %-46s %5d' % (k, v))
print('  строк с ошибкой выдачи       %5d' % s_oshibkoy)
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vylozheno)
print('ИТОГ ' + json.dumps({'людей': lyudi, 'без контакта': bez_tel,
                            'личных': len(lich), 'личных со ссылкой': len(lich_ss)},
                           ensure_ascii=False))

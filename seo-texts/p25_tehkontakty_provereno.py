# -*- coding: utf-8 -*-
"""ТОЛЬКО ПРОВЕРЕННЫЕ ТЕХКОНТАКТЫ. Владелец: «мне нужны только проверенные тех контакты».

Отдельный файл, куда строка попадает, лишь если её привязка проверена НЕ ПО РАЗМЕТКЕ, а по
тому, что видно человеку:

    в видимом тексте страницы стоит И фамилия, И номер   -> ПРОВЕРЕНО
    совпало только в разметке                            -> НЕ проверено, лежит в отвале
    ничего не совпало                                    -> НЕ проверено, лежит в отвале

Почему так строго. Разбор первых снимков показал две ловушки, и обе выглядели как успех:
`tender.pro` держит в разметке чужие тендеры (фамилия и номер нашлись в блоке «другие
тендеры компании», а страница — про демонтаж здания); PDF-презентация совпала фамилией
студента с фамилией «главного инженера». Разметка содержит чужое; видимый текст — то, что
читает человек.

У каждой проверенной строки в файле стоит имя СНИМКА на дропе: продавец может открыть
картинку и увидеть то же, что видела я.

Отвал не выбрасывается: он выкладывается вторым файлом с причиной у каждой строки —
правило владельца «разделять, а не отсеивать».

Числа в КОНЦЕ.
"""
import collections
import io
import re
import json
import os
import urllib.request

from p25_imya_predpriyatiya import nazvano

SCRATCH = os.environ.get('P25_SCRATCH', '.')
VHOD = os.path.join(SCRATCH, 'PARK-SNIMKI-TEHKONTAKTOV-3S.jsonl')
VYHOD = os.path.join(SCRATCH, 'PARK-TEHKONTAKTY-PROVERENO-3S.csv')
OTVAL = os.path.join(SCRATCH, 'PARK-TEHKONTAKTY-NE-PROVERENO-3S.csv')
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MASHINA = re.compile(r'компрессор|воздуходув|нагнетател|ГПА\b|осушител|азотн|кислородн|воздухоразделит', re.I)
KOL = ('inn', 'predpriyatie', 'chelovek', 'dolzhnost', 'nomer', 'chem_provereno',
       'mashina_provereno', 'snimok_chelovek', 'snimok_mashina', 'ssylka',
       'ssylka_mashina')

stroki = []
for s in io.open(VHOD, encoding='utf-8'):
    try:
        stroki.append(json.loads(s))
    except Exception:  # noqa: BLE001
        pass

# СНИМОК-ДВОЙНИК НЕ ДОКАЗЫВАЕТ. Серверная проба называла файл по секундам
# (`browser-shot-probe-<время>`), и четыре потока, закончив в одну секунду, клали на дроп
# один файл: 118 снимков имели 72 разных имени, то есть у 74 строк «доказательство» было
# чужой страницей. У Потаповой из ЮГК под именем её снимка лежала карточка ЭТП ГПБ про
# дробилки Metso. Теперь у каждого снимка своё имя и sha256; совпавший побайтно снимок у
# двух разных строк — признак той же гонки, и такая строка идёт в отвал до пересъёмки.
# Ссылку на машину у ранее снятых строк добираю из списка звонка по паре «ИНН + номер»:
# снимок машины у них сделан, а адрес в запись не писался, и в выдаче стояла картинка без
# первоисточника. Правило владельца — у каждого факта ссылка И снимок.
SPISOK = os.path.join(SCRATCH, 'PARK-SPISOK-DLYA-ZVONKA-3S.csv')
mash_ssylki = {}
if os.path.exists(SPISOK):
    _sh = None
    for _s in io.open(SPISOK, encoding='utf-8-sig'):
        _p = _s.rstrip('\n').split(';')
        if _sh is None:
            _sh = _p
            continue
        if len(_p) != len(_sh):
            continue
        _d = dict(zip(_sh, _p))
        if (_d.get('ssylka_mashina') or '').startswith('http'):
            mash_ssylki[(_d.get('inn'), _d.get('nomer'))] = _d['ssylka_mashina']

sha_sch = collections.Counter(o.get('snimok_sha') for o in stroki if o.get('snimok_sha'))
# Но одинаковый снимок — не всегда гонка: два контакта ОДНОГО тендера честно доказываются
# одной и той же страницей. Гонка — это когда побайтно один снимок стоит у РАЗНЫХ ссылок.
sha_ssylki = collections.defaultdict(set)
for _o in stroki:
    if _o.get('snimok_sha'):
        sha_ssylki[_o['snimok_sha']].add(_o.get('ssylka'))
prov, ne_prov, sch = [], [], collections.Counter()
for o in stroki:
    if o.get('snimok_sha') and sha_sch[o['snimok_sha']] > 1 \
            and len(sha_ssylki[o['snimok_sha']]) > 1:
        ne_prov.append((o, 'снимок побайтно совпал со снимком другой строки — имя файла '
                           'на дропе было перезаписано, нужна пересъёмка'))
        sch['снимок-двойник, нужна пересъёмка'] += 1
        continue
    vid_n = bool(o.get('v_vidimom_tekste_nomer'))
    vid_f = bool(o.get('v_vidimom_tekste_familiya'))
    raz_n = bool(o.get('na_stranice_nomer'))
    raz_f = bool(o.get('na_stranice_familiya'))
    # ТРЕТИЙ ВОПРОС, добавленный после снимка Скворцовой. Прибор поставил «видно глазами»,
    # и он не соврал: фамилия и номер на странице ЭТП ГПБ стоят. Но закупка называется
    # «расценка запасных частей для конусных дробилок Metso HP 300 и насосов центробежных
    # Metso MDM 350» — машина ЧУЖАЯ. Человек верен, предприятие верно, а доказательства
    # НАШЕЙ машины на этой странице нет. Значит проверенным считается только то, где на
    # той же странице стоит и слово нашей машины.
    # ПОПРАВКА ВЛАДЕЛЬЦА, и она снимает мой перегиб целиком. Его слова: «если компания
    # реально покупала наше оборудование, а тут есть номер — то это доказательство хотя бы
    # ЗАКУПЩИКА этой компании, просто доказательство машины нужно дополнительно».
    #
    # Значит доказательств не одно, а два, и они РАЗНЫЕ:
    #     страница человека  доказывает, что человек — контакт ЭТОГО предприятия;
    #     ссылка на машину   доказывает, что у предприятия наша машина.
    # Требовать машину на странице человека — ошибка: у Скворцовой карточка ЭТП ГПБ честно
    # доказывает, что она контактное лицо закупок этого завода, и не обязана упоминать
    # компрессор. Я на этом получила 0 из 40 и назвала нулём то, что было доказано.
    #
    # Заслон вместо перегиба: страница человека обязана НАЗЫВАТЬ предприятие — по ИНН либо
    # по корню названия. Иначе это чужая страница, где просто совпала фамилия.
    # ИМЯ ПРЕДПРИЯТИЯ ищется общей меркой, а не первыми корнями. Прежняя строка брала два
    # первых слова длиной ≥7 букв, а у 1 070 предприятий из 1 266 оба таких слова — это
    # организационная форма: она искала на странице «ФЕДЕРАЛЬНОЕ», когда там написано ФГБУ.
    est_inn_na_str = bool(o.get('na_stranice_inn'))
    est_imya_na_str, chem_imya = nazvano(o.get('predpriyatie'), o.get('inn'),
                                         o.get('vidimyy_tekst') or '')
    nasha = bool(MASHINA.search(o.get('vidimyy_tekst') or '')) or \
        bool(MASHINA.search(o.get('predmet') or ''))
    if vid_n and vid_f and (est_inn_na_str or est_imya_na_str):
        prichina = ('видно на странице: фамилия, номер, предприятие (%s)' % chem_imya
                    + (' и наша машина' if nasha
                       else '; МАШИНА ДОКАЗЫВАЕТСЯ ОТДЕЛЬНОЙ ССЫЛКОЙ, проверяется своим снимком'))
        if o.get('dva_bloka_zakazchik_i_ispolnitel'):
            prichina += '; ВНИМАНИЕ: на странице названы и заказчик, и исполнитель'
        prov.append((o, prichina))
        sch['ПРОВЕРЕНО'] += 1
    elif vid_n and vid_f:
        ne_prov.append((o, 'фамилия и номер видны, но предприятие на странице НЕ названо '
                           '— возможно чужая страница с совпавшей фамилией'))
        sch['человек виден, предприятие на странице не названо'] += 1
    else:
        if raz_n and raz_f:
            p = 'совпало только в разметке, в видимом тексте нет — привязка не доказана'
        elif vid_n or raz_n:
            p = 'номер на странице есть, фамилии нет'
        elif vid_f or raz_f:
            p = 'фамилия на странице есть, номера нет'
        else:
            p = 'на странице нет ни номера, ни фамилии'
        ne_prov.append((o, p))
        sch[p[:52]] += 1


def pisat(put, spisok):
    with io.open(put, 'w', encoding='utf-8-sig') as f:
        f.write(';'.join(KOL) + '\n')
        for o, prichina in spisok:
            # Машина проверяется СВОИМ снимком, и её итог пишется отдельной колонкой:
            # смешивать его с проверкой человека — та самая ошибка, которую поправил владелец.
            mp = ('машина и предприятие видны на её странице'
                  if o.get('mashina_nasha_na_stranice') and o.get('mashina_predpriyatie_na_stranice')
                  else ('машина видна, предприятие на её странице не названо'
                        if o.get('mashina_nasha_na_stranice')
                        else ('снимок машины сделан, машины на странице не видно'
                              if o.get('mashina_snimok')
                              else 'снимок машины ещё не сделан')))
            r = {'inn': o.get('inn', ''), 'predpriyatie': o.get('predpriyatie', ''),
                 'chelovek': o.get('chelovek', ''), 'dolzhnost': o.get('dolzhnost', ''),
                 'nomer': o.get('nomer', ''), 'chem_provereno': prichina,
                 'mashina_provereno': mp,
                 'snimok_chelovek': o.get('snimok', ''),
                 'snimok_mashina': o.get('mashina_snimok', ''),
                 'ssylka': o.get('ssylka', ''),
                 'ssylka_mashina': (o.get('ssylka_mashina')
                                    or mash_ssylki.get((o.get('inn'), o.get('nomer')), ''))}
            f.write(';'.join(str(r[k]).replace(';', ',').replace('\n', ' ')
                             for k in KOL) + '\n')


pisat(VYHOD, prov)
pisat(OTVAL, ne_prov)
vyl = []
for p in (VYHOD, OTVAL):
    try:
        rq = urllib.request.Request('%s/%s' % (drop, os.path.basename(p)),
                                    data=io.open(p, 'rb').read(), method='PUT', headers=tok)
        vyl.append('%s: %s' % (os.path.basename(p),
                               op.open(rq, timeout=240).read().decode('utf-8', 'replace')[:40]))
    except Exception as e:  # noqa: BLE001
        vyl.append('%s НЕ ВЫЛОЖЕН: %s' % (os.path.basename(p), str(e)[:50]))

print('\n\n########## ПРОВЕРЕННЫЕ, ПО ОДНОМУ')
for o, pr in prov[:15]:
    print('  %-12s %-24s %-16s %s' % (o.get('inn'), (o.get('chelovek') or '')[:24],
                                      o.get('nomer'), (o.get('snimok') or '')[:40]))
print('\n########## ЧИСЛА')
print('  снимков разобрано              %5d  (файл %s)' % (len(stroki),
                                                           os.path.basename(VHOD)))
print('  ПРОВЕРЕНО (видно глазами)      %5d  -> %s' % (len(prov), os.path.basename(VYHOD)))
print('  не проверено                   %5d  -> %s' % (len(ne_prov), os.path.basename(OTVAL)))
for k, v in sch.most_common():
    print('     %-56s %5d' % (k[:56], v))
for v in vyl:
    print('  %s' % v)
print('ИТОГ ' + json.dumps({'снимков': len(stroki), 'проверено': len(prov),
                            'не проверено': len(ne_prov)}, ensure_ascii=False))

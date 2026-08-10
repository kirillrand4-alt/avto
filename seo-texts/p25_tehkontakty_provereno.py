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

SCRATCH = os.environ.get('P25_SCRATCH', '.')
VHOD = os.path.join(SCRATCH, 'PARK-SNIMKI-TEHKONTAKTOV-3S.jsonl')
VYHOD = os.path.join(SCRATCH, 'PARK-TEHKONTAKTY-PROVERENO-3S.csv')
OTVAL = os.path.join(SCRATCH, 'PARK-TEHKONTAKTY-NE-PROVERENO-3S.csv')
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MASHINA = re.compile(r'компрессор|воздуходув|нагнетател|ГПА\b|осушител|азотн|кислородн|воздухоразделит', re.I)
KOL = ('inn', 'predpriyatie', 'chelovek', 'dolzhnost', 'nomer', 'chem_provereno',
       'snimok', 'ssylka')

stroki = []
for s in io.open(VHOD, encoding='utf-8'):
    try:
        stroki.append(json.loads(s))
    except Exception:  # noqa: BLE001
        pass

prov, ne_prov, sch = [], [], collections.Counter()
for o in stroki:
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
    est_inn_na_str = bool(o.get('na_stranice_inn'))
    vid_t = (o.get('vidimyy_tekst') or '').upper()
    korni = [w for w in re.findall(r'[А-ЯЁA-Z]{7,}', (o.get('predpriyatie') or '').upper())]
    est_imya_na_str = bool(korni) and any(k in vid_t for k in korni[:2])
    nasha = bool(MASHINA.search(o.get('vidimyy_tekst') or '')) or \
        bool(MASHINA.search(o.get('predmet') or ''))
    if vid_n and vid_f and (est_inn_na_str or est_imya_na_str):
        prichina = ('видно на странице: фамилия, номер, предприятие'
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
            r = {'inn': o.get('inn', ''), 'predpriyatie': o.get('predpriyatie', ''),
                 'chelovek': o.get('chelovek', ''), 'dolzhnost': o.get('dolzhnost', ''),
                 'nomer': o.get('nomer', ''), 'chem_provereno': prichina,
                 'snimok': o.get('snimok', ''), 'ssylka': o.get('ssylka', '')}
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

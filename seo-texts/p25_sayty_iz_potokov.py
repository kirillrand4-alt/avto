# -*- coding: utf-8 -*-
"""Домены предприятий, уже лежащие в моих собственных потоках. Ни одного нового запроса.

ЗАМЕР, КОТОРЫЙ ЭТО ЗАКАЗАЛ. Отдача именного канала по отрезкам мест:

    места      предприятий  сайт известен  подтверждено  запросов на подтверждённого
    21-50          29             6              2              72,5
    51-80          30             9              3              50,0
    81-110         30            21              7              21,4
    111-150        40             6              5              40,0
    151-200        50             1              1             250,0

Связь не с местом (то есть не с размером предприятия), а с колонкой «сайт известен».
Отрезок 81-110 знает 21 домен и платит 21 запрос за подтверждённого; отрезок 151-200 знает
ОДИН домен и платит 250. Разница десятикратная, и объясняет её не бедность выдачи, а то, что
заслону нечем сравнивать: без домена срабатывают только карточка закупки и раскрытие.

ОТСЮДА ДЕЙСТВИЕ. Гнать канал дальше по списку — платить 250 запросов за человека. Дешевле
добыть домены. Один их источник уже есть у 2-й сессии, второй лежит у меня под ногами: в
потоках `p25-imena.jsonl` и `p25-obratnyy.jsonl` тысячи ссылок, и часть из них — сайты самих
предприятий. Их не надо искать, надо узнать.

КАК ОТЛИЧИТЬ СВОЙ САЙТ ОТ ЧУЖОГО БЕЗ ЗАПРОСА. Ядро домена сравнивается с транслитерацией
имени предприятия, и площадки с агрегаторами выбрасываются заранее. Признак слабее, чем ИНН
на странице, поэтому вес ставится 2, а не 3, и в файле сказано, чем именно домен признан:
чужую проверку это не заменяет, а вес 1 в приёмку и так не идёт.
"""
import collections
import csv
import json
import os
import re
import sqlite3

POTOKI = (r'C:\sender\_ops\p25-imena.jsonl', r'C:\sender\_ops\p25-obratnyy.jsonl')
BAZA = 'file:C:/seostat/data/p25.db?mode=ro'
VYHOD = r'C:\sender\_ops\3s_p25_sayty_iz_potokov.csv'

NE_SAYT = re.compile(
    r'zakupki\.gov|roseltorg|rts-tender|etp-?gpb|etpgpb|tektorg|tender\.pro|b2b-center|'
    r'sberbank-ast|fabrikant|otc\.ru|gazneftetorg|estp|torgi\.gov|rusprofile|list-org|'
    r'checko|sbis|kartoteka|audit-it|zachestnyibiznes|datanewton|kontur|b2book|rbc\.|'
    r'inndex|companium|ofcheck|credinform|globas|star-pro|seldon|synapsenet|kontragent|'
    r'hh\.ru|superjob|vk\.com|ok\.ru|t\.me|youtube|dzen|wikipedia|nalog\.ru|egrul|'
    r'gosnadzor|complan|vyborypro|elections|izbirkom|avito|2gis|zoon|yell\.ru|'
    r'gov\.ru|edu\.ru|ac\.ru|livejournal|blogspot|narod\.ru|ucoz', re.I)
TR = str.maketrans({'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
                    'ж': 'z', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
                    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
                    'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'c', 'ш': 's', 'щ': 's', 'ъ': '',
                    'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'u', 'я': 'a'})


def yadro(url):
    v = re.sub(r'^\w+://', '', (url or '').strip().lower()).split('/')[0].split('?')[0]
    ch = [c for c in v.split('.') if c and c != 'www']
    return '.'.join(ch[-2:]) if len(ch) >= 2 else (ch[0] if ch else '')


def translit(imya):
    o = re.sub(r'[^а-яёa-z0-9]', '',
               re.sub(r'\b(ООО|ОАО|ЗАО|ПАО|АО|НАО|ФГУП|ГУП|МУП|ФКП|ФГБУ|НПО|УК)\b', '',
                      imya or '', flags=re.I).lower())
    return o.translate(TR)


def ssylki(z):
    out = []
    for l in z.get('lyudi') or []:
        if l.get('ssylka'):
            out.append(l['ssylka'])
    for k in z.get('kontakty') or []:
        if k.get('ssylka'):
            out.append(k['ssylka'])
    return out


def main():
    b = sqlite3.connect(BAZA, uri=True)
    imena = {i: n for i, n in b.execute('select inn, coalesce(predpriyatie,"") from company')}
    kand = collections.defaultdict(collections.Counter)
    sch = collections.Counter()
    for put in POTOKI:
        if not os.path.exists(put):
            sch['потока нет: ' + os.path.basename(put)] += 1
            continue
        for ln in open(put, encoding='utf-8'):
            try:
                z = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            inn = z.get('inn')
            if not inn or z.get('err'):
                continue
            for u in ssylki(z):
                sch['ссылок просмотрено'] += 1
                if NE_SAYT.search(u):
                    sch['площадка, агрегатор или реестр — не сайт предприятия'] += 1
                    continue
                d = yadro(u)
                if d:
                    kand[inn][d] += 1

    # ПЕРВЫЙ ПРОХОД — кто на какой домен претендует. Второй решает, потому что решение зависит
    # от ВСЕХ претендентов сразу: домен, на который претендуют двое, не принадлежит ни одному.
    pretenzii = collections.defaultdict(set)
    vybor = {}
    for inn, dom in kand.items():
        lat = translit(imena.get(inn, ''))
        if len(lat) < 5:
            sch['имя предприятия короче пяти букв — сравнивать нечем'] += 1
            continue
        for d, n in dom.most_common():
            golo = re.sub(r'[^a-z0-9]', '', d.split('.')[0])
            if not golo:
                continue
            if lat[:8] in golo or golo[:8] in lat:
                vybor[inn] = (d, n)
                pretenzii[d].add(inn)
                break
        else:
            sch['домены есть, имя не узнаётся'] += 1

    ryady = []
    for inn, (d, n) in vybor.items():
        # ОБЩИЙ ДОМЕН НЕ ПРИНАДЛЕЖИТ НИ ОДНОМУ ИЗ ПРЕТЕНДЕНТОВ. Проверка глазами по первым
        # десяти строкам первого прогона поймала ровно это: `alabuga.ru` достался и
        # «СОЛЛЕРС АЛАБУГА», и «АЛАБУГА-ВОЛОКНО» — это домен особой экономической зоны, а
        # совпало в нём НАЗВАНИЕ МЕСТА, стоящее в обоих именах. То же правило, что уже
        # работает на телефонах: номер у нескольких предприятий — линия, а не человек.
        obshchiy = len(pretenzii[d]) > 1
        # ЧУЖАЯ СТРАНА — ЧУЖАЯ КОМПАНИЯ. `АГМК` дал `agmk.uz`: это Алмалыкский ГМК в
        # Узбекистане, а наш АГМК — Амурский. Аббревиатура совпала, предприятие другое.
        chuzhaya_strana = not re.search(r'\.(?:ru|su|рф|com|org)$', d)
        # ХОЛДИНГ ВМЕСТО ПЛОЩАДКИ. «ГАЗПРОМ БУРЕНИЕ» → `gazprom.ru`: по ТЗ страница холдинга
        # подтверждением считается, но в колонку `sayt` такой домен класть нельзя — он
        # подтвердит ЛЮБУЮ страницу газпрома для этой дочки.
        golo = re.sub(r'[^a-z0-9]', '', d.split('.')[0])
        holding = len(golo) + 3 < len(translit(imena.get(inn, '')))
        prichiny = [t for t, e in (('домен общий у %d предприятий' % len(pretenzii[d]), obshchiy),
                                   ('домен не в российской зоне', chuzhaya_strana),
                                   ('домен короче имени — похоже на холдинг', holding)) if e]
        ryady.append({
            'inn': inn, 'predpriyatie': imena.get(inn, ''), 'sayt': d,
            'priznak': ('имя предприятия узнаётся в домене ссылки моих каналов'
                        + (' | ' + ' | '.join(prichiny) if prichiny else '')),
            'ves': 1 if prichiny else 2,
            'godnost': 'кандидат, признака мало' if prichiny else 'подтверждён',
            'vstrech': n})
        sch['ДОМЕН ПРИНЯТ' if not prichiny else 'кандидат: ' + prichiny[0]] += 1

    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, delimiter=';', fieldnames=[
            'inn', 'predpriyatie', 'sayt', 'priznak', 'ves', 'godnost', 'vstrech'])
        w.writeheader()
        w.writerows(ryady)
    for z in ryady[:10]:
        print('REC %s  %-34s %s' % (z['inn'], z['predpriyatie'][:34], z['sayt']))
    print('ИТОГ ' + json.dumps({'файл': VYHOD, 'доменов': len(ryady),
                                'счёт': dict(sch.most_common())}, ensure_ascii=False))


if __name__ == '__main__':
    main()

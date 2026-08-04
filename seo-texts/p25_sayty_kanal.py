# -*- coding: utf-8 -*-
"""Найти официальный сайт предприятия P25. Это узкое место всей задачи, а не отдельный пункт.

ЗАМЕР, КОТОРЫЙ ЭТО ДОКАЗЫВАЕТ. Строгая приёмка P25 засчитывает человека, если страница — сайт
предприятия, страница про него на сайте холдинга, карточка закупки или документ раскрытия. Из
261 человека, найденного моим именным каналом, прошло 3. Я думала, дело в качестве выдачи.
Перепись `p25.db` показала другое: колонка `company.sayt` **пуста у всех 491 предприятия**
(как и `pochta`, и оба телефонных поля). Значит первый и самый сильный путь подтверждения —
«хост страницы совпадает с сайтом предприятия» — не мог сработать НИ РАЗУ ни у кого. Низкая
доля подтверждений была свойством входа.

Даром домены не достаются: из почты — ноль (корпоративной почты в базе нет), из ссылок уже
добытых контактов — 6, потому что 2 550 из 2 568 ссылок ведут на закупочные площадки. Остаётся
поиск, и он окупается: один запрос на предприятие открывает подтверждение для ВСЕХ его людей и
для всех трёх сессий сразу, а также включает приём `site:<домен> главный инженер`, который
сейчас невозможен.

КАК ОТЛИЧИТЬ САЙТ ПРЕДПРИЯТИЯ ОТ АГРЕГАТОРА — три признака, и каждый записывается:
  * ИНН предприятия стоит в тексте страницы. Это решающий признак: свой ИНН публикует в
    подвале почти каждый корпоративный сайт, а агрегатор публикует ЧУЖОЙ ИНН — поэтому
    одного ИНН мало, он засчитывается только вместе с непринадлежностью домена к списку
    агрегаторов и площадок;
  * имя предприятия узнаётся в самом домене после транслитерации («КУМЗ» → kumz.ru);
  * домен повторяется в выдаче по нескольким запросам.
Ни один признак в одиночку не принимается молча: в файл едет и домен, и КАКОЙ признак сработал.
Пустое поле лучше выдуманного: не сошлось — пишем «сайт не определён» и причину.
"""
import collections
import csv
import importlib.util
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

BAZA = 'file:C:/seostat/data/p25.db?mode=ro'
POTOK = r'C:\sender\_ops\p25-sayty.jsonl'
VYHOD = r'C:\sender\_ops\3s_p25_sayty_iz_poiska.csv'
KANDIDATY = (r'C:\sender\_ops\3s_lpr_obratnyy.py', r'C:\sender\_ops\_3s_lpr_obratnyy.py')

NE_SAYT = re.compile(
    r'zakupki\.gov|roseltorg|rts-tender|etp-?gpb|etpgpb|tektorg|tender\.pro|b2b-center|'
    r'sberbank-ast|fabrikant|otc\.ru|gazneftetorg|estp|torgi\.gov|rusprofile|list-org|'
    r'checko|sbis|kartoteka|audit-it|zachestnyibiznes|datanewton|kontur|b2book|rbc\.|'
    r'inndex|companies|hh\.ru|superjob|vk\.com|ok\.ru|t\.me|youtube|dzen|wikipedia|'
    r'seldon|synapsenet|kontragent|gosnadzor|complan|vyborypro|avito|drom|farpost|'
    r'yell\.ru|2gis|zoon|orgpage|spravka|catalog|prom\.ua|tiu\.ru|blizko|flamp', re.I)

TR = str.maketrans({'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
                    'ж': 'z', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
                    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
                    'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'c', 'ш': 's', 'щ': 's', 'ъ': '',
                    'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'u', 'я': 'a'})


def _serp():
    """Готовый двухдвижковый поиск с ретраями. Имя файла на сервере не угадываем: пробуем
    оба написания и говорим вслух, какое нашлось."""
    for put in KANDIDATY:
        if os.path.exists(put):
            spec = importlib.util.spec_from_file_location('lpr_obr', put)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            print('поиск взят из ' + put, file=sys.stderr)
            return m.serp
    raise SystemExit('не найден модуль поиска: ни один из ' + ', '.join(KANDIDATY))


def korotkoe(imya):
    v = re.sub(r'^\s*(ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ|'
               r'(?:ПУБЛИЧНОЕ |ОТКРЫТОЕ |ЗАКРЫТОЕ |НЕПУБЛИЧНОЕ )?АКЦИОНЕРНОЕ ОБЩЕСТВО|'
               r'ООО|ОАО|ЗАО|ПАО|АО|НАО|ФГУП|ГУП|МУП|ФКП|ФГБУ|ИП)\s+', '',
               (imya or '').strip(), flags=re.I)
    v = re.sub(r'["«»]', ' ', v)
    return re.sub(r'\s+', ' ', v).strip()


def yadro(url):
    v = re.sub(r'^\w+://', '', (url or '').strip().lower()).split('/')[0].split('?')[0]
    ch = [c for c in v.split('.') if c and c != 'www']
    return '.'.join(ch[-2:]) if len(ch) >= 2 else (ch[0] if ch else '')


def translit(imya):
    return re.sub(r'[^а-яёa-z0-9]', '', korotkoe(imya).lower()).translate(TR)


def razobrat(docs, inn, predpr):
    """Кандидаты в сайты с названным признаком. Возвращает список (домен, признак, вес)."""
    lat = translit(predpr)
    vstrech = collections.Counter()
    inn_na = set()
    imya_na = set()
    for d in docs:
        url = (d.get('url') or '').strip()
        dom = yadro(url)
        if not dom or NE_SAYT.search(url):
            continue
        tekst = ' '.join(v for k, v in d.items() if k != 'url' and isinstance(v, str))
        vstrech[dom] += 1
        if inn and re.search(r'(?<!\d)' + re.escape(inn) + r'(?!\d)', tekst):
            inn_na.add(dom)
        golo = re.sub(r'[^a-z0-9]', '', dom.split('.')[0])
        if len(lat) >= 4 and golo and (lat[:8] in golo or golo[:8] in lat):
            imya_na.add(dom)
    out = []
    for dom, n in vstrech.most_common():
        priznaki = []
        ves = 0
        if dom in inn_na:
            priznaki.append('ИНН предприятия в тексте страницы')
            ves += 3
        if dom in imya_na:
            priznaki.append('имя предприятия узнаётся в домене')
            ves += 2
        if n > 1:
            priznaki.append('домен встретился в выдаче %d раза' % n)
            ves += 1
        if priznaki:
            out.append((dom, ' + '.join(priznaki), ves))
    out.sort(key=lambda x: -x[2])
    return out


def main():
    import sqlite3
    serp = _serp()
    lim = int(sys.argv[sys.argv.index('--lim') + 1]) if '--lim' in sys.argv else 10 ** 9
    pot = int(sys.argv[sys.argv.index('--potokov') + 1]) if '--potokov' in sys.argv else 6
    b = sqlite3.connect(BAZA, uri=True)
    spisok = [{'inn': i, 'predpriyatie': p, 'region': r} for i, p, r in b.execute(
        'select inn, coalesce(predpriyatie,""), coalesce(region,"") from company '
        'order by mesto_po_summe')]
    gotovo, sboev = set(), 0
    if os.path.exists(POTOK):
        for ln in open(POTOK, encoding='utf-8'):
            try:
                z = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            # Запись со сбоем пройденной не считается — иначе отказ прибора навсегда
            # закрепится как «сайта нет».
            if z.get('err'):
                sboev += 1
                continue
            gotovo.add(z['inn'])
    zad = [c for c in spisok if c['inn'] not in gotovo][:lim]
    print('предприятий %d, уже спрошено %d, к обходу %d, в потоке сбоев %d'
          % (len(spisok), len(gotovo), len(zad), sboev), file=sys.stderr, flush=True)

    f = open(POTOK, 'a', encoding='utf-8')
    lock = threading.Lock()
    sch = collections.Counter()

    def odin(c):
        imya = korotkoe(c['predpriyatie'])
        ch = imya.split()
        if len(ch) > 4:
            imya = ' '.join(ch[:4])
        q = '"%s" официальный сайт %s' % (imya, c['region'].split(',')[0][:24])
        docs, err = serp(q)
        kand = [] if err else razobrat(docs, c['inn'], c['predpriyatie'])
        return {**c, 'zapros': q, 'err': err, 'stranic': len(docs), 'kandidaty': kand}

    with ThreadPoolExecutor(max_workers=pot) as ex:
        for r in ex.map(odin, zad):
            with lock:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
                if r['err']:
                    sch['сбой: ' + str(r['err'])[:50]] += 1
                elif r['kandidaty']:
                    top = r['kandidaty'][0]
                    sch['САЙТ НАЙДЕН, вес %d' % top[2]] += 1
                else:
                    sch['кандидатов нет: в выдаче только агрегаторы и площадки'] += 1
    f.close()
    svesti()
    for k, v in sch.most_common():
        print('REC %s\t%d' % (k, v))
    print('ИТОГ ' + json.dumps({'спрошено_в_этот_раз': len(zad)}, ensure_ascii=False))


def svesti():
    """Из потока — CSV с одним сайтом на предприятие и названным признаком."""
    ryady, sch = [], collections.Counter()
    if not os.path.exists(POTOK):
        return
    vidno = {}
    for ln in open(POTOK, encoding='utf-8'):
        try:
            z = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        if z.get('err') or not z.get('kandidaty'):
            continue
        vidno[z['inn']] = z
    for inn, z in vidno.items():
        dom, priznak, ves = z['kandidaty'][0]
        # Вес 1 — это только «домен встретился дважды», ни ИНН, ни имени. Такой сайт
        # называется кандидатом и в приёмку не идёт: подтверждать им — значит подтверждать
        # совпадением, а не признаком.
        ryady.append({'inn': inn, 'predpriyatie': z['predpriyatie'], 'sayt': dom,
                      'priznak': priznak, 'ves': ves,
                      'godnost': 'подтверждён' if ves >= 2 else 'кандидат, признака мало',
                      'zapros': z['zapros'],
                      'drugie': ' | '.join('%s (%s)' % (d, p) for d, p, _ in z['kandidaty'][1:4])})
        sch['подтверждён' if ves >= 2 else 'кандидат'] += 1
    ryady.sort(key=lambda x: -x['ves'])
    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, delimiter=';', fieldnames=[
            'inn', 'predpriyatie', 'sayt', 'priznak', 'ves', 'godnost', 'zapros', 'drugie'])
        w.writeheader()
        w.writerows(ryady)
    for z in ryady[:6]:
        print('REC ' + json.dumps({k: z[k] for k in ('inn', 'predpriyatie', 'sayt', 'priznak')},
                                  ensure_ascii=False))
    print('REC файл %s: строк %d, %s' % (VYHOD, len(ryady), dict(sch)))


if __name__ == '__main__':
    if '--svesti' in sys.argv:
        svesti()
    else:
        main()

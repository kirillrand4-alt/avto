# -*- coding: utf-8 -*-
"""Полное ФИО по фамилии, снятой с именной почты предприятия.

ОТКУДА ФАМИЛИИ. Не из головы: они стоят в самих почтах, которые предприятие публикует на
своём сайте и в карточке чеко. `louzgin@peko-msk.ru` рядом с подписью «Служба технического
директора» — это фамилия технического директора, а не догадка.

ЗАСЛОН. Имя засчитывается, только если найдено ОТЧЕСТВО или инициалы РЯДОМ с фамилией
(±120 знаков) и в том же тексте есть название предприятия. Иначе — однофамилец из другого
города, а такую находку выдавать за контакт нельзя.
"""
import json, os, re, urllib.parse, urllib.request

USER = os.environ.get('XMLRIVER_USER', '')
KEY = os.environ.get('XMLRIVER_KEY', '')
CELI = [
    ('Хлебокомбинат ПЕКО', 'Лузгин', ['"Лузгин" "Хлебокомбинат ПЕКО"',
                                      'Лузгин технический директор Хлебокомбинат ПЕКО Москва',
                                      '"Лузгин" ПЕКО хлебокомбинат Полярная']),
    ('Хлебокомбинат ПЕКО', 'Скворцов', ['"Скворцов" "Хлебокомбинат ПЕКО"',
                                        'Скворцов ПЕКО хлебокомбинат Москва']),
    ('Брянский молочный комбинат', 'Кудрявцев', ['"Кудрявцев" "Брянский молочный комбинат"',
                                                 'Кудрявцев БМК Брянск молочный комбинат']),
    ('МАЯК Хлеб-соль', 'Шафиков', ['"Шафиков" Слата Иркутск', '"Шафиков" "Хлеб-соль"']),
    ('МАЯК Хлеб-соль', 'Зудов', ['"Зудов" Слата Иркутск', '"Зудов" "Хлеб-соль"']),
    ('МАЯК Хлеб-соль', 'Колмакова', ['"Колмакова" Слата Иркутск']),
    ('Дмитровские колбасы', 'Ланин', ['"Ланин Александр Владимирович" Дмитровские колбасы',
                                      '"Дмитровские колбасы" технический директор Ланин']),
]
OTCH = re.compile(r'[А-ЯЁ][а-яё]{2,}(?:ович|евич|ьевич|овна|евна|ична|инична)\b')
INIC = re.compile(r'\b[А-ЯЁ]\.\s?[А-ЯЁ]\.')
DOLZH = re.compile(r'(техническ\w+\s+директор|главн\w+\s+инженер|директор\s+по\s+качеств|'
                   r'главн\w+\s+технолог|главн\w+\s+энергетик|главн\w+\s+механик|'
                   r'начальник\w*\s+производств|генеральн\w+\s+директор|коммерческ\w+\s+директор|'
                   r'директор\s+по\s+развити|начальник\w*\s+отдела)', re.I)


def serp(q):
    if not (USER and KEY):
        return [{'err': 'нет ключей'}]
    u = ('http://xmlriver.com/search/xml?user=%s&key=%s&query=%s&groupby=30'
         % (USER, KEY, urllib.parse.quote(q)))
    try:
        x = urllib.request.urlopen(u, timeout=45).read().decode('utf-8', 'replace')
    except Exception as e:
        return [{'err': str(e)[:80]}]
    out = []
    for m in re.finditer(r'<doc>(.*?)</doc>', x, re.S):
        d = m.group(1)
        url = (re.search(r'<url>(.*?)</url>', d, re.S) or [None, ''])[1]
        tit = re.sub(r'<[^>]+>', ' ', (re.search(r'<title>(.*?)</title>', d, re.S) or [None, ''])[1])
        pas = re.sub(r'<[^>]+>', ' ', (re.search(r'<passages>(.*?)</passages>', d, re.S) or [None, ''])[1])
        out.append({'url': url, 't': ' '.join((tit + ' ' + pas).split())})
    return out


for cel, familiya, zaprosy in CELI:
    nashli, vidal = [], set()
    for q in zaprosy:
        for d in serp(q):
            if d.get('err'):
                print(json.dumps({'ошибка': d['err']}, ensure_ascii=False), flush=True)
                break
            t = d['t']
            for m in re.finditer(re.escape(familiya) + r'\w{0,3}', t):
                okno = t[max(0, m.start() - 130):m.start() + 190]
                otch = OTCH.findall(okno)
                inic = INIC.findall(okno)
                if not (otch or inic):
                    continue
                dl = DOLZH.search(okno)
                k = (okno[:60],)
                if k in vidal:
                    continue
                vidal.add(k)
                nashli.append({'familiya': familiya, 'otchestvo_ili_inicialy': (otch or inic)[:2],
                               'dolzhnost': dl.group(1) if dl else '',
                               'ssylka': d['url'], 'citata': ' '.join(okno.split())[:220]})
    print(json.dumps({'цель': cel, 'фамилия': familiya, 'найдено': len(nashli),
                      'варианты': nashli[:6]}, ensure_ascii=False), flush=True)

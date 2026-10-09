# -*- coding: utf-8 -*-
"""fixG (локально): третий проход по сайтам кандидатов, у которых своё не доказано (только название
или ничего): sitemap.xml/robots.txt -> адреса с «политика/оферта/реквизиты/контакты/о компании/
документы/раскрытие» + угаданные пути реквизитов и политики, до 10 новых страниц на домен.
Скачиватель – тот же, что у агента D (fixD_kachat.vzyat, кэш общий). Затем снова fixD_chey_sayt.py.

    python3 fixG_sayty_dop.py <папка-страниц> <kandidaty.db> <svyazi.json> <razbor.json> <выход-chey.json> домен[,домен...]
"""
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

PAPKA, BAZA, SVYAZI, RAZBOR, VYHOD, DOMENY = sys.argv[1:7]
ZDES = os.path.dirname(os.path.abspath(__file__))
sys.argv = [os.path.join(ZDES, 'fixD_kachat.py'), BAZA, PAPKA]
sys.path.insert(0, ZDES)
import fixD_kachat as K  # noqa: E402
import requests  # noqa: E402

NUZHNO = re.compile(r'polit|privacy|policy|konfid|oferta|offer|rekviz|requisit|kontakt|contact|about|o-kompan|o-nas|'
                    r'company|dokument|document|raskryt|disclos|personal|soglas|agreement|terms|legal|info', re.I)
UGADAT = ('rekvizity/', 'requisites/', 'contacts/', 'kontakty/', 'about/', 'o-kompanii/', 'policy/', 'privacy/',
          'politika-konfidencialnosti/', 'privacy-policy/', 'politika/', 'oferta/', 'company/', 'o-nas/',
          'rekvizity', 'contacts', 'kontakty', 'policy', 'privacy', 'politika-konfidentsialnosti/', 'personal-data/')


def rab(d):
    ses = requests.Session()
    ses.headers.update({'User-Agent': K.UA, 'Accept-Language': 'ru-RU,ru;q=0.9'})
    est = {u for u in K.indeks if K.domen(u) == d}
    ok = [u for u in est if (K.indeks.get(u) or {}).get('kod') == 200]
    baza = None
    for u in ok:
        z = K.indeks[u]
        it = z.get('itog') or u
        baza = baza or ('%s://%s/' % (it.split('://')[0], it.split('://')[1].split('/')[0]))
    baza = baza or 'https://%s/' % d
    novye = []
    for put in ('sitemap.xml', 'robots.txt'):
        u = urljoin(baza, put)
        z = K.vzyat(ses, u)
        time.sleep(0.5)
        if z.get('kod') == 200:
            t = K.tekst(z)
            for m in re.finditer(r'(https?://[^\s<>"\']+)', t):
                uu = m.group(1).strip().rstrip('/') + '/'
                if K.domen(uu) == d and NUZHNO.search(uu.split(d, 1)[-1]) and not re.search(r'\.(xml|jpe?g|png|pdf|gz)/?$', uu):
                    novye.append(uu)
    novye = [u for u in dict.fromkeys(novye) if u not in est and u.rstrip('/') not in est][:6]
    ugad = [urljoin(baza, p) for p in UGADAT if urljoin(baza, p) not in est and urljoin(baza, p) not in novye]
    for u in (novye + ugad)[:12]:
        K.vzyat(ses, u)
        time.sleep(0.5)
    return d


t0 = time.time()
spisok = [x for x in DOMENY.split(',') if x]
with ThreadPoolExecutor(10) as ex:
    list(ex.map(rab, spisok))
K.sohranit_indeks()
print('третий проход: %d доменов за %d с' % (len(spisok), time.time() - t0))
r = subprocess.run([sys.executable, '-I', os.path.join(ZDES, 'fixD_chey_sayt.py'), BAZA, PAPKA, SVYAZI, RAZBOR, VYHOD],
                   capture_output=True, text=True)
print(r.stdout[-2000:], r.stderr[-2000:])

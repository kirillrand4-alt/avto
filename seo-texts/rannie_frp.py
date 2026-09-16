# -*- coding: utf-8 -*-
"""Ранний источник 1: ФРП (frprf.ru) — лента выданных займов.

ЧТО ЭТО ДАЁТ. Заём ФРП это подтверждённый капекс на стадии 5 «финансирование»:
деньги на цех уже выделены, оборудование ещё не куплено. Для нас это вход
раньше закупки.

СОСТОЯНИЕ КАНАЛА (проверено 16.09.2026, коды ответов в RANNIE-ISTOCHNIKI-OPIS.md):

    из песочницы        403, тело «DDoS-Guard ... website owner has restricted
                        access from your current IP address», заголовок
                        server: ddos-guard. Это ГЕОБЛОК по стране выхода,
                        а не защита от ботов и не наш дефект
    с сервера владельца 200. Главная 207 595 знаков, /press-tsentr/novosti/
                        85 091 знак, sitemap-iblock-9.xml = 471 карточка новостей
    мобильные прокси    ВСЕ ТРИ из C:\\sender\\proxies-mobile.txt мертвы:
                        194.143.150.98:1650 -> WinError 10054 (соединение
                        закрыто удалённой стороной), 77.51.189.183:10498 и
                        bproxy.site:10917 -> то же. Прокси не понадобился:
                        сервер и так отдаёт 200

    ЯМА: постраничный список /press-tsentr/novosti/?PAGEN_1=N отдаёт 503 на
    ВСЕХ страницах (замер: 14 из 14). Ходить надо по sitemap и С ПАУЗОЙ:
    без пауз из 150 карточек открылось 31, остальные 119 закрыты частотным
    заслоном. С паузой 1,5 с канал держится.

ЗАПУСК (только с сервера владельца, из песочницы будет 403):

    python3 seo-texts/zapusk_na_servere.py seo-texts/rannie_frp.py 70 1.5

Аргументы: сколько карточек взять и пауза в секундах. Результат кладётся в
C:\\sender\\_ops\\3s_frp_lenta.csv.

ЧЕГО В ИСТОЧНИКЕ НЕТ: ИНН. В карточке стоят название («ООО «Балткат»»), дата,
сумма займа и регион. ИНН добывается вторым шагом через dadata по названию
(готовый приём — seo-texts/pishchevka_dadata.py), и это отдельная работа.
"""
import csv
import os
import re
import sys
import time
import urllib.error
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
SITEMAP = 'https://frprf.ru/sitemap-iblock-9.xml'
VYHOD = r'C:\sender\_ops\3s_frp_lenta.csv'

KOMPANIYA = re.compile(r'(?:ООО|АО|ПАО|ЗАО|ОАО|НПО|НПП|ГК|АПХ)\s*[«"]([^»"]{2,60})[»"]')
SUMMA = re.compile(r'(\d[\d\s.,]{0,12})\s*(млн|млрд)\s*(?:руб|рублей)')
DATA = re.compile(r'(\d{1,2}\s+(?:январ|феврал|март|апрел|ма[йя]|июн|июл|август|'
                  r'сентябр|октябр|ноябр|декабр)\w*\s+20\d\d)')
# контроль: заведомо негодный вход — в живой выгрузке обязан дать 0
KONTROL = 'щварцкопфер'


def vzyat(url, timeout=45):
    """Код ответа и тело. Код возврата — это ОТВЕТ: 403 и 503 значат, что хост достигнут."""
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ru-RU,ru;q=0.9'})
        with urllib.request.urlopen(req, timeout=timeout) as f:
            return f.status, f.read(3000000)
    except urllib.error.HTTPError as e:
        return e.code, (e.read(1500) if e.fp else b'')
    except Exception as e:  # noqa: BLE001
        return 0, ('%s: %s' % (type(e).__name__, e)).encode()


def raskodirovat(b):
    t = b.decode('utf-8', 'replace')
    return b.decode('cp1251', 'replace') if t.count('\ufffd') > 300 else t


def spisok_kartochek():
    """Адреса новостей из sitemap, свежие первыми (по lastmod, если он есть)."""
    kod, telo = vzyat(SITEMAP, timeout=60)
    if kod != 200:
        return kod, []
    xml = raskodirovat(telo)
    pary = []
    for zapis in re.findall(r'<url>(.*?)</url>', xml, re.S):
        u = re.search(r'<loc>([^<]+)</loc>', zapis)
        lm = re.search(r'<lastmod>([^<]*)</lastmod>', zapis)
        if u and '/novosti/' in u.group(1) and u.group(1).rstrip('/').count('/') > 4:
            pary.append((u.group(1), lm.group(1) if lm else ''))
    pary.sort(key=lambda p: p[1], reverse=True)
    return kod, pary


def razobrat(url, lastmod, telo):
    html = re.sub(r'<script.*?</script>', '', raskodirovat(telo), flags=re.S)
    ploskiy = ' '.join(re.sub(r'<[^>]+>', ' ', html).split())
    zg = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
    zagolovok = ' '.join(re.sub(r'<[^>]+>', '', zg.group(1)).split()) if zg else ''
    nachalo = ploskiy.find(zagolovok) if zagolovok else 0
    telo_stati = ploskiy[max(nachalo, 0):max(nachalo, 0) + 3000]
    d = DATA.search(ploskiy)
    s = SUMMA.search(telo_stati)
    return {'url': url, 'lastmod': lastmod,
            'data': d.group(1) if d else '',
            'zagolovok': zagolovok[:200],
            'kompanii': ' | '.join(dict.fromkeys(KOMPANIYA.findall(telo_stati)))[:220],
            'summa': s.group(0) if s else ''}


def main():
    skolko = int(sys.argv[1]) if len(sys.argv) > 1 else 70
    pauza = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5

    kod, pary = spisok_kartochek()
    print('sitemap: код=%s карточек=%d' % (kod, len(pary)))
    if not pary:
        print('НОЛЬ КАРТОЧЕК. Это либо геоблок (из песочницы будет 403), либо смена адреса.')
        return 1

    stroki, kody = [], {}
    for url, lastmod in pary[:skolko]:
        k, b = vzyat(url, timeout=35)
        kody[k] = kody.get(k, 0) + 1
        time.sleep(pauza)
        if k == 200:
            stroki.append(razobrat(url, lastmod, b))
    print('коды карточек:', kody)

    s_datoy = sum(1 for r in stroki if r['data'])
    s_imenem = sum(1 for r in stroki if r['kompanii'])
    s_summoy = sum(1 for r in stroki if r['summa'])
    print('ИТОГ: карточек=%d | с датой=%d | с названием=%d | с суммой=%d'
          % (len(stroki), s_datoy, s_imenem, s_summoy))
    # контроль с заведомо негодным входом: обязан дать 0
    print('КОНТРОЛЬ «%s» в выгрузке: %d (обязан быть 0)' % (
        KONTROL, sum(1 for r in stroki if KONTROL in (r['zagolovok'] + r['kompanii']).lower())))

    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, delimiter=';',
                           fieldnames=['url', 'lastmod', 'data', 'zagolovok', 'kompanii', 'summa'])
        w.writeheader()
        for r in stroki:
            w.writerow(r)
    print('записано:', VYHOD, os.path.getsize(VYHOD))
    for r in stroki[:12]:
        print('  *', r['data'], '|', r['zagolovok'][:78], '|', r['kompanii'][:42], '|', r['summa'])
    return 0


if __name__ == '__main__':
    sys.exit(main())

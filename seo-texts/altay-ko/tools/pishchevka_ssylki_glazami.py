# -*- coding: utf-8 -*-
"""Проверка ВСЕХ 27 ссылок-доказательств: открывается ли, и стоит ли на странице искомое.

Правило владельца: «в конце глазами проверить, куда ведёт хотя бы 25 случайных ссылок».
Их ровно 27, поэтому проверяю все — случайная выборка тут не нужна.

Проверка двойная, иначе она ничего не стоит:
  1) страница ОТКРЫЛАСЬ (HTTP-код; код ошибки — это ответ, а не отсутствие связи);
  2) на странице СТОИТ то, чем я её подписала (ИНН, фамилия, номер или ключевое слово).
Второе важнее первого: открывшаяся страница, где искомого нет, — это ссылка «в никуда»,
и раньше такие у меня проходили за доказательство.
"""
import io
import re
import ssl
import sys
import urllib.request

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')

# что должно стоять на странице, чтобы ссылка считалась доказывающей
CHTO = {
    'bmk-milk.com/contacts': ['52-49-11', '8-800-100-73-77'],
    'bmk-milk.com/company/vacancy': ['52-42-10', 'Главный технолог'],
    'milgrad.ru/contacts': ['52-85-55', 'bmk32.ru'],
    'peko-msk.com/contacts': ['473-97-30', 'louzgin', '7725702610', 'Пахарев'],
    'rarus.ru/1c-corp': ['Пахарев', 'Королева'],
    'zaprodukt.ru/quality': ['Андреева'],
    'zaprodukt.ru/contacts': ['783 7131', '722 1780'],
    'zaprodukt.ru/vacancies': ['Малькова', '996-66-10'],
    'zaprodukt.ru/': ['Дмитровские колбасы'],
    'trudvsem.ru/vacancy/card/1025001097681/a829cb58': ['Малькова', 'олодильн'],
    'trudvsem.ru/vacancy/card/1025001097681/cf0e136b': ['Боромыкина'],
    'trudvsem.ru/vacancy/card/1083811008160/509464f8': ['Ракина'],
    'trudvsem.ru/vacancy/card/1083811008160/60a5bf58': ['Ракина'],
    'opendata.trudvsem.ru': ['Ракина', 'slata.com'],
    'checko.ru/company/bmk': ['Рябцев', '3232000207'],
    'checko.ru/company/dmitrovskie': ['Ланин', '5007030589'],
    'rusprofile.ru/id/4134053': ['3232000207'],
    'rusprofile.ru/id/3566459': ['7725702610'],
    'rusprofile.ru/id/421920': ['5007030589'],
    'rusprofile.ru/id/696022': ['3811125221'],
    'sbis.ru/contragents/5007100162': ['5007100162'],
    'companies.rbc.ru': ['3811125221', 'Икс 5'],
    'monitor-pb.ru/customer/3232000207': ['ДКВР', 'БМК'],
    'monitor-pb.ru/customer/7725702610': ['ПЕКО'],
    'eposlink.com': ['Щеглов'],
    'ok.ru/group/53447261946008': ['Шарунина'],
    'inndex.ru': ['Климов'],
}

ssylki = [s.strip() for s in io.open(sys.argv[1], encoding='utf-8') if s.strip()]
print('ссылок к проверке: %d\n' % len(ssylki))
otkrylos = dokazyvaet = ne_otkrylos = pusto = 0
for u in ssylki:
    klyuch = next((k for k in CHTO if k in u), None)
    nado = CHTO.get(klyuch, [])
    try:
        h = net.open(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=45)
        kod, raw = h.getcode(), h.read(3000000)
    except urllib.error.HTTPError as e:
        print('  %-3s %s\n        ХОСТ ОТВЕТИЛ КОДОМ, страницы нет' % (e.code, u[:100]))
        ne_otkrylos += 1
        continue
    except Exception as e:  # noqa: BLE001
        print('  --  %s\n        СВЯЗИ НЕТ: %s' % (u[:100], str(e)[:70]))
        ne_otkrylos += 1
        continue
    otkrylos += 1
    txt = ''
    for k in ('utf-8', 'cp1251'):
        try:
            probe = raw.decode(k)
        except Exception:  # noqa: BLE001
            continue
        if len(re.findall(r'[а-яё]', probe, re.I)) > len(re.findall(r'[а-яё]', txt, re.I)):
            txt = probe
    txt = txt or raw.decode('utf-8', 'replace')
    plain = re.sub(r'<[^>]+>', ' ', txt)
    est = [s for s in nado if s.lower() in plain.lower()]
    net_ = [s for s in nado if s not in est]
    if not nado:
        print('  %-3s %s\n        подпись не задана — проверить нечем' % (kod, u[:100]))
        pusto += 1
    elif est:
        dokazyvaet += 1
        print('  %-3s %s\n        ДОКАЗЫВАЕТ: нашлось %s%s'
              % (kod, u[:100], ', '.join(est[:4]),
                 ('; НЕ нашлось: ' + ', '.join(net_[:3])) if net_ else ''))
    else:
        pusto += 1
        print('  %-3s %s\n        ОТКРЫЛАСЬ, НО ИСКОМОГО НЕТ (ждала: %s), знаков %d'
              % (kod, u[:100], ', '.join(nado[:3]), len(plain)))

print('\n########## ЧИСЛА')
print('  ссылок проверено ............ %d' % len(ssylki))
print('  открылось ................... %d' % otkrylos)
print('  из них ДОКАЗЫВАЮТ ........... %d' % dokazyvaet)
print('  открылись, искомого нет ..... %d' % pusto)
print('  не открылись вовсе .......... %d' % ne_otkrylos)

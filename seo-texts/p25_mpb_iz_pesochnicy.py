# -*- coding: utf-8 -*-
"""1-я сессия (запись 136): monitor-pb с сервера не отдаёт страницы вовсе, НО ИЗ ПЕСОЧНИЦЫ
открывается обычным HTTP-клиентом — так они собрали 2 139 карточек ЭПБ.

Проверяю это утверждение своим прибором ИЗ ПЕСОЧНИЦЫ. Если открывается — мой вывод «813
фактов недоказуемы» был неверен по формулировке: они недоказуемы С СЕРВЕРА, а не вообще, и
проверять ЭПБ надо отсюда.

Контроль обязателен и здесь: рядом идёт заведомо живой хост. Если не откроется НИЧЕГО —
беда в песочнице, и про monitor-pb вывода делать нельзя.
"""
import ssl, urllib.request
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
# КОНТРОЛЬ ВЫБРАН НЕВЕРНО В ПЕРВЫЙ РАЗ. Я поставила контролем zakupki.gov.ru — а он из
# песочницы НЕ читается по давно известной причине (Connection reset), это записано у меня
# же в правилах тика. Контроль обязан быть заведомо живым ИМЕННО ЗДЕСЬ, иначе он объявляет
# сломанной песочницу вместо проверяемого хоста. Беру дроп владельца и checko.ru.
CELI = [('monitor-pb, заключение 1', 'https://monitor-pb.ru/conclusion/54-%D0%A2%D0%A3-06283-2023'),
        ('monitor-pb, заключение 2', 'https://monitor-pb.ru/conclusion/42-%D0%A2%D0%A3-896427-2026'),
        ('monitor-pb, корень', 'https://monitor-pb.ru/'),
        ('КОНТРОЛЬ: checko.ru', 'https://checko.ru/'),
        ('КОНТРОЛЬ: дроп владельца', 'https://parsercompressor.online/')]
zhiv = {}
for imya, u in CELI:
    try:
        r = op.open(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=60)
        d = r.read()
        print('  %-26s HTTP %s, байт %7d' % (imya, r.getcode(), len(d)))
        zhiv[imya] = len(d)
    except urllib.error.HTTPError as e:
        # ОТВЕТ С КОДОМ ОШИБКИ — ЭТО ОТВЕТ. 401 и 429 означают, что хост ДОСТИГНУТ и даже
        # разговаривает; связи они не опровергают. Мой первый вывод объявил песочницу
        # неработающей именно потому, что считал 401/429 недостижимостью — и заодно едва не
        # похоронил верный результат по monitor-pb. Третий раз этот класс: страница ошибки
        # Chrome в 210 знаков, «текст получен» по длине, теперь HTTP-код. Правило: НЕДОСТУПЕН
        # только тот, кто не ответил ВОВСЕ.
        print('  %-26s ХОСТ ОТВЕТИЛ КОДОМ %s (связь есть)' % (imya, e.code))
        zhiv[imya] = -1
    except Exception as e:  # noqa: BLE001
        print('  %-26s СВЯЗИ НЕТ: %s' % (imya, str(e)[:60]))
        zhiv[imya] = 0
mp = [v for k, v in zhiv.items() if k.startswith('monitor-pb')]
print('\n########## ЧИСЛА')
kontroli = [v for k, v in zhiv.items() if k.startswith('КОНТРОЛЬ')]
dostignut = [v for v in kontroli if v != 0]   # ответ любым кодом = связь есть
print('  адресов monitor-pb открылось из песочницы  %d из 3' % len([v for v in mp if v > 500]))
print('  контрольных живых хостов открылось         %d из %d'
      % (len([v for v in kontroli if v > 500]), len(kontroli)))
print('  ВЫВОД: %s'
      % ('песочница тянет — и заключения monitor-pb ЧИТАЮТСЯ отсюда'
         if len([v for v in mp if v > 500]) >= 2 and dostignut else
         'песочница тянет, но заключения monitor-pb отсюда НЕ читаются'
         if dostignut else
         'ни один контроль не ответил — вывода делать нельзя'))
print('  контрольных хостов ДОСТИГНУТО (любой код)  %d из %d' % (len(dostignut), len(kontroli)))

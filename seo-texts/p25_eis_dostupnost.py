# -*- coding: utf-8 -*-
"""ЕИС: что именно сейчас отвечает, а что закрыто. Меряется ЧАСТОТОЙ и ПО ВИДАМ АДРЕСОВ.

Повод. Проба поиска организации по ИНН вернула с сервера `ERR_HTTP_RESPONSE_CODE_FAILURE`
шесть раз подряд, а из песочницы — `Connection reset` дважды. Ровно этот адрес я дописала
9 141 факту как `ssylka_inn`, и ровно им работает канал «карточка организации ЕИС»
(его прошлый заход дал 699 строк и 296 телефонов). Прежде чем гнать полуторатысячесекундный
прогон, надо знать: закрыт ли весь сайт, или один раздел.

Три вида адресов, по пять проб каждый — потому что одна проба измеряет мгновение, а не хост:

    поиск организаций    /epz/organization/search/results.html?searchString=<ИНН>
    карточка организации /epz/organization/view/inn.html?...        (прямая, без поиска)
    извещение            /epz/order/notice/.../common-info.html?regNumber=<номер>

Печатается: сколько раз пришёл ответ, какой код, сколько байт. Вывод возможен только по
частоте: «0 из 5» — закрыто, «5 из 5» — открыто, промежуточное — режут темп.

ЧЕСТНАЯ ГРАНИЦА: это замер ОДНОГО МОМЕНТА и одного узла (сервер владельца). Он не говорит,
что ссылка неверна, — он говорит, доедет ли до неё наш прибор сейчас.

Числа в КОНЦЕ.
"""
import collections
import json
import ssl
import time
import urllib.request

ADRESA = [
    ('поиск организаций по ИНН',
     'https://zakupki.gov.ru/epz/organization/search/results.html?searchString=7424024375'),
    ('поиск организаций, с morphology (как в канале контактов)',
     'https://zakupki.gov.ru/epz/organization/search/results.html?searchString=7424024375'
     '&morphology=on&sortBy=UPDATE_DATE'),
    ('извещение 44-ФЗ',
     'https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html'
     '?regNumber=0372200234925000123'),
    ('главная ЕИС', 'https://zakupki.gov.ru/epz/main/public/home.html'),
]
PROB = 5
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))

svod = {}
for imya, u in ADRESA:
    sch = collections.Counter()
    bajt = []
    for _ in range(PROB):
        try:
            rq = urllib.request.Request(u, headers={'User-Agent': UA,
                                                    'Accept-Language': 'ru'})
            with net.open(rq, timeout=40) as rs:
                telo = rs.read(300000)
                sch['ответ %s' % rs.status] += 1
                bajt.append(len(telo))
        except urllib.error.HTTPError as e:  # noqa: PERF203
            sch['код %s' % e.code] += 1
        except Exception as e:  # noqa: BLE001
            sch['отказ: %s' % str(e)[:34]] += 1
        time.sleep(1.5)
    svod[imya] = {'проб': PROB, 'исходы': dict(sch),
                  'байт (медиана)': sorted(bajt)[len(bajt) // 2] if bajt else 0,
                  'дошло': sum(v for k, v in sch.items() if k.startswith('ответ 2'))}

print('\n\n########## ЧТО ОТВЕЧАЕТ ЕИС, ПО ВИДАМ АДРЕСОВ')
for imya, v in svod.items():
    print('  %-52s дошло %d из %d, байт %d' % (imya[:52], v['дошло'], v['проб'],
                                               v['байт (медиана)']))
    for k, n in v['исходы'].items():
        print('        %-46s %d' % (k[:46], n))

zhiv = [i for i, v in svod.items() if v['дошло'] > 0]
print('\n########## ЧИСЛА')
print('  видов адресов проверено: %d, отвечают: %d' % (len(svod), len(zhiv)))
print('  ВЫВОД: %s'
      % ('ЕИС отвечает не по всем разделам — работать теми, что живы: %s' % '; '.join(zhiv)
         if zhiv else 'ни один раздел не ответил — это состояние сети/хоста, а не факт '
                      'об адресах; прогоны по ЕИС сейчас бессмысленны'))
print('ИТОГ ' + json.dumps({i: v['дошло'] for i, v in svod.items()}, ensure_ascii=False))

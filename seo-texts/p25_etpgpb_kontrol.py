# -*- coding: utf-8 -*-
"""КОНТРОЛЬ ПРОБИТ, и это опровергает мой вчерашний вывод. Жребий 338396 подсунул
отрицательный контроль `etpgpb.ru/procedures/?search=щварцкопфер` — и он ДОКАЗАЛ машину.
То есть страница ЭТП ГПБ показывает компрессорные процедуры на ЛЮБОЙ запрос, а моя проверка
«слово машины на странице» проходит на ней даром.

Это бьёт прямо по вчерашнему успокоению: 4 351 факт держится ТОЛЬКО на ссылках вида
`etpgpb.ru/procedures/?search=<код>`, и я записала их в «адресные запросы, всё в порядке».

Проверяю три вещи разом, чтобы не гадать:
   1. настоящий код процедуры — что на странице;
   2. выдуманное слово — что на странице;
   3. РАЗНЫЕ ли это страницы (сравниваю длину и наличие самого кода в тексте).

Если страница для выдуманного слова совпадает с настоящей — поиск запрос не читает, и
ссылка вида `?search=` НЕ доказывает ничего, кроме того, что на ЭТП ГПБ есть компрессоры.
"""
import json, sys
sys.path.insert(0, '/home/user/avto/seo-texts/server')
import run_on_server as R
CELI = [('настоящий код ГП131308', 'ГП131308',
         'https://etpgpb.ru/procedures/?search=%D0%93%D0%9F131308'),
        ('настоящий код ГП415801', 'ГП415801',
         'https://etpgpb.ru/procedures/?search=%D0%93%D0%9F415801'),
        ('ВЫДУМАННОЕ слово', 'щварцкопфер',
         'https://etpgpb.ru/procedures/?search=щварцкопфер'),
        ('ВЫДУМАННЫЙ код ГП999999', 'ГП999999',
         'https://etpgpb.ru/procedures/?search=%D0%93%D0%9F999999')]
rez = []
for imya, kod, u in CELI:
    try:
        r = R.submit('browser_probe',
                     {'url': u, 'proxy': False, 'ignore_https_errors': True, 'after_ms': 8000,
                      'eval_js': {'return': '(() => {const t=document.body?'
                                            'document.body.innerText:"";return [t.length,'
                                            '(t.indexOf("%s")>=0?1:0),'
                                            '(/компрессор|воздуходув|нагнетател/i.test(t)?1:0),'
                                            '(/ничего не найдено|не найдено|нет резуль/i.test(t)?1:0)'
                                            '].join(";");})()' % kod}}, timeout=200)
        d = r.get('data') or {}
        ch = str(d.get('eval_js_value') or '').split(';')
        if len(ch) != 4:
            print('  %-26s ОТВЕТА НЕТ (ok=%s err=%s)' % (imya, d.get('eval_js_ok'),
                                                         str(d.get('eval_js_err'))[:40]))
            continue
        print('  %-26s знаков %-7s код на странице %-6s слово машины %-6s «не найдено» %s'
              % (imya, ch[0], ch[1] == '1', ch[2] == '1', ch[3] == '1'))
        rez.append((imya, int(ch[0]), ch[1] == '1', ch[2] == '1'))
    except Exception as e:  # noqa: BLE001
        print('  %-26s ЗАДАНИЕ УПАЛО: %s' % (imya, str(e)[:50]))
nast = [x for x in rez if x[0].startswith('настоящий')]
vyd = [x for x in rez if x[0].startswith('ВЫДУМАН')]
print('\n########## ЧИСЛА')
print('  настоящих кодов проверено %d, из них СВОЙ КОД на странице %d'
      % (len(nast), len([x for x in nast if x[2]])))
print('  выдуманных проверено %d, из них слово машины на странице %d'
      % (len(vyd), len([x for x in vyd if x[3]])))
if nast and vyd:
    print('  длины: настоящие %s, выдуманные %s'
          % ([x[1] for x in nast], [x[1] for x in vyd]))
    odinakovo = len({x[1] for x in nast} | {x[1] for x in vyd}) == 1
    print('  ВЫВОД: %s'
          % ('страницы РАЗНЫЕ и свой код виден — ссылка `?search=<код>` доказывает процедуру'
             if all(x[2] for x in nast) and not any(x[3] for x in vyd) else
             'ОДНА И ТА ЖЕ СТРАНИЦА на любой запрос — ссылка `?search=` НЕ доказательство'
             if odinakovo else
             'страницы разной длины, но слово машины есть и у выдумки — признак «слово машины» '
             'на этой площадке НЕ ГОДИТСЯ, нужен признак «свой код на странице»'))
print('ИТОГ ' + json.dumps({'настоящих со своим кодом': len([x for x in nast if x[2]]),
                            'выдуманных со словом машины': len([x for x in vyd if x[3]])},
                           ensure_ascii=False))

# -*- coding: utf-8 -*-
"""Проверяю чужую находку СВОИМ прибором — и на СВОЕЙ форме ссылки.

1-я сессия (запись 131) нашла: карточка организации 223-ФЗ вида
`view223/info.html?&inn=…&kpp=…&ogrn=…` печатает ИНН ИЗ СОБСТВЕННОГО АДРЕСА, поэтому признак
«ИНН есть на странице» ложный — выдуманный ИНН тоже «доказывается». Различают три условия:
ИНН после слова + ОГРН + «Местонахождение».

У МЕНЯ такие ссылки есть — 661 штука, и 658 из них ЕДИНСТВЕННОЕ доказательство своей строки.
Но форма другая: у меня в адресе стоит `agencyId=39719`, а ИНН в адресе НЕТ ВООБЩЕ. Значит
эхо-дефекта на моей форме быть не может — странице неоткуда списать ИНН. Зато у моей формы
СВОЙ вопрос: показывает ли страница агентства ИМЕННО МОЙ ИНН, а не соседний.

ЧТО ДЕЛАЮ. Открываю с сервера 6 своих ссылок и спрашиваю каждую: стоит ли на странице мой
ИНН. КОНТРОЛЬ — та же форма адреса с выдуманным agencyId=99999999: если она «докажет» ИНН,
признак ложный и у меня тоже.
"""
import json
import os
import re
import sys
sys.path.insert(0, '/home/user/avto/seo-texts/server')
import run_on_server as R

PARY = [('7017005296', 'https://zakupki.gov.ru/epz/organization/view223/info.html?agencyId=20905'),
        ('5050073540', 'https://zakupki.gov.ru/epz/organization/view223/info.html?agencyId=21215'),
        ('9704210635', 'https://zakupki.gov.ru/epz/organization/view223/info.html?agencyId=683076'),
        ('7734034550', 'https://zakupki.gov.ru/epz/organization/view223/info.html?agencyId=42951'),
        ('5003028028', 'https://zakupki.gov.ru/epz/organization/view223/info.html?agencyId=16635'),
        ('8904045666', 'https://zakupki.gov.ru/epz/organization/view223/info.html?agencyId=18816'),
        ('7017005296', 'https://zakupki.gov.ru/epz/organization/view223/info.html?agencyId=99999998')]

print('########## ПО ОДНОЙ')
itog = []
for n, (inn, u) in enumerate(PARY, 1):
    kontrol = u.endswith('99999998')
    try:
        r = R.submit('browser_probe',
                     {'url': u, 'proxy': False, 'ignore_https_errors': True,
                      'after_ms': 6000,
                      # ДВА ЗАСЛОНА, оба куплены пустыми ответами этого же скрипта:
                      # 1) отдавать СТРОКУ, а не объект — объект доезжает до песочницы
                      #    нечитаемым, и печаталось шесть строк «знаков None»;
                      # 2) всё держать в ОДНОМ выражении `return`. Поле `script` и поле
                      #    `return` исполняются РАЗНЫМИ вызовами, переменная из первого во
                      #    втором не видна: `ReferenceError: t is not defined`, а
                      #    `eval_js_ok` при этом True. Оба раза ноль был свойством прибора,
                      #    а не страницы, и оба раза его выдал напечатанный `eval_js_err`.
                      'eval_js': {'return': '(() => {const t=document.body?'
                                            'document.body.innerText:"";return [t.length,'
                                            '(/ИНН[^0-9]{0,12}%s/.test(t)?1:0),'
                                            '(t.indexOf("%s")>=0?1:0),'
                                            '(/ОГРН/.test(t)?1:0),'
                                            '(/Местонахождени/.test(t)?1:0)].join(";");})()'
                                            % (inn, inn)}},
                     timeout=180)
        # ИМЯ ПОЛЯ ОТВЕТА — `eval_js_value`, и я по нему уже промахнулась. Первый заход этой
        # проверки напечатал шесть строк «знаков None»: читалось `data['eval']`, а раннер
        # кладёт результат в `data['eval_js_value']`. Ноль был не свойством страниц, а моим
        # промахом по имени поля — ровно то, за что я держу правило «ноль это диагноз
        # прибора». Если поля снова не будет, печатаются ИМЕНА пришедших ключей.
        d = (r.get('data') or {})
        syr = d.get('eval_js_value')
        ch = str(syr or '').split(';')
        if len(ch) != 5 or not ch[0].isdigit():
            print('     ОТВЕТА НЕТ: eval_js_ok=%s eval_js_err=%s http=%s'
                  % (d.get('eval_js_ok'), str(d.get('eval_js_err'))[:60], d.get('http_status')))
            v = {}
        else:
            v = {'len': int(ch[0]), 'inn_posle_slova': ch[1] == '1',
                 'inn_gde_ugodno': ch[2] == '1', 'ogrn': ch[3] == '1', 'mesto': ch[4] == '1'}
    except Exception as e:  # noqa: BLE001
        print('  %d %s НЕ ОТКРЫЛАСЬ: %s' % (n, inn, str(e)[:60]))
        itog.append((inn, kontrol, None))
        continue
    print('  %d %-12s %s%s' % (n, inn, 'КОНТРОЛЬ ' if kontrol else '', u[-28:]))
    print('     знаков %-7s ИНН после слова %-6s ИНН где угодно %-6s ОГРН %-6s Местонахождение %s'
          % (v.get('len'), v.get('inn_posle_slova'), v.get('inn_gde_ugodno'),
             v.get('ogrn'), v.get('mesto')))
    itog.append((inn, kontrol, v))

print('\n########## ЧИСЛА')
nast = [v for i, k, v in itog if not k and isinstance(v, dict)]
kon = [v for i, k, v in itog if k and isinstance(v, dict)]
dok = [v for v in nast if v.get('inn_posle_slova') and v.get('ogrn') and v.get('mesto')]
print('  моих ссылок проверено                       %d' % len(nast))
print('  ДОКАЗЫВАЮТ ИНН по строгому признаку 1-й с.  %d' % len(dok))
print('  из них показали ИНН хоть где-то             %d'
      % len([v for v in nast if v.get('inn_gde_ugodno')]))
for v in kon:
    print('  КОНТРОЛЬ (выдуманный agencyId): ИНН после слова %s, ОГРН %s, Местонахождение %s -> %s'
          % (v.get('inn_posle_slova'), v.get('ogrn'), v.get('mesto'),
             'ПРИЗНАК ЛОЖНЫЙ' if (v.get('inn_posle_slova') and v.get('ogrn') and v.get('mesto'))
             else 'контроль чист'))
print('ИТОГ ' + json.dumps({'проверено': len(nast), 'доказывают': len(dok)}, ensure_ascii=False))

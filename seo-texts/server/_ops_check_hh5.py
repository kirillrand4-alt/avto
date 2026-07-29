# -*- coding: utf-8 -*-
"""Разведка №7: три вакансии по одной, ИСТИННЫЙ размер страницы и телефон.

Что доказываем:
  * рубит ли боевой html_cap=2.5 МБ страницу вакансии (тогда стейт не
    разбирается, работодатель пуст и страница уходит в «пропущено»);
  * есть ли на странице контактное ЛИЦО и прячется ли номер за
    callTracking (тогда наш разбор выбрасывает живого человека целиком);
  * достаётся ли номер кликом «Показать контакты».
"""
import json
import re
import sys
import time
import traceback
import urllib.parse

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import browser_probe as BP    # noqa: E402

ПРОФ = [x for x in re.split(r'[,\s]+', EC._HH_DOLPHIN_DEF) if x]
ТОК = EC._read_secret('DOLPHIN_TOKEN')
_i = [0]


def p(*a):
    print(*a)
    sys.stdout.flush()


def стейт(b):
    m = re.search(r'HH-Lux-InitialState"?\s*>(.*?)</template>', b or '', re.S)
    if not m:
        return {}, 'нет шаблона'
    try:
        import html as _h
        return json.loads(_h.unescape(m.group(1))), ''
    except Exception as ex:  # noqa: BLE001
        return {}, type(ex).__name__


def сходить(арг, попыток=3):
    посл = ''
    for _ in range(попыток):
        _i[0] += 1
        try:
            r = BP.probe(dict(арг, dolphin_profile=ПРОФ[_i[0] % len(ПРОФ)],
                              dolphin_token=ТОК))
            if (r or {}).get('html'):
                return r, ''
            посл = str((r or {}).get('error'))[:70]
        except Exception as ex:  # noqa: BLE001
            посл = f'{type(ex).__name__}: {str(ex)[:50]}'
        time.sleep(9)
    return {}, посл


def main():
    имя, inn = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    бренд = EC.бренд_компании(имя, '')
    поиск = ('https://hh.ru/search/vacancy?text=' + urllib.parse.quote(бренд)
             + '&search_field=company_name&items_on_page=50')
    r, err = сходить({'url': поиск, 'return_html': True, 'html_cap': 6000000,
                      'wait_ms': 4500, 'screenshot': False, 'solve': True})
    b = (r or {}).get('html') or ''
    if not b:
        p('ИТОГ: поиск не открылся:', err)
        return
    st, _ = стейт(b)
    сыр = json.dumps(st, ensure_ascii=False)
    ids, вид = [], set()
    for i in re.findall(r'"vacancyId"\s*:\s*"?(\d+)', сыр):
        if i not in вид:
            вид.add(i)
            ids.append(i)
    p('БРЕНД=%s поиск_байт=%d id=%d' % (бренд, len(b), len(ids)))
    итог = {'открыто': 0, 'больше_2_5МБ': 0, 'стейт_ок': 0, 'есть_лицо': 0,
            'есть_номер': 0, 'callTracking': 0}
    for k, vid in enumerate(ids[:n]):
        арг = {'url': 'https://hh.ru/vacancy/' + vid, 'return_html': True,
               'html_cap': 6000000, 'wait_ms': 4500, 'screenshot': False,
               'solve': True}
        if k == 0:
            # первую пробуем ещё и КЛИКНУТЬ «Показать контакты»
            арг['click'] = ['[data-qa=vacancy-contacts-call-tracking__show-phone-number]',
                            'button:has-text("Показать контакты")',
                            '[data-qa*=show-phone]']
            арг['card_wait_ms'] = 5000
        r2, e2 = сходить(арг, попыток=2)
        vb = (r2 or {}).get('html') or ''
        if not vb:
            p(vid, 'не открылась:', e2)
            continue
        итог['открыто'] += 1
        if len(vb) > 2500000:
            итог['больше_2_5МБ'] += 1
        stv, ошv = стейт(vb)
        vv = stv.get('vacancyView') or {}
        if vv:
            итог['стейт_ок'] += 1
        ci = vv.get('contactInfo') or {}
        фио = (ci.get('fio') or '').strip() or ' '.join(
            x for x in (ci.get('lastName'), ci.get('firstName'),
                        ci.get('middleName')) if x).strip()
        тел = ci.get('phones')
        если = тел.get('phones') if isinstance(тел, dict) else (тел or [])
        номера = [x for x in (если or []) if isinstance(x, dict) and x.get('number')]
        if фио:
            итог['есть_лицо'] += 1
        if номера:
            итог['есть_номер'] += 1
        if ci.get('callTrackingEnabled'):
            итог['callTracking'] += 1
        # что дал КЛИК: ищем номер в тексте страницы после раскрытия
        видимые = sorted(set(re.findall(
            r'(?<!\d)(?:\+7|8)[\s\-(]*\d{3,5}[\s\-)]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}',
            re.sub(r'<[^>]+>', ' ', vb))))[:4]
        p(json.dumps({'vid': vid, 'байт': len(vb), 'обрежет_боевой_кап':
                      len(vb) > 2500000, 'стейт_ош': ошv,
                      'emp': ((vv.get('company') or {}).get('name') or ''),
                      'вакансия': (vv.get('name') or '')[:40],
                      'contactInfo': json.dumps(ci, ensure_ascii=False)[:230],
                      'фио': фио, 'номеров_в_стейте': len(номера),
                      'клик': (r2 or {}).get('click_used'),
                      'номера_на_странице': видимые},
                     ensure_ascii=False)[:900])
        time.sleep(4)
    p('ИТОГ %s: %s' % (бренд, json.dumps(итог, ensure_ascii=False)))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        p('ФАТАЛЬНО:', traceback.format_exc()[-500:])

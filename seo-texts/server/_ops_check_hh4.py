# -*- coding: utf-8 -*-
"""Разведка №5: РЕШАЮЩИЙ замер hh на одной компании.

Две гипотезы дефекта, обе из прошлого захода:
  1) html_cap 2.5 МБ РЕЖЕТ страницу вакансии -> стейт не разбирается -> имя
     работодателя пустое, contactInfo не читается вовсе;
  2) рубеж принадлежности валит ЖИВОЕ совпадение, потому что hh пишет
     «ПАО «КАМАЗ»», а бренд у нас «КАМАЗ» — полное равенство не выполняется.
Открываем восемь вакансий одной сессией с большим капом и считаем честно.
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


def p(*a):
    print(*a)
    sys.stdout.flush()


def стейт(b):
    m = re.search(r'HH-Lux-InitialState"?\s*>(.*?)</template>', b or '', re.S)
    if not m:
        return {}, 'нет шаблона стейта'
    try:
        import html as _h
        return json.loads(_h.unescape(m.group(1))), ''
    except Exception as ex:  # noqa: BLE001
        return {}, f'{type(ex).__name__} (обрыв json)'


def сходить(арг, попыток=3):
    посл = ''
    for k in range(попыток):
        try:
            r = BP.probe(dict(арг, dolphin_profile=ПРОФ[k % len(ПРОФ)],
                              dolphin_token=ТОК))
            if (r or {}).get('html'):
                return r, ''
            посл = str((r or {}).get('error'))[:80]
        except Exception as ex:  # noqa: BLE001
            посл = f'{type(ex).__name__}: {str(ex)[:60]}'
        time.sleep(10)
    return {}, посл


def main():
    имя, inn = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    комп = {'name': имя, 'inn': inn, 'site': ''}
    бренд = EC.бренд_компании(имя, '')
    поиск = ('https://hh.ru/search/vacancy?text=' + urllib.parse.quote(бренд)
             + '&search_field=company_name&items_on_page=50')
    r, err = сходить({'url': поиск, 'return_html': True, 'html_cap': 6000000,
                      'wait_ms': 5000, 'screenshot': False, 'solve': True})
    b = (r or {}).get('html') or ''
    if not b:
        p('ИТОГ: поиск не открылся:', err)
        return
    st, ош = стейт(b)
    сыр = json.dumps(st, ensure_ascii=False)
    ids, видели = [], set()
    for i in re.findall(r'"vacancyId"\s*:\s*"?(\d+)', сыр):
        if i not in видели:
            видели.add(i)
            ids.append(i)
    всего = re.search(r'найдена?о? ([\d\s\u00a0]{1,9}) ваканс', b, re.I)
    p('БРЕНД=%s поиск: полн_байт=%s обрезано=%s стейт_ош=%s id=%d всего=%s'
      % (бренд, r.get('html_full_len'), r.get('html_truncated'), ош, len(ids),
         (всего.group(1) if всего else '?')))
    time.sleep(8)
    ids = ids[:n]
    r2, err2 = сходить({'url': 'https://hh.ru/vacancy/' + ids[0],
                        'urls': ['https://hh.ru/vacancy/' + i for i in ids],
                        'return_html': True, 'html_cap': 6000000,
                        'urls_cap': n + 1, 'wait_ms': 4500,
                        'urls_wait_ms': 2000, 'screenshot': False, 'solve': True})
    if not r2:
        p('ИТОГ: вакансии не открылись:', err2)
        return
    стр = [{'url': r2.get('url'), 'html': r2.get('html'),
            'html_full_len': r2.get('html_full_len'),
            'html_truncated': r2.get('html_truncated')}]
    стр += list(r2.get('pages') or [])
    итог = {'страниц': 0, 'стейт_ок': 0, 'обрезано': 0, 'ci_не_null': 0,
            'рубеж_старый': 0, 'рубеж_мягкий': 0}
    for s in стр:
        vb = s.get('html') or ''
        if not vb:
            p('пустая страница:', s.get('url'), 'статус', s.get('http_status'))
            continue
        итог['страниц'] += 1
        if s.get('html_truncated'):
            итог['обрезано'] += 1
        stv, ошv = стейт(vb)
        vv = (stv.get('vacancyView') or {})
        if vv:
            итог['стейт_ок'] += 1
        emp = ((vv.get('company') or {}).get('name') or '')
        ci = vv.get('contactInfo')
        if ci:
            итог['ci_не_null'] += 1
        наш, почему = EC.hh_страница_наша(vb, комп)
        полн = (re.sub(r'[^0-9a-zа-яё]+', '', emp.lower())
                == re.sub(r'[^0-9a-zа-яё]+', '', бренд.lower()))
        if наш or полн:
            итог['рубеж_старый'] += 1
        # МЯГКИЙ рубеж: бренд как ОТДЕЛЬНОЕ слово в имени работодателя
        мягко = bool(emp) and bool(re.search(
            r'(?<![а-яёa-z0-9])' + re.escape(бренд.lower()) + r'(?![а-яёa-z0-9])',
            emp.lower()))
        if мягко:
            итог['рубеж_мягкий'] += 1
        сырой_ci = len(re.findall(r'"contactInfo"\s*:\s*\{', vb))
        p(json.dumps({'vid': (s.get('url') or '')[-9:], 'emp': emp,
                      'полн_байт': s.get('html_full_len'),
                      'обрез': s.get('html_truncated'), 'стейт_ош': ошv,
                      'ci': (json.dumps(ci, ensure_ascii=False)[:160] if ci else None),
                      'ci_фигурная_в_html': сырой_ci,
                      'рубеж': наш, 'почему': почему[:60], 'полн_совп': полн,
                      'мягко': мягко}, ensure_ascii=False)[:800])
    p('ИТОГ %s: %s' % (бренд, json.dumps(итог, ensure_ascii=False)))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        p('ФАТАЛЬНО:', traceback.format_exc()[-600:])

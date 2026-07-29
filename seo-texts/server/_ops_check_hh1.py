# -*- coding: utf-8 -*-
"""Разведка №2: живой hh по ОДНОЙ крупной компании, до самой разметки.

Проверяем не «мало ли вакансий», а ГДЕ теряется: на поиске, на разборе id,
на рубеже принадлежности или в contactInfo. Печатаем сырьё, а не выводы.
"""
import json
import re
import sys
import urllib.parse

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import browser_probe as BP    # noqa: E402


def стейт(b):
    m = re.search(r'HH-Lux-InitialState"?\s*>(.*?)</template>', b or '', re.S)
    if not m:
        return {}
    try:
        import html as _h
        return json.loads(_h.unescape(m.group(1)))
    except Exception as ex:  # noqa: BLE001
        return {'__ошибка_разбора__': f'{type(ex).__name__}: {str(ex)[:80]}'}


def main():
    имя = sys.argv[1]
    inn = sys.argv[2]
    n_vac = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    комп = {'name': имя, 'inn': inn, 'site': ''}
    бренд = EC.бренд_компании(имя, '')
    tokd = EC._read_secret('DOLPHIN_TOKEN')
    проф = [x for x in re.split(r'[,\s]+', EC._HH_DOLPHIN_DEF) if x]
    pid = проф[EC._hh_prof_next() % len(проф)]
    поиск = ('https://hh.ru/search/vacancy?text=' + urllib.parse.quote(бренд)
             + '&search_field=company_name&items_on_page=50')
    print('БРЕНД:', бренд, '| профиль:', pid)
    r = BP.probe({'url': поиск, 'return_html': True, 'html_cap': 2500000,
                  'wait_ms': 6000, 'screenshot': False, 'solve': True,
                  'dolphin_profile': pid, 'dolphin_token': tokd})
    b = r.get('html') or ''
    print('поиск: байт=%d ошибка=%s капча=%s' % (
        len(b), str(r.get('error'))[:80], r.get('captcha_type')))
    st = стейт(b)
    сыр = json.dumps(st, ensure_ascii=False) if st else ''
    print('стейт: ключей=%d байт=%d %s' % (
        len(st), len(сыр), st.get('__ошибка_разбора__', '')))
    ids_st = []
    видели = set()
    for i in re.findall(r'"vacancyId"\s*:\s*"?(\d+)', сыр):
        if i not in видели:
            видели.add(i)
            ids_st.append(i)
    ids_md = sorted(set(re.findall(r'/vacancy/(\d+)', b)))
    print('ID из стейта=%d из разметки=%d' % (len(ids_st), len(ids_md)))
    # сколько ВСЕГО вакансий заявляет сама выдача
    for пат in (r'найдена?о? ([\d\s\u00a0]{1,9}) ваканс',
                r'"totalResults"\s*:\s*(\d+)', r'"found"\s*:\s*(\d+)'):
        m = re.search(пат, b, re.I)
        if m:
            print('счётчик выдачи (%s): %s' % (пат[:18], m.group(1)))
            break
    имена_раб = sorted(set(re.findall(
        r'"employer"\s*:\s*\{[^{}]{0,300}?"name"\s*:\s*"([^"]{2,90})"', b)))[:6]
    print('имена работодателей в поиске:', json.dumps(имена_раб, ensure_ascii=False))
    ids = (ids_st or ids_md)[:n_vac]
    if not ids:
        print('ИТОГ: вакансий 0 — дальше идти не с чем')
        return
    r2 = BP.probe({'url': 'https://hh.ru/vacancy/' + ids[0],
                   'urls': ['https://hh.ru/vacancy/' + i for i in ids],
                   'return_html': True, 'html_cap': 2500000,
                   'urls_cap': n_vac + 1, 'wait_ms': 6000, 'urls_wait_ms': 2500,
                   'screenshot': False, 'solve': True,
                   'dolphin_profile': pid, 'dolphin_token': tokd})
    стр = [{'url': r2.get('url'), 'html': r2.get('html')}] + list(r2.get('pages') or [])
    сводка = {'страниц': 0, 'contactInfo_есть': 0, 'рубеж_пропустил': 0,
              'слово_контакт': 0}
    for s in стр:
        vb = s.get('html') or ''
        if not vb:
            continue
        сводка['страниц'] += 1
        vv = (стейт(vb).get('vacancyView') or {})
        emp = ((vv.get('company') or {}).get('name') or '')
        ci = vv.get('contactInfo')
        наш, почему = EC.hh_страница_наша(vb, комп)
        полн = (re.sub(r'[^0-9a-zа-яё]+', '', emp.lower())
                == re.sub(r'[^0-9a-zа-яё]+', '', бренд.lower()))
        если_контакт = len(re.findall(r'[Кк]онтактн\w+ лиц', vb))
        if ci:
            сводка['contactInfo_есть'] += 1
        if наш or полн:
            сводка['рубеж_пропустил'] += 1
        if если_контакт:
            сводка['слово_контакт'] += 1
        print(json.dumps({
            'url': s.get('url'), 'вакансия': (vv.get('name') or '')[:50],
            'работодатель': emp, 'contactInfo': (json.dumps(ci, ensure_ascii=False)[:220]
                                                 if ci else None),
            'рубеж': наш, 'почему': почему[:90], 'полное_совпадение': полн,
            'слов_контактное_лицо_в_html': если_контакт,
            'ключи_vacancyView': sorted(vv.keys())[:28] if vv else [],
        }, ensure_ascii=False)[:900])
    print('ИТОГ %s: id_поиска=%d открыто=%d contactInfo=%d рубеж_пропустил=%d'
          % (бренд, len(ids_st or ids_md), сводка['страниц'],
             сводка['contactInfo_есть'], сводка['рубеж_пропустил']))


if __name__ == '__main__':
    main()

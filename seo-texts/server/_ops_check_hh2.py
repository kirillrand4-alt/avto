# -*- coding: utf-8 -*-
"""Разведка №3: страница вакансии в СЫРОМ виде + рубеж принадлежности.

Прошлый заход умер молча на пачке — здесь каждый шаг под своим except и с
flush, чтобы увидеть место обрыва, а не гадать.
"""
import json
import re
import sys
import traceback
import urllib.parse

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import browser_probe as BP    # noqa: E402


def p(*a):
    print(*a, flush=True)


def стейт(b):
    m = re.search(r'HH-Lux-InitialState"?\s*>(.*?)</template>', b or '', re.S)
    if not m:
        return {}
    try:
        import html as _h
        return json.loads(_h.unescape(m.group(1)))
    except Exception:  # noqa: BLE001
        return {}


def main():
    имя, inn = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    комп = {'name': имя, 'inn': inn, 'site': ''}
    бренд = EC.бренд_компании(имя, '')
    tokd = EC._read_secret('DOLPHIN_TOKEN')
    проф = [x for x in re.split(r'[,\s]+', EC._HH_DOLPHIN_DEF) if x]
    pid = проф[EC._hh_prof_next() % len(проф)]
    поиск = ('https://hh.ru/search/vacancy?text=' + urllib.parse.quote(бренд)
             + '&search_field=company_name&items_on_page=50')
    r = BP.probe({'url': поиск, 'return_html': True, 'html_cap': 2500000,
                  'wait_ms': 5000, 'screenshot': False, 'solve': True,
                  'dolphin_profile': pid, 'dolphin_token': tokd})
    b = r.get('html') or ''
    сыр = json.dumps(стейт(b), ensure_ascii=False)
    ids, видели = [], set()
    for i in re.findall(r'"vacancyId"\s*:\s*"?(\d+)', сыр):
        if i not in видели:
            видели.add(i)
            ids.append(i)
    p('БРЕНД=%s профиль=%s id=%d' % (бренд, pid, len(ids)))
    # КАК hh НА САМОМ ДЕЛЕ ЗОВЁТ РАБОТОДАТЕЛЯ В СТЕЙТЕ ПОИСКА
    p('company.name в стейте:', json.dumps(sorted(set(re.findall(
        r'"company"\s*:\s*\{[^{}]{0,400}?"name"\s*:\s*"([^"]{2,80})"', сыр)))[:5],
        ensure_ascii=False))
    p('employerName/ключи:', json.dumps(sorted(set(re.findall(
        r'"(employer\w*|companyName|employerName)"\s*:', сыр)))[:8], ensure_ascii=False))
    for vid in ids[:n]:
        try:
            r2 = BP.probe({'url': 'https://hh.ru/vacancy/' + vid,
                           'return_html': True, 'html_cap': 1600000,
                           'wait_ms': 5000, 'screenshot': False, 'solve': True,
                           'dolphin_profile': pid, 'dolphin_token': tokd})
        except Exception:  # noqa: BLE001
            p(vid, 'ОШИБКА probe:', traceback.format_exc()[-300:])
            continue
        vb = r2.get('html') or ''
        st = стейт(vb)
        vv = st.get('vacancyView') or {}
        emp = ((vv.get('company') or {}).get('name') or '')
        наш, почему = EC.hh_страница_наша(vb, комп)
        полн = (re.sub(r'[^0-9a-zа-яё]+', '', emp.lower())
                == re.sub(r'[^0-9a-zа-яё]+', '', бренд.lower()))
        # СЫРЬЁ: что вообще есть на странице про контакт
        сырьё = {}
        for метка, пат in (
                ('contactInfo_в_html', r'"contactInfo"\s*:\s*(\{|null|\[)'),
                ('слово_Контактное_лицо', r'[Кк]онтактн\w+ лиц\w*'),
                ('слово_Показать_контакты', r'[Пп]оказать контакт'),
                ('телефоны_в_тексте', r'(?<!\d)(?:\+7|8)[\s\-(]*\d{3,5}[\s\-)]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}'),
                ('почты_в_тексте', r'[A-Za-z0-9._%%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')):
            м = re.findall(пат, vb)
            сырьё[метка] = len(м)
        m = re.search(r'"contactInfo"\s*:\s*(\{.{0,400})', vb, re.S)
        p(json.dumps({'vid': vid, 'работодатель': emp,
                      'вакансия': (vv.get('name') or '')[:45],
                      'contactInfo_объект': vv.get('contactInfo'),
                      'рубеж': наш, 'почему': почему[:80],
                      'полное_совпадение': полн, 'сырьё': сырьё,
                      'кусок_contactInfo': (m.group(1)[:300] if m else None),
                      'байт': len(vb), 'обрезано': r2.get('html_truncated'),
                      }, ensure_ascii=False)[:1400], flush=True)
    p('ИТОГ: бренд=%s вакансий_в_выдаче=%d открыто=%d' % (бренд, len(ids), min(n, len(ids))))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        p('ФАТАЛЬНО:', traceback.format_exc()[-700:])

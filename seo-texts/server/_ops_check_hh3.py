# -*- coding: utf-8 -*-
"""Разведка №4: страницы вакансий одной сессией + ретрай по трём профилям.

Дельфин отдаёт HTTP 500, когда профиль ещё занят предыдущим прогоном, — это
не «источник пуст», а слот. Поэтому ретраим по кругу и с паузой.
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


def p(*a, **kw):
    kw.pop('flush', None)
    print(*a)
    sys.stdout.flush()


def стейт(b):
    m = re.search(r'HH-Lux-InitialState"?\s*>(.*?)</template>', b or '', re.S)
    if not m:
        return {}
    try:
        import html as _h
        return json.loads(_h.unescape(m.group(1)))
    except Exception:  # noqa: BLE001
        return {}


def сходить(арг, попыток=4):
    посл = ''
    for k in range(попыток):
        pid = ПРОФ[k % len(ПРОФ)]
        try:
            r = BP.probe(dict(арг, dolphin_profile=pid, dolphin_token=ТОК))
            if (r or {}).get('html'):
                return r, pid, ''
            посл = str((r or {}).get('error'))[:90]
        except Exception as ex:  # noqa: BLE001
            посл = f'{type(ex).__name__}: {str(ex)[:60]}'
        time.sleep(12)
    return {}, '', посл


def main():
    имя, inn = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    комп = {'name': имя, 'inn': inn, 'site': ''}
    бренд = EC.бренд_компании(имя, '')
    поиск = ('https://hh.ru/search/vacancy?text=' + urllib.parse.quote(бренд)
             + '&search_field=company_name&items_on_page=50')
    r, pid, err = сходить({'url': поиск, 'return_html': True,
                           'html_cap': 2500000, 'wait_ms': 5000,
                           'screenshot': False, 'solve': True})
    b = (r or {}).get('html') or ''
    if not b:
        p('ИТОГ: поиск не открылся:', err)
        return
    сыр = json.dumps(стейт(b), ensure_ascii=False)
    ids, видели = [], set()
    for i in re.findall(r'"vacancyId"\s*:\s*"?(\d+)', сыр):
        if i not in видели:
            видели.add(i)
            ids.append(i)
    p('БРЕНД=%s поиск_профиль=%s id=%d' % (бренд, pid, len(ids)))
    time.sleep(10)
    ids = ids[:n]
    r2, pid2, err2 = сходить({'url': 'https://hh.ru/vacancy/' + ids[0],
                              'urls': ['https://hh.ru/vacancy/' + i for i in ids],
                              'return_html': True, 'html_cap': 1500000,
                              'urls_cap': n + 1, 'wait_ms': 5000,
                              'urls_wait_ms': 2500, 'screenshot': False,
                              'solve': True})
    if not r2:
        p('ИТОГ: вакансии не открылись:', err2)
        return
    стр = [{'url': r2.get('url'), 'html': r2.get('html')}] + list(r2.get('pages') or [])
    с_контактом = 0
    for s in стр:
        vb = s.get('html') or ''
        if not vb:
            continue
        vv = (стейт(vb).get('vacancyView') or {})
        emp = ((vv.get('company') or {}).get('name') or '')
        ci = vv.get('contactInfo')
        наш, почему = EC.hh_страница_наша(vb, комп)
        полн = (re.sub(r'[^0-9a-zа-яё]+', '', emp.lower())
                == re.sub(r'[^0-9a-zа-яё]+', '', бренд.lower()))
        сырьё = {}
        for метка, пат in (
                ('ci_ключ_в_html', r'"contactInfo"'),
                ('Контактное_лицо', r'[Кк]онтактн\w+ лиц'),
                ('Показать_контакты', r'[Пп]оказать контакт'),
                ('телефон_в_тексте', r'(?<!\d)(?:\+7|8)[\s\-(]*\d{3,5}[\s\-)]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}'),
                ('почта_в_тексте', r'[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,6}')):
            сырьё[метка] = len(re.findall(пат, vb))
        if ci:
            с_контактом += 1
        m = re.search(r'"contactInfo"\s*:\s*(.{0,260})', vb, re.S)
        p(json.dumps({'url': s.get('url'), 'работодатель': emp,
                      'вакансия': (vv.get('name') or '')[:45],
                      'contactInfo': ci, 'рубеж': наш, 'почему': почему[:70],
                      'полное_совпадение': полн, 'сырьё': сырьё,
                      'кусок': (m.group(1)[:200] if m else None),
                      'байт': len(vb)}, ensure_ascii=False)[:1200], flush=True)
    p('ИТОГ %s: вакансий_в_выдаче=%d открыто=%d с_contactInfo=%d профиль=%s'
      % (бренд, len(ids), len([x for x in стр if x.get('html')]), с_контактом, pid2))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        p('ФАТАЛЬНО:', traceback.format_exc()[-600:])

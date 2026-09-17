# -*- coding: utf-8 -*-
"""Второй проход: округ из краткого описания + поиск в ЕГРЗ рядом с датой карточки."""
import json
import re
import ssl
import sys
import urllib.request

sys.path.insert(0, r'C:\sender\server')
import collector_egrz as C  # noqa: E402

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36',
     'Accept-Language': 'ru', 'Referer': 'https://investprojects.info/project-base'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
o = {}


def кратко(ид):
    try:
        r = НП.open(urllib.request.Request(
            'https://investprojects.info/project-base/%s' % ид, headers=H), timeout=50)
        html = r.read(700000).decode('utf-8', 'replace')
    except Exception as e:
        return 'ошибка: %r' % (e,)
    ч = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', html, flags=re.S)
    ч = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', ч))
    m = re.search(r'Краткое описание (.{0,260}?) Сроки проекта', ч)
    доб = re.search(r'Дата добавления ([\d.]+)', ч)
    обн = re.search(r'Последнее обновление ([\d.]+)', ч)
    отр = re.search(r'Отрасль (.{0,40}?) Подотрасль (.{0,45}?) ', ч)
    return {'краткое': (m.group(1) if m else '')[:240],
            'добавлена': доб.group(1) if доб else '',
            'обновлена': обн.group(1) if обн else '',
            'отрасль': отр.group(1).strip() if отр else '',
            'подотрасль': отр.group(2).strip() if отр else ''}


def егрз(слова, с_даты, по_дату=None, лимит=8):
    усл = ' or '.join("contains(tolower(ExpertiseObjectName),'%s')" % s for s in слова)
    флт = "ExpertiseConclusionDate gt %s and (%s)" % (с_даты, усл)
    if по_дату:
        флт += " and ExpertiseConclusionDate lt %s" % по_дату
    код, d = C._page(флт, 0, top=лимит)
    зап = []
    for з in (d.get('value') or []) if isinstance(d, dict) else []:
        зап.append({
            'объект': (з.get('ExpertiseObjectName') or '')[:90],
            'регион': (з.get('SubjectRf') or '')[:30],
            'застройщик': (з.get('DeveloperOrganizationInfo') or '')[:78],
            'дата': (з.get('ExpertiseConclusionDate') or '')[:10]})
    return {'всего': d.get('@odata.count') if isinstance(d, dict) else None, 'записи': зап}


o['271244_роботы'] = {'карточка': кратко('271244'),
                      'егрз': егрз(['робот', 'манипулятор'], '2024-06-01T00:00:00Z')}
o['351051_зерно'] = {'карточка': кратко('351051'),
                     'егрз_вокруг_даты': егрз(
                         ['подработк', 'зернохранилищ', 'зерносушил', 'зерноочист', 'элеватор'],
                         '2026-09-08T00:00:00Z', '2026-09-18T00:00:00Z')}
o['351070_молоко'] = {'карточка': кратко('351070'),
                      'егрз': егрз(['молочноконсерв', 'молочно-консерв', 'молочн'],
                                   '2026-08-15T00:00:00Z')}
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5600])

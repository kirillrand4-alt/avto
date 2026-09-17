# -*- coding: utf-8 -*-
"""Три карточки investprojects: открытые поля + поиск кандидатов в ЕГРЗ."""
import json
import re
import ssl
import sys
import urllib.error
import urllib.request

sys.path.insert(0, r'C:\sender\server')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36',
     'Accept-Language': 'ru', 'Referer': 'https://investprojects.info/project-base'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))

ЦЕЛИ = {
    '351070': ['молочноконсерв', 'молочно-консерв'],
    '351051': ['подработк', 'зернохранилищ', 'зерносушил'],
    '271244': ['промышленных роботов', 'робототехн'],
}
ПОЛЯ = ('Дата добавления', 'Последнее обновление', 'Следующее обновление', 'Тип работ',
        'Краткое описание', 'Сроки проекта', 'Стадия', 'Вид собственности', 'Отрасль',
        'Подотрасль', 'Объем инвестиций')
o = {}


def карточка(ид):
    try:
        r = НП.open(urllib.request.Request(
            'https://investprojects.info/project-base/%s' % ид, headers=H), timeout=50)
        html = r.read(700000).decode('utf-8', 'replace')
    except Exception as e:
        return {'ошибка': repr(e)[:80]}
    ч = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', html, flags=re.S)
    ч = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', ч))
    i = ч.find('ID %s' % ид)
    хвост = ч[i:i + 2600] if i > 0 else ч[-2600:]
    зап = {'заголовок': (re.search(r'<title>(.*?)</title>', html, re.S) or ['', ''])[1][:120]}
    for п in ПОЛЯ:
        m = re.search(re.escape(п) + r'\s+(.{0,120}?)(?=' +
                      '|'.join(re.escape(x) for x in ПОЛЯ) + r'|Отраслевые|$)', хвост)
        if m:
            зн = m.group(1).strip()
            зап[п] = ('(скрыто)' if set(зн) <= set('·. ') and зн else зн)[:110]
    return зап


import collector_egrz as C  # noqa: E402


def кандидаты(слова):
    усл = ' or '.join("contains(tolower(ExpertiseObjectName),'%s')" % s for s in слова)
    флт = "ExpertiseConclusionDate gt 2023-06-01T00:00:00Z and (%s)" % усл
    код, d = C._page(флт, 0, top=12)
    итог = []
    for з in (d.get('value') or []) if isinstance(d, dict) else []:
        итог.append({
            'объект': (з.get('ExpertiseObjectName') or '')[:95],
            'адрес': (з.get('ExpertiseObjectAddress') or '')[:70],
            'регион': (з.get('SubjectRf') or '')[:32],
            'застройщик': (з.get('DeveloperOrganizationInfo') or '')[:85],
            'дата': (з.get('ExpertiseConclusionDate') or '')[:10],
            'вид': (з.get('WorkType') or '')[:22],
        })
    return {'код': код, 'всего': d.get('@odata.count') if isinstance(d, dict) else None,
            'записи': итог[:6]}


for ид, слова in ЦЕЛИ.items():
    o[ид] = {'карточка': карточка(ид), 'егрз': кандидаты(слова)}

print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5600])

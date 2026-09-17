# -*- coding: utf-8 -*-
"""Опознать объект 302390: длины скрытых слов + поиск по ЕГРЗ.

Маска на сайте сделана точками по числу символов, то есть длины слов не скрыты.
Это даёт шаблон: «слово из 4 букв, слово из 12, слово из 8...». Сверяем шаблон
с кандидатами, найденными в открытом ЕГРЗ по типу объекта и округу.
"""
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
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
     'Accept-Language': 'ru', 'Referer': 'https://investprojects.info/project-base'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
o = {}

# 1. Забираем карточку и вытаскиваем маски с длинами слов.
try:
    r = НП.open(urllib.request.Request(
        'https://investprojects.info/project-base/302390', headers=H), timeout=45)
    html = r.read(600000).decode('utf-8', 'replace')
except Exception as e:
    html = ''
    o['карточка'] = repr(e)[:90]

ч = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', html, flags=re.S)
ч = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', ч))


def маска(поле, следом):
    """Кусок текста между названием поля и следующим полем."""
    i = ч.find(поле)
    j = ч.find(следом, i + 1) if i >= 0 else -1
    if i < 0 or j < 0:
        return ''
    return ч[i + len(поле):j].strip()


поля = {
    'местоположение': маска('Местоположение', 'Полное описание'),
    'полное_описание': маска('Полное описание', 'Краткое описание'),
    'техзаказчик': маска('Технический заказчик', 'Застройщик')
                   or маска('Технический заказчик', 'Инвестор')
                   or маска('Технический заказчик', 'Генеральный'),
}
o['маски'] = {}
for имя, текст in поля.items():
    слова = [w for w in текст.split(' ') if set(w) <= set('·.•…') and w]
    o['маски'][имя] = {'как_есть': текст[:140],
                       'длины_слов': [len(w) for w in слова][:14]}

# 2. Кандидаты из ЕГРЗ: торгово-бытовые комплексы, регионы СФО.
СФО = ['04', '17', '19', '22', '24', '38', '42', '54', '55', '70']
try:
    import collector_egrz as C
    флт = ("ExpertiseConclusionDate gt 2024-01-01T00:00:00Z and ("
           "contains(tolower(ExpertiseObjectName),'торгово-бытов') or "
           "contains(tolower(ExpertiseObjectName),'торгово-быт'))")
    код, d = C._page(флт, 0, top=30)
    o['егрз_по_названию'] = {'код': код, 'найдено': d.get('@odata.count') if isinstance(d, dict) else None}
    кандидаты = []
    for з in (d.get('value') or []) if isinstance(d, dict) else []:
        кандидаты.append({
            'объект': (з.get('ExpertiseObjectName') or '')[:110],
            'регион': (з.get('SubjectRf') or '')[:40],
            'застройщик': (з.get('DeveloperOrganizationInfo') or '')[:90],
            'техзаказчик': (з.get('TechnicalCustomerOrganizationInfo') or '')[:90],
            'дата': (з.get('ExpertiseConclusionDate') or '')[:10],
        })
    o['кандидаты_все_регионы'] = кандидаты[:10]
    o['кандидаты_СФО'] = [k for k in кандидаты
                          if any(s in k['регион'] for s in (
                              'Алтай', 'Тыва', 'Хакас', 'Краснояр', 'Иркут', 'Кемеров',
                              'Новосибир', 'Омск', 'Томск'))][:10]
except Exception as e:
    o['егрз'] = 'ОШИБКА: %r' % (e,)

print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5200])

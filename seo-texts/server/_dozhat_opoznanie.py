# -*- coding: utf-8 -*-
"""Добить: ИНН Любинского МКК, округ карточки роботов, чужая база bbgl."""
import json, os, re, ssl, urllib.request

CTX = ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0', 'Accept-Language': 'ru'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
o = {}

# 1. ИНН Любинского МКК через dadata по названию.
ТОК = os.environ.get('DADATA_TOKEN', '')
try:
    req = urllib.request.Request(
        'https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party',
        data=json.dumps({'query': 'Любинский молочноконсервный комбинат', 'count': 3}).encode(),
        headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                 'Authorization': 'Token ' + ТОК})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    o['любинский_мкк'] = [{'имя': s.get('value'),
                           'инн': (s.get('data') or {}).get('inn'),
                           'статус': (((s.get('data') or {}).get('state') or {}).get('status')),
                           'регион': (((s.get('data') or {}).get('address') or {}).get('data') or {}).get('region_with_type'),
                           'оквэд': ((s.get('data') or {}).get('okved'))}
                          for s in (d.get('suggestions') or [])[:3]]
except Exception as e:
    o['любинский_мкк'] = repr(e)[:90]

# 2. Карточка роботов: округ и сроки.
try:
    r = НП.open(urllib.request.Request(
        'https://investprojects.info/project-base/271244', headers=H), timeout=45)
    ч = re.sub(r'<script.*?</script>|<style.*?</style>', ' ',
               r.read(700000).decode('utf-8','replace'), flags=re.S)
    ч = re.sub(r'\s+',' ', re.sub(r'<[^>]+>',' ',ч))
    o['карточка_271244'] = {
        'краткое': (re.search(r'Краткое описание (.{0,230}?) Сроки проекта', ч) or ['',''])[1][:200],
        'сроки': (re.search(r'Сроки проекта (.{0,60}?) Стадия', ч) or ['',''])[1],
        'стадия': (re.search(r'Стадия (.{0,40}?) (Технический|Застройщик|Инвестор|Объем)', ч) or ['','',''])[1],
        'отрасль': (re.search(r'Отрасль (.{0,45}?) Подотрасль', ч) or ['',''])[1]}
except Exception as e:
    o['карточка_271244'] = repr(e)[:80]

# 3. Чужая база bbgl: открыта ли карточка проекта целиком.
try:
    r = НП.open(urllib.request.Request('https://bbgl.ru/prjcts/17003', headers=H), timeout=45)
    html = r.read(400000).decode('utf-8','replace')
    ч2 = re.sub(r'\s+',' ', re.sub(r'<[^>]+>',' ', re.sub(
        r'<script.*?</script>|<style.*?</style>',' ', html, flags=re.S)))
    i = ч2.find('Строительство')
    o['bbgl_17003'] = {'код': 200, 'байт': len(html),
                       'просит_вход': bool(re.search(r'зарегистрир|подписк|доступ', ч2[:2500], re.I)),
                       'текст': ч2[i:i+900] if i>0 else ч2[:700]}
except Exception as e:
    o['bbgl_17003'] = repr(e)[:80]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5200])

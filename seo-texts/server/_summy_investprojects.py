# -*- coding: utf-8 -*-
"""Бывает ли «Объем инвестиций» открытым и похож ли он на новостную цифру."""
import json, re, ssl, urllib.request
from concurrent.futures import ThreadPoolExecutor

CTX = ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
     'Accept-Language': 'ru', 'Referer': 'https://investprojects.info/project-base'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))

ИДЫ = ['302390','351070','351051','271244','317768','342370','350586','347698',
       '345796','155594','348969','351052','207778','212719','345663']

def карточка(ид):
    try:
        r = НП.open(urllib.request.Request(
            'https://investprojects.info/project-base/%s' % ид, headers=H), timeout=40)
        html = r.read(600000).decode('utf-8','replace')
    except Exception as e:
        return {'ид': ид, 'ошибка': repr(e)[:40]}
    ч = re.sub(r'\s+',' ', re.sub(r'<[^>]+>',' ', re.sub(
        r'<script.*?</script>|<style.*?</style>',' ', html, flags=re.S)))
    м = re.search(r'Объем инвестиций (.{0,60}?) (?:Вид собственности|Отрасль|Стадия)', ч)
    знач = (м.group(1).strip() if м else '')
    скрыто = bool(знач) and set(знач.replace(' ','')) <= set('·.')
    цифры = re.findall(r'\d[\d\s.,]*\s*(?:млн|млрд|руб)', знач)
    # заодно — есть ли на странице вообще какие-то открытые суммы
    все_суммы = re.findall(r'\d[\d\s.,]{0,12}\s*(?:млн|млрд)\s*(?:руб|₽)?', ч)[:4]
    return {'ид': ид, 'поле': знач[:40], 'скрыто': скрыто, 'цифры_в_поле': цифры,
            'суммы_на_странице': все_суммы}

with ThreadPoolExecutor(max_workers=6) as ex:
    строки = list(ex.map(карточка, ИДЫ))
o = {'карточек': len(строки),
     'скрыто_поле': sum(1 for x in строки if x.get('скрыто')),
     'открыто_поле': [x for x in строки if x.get('цифры_в_поле')],
     'есть_суммы_где_то_на_странице': [x['ид'] for x in строки if x.get('суммы_на_странице')],
     'примеры': строки[:6]}
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5000])

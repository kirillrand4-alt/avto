# -*- coding: utf-8 -*-
"""Правда ли карточки «ведут»: распределение стадий и связь дат с новостями."""
import json, os, re, ssl, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

CTX = ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
     'Accept-Language': 'ru', 'Referer': 'https://investprojects.info/project-base'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
U = os.environ.get('XMLRIVER_USER',''); K = os.environ.get('XMLRIVER_KEY','')
o = {}

ИДЫ = ['302390','351070','351051','271244','348969','345796','155594','347698',
       '342370','317768','351052','350586']

def карточка(ид):
    try:
        r = НП.open(urllib.request.Request(
            'https://investprojects.info/project-base/%s' % ид, headers=H), timeout=40)
        ч = re.sub(r'\s+',' ', re.sub(r'<[^>]+>',' ', re.sub(
            r'<script.*?</script>|<style.*?</style>',' ',
            r.read(600000).decode('utf-8','replace'), flags=re.S)))
    except Exception as e:
        return {'ид': ид, 'ошибка': repr(e)[:50]}
    def п(rx, d=''):
        m = re.search(rx, ч)
        return m.group(1).strip() if m else d
    return {'ид': ид,
            'стадия': п(r'Стадия (.{0,45}?) (?:Технический|Застройщик|Инвестор|Объем|Вид)'),
            'добавлена': п(r'Дата добавления ([\d.]+)'),
            'обновлена': п(r'Последнее обновление ([\d.]+)'),
            'следующее': п(r'Следующее обновление ([\d.]+)'),
            'название': п(r'ID %s (.{0,60}?) Дата добавления' % ид)}

with ThreadPoolExecutor(max_workers=6) as ex:
    o['карточки'] = list(ex.map(карточка, ИДЫ))
из_стадий = {}
for к in o['карточки']:
    s = к.get('стадия') or '?'
    из_стадий[s] = из_стадий.get(s, 0) + 1
o['распределение_стадий'] = из_стадий

def искать(q, n=4):
    try:
        with НП.open('http://xmlriver.com/search_google/xml?user=%s&key=%s&query=%s&groupby=%d'
                     % (U, K, urllib.parse.quote(q), n), timeout=80) as r:
            xml = r.read(300000).decode('utf-8','replace')
    except Exception as e:
        return ['ОШИБКА %r' % (e,)]
    ч = lambda s: re.sub(r'\s+',' ', re.sub(r'<[^>]+>','',s)).strip()
    return [{'з': ч((re.search(r'<title>(.*?)</title>',б,re.S) or ['',''])[1])[:90],
             'т': ч((re.search(r'<passage>(.*?)</passage>',б,re.S) or ['',''])[1])[:160],
             'u': ч((re.search(r'<url>(.*?)</url>',б,re.S) or ['',''])[1])[:70]}
            for б in re.findall(r'<doc>(.*?)</doc>', xml, re.S)[:n]]

o['новость_любинский_дата'] = искать('Хоценко модернизация Любинского молочноконсервного комбината сентябрь 2026')
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5400])

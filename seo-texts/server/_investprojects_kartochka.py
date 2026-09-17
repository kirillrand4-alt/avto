# -*- coding: utf-8 -*-
"""Одна карточка проекта: что видно без входа. Плюс полный robots для проверки."""
import json, re, ssl, urllib.error, urllib.request

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
     'Accept-Language': 'ru', 'Referer': 'https://investprojects.info/project-base'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def взять(u, лимит=600000):
    try:
        r = НП.open(urllib.request.Request(u, headers=H), timeout=45)
        return r.getcode(), r.geturl(), r.read(лимит).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, u, (e.read(500) or b'').decode('utf-8', 'replace')
    except Exception as e:
        return -1, u, repr(e)[:100]

o = {}
код, _, robots = взять('https://investprojects.info/robots.txt', 20000)
o['robots_полностью'] = robots[:1600]
o['запрещён_ли_project_base'] = [s for s in robots.splitlines()
                                 if 'project-base' in s or 'project-base' in s.lower()]

код, финал, html = взять('https://investprojects.info/project-base/302390')
o['карточка'] = {'код': код, 'финал': финал[:80], 'байт': len(html)}
ч = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', html, flags=re.S)
ч = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', ч))
o['карточка']['заголовок'] = (re.search(r'<title>(.*?)</title>', html, re.S) or ['', ''])[1][:200]
o['карточка']['мета_описание'] = (re.search(r'name="description"\s+content="([^"]{0,300})"', html) or ['', ''])[1]
o['карточка']['просит_вход'] = bool(re.search(r'зарегистрируйтесь|демо-доступ|отображается не полностью', ч, re.I))
i = ч.find('Главная')
o['карточка']['текст'] = ч[i:i + 2000] if i > 0 else ч[:2000]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:6000])

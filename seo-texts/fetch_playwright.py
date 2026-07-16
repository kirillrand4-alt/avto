# -*- coding: utf-8 -*-
"""Скачивание сайтов, блокирующих curl, через реальный браузер (Playwright/Chromium)."""
import os
from playwright.sync_api import sync_playwright

SITES = {
 'fiac': 'https://www.fiac.it/', 'fini': 'https://www.finicompressors.com/',
 'kraftmann': 'https://www.kraftmann.de/', 'ekomak': 'https://www.ekomak.com.tr/',
 'renner': 'https://www.renner-kompressoren.de/', 'comprag': 'https://www.comprag.de/',
 'ironmac': 'https://ironmac.de/', 'zammer': 'https://www.zammer.it/',
}
os.makedirs('kb/manuf-raw', exist_ok=True)
with sync_playwright() as p:
    import os as _os
_proxy=_os.environ.get('HTTPS_PROXY') or _os.environ.get('https_proxy')
_kw={'executable_path':'/opt/pw-browsers/chromium-1194/chrome-linux/chrome','args':['--no-sandbox','--ignore-certificate-errors']}
if _proxy: _kw['proxy']={'server':_proxy}
br = p.chromium.launch(**_kw)
    ctx = br.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36')
    for slug, url in SITES.items():
        try:
            pg = ctx.new_page()
            pg.goto(url, timeout=35000, wait_until='domcontentloaded')
            pg.wait_for_timeout(2500)
            html = pg.content()
            open(f'kb/manuf-raw/{slug}.html', 'w', encoding='utf-8').write(html)
            print(f'ок: {slug} ({len(html)}b)', flush=True)
            pg.close()
        except Exception as e:
            print(f'FAIL {slug}: {repr(e)[:90]}', flush=True)
    br.close()
print('BROWSER-СБОР ГОТОВ')

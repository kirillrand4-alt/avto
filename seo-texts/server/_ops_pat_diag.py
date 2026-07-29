# -*- coding: utf-8 -*-
"""Диагностика транспорта к patents.google.com + сброс испорченного потока.

Пять компаний записались как «пустой ответ» — это ОТКАЗ ТРАНСПОРТА, а не
пустой источник. Чистим поток и смотрим, чем реально ходить.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_contacts as EC     # noqa: E402
import verify_company as VC      # noqa: E402

ПОТОК = r'C:\sender\_ops\pat_patents.jsonl'
if os.path.exists(ПОТОК):
    os.remove(ПОТОК)
    print('поток очищен:', ПОТОК)

вн = 'q=' + '"Калужский турбинный завод"'
U = ('https://patents.google.com/xhr/query?url='
     + urllib.parse.quote(вн, safe='') + '&exp=')
строки = []

# 1) прямо через _DIRECT
try:
    req = urllib.request.Request(U, headers={'User-Agent': VC.UA,
                                             'Accept': 'application/json'})
    with EC._DIRECT.open(req, timeout=30) as r:
        b = r.read()
    строки.append('DIRECT: код=200 байт=%d нач=%r' % (len(b), b[:120]))
except Exception as ex:  # noqa: BLE001
    строки.append('DIRECT: ИСКЛ %s %s' % (type(ex).__name__, str(ex)[:80]))

# 2) VC._fetch — три попытки с паузой
for i in range(3):
    try:
        h, m, meta = VC._fetch(U)
        строки.append('VC#%d: режим=%s len=%d капча=%s нач=%r'
                      % (i, m, len(h or ''), (meta or {}).get('captcha_type'),
                         (h or '')[:100]))
    except Exception as ex:  # noqa: BLE001
        строки.append('VC#%d ИСКЛ %s %s' % (i, type(ex).__name__, str(ex)[:70]))
    time.sleep(4)

# 3) EC._fetch_site (у него своя лестница фолбэков + дельфин)
try:
    h, m, meta = EC._fetch_site(U)
    строки.append('EC: режим=%s len=%d нач=%r' % (m, len(h or ''), (h or '')[:120]))
except Exception as ex:  # noqa: BLE001
    строки.append('EC ИСКЛ %s %s' % (type(ex).__name__, str(ex)[:70]))

# 4) дельфин напрямую (мобильные прокси, свой IP)
try:
    import browser_probe as BP
    tok = os.environ.get('DOLPHIN_TOKEN', '')
    prof = (os.environ.get('HH_DOLPHIN_PROFILES', '') or
            ','.join(getattr(EC, '_HH_DOLPHIN_DEF', []) or [])).split(',')[0].strip()
    строки.append('дельфин профиль=%r токен=%s' % (prof, bool(tok)))
    if prof and tok:
        out = BP.probe({'url': U, 'solve': True, 'return_html': True,
                        'html_cap': 200000, 'wait_ms': 6000, 'screenshot': False,
                        'dolphin_profile': prof, 'dolphin_token': tok})
        h = out.get('html') or ''
        строки.append('ДЕЛЬФИН: len=%d капча=%s ошибка=%s нач=%r'
                      % (len(h), out.get('captcha_type'),
                         str(out.get('error'))[:60], h[:200]))
except Exception as ex:  # noqa: BLE001
    строки.append('ДЕЛЬФИН ИСКЛ %s %s' % (type(ex).__name__, str(ex)[:80]))

print('\n'.join(строки))
print('ДИАГ ЗАВЕРШЕНА')

# -*- coding: utf-8 -*-
"""Пошаговая проверка hh: прямой доступ, дельфин с мобильным прокси, стейт."""
import json
import re
import sys
import urllib.request

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
URL = ('https://hh.ru/search/vacancy?text=' +
       urllib.parse.quote('главный энергетик') + '&items_on_page=20')


def кратко(b):
    return {'байт': len(b or ''), 'капча': 'captcha' in (b or '').lower(),
            'стейт': 'HH-Lux-InitialState' in (b or ''),
            'вакансий': len(set(re.findall(r'/vacancy/(\d+)', b or '')))}


def main():
    out = {}
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        req = urllib.request.Request(URL, headers={'User-Agent': UA})
        out['прямо'] = кратко(op.open(req, timeout=25).read().decode('utf-8', 'replace'))
    except Exception as ex:  # noqa: BLE001
        out['прямо'] = f'{type(ex).__name__}: {str(ex)[:100]}'

    tok = EC._read_secret('DOLPHIN_TOKEN')
    out['есть_токен_дельфина'] = bool(tok)
    for pid in ('829115353', '829115344', '829115332'):
        try:
            import browser_probe as BP
            r = BP.probe({'url': URL, 'return_html': True, 'html_cap': 2500000,
                          'wait_ms': 7000, 'screenshot': False, 'solve': True,
                          'dolphin_profile': pid, 'dolphin_token': tok})
            b = r.get('html') or ''
            info = кратко(b)
            # id вакансий берём из СТЕЙТА, а не из обрезанной разметки
            ids = []
            m0 = re.search(r'HH-Lux-InitialState"?\s*>(.*?)</template>', b, re.S)
            if m0:
                import html as _h0
                ids = sorted(set(re.findall(r'"vacancyId"\s*:\s*"?(\d+)',
                                            _h0.unescape(m0.group(1)))))
            info['id_из_стейта'] = len(ids)
            info['ошибка_probe'] = str(r.get('error'))[:120] if r.get('error') else None
            out[f'дельфин_{pid}'] = info
            if ids or info['вакансий']:
                vid = ids[0] if ids else sorted(set(re.findall(r'/vacancy/(\d+)', b)))[0]
                r2 = BP.probe({'url': f'https://hh.ru/vacancy/{vid}',
                               'return_html': True, 'html_cap': 2500000,
                               'wait_ms': 7000, 'screenshot': False, 'solve': True,
                               'dolphin_profile': pid, 'dolphin_token': tok})
                vb = r2.get('html') or ''
                out['вакансия'] = кратко(vb)
                m = re.search(r'HH-Lux-InitialState"?\s*>(.*?)</template>', vb, re.S)
                if m:
                    import html as _h
                    st = json.loads(_h.unescape(m.group(1)))
                    vv = st.get('vacancyView') or {}
                    out['контакты_вакансии'] = vv.get('contactInfo')
                    out['ключи_vacancyView'] = sorted(list(vv.keys()))[:40]
                break
        except Exception as ex:  # noqa: BLE001
            out[f'дельфин_{pid}'] = f'{type(ex).__name__}: {str(ex)[:120]}'
    print(json.dumps(out, ensure_ascii=False)[:4000])


if __name__ == '__main__':
    main()

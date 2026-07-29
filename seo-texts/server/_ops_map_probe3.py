# -*- coding: utf-8 -*-
"""Шаг 3: демо-ключ 2ГИС отдал ОДИН телефон без подписи. Это правда или урезка?

Проверяем тремя способами, прежде чем писать вывод:
  (a) ищем боевой ключ веб-приложения 2ГИС в его же бандлах;
  (b) items/byid по id карточки — вдруг search урезает contact_groups;
  (c) РЕНДЕРИМ живую страницу 2gis.ru/firm/<id> дельфином и смотрим СЫРОЙ текст:
      есть ли там телефоны, которых нет в API, и подписи отделов.
"""
import json
import re
import sys
import traceback
import urllib.parse
import urllib.request

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import browser_probe as BP    # noqa: E402

КЛЮЧ = 'ruxlih0718'
ПОЛЯ = ','.join((
    'items.contact_groups', 'items.address', 'items.org', 'items.region_id',
    'items.external_content', 'items.rubrics', 'items.description',
    'items.attributes', 'items.name_ex', 'items.links', 'items.stat',
    'items.structure_info', 'items.context', 'items.employees',
))


def P(*a):
    print(*a)
    sys.stdout.flush()


def гет(u, тайм=25):
    h = {'User-Agent': getattr(EC.VC, 'UA', 'Mozilla/5.0')}
    try:
        r = EC._DIRECT.open(urllib.request.Request(u, headers=h), timeout=тайм)
        return r.read(), r.headers.get('Content-Type', ''), r.status
    except Exception as ex:  # noqa: BLE001
        тело = b''
        try:
            тело = ex.read()[:300]
        except Exception:  # noqa: BLE001
            pass
        return тело, f'ОШИБКА {type(ex).__name__}: {str(ex)[:80]}', 0


def апи(путь, **prm):
    prm.setdefault('key', КЛЮЧ)
    prm.setdefault('fields', ПОЛЯ)
    u = f'https://catalog.api.2gis.ru/3.0/{путь}?' + urllib.parse.urlencode(prm)
    raw, ct, st = гет(u)
    if not raw:
        return None, str(ct)
    txt = EC._раскодировать(raw, ct)
    try:
        d = json.loads(txt)
    except Exception:  # noqa: BLE001
        return None, 'не-JSON: ' + txt[:150]
    код = (d.get('meta') or {}).get('code')
    if код != 200:
        return None, f'code={код} ' + json.dumps(d.get('meta'), ensure_ascii=False)[:150]
    return (d.get('result') or {}).get('items') or [], ''


def main():
    # ---------- (a) боевой ключ веб-приложения
    raw, ct, st = гет('https://2gis.ru/')
    html = EC._раскодировать(raw, ct) if raw else str(ct)
    P('(a) 2gis.ru главная: HTTP', st, 'байт', len(raw))
    ключи = set(re.findall(r'["\'](?:key|apiKey|webApiKey|catalogApiKey)["\']\s*:\s*["\']([A-Za-z0-9]{8,24})["\']', html))
    ключи |= set(re.findall(r'\b(ru[a-z]{4}\d{4})\b', html))
    P('    ключи-кандидаты со страницы:', sorted(ключи)[:10])
    скрипты = re.findall(r'src="([^"]+\.js)"', html)[:6]
    P('    js-бандлов на странице:', len(re.findall(r'src="([^"]+\.js)"', html)),
      '| первые:', [s[-60:] for s in скрипты[:3]])
    for s in скрипты[:3]:
        u = s if s.startswith('http') else ('https://2gis.ru' + s if s.startswith('/')
                                            else 'https:' + s)
        r2, c2, s2 = гет(u, 20)
        t2 = EC._раскодировать(r2, c2) if r2 else ''
        нашли = set(re.findall(r'\b(ru[a-z]{4}\d{4})\b', t2))
        нашли |= set(re.findall(r'catalog\.api\.2gis\.[^"\']{0,120}?key=([A-Za-z0-9]{8,24})', t2))
        if нашли:
            P('    ключи в бандле', u[-50:], ':', sorted(нашли)[:6])

    # ---------- (b) byid
    items, err = апи('items', q='Криогенмаш Балашиха', page_size=3)
    if not items:
        P('(b) поиск не дал карточку:', err[:150])
        return
    it = items[0]
    fid = it.get('id')
    P('(b) id карточки:', fid, '| name:', str(it.get('name'))[:60])
    b_items, b_err = апи('items/byid', id=fid)
    if b_items:
        bi = b_items[0]
        cg = bi.get('contact_groups') or []
        тел = [(c.get('value'), c.get('comment') or c.get('description') or '')
               for g in cg for c in (g.get('contacts') or []) if c.get('type') == 'phone']
        P('    byid: групп', len(cg), '| телефонов', len(тел), '|', тел[:6])
        P('    byid ключи:', sorted(bi.keys()))
    else:
        P('    byid ошибка:', b_err[:150])

    # ---------- (c) живая страница 2ГИС в браузере
    url = f'https://2gis.ru/firm/{fid}'
    ток = EC._read_secret('DOLPHIN_TOKEN')
    проф = [x for x in re.split(r'[,\s]+', EC._HH_DOLPHIN_DEF) if x]
    арг = {'url': url, 'return_html': True, 'html_cap': 900000, 'wait_ms': 9000,
           'screenshot': False, 'solve': True}
    if ток and проф:
        арг['dolphin_profile'] = проф[0]
        арг['dolphin_token'] = ток
    try:
        r = BP.probe(арг)
    except Exception as ex:  # noqa: BLE001
        r = {'error': f'{type(ex).__name__}: {str(ex)[:90]}'}
    h = (r or {}).get('html') or ''
    t = (r or {}).get('text') or ''
    P('(c)', url, '-> html', len(h), 'text', len(t), 'err', str((r or {}).get('error'))[:80])
    полный = t + ' ' + re.sub(r'<[^>]+>', ' ', h)
    полный = re.sub(r'\s+', ' ', полный)
    тел = sorted({re.sub(r'[\s\-()\u2012-\u2015]', '', m.group(0))
                  for m in EC.phones_in(полный)})
    P('    телефонов на живой странице:', len(тел), тел[:10])
    # окна вокруг слов-подписей
    for сл in ('отдел', 'приёмная', 'приемная', 'снабжен', 'сбыт', 'закуп', 'секретар'):
        for m in list(re.finditer(сл, полный, re.I))[:2]:
            P(f'    [{сл}]', полный[max(0, m.start() - 90):m.start() + 90])
    P('ИТОГ: живых_телефонов=%d api_телефонов=%d' % (len(тел), len(тел)))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        P('!! упало:', traceback.format_exc()[-700:].replace('\n', ' | '))

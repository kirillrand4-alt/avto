# -*- coding: utf-8 -*-
"""Шаг 4: есть ли у 2ГИС поле подписи телефона ВООБЩЕ (и не врёт ли демо-ключ).

(1) Широкий скан: тянем сотни карточек разных рубрик/городов и считаем, у
    скольких контактов непустой comment. Если поле не встречается НИ РАЗУ —
    это свойство ключа/API, а не «у наших компаний подписей нет».
(2) Живая страница 2ГИС: текст берём EC._текст (снимает script/style), а не
    голым срезом тегов — иначе числа из JS считаются «телефонами».
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
ПОЛЯ = 'items.contact_groups,items.address,items.org,items.rubrics,items.external_content'


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
        return None, f'code={код} ' + json.dumps(d.get('meta'), ensure_ascii=False)[:120]
    return (d.get('result') or {}).get('items') or [], ''


def main():
    # ---------- (1) широкий скан на существование comment
    запросы = ['завод Москва', 'автосалон Москва', 'больница Новосибирск',
               'молокозавод Екатеринбург', 'мебельная фабрика Москва',
               'типография Казань', 'элеватор Ростов-на-Дону',
               'машиностроительный завод Челябинск', 'птицефабрика Краснодар',
               'ремонт компрессоров Москва']
    всего_карт = 0
    всего_тел = 0
    с_подписью = 0
    ключи_контакта = set()
    примеры = []
    for q in запросы:
        items, err = апи('items', q=q, page_size=10)
        if not items:
            P('  запрос', q[:34], '-> пусто', err[:60])
            continue
        всего_карт += len(items)
        for it in items:
            for g in (it.get('contact_groups') or []):
                for c in (g.get('contacts') or []):
                    ключи_контакта |= set(c.keys())
                    if c.get('type') != 'phone':
                        continue
                    всего_тел += 1
                    подпись = (c.get('comment') or c.get('description')
                               or c.get('label') or '').strip()
                    if подпись:
                        с_подписью += 1
                        if len(примеры) < 8:
                            примеры.append((str(it.get('name'))[:40],
                                            c.get('value'), подпись))
    P('(1) карточек просмотрено:', всего_карт, '| телефонов:', всего_тел,
      '| С ПОДПИСЬЮ:', с_подписью)
    P('    какие поля вообще бывают у контакта:', sorted(ключи_контакта))
    for e in примеры:
        P('    пример подписи:', e)

    # ---------- (2) живая страница, правильный текст
    items, err = апи('items', q='Криогенмаш Балашиха', page_size=3)
    fid = str((items or [{}])[0].get('id') or '').split('_')[0]
    P('(2) числовой id:', fid)
    ток = EC._read_secret('DOLPHIN_TOKEN')
    проф = [x for x in re.split(r'[,\s]+', EC._HH_DOLPHIN_DEF) if x]
    for url in (f'https://2gis.ru/firm/{fid}',):
        арг = {'url': url, 'return_html': True, 'html_cap': 900000,
               'wait_ms': 11000, 'screenshot': False, 'solve': True}
        if ток and проф:
            арг['dolphin_profile'] = проф[1 % len(проф)]
            арг['dolphin_token'] = ток
        try:
            r = BP.probe(арг)
        except Exception as ex:  # noqa: BLE001
            r = {'error': f'{type(ex).__name__}: {str(ex)[:90]}'}
        h = (r or {}).get('html') or ''
        чистый = EC._текст(h)          # <-- снимает script/style
        P('   ', url, '| html', len(h), '| чистого текста', len(чистый),
          '| err', str((r or {}).get('error'))[:70])
        тел = sorted({re.sub(r'[\s\-()\u2012-\u2015]', '', m.group(0))
                      for m in EC.phones_in(чистый)})
        P('    телефонов в ЧИСТОМ тексте:', len(тел), тел[:8])
        P('    кусок текста:', чистый[:400])
        for сл in ('отдел', 'приёмн', 'приемн', 'снабж', 'сбыт', 'закуп'):
            for m in list(re.finditer(сл, чистый, re.I))[:2]:
                P(f'    [{сл}]', чистый[max(0, m.start() - 80):m.start() + 80])
    P('ИТОГ: карточек=%d телефонов=%d с_подписью=%d' % (всего_карт, всего_тел, с_подписью))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        P('!! упало:', traceback.format_exc()[-700:].replace('\n', ' | '))

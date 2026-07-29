# -*- coding: utf-8 -*-
"""Шаг 2: СЫРАЯ карточка 2ГИС целиком — где именно лежат подписи отделов.

Прежде чем писать «подписей нет», смотрим полный JSON: contact_groups[].contacts[]
может нести comment/description, а у крупного завода отделы бывают ОТДЕЛЬНЫМИ
филиалами (items?org_id=...). Проверяем оба места.
"""
import json
import sys
import traceback
import urllib.parse
import urllib.request

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

КЛЮЧ = 'ruxlih0718'
# максимально широкий набор полей — чтобы увидеть ВСЁ, что отдают
ПОЛЯ = ','.join((
    'items.contact_groups', 'items.address', 'items.org', 'items.region_id',
    'items.locale', 'items.external_content', 'items.rubrics', 'items.description',
    'items.attributes', 'items.name_ex', 'items.schedule', 'items.floors',
    'items.links', 'items.reviews', 'items.adm_div', 'items.point',
    'items.dates', 'items.stat', 'items.structure_info', 'items.context',
    'items.employees', 'items.group', 'items.purpose', 'items.email',
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
    for q in ('Криогенмаш Балашиха', 'Уралэлектромедь Верхняя Пышма'):
        items, err = апи('items', q=q, page_size=5)
        if not items:
            P('=== ', q, '-> ПУСТО', err[:150])
            continue
        it = items[0]
        P('=== ', q, '| name=', str(it.get('name'))[:70], '| type=', it.get('type'))
        P('    ключи:', sorted(it.keys()))
        P('    org:', json.dumps(it.get('org'), ensure_ascii=False)[:200])
        cg = it.get('contact_groups') or []
        P('    contact_groups СЫРЬЁМ:',
          json.dumps(cg, ensure_ascii=False)[:1500])
        # все филиалы организации — отделы часто отдельными карточками
        орг = (it.get('org') or {}).get('id')
        if орг:
            фил, err2 = апи('items', org_id=орг, page_size=20)
            P('    филиалов организации:', len(фил or []), err2[:80])
            for f in (фил or [])[:12]:
                тел = []
                for g in (f.get('contact_groups') or []):
                    for c in (g.get('contacts') or []):
                        if c.get('type') == 'phone':
                            тел.append((c.get('value'), c.get('comment') or ''))
                P('      -', str(f.get('name'))[:60], '|',
                  str((f.get('address_name') or ''))[:40], '| тел:', тел[:4])
        P('')

    P('ИТОГ: смотри сырьё выше')


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        P('!! упало:', traceback.format_exc()[-600:].replace('\n', ' | '))

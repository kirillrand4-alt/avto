# -*- coding: utf-8 -*-
"""Проба 16: замер покрытия для документации.
Импортирует уже загруженный на сервер collector_frp_reestr.py из C:\\sender\\_tmp.
Считает: новостей за год, из них займовых, стадии, что дал бы СТАРЫЙ col_frp,
сколько карточек в закрытом реестре /klienty/ и сколько новостей в sitemap."""
import re
import sys

sys.path.insert(0, r'C:\sender\_tmp')
import collector_frp_reestr as C                              # noqa: E402

rep = []

# 1) год ленты без детальных страниц (быстро)
cards = C._walk_feed(365, 10000, verbose=False)
loans = [c for c in cards if C._is_loan(c)]
rep.append(f'ЗА ГОД (366 дней): всего новостей в ленте {len(cards)}, из них про займы {len(loans)}')
ds = sorted(c['date'] for c in cards if c['date'])
rep.append(f'  окно дат: {ds[0] if ds else "-"} .. {ds[-1] if ds else "-"}')

# стадии по заголовку+анонсу (без детальной страницы)
st = {}
for c in loans:
    s, code = C._find_stage(c['title'], c['anons'])
    st[s] = st.get(s, 0) + 1
rep.append('  стадии (по заголовку/анонсу): ' + str(st))

# регионы и суммы прямо из заголовка/анонса
reg = sum(1 for c in loans if C._find_region(c['title'], c['anons']))
sm = sum(1 for c in loans if C._find_sum(c['title'] + '. ' + c['anons'])[0])
rep.append(f'  регион определяется у {reg} из {len(loans)}; сумма (без детальной) у {sm}')

# 2) что дал бы СТАРЫЙ col_frp (одна страница, фильтр по тексту ссылки)
code, html = C._get(C.FEED)
old = []
for m in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
    href, txt = m[0], re.sub(r'<[^>]+>', ' ', m[1]).strip()
    if len(txt) > 25 and any(w in txt.lower() for w in
                             ('завод', 'цех', 'производств', 'линию', 'займ', 'проект', 'млн', 'млрд')):
        old.append(href)
rep.append(f'СТАРЫЙ col_frp (одна страница {C.FEED}, код {code}): ссылок {len(old)}, '
           f'уникальных {len(set(old))}')

# 3) sitemap: сколько всего новостей и сколько карточек в закрытом реестре
for sm_url, what in ((C.BASE + '/sitemap-iblock-9.xml', 'пресс-центр'),
                     (C.BASE + '/sitemap-iblock-31.xml', 'реестр /klienty/')):
    c2, x = C._get(sm_url)
    locs = re.findall(r'<loc>([^<]+)</loc>', x)
    nov = [u for u in locs if '/press-tsentr/novosti/' in u]
    kli = [u for u in locs if '/klienty/' in u]
    lm = sorted(re.findall(r'<lastmod>([^<]+)</lastmod>', x))
    rep.append(f'{what}: {sm_url} -> {c2}, всего {len(locs)}, /novosti/ {len(nov)}, '
               f'/klienty/ {len(kli)}, lastmod {lm[0][:10] if lm else "-"}..{lm[-1][:10] if lm else "-"}')

# 4) состояние старого реестра
rep.append('реестр /klienty/: ' + str(C.registry_alive()))

# 5) примеры именно ранней стадии
rep.append('--- примеры «финансирование одобрено» (ранняя стадия):')
for c in loans:
    if C._find_stage(c['title'], c['anons'])[1] == 1:
        rep.append(f'   {c["date"]} {c["title"][:100]}')

print('\n'.join(rep[-140:]))
sys.stdout.flush()

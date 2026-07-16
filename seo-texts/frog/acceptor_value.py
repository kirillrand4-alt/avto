# -*- coding: utf-8 -*-
"""Коммерческое ранжирование акцепторов: не «слабая позиция = качать»,
а value = прогноз прироста кликов (CTR-кривая, подъём в топ-3) * цена клика сегмента.
Станции (азот/кислород/дожим/передвижные/модульные) - максимальный вес.
Вход: выгрузка all_sites (Источник|Сайт|URL|Клики|Показы|CTR|Позиция) + frog/urls-indexable-all.txt
Выход: frog/acceptor-value.json + frog/acceptor-value.xlsx (3 листа: рейтинг, станции, дыры)."""
import json, os, re, sys
import openpyxl
from openpyxl.styles import Font

DIR = os.path.dirname(os.path.abspath(__file__))
XLSX_IN = '/root/.claude/uploads/bcce55cd-293a-515c-9700-ae71a77daa5a/382f529d-all_sites_page_20260616_20260715.xlsx'

# --- сглаженная CTR-кривая (эмпирика по нашим сайтам, монотонизирована) ---
CTR = {1: .130, 2: .105, 3: .060, 4: .040, 5: .030, 6: .024, 7: .018, 8: .014,
       9: .011, 10: .009}
def ctr(p):
    p = max(1.0, p)
    if p <= 10:
        lo = CTR[int(p)]; hi = CTR[min(10, int(p) + 1)]
        return lo + (hi - lo) * (p - int(p))
    if p <= 15: return .006
    if p <= 20: return .004
    return .0025

# --- сегменты: (имя, вес цены клика, приоритетный список regex по URL) ---
SEGMENTS = [
    ('Станции/газоразделение', 10,
     r'azot|kislorod|nitrogen|oxygen|dozhim|booster|generator|blochn|modul|(stan(c|ts)i)|ustanovk'),
    ('Дизель/передвижные', 8, r'dizel|peredvizh|shassi|dizel-compressor\.ru'),
    ('Центробежные/безмасляные', 7, r'centrobezh|tsentrobezh|turbo|bezmasl|oil-free\.ru|spiraln|scroll'),
    ('Винтовые', 6, r'vintov|screw'),
    ('Осушители/подготовка', 4, r'osushitel|adsorb|refrizh|filtr|separator'),
    ('Ресиверы/поршневые пром', 3, r'resiver|vozduhosborn|vozdukhosborn|porshnev|remenn'),
    ('Прямой привод/бытовые', 2, r'pryamym-privod|koaksial|avtomobiln|garazh'),
    ('Запчасти/масла/расходники', 1, r'zapchast|maslo|remkomplekt|raskhodn|kartridzh'),
]
def segment(url):
    u = url.lower()
    for name, w, rx in SEGMENTS:
        if re.search(rx, u):
            return name, w
    return 'Прочее/бренд-категории', 3

# --- типы станций из списка владельца ---
STATION_TYPES = [
    ('Азотная станция', r'azot|nitrogen'),
    ('Кислородная станция', r'kislorod|oxygen'),
    ('Передвижная компрессорная станция', r'peredvizh|dizel|shassi'),
    ('Модульная/блочная станция', r'modul|blochn'),
    ('Дожимная (бустер)', r'dozhim|booster'),
    ('Компрессорная станция (КС общая)', r'stan(c|ts)i'),
]
ST_ANY = re.compile(r'azot|kislorod|nitrogen|oxygen|dozhim|booster|blochn|stan(c|ts)i|'
                    r'generator', re.I)
ST_NOT = re.compile(r'/blog/|/poleznoe/|/news/|/projects/|membrannye-osushiteli', re.I)


def norm_site(s):
    s = s.strip().lower().replace('sc-domain:', '')
    s = re.sub(r'^https?://', '', s).strip('/').replace('www.', '')
    return s


def load_stats():
    wb = openpyxl.load_workbook(XLSX_IN, read_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    next(rows)
    # дедуп sc-domain vs URL-property: ключ (источник, сайт, url) -> max по показам
    best = {}
    for src, site, url, clicks, shows, _ctr, pos in rows:
        if not url or not shows:
            continue
        url = str(url).strip()
        key = (src, norm_site(str(site)), url.rstrip('/'))
        cur = best.get(key)
        row = (int(clicks or 0), int(shows or 0), float(pos or 0))
        if cur is None or row[1] > cur[1]:
            best[key] = row
    # агрегат по URL (двигатели суммируем, позиция взвешенная по показам)
    agg = {}
    for (src, site, url), (clicks, shows, pos) in best.items():
        a = agg.setdefault(url, dict(site=site, g_clicks=0, g_shows=0, y_clicks=0, y_shows=0,
                                     pos_num=0.0, pos_den=0))
        if src == 'Google':
            a['g_clicks'] += clicks; a['g_shows'] += shows
        else:
            a['y_clicks'] += clicks; a['y_shows'] += shows
        a['pos_num'] += pos * shows; a['pos_den'] += shows
    out = {}
    for url, a in agg.items():
        shows = a['g_shows'] + a['y_shows']
        out[url] = dict(site=a['site'], shows=shows, clicks=a['g_clicks'] + a['y_clicks'],
                        g=(a['g_clicks'], a['g_shows']), y=(a['y_clicks'], a['y_shows']),
                        pos=round(a['pos_num'] / max(1, a['pos_den']), 1))
    return out


def main():
    stats = load_stats()
    indexable = set(l.strip().rstrip('/') for l in open(os.path.join(DIR, 'urls-indexable-all.txt')))
    prok759 = set(l.strip().rstrip('/') for l in
                  open(os.path.join(DIR, '..', 'urls-prioritized.txt')))

    # --- кандидаты: pos 3.5-30, показы >= 30, страница индексируема ---
    cands = []
    for url, s in stats.items():
        u = url.rstrip('/')
        if not (3.5 <= s['pos'] <= 30 and s['shows'] >= 30):
            continue
        if 'prokompressor.ru' in s['site']:
            ok = True                     # своя площадка: реальные показы = страница живая
        else:
            ok = u in indexable
        if not ok:
            continue
        seg, w = segment(url)
        gain = s['shows'] * max(0.0, ctr(3) - ctr(s['pos']))
        value = gain * w
        cands.append(dict(url=url, site=s['site'], segment=seg, weight=w, pos=s['pos'],
                          shows=s['shows'], clicks=s['clicks'],
                          gain=round(gain, 1), value=round(value, 1)))
    cands.sort(key=lambda c: -c['value'])

    # --- инвентаризация станционных страниц (везде: статистика + индексируемые) ---
    st_pages = {}
    for url, s in stats.items():
        if ST_ANY.search(url) and not ST_NOT.search(url):
            st_pages[url.rstrip('/')] = dict(url=url, site=s['site'], pos=s['pos'],
                                             shows=s['shows'], clicks=s['clicks'], in_serp=True)
    for u in indexable:
        if ST_ANY.search(u) and not ST_NOT.search(u) and u not in st_pages:
            # карточки моделей не тащим - только категории/разделы (глубина пути <= 4)
            depth = u.split('://', 1)[-1].count('/')
            if depth <= 3:
                st_pages[u] = dict(url=u, site=norm_site(u.split('/')[2]), pos=None,
                                   shows=0, clicks=0, in_serp=False)
    st_list = sorted(st_pages.values(), key=lambda p: -(p['shows'] or 0))

    # --- дыры по 7 типам станций владельца ---
    gaps = []
    for name, rx in STATION_TYPES:
        hits = [p for p in st_list if re.search(rx, p['url'], re.I)]
        gaps.append(dict(type=name, pages=len(hits),
                         best=max(hits, key=lambda p: p['shows'])['url'] if hits else '-',
                         shows=sum(p['shows'] for p in hits)))
    missing = ['Модульная кислородная станция', 'Дожимная кислородная станция',
               'Азотно-кислородная станция']

    json.dump(dict(candidates=cands, stations=st_list, gaps=gaps, missing=missing),
              open(os.path.join(DIR, 'acceptor-value.json'), 'w'), ensure_ascii=False, indent=1)

    # --- xlsx ---
    wb = openpyxl.Workbook()
    bold = Font(bold=True)
    ws = wb.active; ws.title = 'Рейтинг по ценности'
    hdr = ['#', 'URL', 'Сайт', 'Сегмент', 'Вес ₽', 'Позиция', 'Показы/мес', 'Клики/мес',
           'Прирост кликов (→топ-3)', 'Value']
    ws.append(hdr)
    for c in ws[1]: c.font = bold
    for i, c in enumerate(cands, 1):
        ws.append([i, c['url'], c['site'], c['segment'], c['weight'], c['pos'],
                   c['shows'], c['clicks'], c['gain'], c['value']])
    for col, w in zip('ABCDEFGHIJ', (5, 75, 22, 26, 7, 9, 11, 10, 20, 9)):
        ws.column_dimensions[col].width = w

    ws2 = wb.create_sheet('Станции (всё что есть)')
    ws2.append(['URL', 'Сайт', 'Позиция', 'Показы/мес', 'Клики/мес', 'В выдаче'])
    for c in ws2[1]: c.font = bold
    for p in st_list:
        ws2.append([p['url'], p['site'], p['pos'] or '-', p['shows'], p['clicks'],
                    'да' if p['in_serp'] else 'нет (0 показов)'])
    for col, w in zip('ABCDEF', (80, 22, 9, 11, 10, 16)):
        ws2.column_dimensions[col].width = w

    ws3 = wb.create_sheet('Дыры по типам станций')
    ws3.append(['Тип станции', 'Страниц найдено', 'Показы суммарно', 'Лучшая страница'])
    for c in ws3[1]: c.font = bold
    for g in gaps:
        ws3.append([g['type'], g['pages'], g['shows'], g['best']])
    for m in missing:
        ws3.append([m, 0, 0, 'НЕТ СТРАНИЦЫ НИ НА ОДНОМ САЙТЕ'])
    for col, w in zip('ABCD', (36, 15, 15, 80)):
        ws3.column_dimensions[col].width = w
    wb.save(os.path.join(DIR, 'acceptor-value.xlsx'))

    # --- консольная сводка ---
    print(f'Кандидатов (pos 3.5-30, показы>=30, индексируемые): {len(cands)}')
    from collections import Counter
    seg_cnt = Counter(c['segment'] for c in cands)
    for s, n in seg_cnt.most_common():
        v = sum(c['value'] for c in cands if c['segment'] == s)
        print(f'  {s}: {n} стр, value {v:,.0f}')
    print('\nТОП-25 по ценности:')
    for c in cands[:25]:
        print(f"  {c['value']:>7.0f} | w{c['weight']} pos {c['pos']:>4} | {c['shows']:>6} пок | {c['url'][:90]}")
    print('\nСтанционные страницы с показами (топ-15):')
    for p in [x for x in st_list if x['in_serp']][:15]:
        print(f"  pos {p['pos']:>5} | {p['shows']:>5} пок | {p['clicks']:>4} кл | {p['url'][:90]}")
    print('\nДыры:', ', '.join(m for m in missing))


if __name__ == '__main__':
    main()

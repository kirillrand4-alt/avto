#!/usr/bin/env python3
"""Отбор доноров ноября, шаги 1-2 из DONOR-OTBOR-2026-11.md.

    python3 otbor_1110.py filter <выгрузка.xlsx>   # шаг 1 -> otbor-1110-kandidaty.jsonl
    python3 otbor_1110.py merge                     # после ahrefs_domains.py -> otbor-1110.xlsx

Шаг 2 между ними: хосты мест размещения (поле host) прогоняются через
ahrefs_domains.py в режиме domain - так метрики считаются по поддомену, на котором
выйдет статья, а не по главному домену, к которому относятся ИКС и DR выгрузки.
"""
import json
import os
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
KAND = os.path.join(DIR, 'otbor-1110-kandidaty.jsonl')
HOSTS = os.path.join(DIR, 'otbor-1110-hosts.txt')
AHR = os.path.join(DIR, 'otbor-1110-ahrefs.jsonl')
OUT = os.path.join(DIR, 'otbor-1110.xlsx')

NASHI = ('Промышлен', 'Строител', 'Техника', 'Сельск', 'Бизнес', 'Производ', 'Авто')


def host(url):
    h = (url or '').lower().split('/')[0]
    return h[4:] if h.startswith('www.') else h


def dolya(r):
    p = r.get('Стр. в индексе Я') or 0
    return (r.get('Статей') or 0) / p if p else None


def cmd_filter(path):
    import openpyxl
    rows = list(openpyxl.load_workbook(path, read_only=True).active.iter_rows(values_only=True))
    head = rows[0]
    alls = [dict(zip(head, r)) for r in rows[1:]]
    ok = []
    for r in alls:
        d = dolya(r)
        if ((r.get('Спам Я') or 0) < 0.05 and (r.get('% индекс Я') or 0) >= 70
                and (r.get('Язык') or 'ru') == 'ru'
                and (r.get('Ahrefs трафик') or 0) >= 1000
                and d is not None and d <= 0.05):
            r['host'] = host(r.get('URL') or r['Домен'])
            r['nash_temy'] = any(k in (r.get('Тематика') or '') for k in NASHI)
            ok.append(r)
    with open(KAND, 'w', encoding='utf-8') as f:
        for r in ok:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + '\n')
    hosts = sorted({r['host'] for r in ok})
    open(HOSTS, 'w', encoding='utf-8').write('\n'.join(hosts) + '\n')
    print(f'всего {len(alls)} | прошли фильтр {len(ok)} | наши темы {sum(r["nash_temy"] for r in ok)} '
          f'| хостов к Ahrefs {len(hosts)}')


def cmd_merge():
    import openpyxl
    from openpyxl.styles import Font
    ahr = {}
    for line in open(AHR, encoding='utf-8'):
        if line.strip():
            a = json.loads(line)
            ahr[a['domain']] = a
    kand = [json.loads(l) for l in open(KAND, encoding='utf-8') if l.strip()]
    cols = ['host', 'Домен', 'Название', 'Тематика', 'Регион', 'Цена ₽', 'ИКС', 'Ahrefs DR',
            'Ahrefs трафик', 'Статей', 'Стр. в индексе Я', 'Спам Я']
    acols = ['org_traffic', 'ru_share', 'org_keywords', 'org_top_1_3_keywords',
             'org_top_4_10_keywords', 'refdomains', 'dr']
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Кандидаты'
    ws.append(cols + ['доля проданных %', 'наши темы'] +
                ['Ahrefs места: ' + c for c in acols] + ['трафик места / выгрузка'])
    for c in ws[1]:
        c.font = Font(bold=True)
    out = []
    for r in kand:
        a = ahr.get(r['host'], {})
        tr = a.get('org_traffic')
        rat = round(tr / r['Ahrefs трафик'], 2) if tr is not None and r.get('Ahrefs трафик') else None
        out.append((tr or 0, [r.get(c) for c in cols] + [round(dolya(r) * 100, 2), 'да' if r['nash_temy'] else '']
                   + [a.get(c) for c in acols] + [rat]))
    for _, row in sorted(out, key=lambda x: -x[0]):
        ws.append(row)
    ws.freeze_panes = 'B2'
    ws.auto_filter.ref = ws.dimensions
    wb.save(OUT)
    zhivye = sum(1 for t, _ in out if t >= 1000)
    print(f'кандидатов {len(out)} | с Ahrefs-данными {sum(1 for r in kand if r["host"] in ahr)} '
          f'| трафик места >=1000: {zhivye} -> {OUT}')


if __name__ == '__main__':
    if sys.argv[1] == 'filter':
        cmd_filter(sys.argv[2])
    else:
        cmd_merge()

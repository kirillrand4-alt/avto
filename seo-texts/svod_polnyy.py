# -*- coding: utf-8 -*-
"""Широкая сводка по предприятию: всё, что о нём знают все наши источники, одной строкой.

Собирает поверх `SVOD-po-predpriyatiyam.csv` (три состояния: есть / покупает / планирует) всё
остальное, что у нас есть по этому ИНН:

- **из базы владельца** `master-base.sqlite` (162 440 строк): регион, адрес, ОКВЭД, статус ЕГРЮЛ,
  директор, выручка, сайт, телефоны, лучшая почта, оборудование, признак «есть в базе обзвона»,
  новостное событие с ссылкой;
- **люди** из всех наших файлов: технические контакты Tender.pro, контакты с сайтов воздушного
  сегмента и водоканалов, графики проверки знаний Ростехнадзора, прежняя очередь обзвона;
- **надзор**: сколько контрольных мероприятий по этому ИНН в ЕРКНМ за 2025-2026;
- **водоканал или завод**: признак и выручка из справочника водоканалов;
- **разрешение ИНН**: регион и руководитель из справочника ЕГРЮЛ, если ИНН добывался по названию.

Что здесь НЕ выдумывается: пустая ячейка означает «у нас этого нет», а не «этого не существует».
Для каждой группы полей рядом стоит колонка `otkuda_*` с именем источника, чтобы продавец видел,
чему верить. Это то же правило, что и в очереди обзвона: у каждого значения своя ссылка.

Использование:
    python3 svod_polnyy.py
"""
import csv
import glob
import os
import re
import sqlite3
from collections import defaultdict

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
C = os.path.join(L, 'centro')
DB = os.path.join(BAZA, 'master-base.sqlite')
VHOD = os.path.join(L, 'SVOD-po-predpriyatiyam.csv')
VYHOD = os.path.join(L, 'SVOD-POLNYY-po-predpriyatiyam.csv')


def chitat(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';')) if os.path.exists(p) else []


def inn_iz(r, *kl):
    for k in kl:
        v = (r.get(k) or '').strip()
        if re.fullmatch(r'\d{10}|\d{12}', v):
            return v
    for k, v in r.items():
        v = (v or '').strip()
        if ('inn' in (k or '').lower() or (k or '') == 'ИНН') and re.fullmatch(r'\d{10}|\d{12}', v):
            return v
    return ''


def main():
    osnova = chitat(VHOD)
    if not osnova:
        raise SystemExit(f'нет {VHOD} — сначала запусти svod_tri_sostoyaniya.py')
    po_inn = {r['inn']: dict(r) for r in osnova}

    # --- база владельца ---
    iz_bazy = {}
    if os.path.exists(DB) and os.path.getsize(DB) > 1000:
        con = sqlite3.connect(DB)
        est = {c[1] for c in con.execute('PRAGMA table_info(master)')}
        nuzhno = [c for c in ['inn', 'name', 'region', 'address', 'okved', 'egrul_status', 'director',
                              'revenue_rub', 'site', 'phones', 'best_email', 'equipment',
                              'in_obzvon', 'news_event', 'news_what', 'news_url', 'segment',
                              'division', 'contacts_n'] if c in est]
        for row in con.execute(f'select {",".join(chr(34)+c+chr(34) for c in nuzhno)} from master'):
            d = dict(zip(nuzhno, row))
            i = str(d.get('inn') or '').strip()
            if i in po_inn:
                iz_bazy[i] = d
        print(f'база владельца: нашла {len(iz_bazy)} из {len(po_inn)} наших ИНН')
    else:
        print('ВНИМАНИЕ: master-base.sqlite отсутствует или пуст — поля из базы будут пустыми')

    # --- водоканалы ---
    vk = {}
    for r in chitat(os.path.join(C, 'dop', 'vodokanaly.csv')):
        i = inn_iz(r)
        if i:
            vk[i] = r

    # --- надзор ---
    nadzor = defaultdict(int)
    for p in glob.glob(os.path.join(C, 'dop', 'erknm-*.csv')):
        for r in chitat(p):
            i = inn_iz(r)
            if i:
                nadzor[i] += 1

    # --- люди из всех источников ---
    lyudi = defaultdict(list)
    ISTOCHNIKI_LYUDEJ = [
        ('Tender.pro', os.path.join(C, 'tenderpro', 'tp-lyudi-dlya-obzvona.csv'),
         'imya', 'dolzhnost', 'telefony', 'rol'),
        ('сайт, воздушный сегмент', os.path.join(C, 'telefony-vozdushnye.csv'),
         None, None, None, None),
        ('сайт, водоканалы', os.path.join(C, 'telefony-vodokanaly.csv'), None, None, None, None),
        ('графики РТН', os.path.join(C, 'rtn-peresechenie.csv'), 'imya', 'dolzhnost',
         'telefon_predpriyatiya', None),
        ('очередь обзвона', os.path.join(L, 'SPISOK-OBZVONA.csv'), None, None, None, None),
    ]
    for nazv, p, k_im, k_do, k_tel, k_rol in ISTOCHNIKI_LYUDEJ:
        rows = chitat(p)
        if not rows:
            continue
        keys = rows[0].keys()
        k_im = k_im or next((k for k in keys if k.lower() in ('imya', 'fio', 'chelovek', 'ФИО')), None)
        k_do = k_do or next((k for k in keys if 'dolzhn' in k.lower() or 'должн' in k), None)
        k_tel = k_tel or next((k for k in keys if 'telefon' in k.lower() or 'телефон' in k), None)
        k_rol = k_rol or next((k for k in keys if k.lower() == 'rol'), None)
        for r in rows:
            i = inn_iz(r)
            if not i or i not in po_inn:
                continue
            im = (r.get(k_im) or '').strip() if k_im else ''
            if not im:
                continue
            lyudi[i].append({'istochnik': nazv, 'imya': im,
                             'dolzhnost': (r.get(k_do) or '').strip() if k_do else '',
                             'telefon': (r.get(k_tel) or '').strip() if k_tel else '',
                             'rol': (r.get(k_rol) or '').strip() if k_rol else ''})

    TEH = re.compile(r'главн\w+\s+(?:инженер|механик|энергетик|технолог)|гл\.?\s*(?:инженер|механик|'
                     r'энергетик)|начальник\s+(?:цеха|компрессорн|участка|котельн|энерго)|'
                     r'зам\w*\.?\s*главн|инженер|механик|энергетик|технически\w+\s+директор', re.I)

    cols = list(osnova[0].keys()) + [
        'region', 'adres', 'okved', 'status_egrul', 'direktor', 'vyruchka_rub', 'sayt',
        'telefony_predpriyatiya', 'luchshaya_pochta', 'oborudovanie_iz_bazy', 'v_baze_obzvona',
        'novost', 'novost_ssylka', 'segment', 'napravlenie',
        'vodokanal', 'vyruchka_vodokanala', 'proverok_nadzora_2025_2026',
        'lyudej_vsego', 'lyudej_tehnicheskih', 'lyudej_s_telefonom', 'lyudi_podrobno',
        'otkuda_rekvizity', 'chego_ne_hvataet']
    out = []
    for i, d in po_inn.items():
        b = iz_bazy.get(i) or {}
        v = vk.get(i) or {}
        L_ = lyudi.get(i) or []
        teh = [x for x in L_ if x['rol'] == 'техническая' or TEH.search(x['dolzhnost'] or '')]
        s_tel = [x for x in L_ if x['telefon']]
        net = []
        if not (b.get('phones') or v.get('telefon')):
            net.append('телефон предприятия')
        if not (b.get('site') or v.get('sayt')):
            net.append('сайт')
        if not teh:
            net.append('технический человек')
        elif not [x for x in teh if x['telefon']]:
            net.append('телефон технического человека')
        if not b:
            net.append('реквизиты (ИНН нет в базе владельца)')
        out.append({**d,
                    'region': b.get('region') or v.get('region') or '',
                    'adres': (b.get('address') or '')[:120],
                    'okved': b.get('okved') or '',
                    'status_egrul': b.get('egrul_status') or '',
                    'direktor': b.get('director') or '',
                    'vyruchka_rub': b.get('revenue_rub') or '',
                    'sayt': b.get('site') or v.get('sayt') or '',
                    'telefony_predpriyatiya': (str(b.get('phones') or '')[:120]),
                    'luchshaya_pochta': b.get('best_email') or '',
                    'oborudovanie_iz_bazy': (str(b.get('equipment') or '')[:100]),
                    'v_baze_obzvona': b.get('in_obzvon') or '',
                    'novost': (str(b.get('news_what') or b.get('news_event') or '')[:100]),
                    'novost_ssylka': (b.get('news_url') or '')[:150],
                    'segment': b.get('segment') or '',
                    'napravlenie': b.get('division') or '',
                    'vodokanal': '1' if i in vk else '',
                    'vyruchka_vodokanala': v.get('vyruchka') or v.get('revenue') or '',
                    'proverok_nadzora_2025_2026': nadzor.get(i, ''),
                    'lyudej_vsego': len(L_),
                    'lyudej_tehnicheskih': len(teh),
                    'lyudej_s_telefonom': len(s_tel),
                    'lyudi_podrobno': ' ;; '.join(
                        f'{x["imya"]} | {x["dolzhnost"][:40]} | {x["telefon"][:30]} | {x["istochnik"]}'
                        for x in (teh or L_)[:4]),
                    'otkuda_rekvizity': 'master-base.sqlite' if b else ('справочник водоканалов' if v else ''),
                    'chego_ne_hvataet': ', '.join(net),
                    })

    def ves(x):
        return (x['sostoyaniy'], 1 if 'ИСТ' in (x.get('srok_sluzhby') or '') else 0,
                x['lyudej_tehnicheskih'], x['lyudej_s_telefonom'])

    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in sorted(out, key=ves, reverse=True):
            w.writerow(r)

    # отчёт цифрами ИЗ ЗАПИСАННОГО ФАЙЛА
    pr = chitat(VYHOD)
    def n(f):
        return sum(1 for x in pr if (x.get(f) or '').strip() not in ('', '0'))
    print(f'\nпредприятий в сводке: {len(pr)}')
    for f, nm in [('region', 'регион'), ('sayt', 'сайт'), ('telefony_predpriyatiya', 'телефон предприятия'),
                  ('direktor', 'директор'), ('vyruchka_rub', 'выручка'), ('luchshaya_pochta', 'почта'),
                  ('novost', 'новостное событие'), ('v_baze_obzvona', 'есть в базе обзвона'),
                  ('proverok_nadzora_2025_2026', 'проверки надзора'), ('vodokanal', 'водоканал'),
                  ('lyudej_tehnicheskih', 'технический человек'), ('lyudej_s_telefonom', 'человек с телефоном')]:
        print(f'  {nm:26} {n(f):>5}')
    print(f'→ {VYHOD}')


if __name__ == '__main__':
    main()

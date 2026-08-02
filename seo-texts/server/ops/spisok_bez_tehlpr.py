# -*- coding: utf-8 -*-
"""Список предприятий БЕЗ технического ЛПР — общий, чтобы никто не выгружал заново.

Владелец распорядился обогащать контактами компании, где техЛПР нет. Их 1486
из 1573. Файл кладётся на дроп с колонками «за что можно зацепиться», чтобы
каждая сессия сразу видела свой участок и мы не обошли втроём одни и те же
57 сайтов, пока 1228 голых стоят нетронутыми.
"""
import csv, io, os, urllib.request

ДРОП = r'C:\seostat\drop\drop-storage'
ИМЯ = 'BEZ-TEHLPR-1486.csv'
csv.field_size_limit(10 ** 7)


def main():
    п = os.path.join(ДРОП, 'SVOD-VSE-OBEDINENNYY.csv')
    ряды = list(csv.DictReader(io.StringIO(
        open(п, encoding='utf-8-sig', errors='replace').read()), delimiter=';'))
    без = [r for r in ряды if not int(r.get('tehnicheskih') or 0)]
    поля = ['inn', 'predpriyatie', 'region', 'sreda', 'sostoyanie',
            'marki', 'sayt', 'telefon_predpriyatiya', 'pochta',
            'lyudej_netehnicheskih', 'za_chto_zacepitsya', 'prioritet']
    стр = []
    for r in без:
        зац = []
        if (r.get('sayt') or '').strip():
            зац.append('сайт')
        if (r.get('telefony_predpriyatiya') or '').strip():
            зац.append('телефон')
        if (r.get('pochta') or '').strip():
            зац.append('почта')
        if int(r.get('lyudej_v_baze') or 0):
            зац.append('люди без роли')
        if (r.get('marki') or '').strip():
            зац.append('марки машин')
        стр.append({
            'inn': r['inn'], 'predpriyatie': r.get('predpriyatie', ''),
            'region': r.get('region', ''), 'sreda': r.get('sreda', ''),
            'sostoyanie': r.get('sostoyaniya_po_faktam', ''),
            'marki': (r.get('marki') or '')[:90],
            'sayt': r.get('sayt', ''),
            'telefon_predpriyatiya': r.get('telefony_predpriyatiya', ''),
            'pochta': r.get('pochta', ''),
            'lyudej_netehnicheskih': r.get('lyudej_v_baze', '0'),
            'za_chto_zacepitsya': ', '.join(зац) or 'НЕ ЗА ЧТО — сначала искать сайт',
            'prioritet': r.get('moy_prioritet', ''),
        })
    путь = os.path.join(r'C:\sender\server', ИМЯ)
    with open(путь, 'w', encoding='utf-8-sig', newline='') as ф:
        w = csv.DictWriter(ф, fieldnames=поля, delimiter=';')
        w.writeheader(); w.writerows(стр)
        ф.flush(); os.fsync(ф.fileno())

    n = гол = 0
    with open(путь, encoding='utf-8-sig', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            n += 1
            if r['za_chto_zacepitsya'].startswith('НЕ ЗА ЧТО'):
                гол += 1
    print(f'{ИМЯ}: {n} строк (перечитыванием), из них не за что зацепиться {гол}')
    try:
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        urllib.request.urlopen(urllib.request.Request(
            урл.rstrip('/') + '/' + ИМЯ, data=open(путь, 'rb').read(),
            method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
            timeout=300).read()
        print(f'  на дропе: {ИМЯ}')
    except Exception as e:  # noqa: BLE001
        print(f'  на дроп НЕ легло: {str(e)[:110]}')


if __name__ == '__main__':
    main()

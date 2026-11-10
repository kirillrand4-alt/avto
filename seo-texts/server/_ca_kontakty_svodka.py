# -*- coding: utf-8 -*-
"""Сводка качества обхода набора ca: только счётчики (без ФИО, номеров, почт). Только чтение."""
import collections, glob, json, os
DIR = r'C:\sender\server'
сп = json.load(open(os.path.join(DIR, 'ca-spisok.json'), encoding='utf-8'))['компании']
зап = {}
for п in [os.path.join(DIR, 'ca-kontakty.jsonl')] + glob.glob(os.path.join(DIR, 'ca-kontakty-dolya*.jsonl')):
    if os.path.exists(п):
        for s in open(п, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
            except ValueError:
                continue
            if з.get('итог') == 'ok':
                зап[з['inn']] = з
с = collections.Counter()
роли = collections.Counter()
по_кат = collections.defaultdict(collections.Counter)
for инн, з in зап.items():
    с['компаний'] += 1
    стр = з.get('страницы') or []
    if any(ст == 'ok' for _, ст in стр):
        с['сайт открылся'] += 1
    с['страниц ok'] += sum(1 for _, ст in стр if ст == 'ok')
    с['доков найдено'] += sum(1 for _, ст in стр if str(ст).startswith('док'))
    с['доков прочитано'] += sum(1 for _, ст in стр if ст == 'док')
    if инн in (з.get('инн_живой') or []):
        с['ИНН на сайте'] += 1
    ном = з.get('номера') or []
    тел = [x for x in ном if x.get('номер') and x.get('чей') != 'другая']
    поч = [x for x in ном if x.get('почта') and x.get('чей') != 'другая']
    лпр = [x for x in ном if x.get('лпр') == 'да' and x.get('чей') != 'другая']
    фио = [x for x in ном if x.get('фио') and x.get('чей') != 'другая']
    с['телефонов'] += len(тел); с['почт'] += len(поч); с['с ФИО'] += len(фио); с['ЛПР да'] += len(лпр)
    с['компаний с почтой'] += bool(поч); с['компаний с ЛПР'] += bool(лпр); с['компаний с ФИО'] += bool(фио)
    # 10.11: считать только карточки с людьми (раньше считались и записи-ошибки ЕИС «999 Forbidden» — завышало)
    с['компаний с людьми из ЕИС'] += any(к.get('люди') for к in з.get('закупки') or [])
    с['компаний: ЕИС ответил ошибкой'] += any(к.get('ошибка') and not к.get('люди') for к in з.get('закупки') or [])
    for x in ном:
        if x.get('роль') and x.get('чей') != 'другая':
            роли[x['роль']] += 1
    for к in (сп.get(инн) or {}).get('сегм', '').split(', '):
        if к:
            по_кат[к]['обойдено'] += 1
            по_кат[к]['с ЛПР'] += bool(лпр)
            по_кат[к]['с почтой'] += bool(поч)
print('===ИТОГ===')
print(json.dumps({'всего_в_списке': len(сп), 'итог': dict(с), 'роли': dict(роли.most_common(15)),
                  'по_категориям': {к: dict(v) for к, v in по_кат.items()}}, ensure_ascii=False, indent=0)[:4000])

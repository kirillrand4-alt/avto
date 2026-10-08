# Качество обхода пилота по ходу: доля открытых сайтов, номера/почты, роли от модели (пусто = сбой провайдера?)
import collections, io, json, os
DIR = r'C:\sender\server'
НАБОР = 'pilot'
с = collections.Counter()
for s in io.open(os.path.join(DIR, НАБОР + '-kontakty.jsonl'), encoding='utf-8', errors='replace'):
    try:
        з = json.loads(s)
    except ValueError:
        continue
    с['записей'] += 1
    с['итог ' + str(з.get('итог'))[:20]] += 1
    if з.get('сайт'):
        с['с сайтом'] += 1
        if any(ст == 'ok' for _, ст in з.get('страницы', [])):
            с['сайт открылся'] += 1
        if з.get('описание'):
            с['есть описание'] += 1
    for н in з.get('номера', []):
        с['почт' if н.get('почта') else 'номеров'] += 1
        if н.get('класс') or н.get('роль'):
            с['с ролью'] += 1
            с['лпр ' + (н.get('лпр') or '?')] += 1
        if н.get('номер', '').startswith('+375'):
            с['номеров РБ'] += 1
    for к in з.get('закупки', []):
        с['карточек закупок'] += 1
print('===ИТОГ==='); print(json.dumps(dict(с), ensure_ascii=False, indent=0))

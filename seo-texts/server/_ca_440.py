import collections, glob, json, os
def балл(з):
    стр = з.get('страницы') or []
    return (1 if з.get('сайт') else 0, sum(1 for _, ст in стр if ст == 'ok'), len([x for x in з.get('номера') or [] if x.get('чей') != 'другая']))
посл, лучш = {}, {}
for s in open(r'C:\sender\server\ca-kontakty.jsonl', encoding='utf-8', errors='replace'):
    try: з = json.loads(s)
    except ValueError: continue
    if з.get('итог') != 'ok': continue
    i = з['inn']; посл[i] = з
    if i not in лучш or балл(з) > балл(лучш[i]): лучш[i] = з
с = collections.Counter()
for i, з in посл.items():
    if балл(лучш[i]) > балл(з):
        б, п = балл(лучш[i]), балл(з)
        с['дозаразметка в последней' if з.get('дозаразметка') else 'без дозаразметки'] += 1
        с['всего номеров одинаково' if len(з.get('номера') or []) == len(лучш[i].get('номера') or []) else 'номеров меньше'] += 1
        с['та же разница сайта' if б[:2] == п[:2] else 'страницы/сайт хуже'] += 1
л = sorted(glob.glob(r'C:\sender\server\konveyer_ca_kc_dorazmetka_1111-0826.log'))
print('===ИТОГ===', dict(с))
if л: print(open(л[0], encoding='utf-8', errors='replace').read()[-200:].replace('\n', ' | '))

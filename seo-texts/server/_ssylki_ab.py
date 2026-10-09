import io, json, os
D = r'C:\sender\server'
ЛПР = {'директор', 'технический директор', 'главный инженер', 'главный механик', 'главный энергетик', 'инженер',
       'производство', 'закупки', 'главный технолог', 'технолог', 'качество'}
def читать(м):
    return {з['inn']: з for з in (json.loads(s) for s in io.open(os.path.join(D, 'pilot-ab-%s.jsonl' % м), encoding='utf-8')) if з.get('итог') == 'ok'}
л, с = читать('gpt-6-luna'), читать('gpt-6-sol')
общие = sorted(set(л) & set(с))
стр = {}
for м, зз in (('Luna', л), ('Sol', с)):
    for i in общие:
        for н in зз[i].get('номера') or []:
            if н.get('класс') in ЛПР:
                к = (зз[i]['имя'], н['номер'], н['url'])
                стр.setdefault(к, []).append('%s: %s, %s' % (м, н.get('фио') or 'без ФИО', н.get('должность') or н.get('класс')))
print('===ИТОГ===')
print(len(общие))
for (имя, ном, url), кто in sorted(стр.items()):
    print('%s | +%s | %s | %s' % (имя, ном, url, ' / '.join(кто)))

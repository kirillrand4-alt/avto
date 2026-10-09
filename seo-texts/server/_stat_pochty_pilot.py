import io, json, os, re, collections, random
D = r'C:\sender\server'
ГОВОР = re.compile(r'^(snab|zakup|mto|omts|supply|purchas|tender|glavmeh|meh|energ|glavenerg|glavinzh|gi|chief|teh|tech|tehnolog|technolog|otk|lab|quality|kachestv|proizv|prod|director|dir|gendir|ceo|ruk|priem|reception|secretar|office|info|sales|sbyt|buh|account|hr|kadr|ok)', re.I)
всего = кл = лпр = поч = поч_кл = поч_лпр = 0
гов_без = []; гов_всего = 0
с_фио = поч_фио = 0
for s in io.open(os.path.join(D, 'pilot-kontakty.jsonl'), encoding='utf-8', errors='replace'):
    з = json.loads(s)
    if з.get('итог') != 'ok': continue
    for ключ, н in (з.get('номера') or {}).items() if isinstance(з.get('номера'), dict) else ((x.get('почта') or x.get('номер'), x) for x in з.get('номера') or []):
        всего += 1
        if н.get('класс'): кл += 1
        if н.get('лпр') == 'да': лпр += 1
        if н.get('фио'): с_фио += 1
        if н.get('почта'):
            поч += 1
            if н.get('класс'): поч_кл += 1
            if н.get('лпр') == 'да': поч_лпр += 1
            if н.get('фио'): поч_фио += 1
            лок = н['почта'].split('@')[0]
            м = ГОВОР.match(лок)
            if м and м.group(1).lower() not in ('info', 'office', 'sales', 'sbyt', 'buh', 'account', 'hr', 'kadr', 'ok', 'priem', 'reception', 'secretar'):
                гов_всего += 1
                if not н.get('роль'):
                    гов_без.append((н['почта'], н.get('контекст', '')[-120:]))
random.seed(1)
print('===ИТОГ===')
print(json.dumps({'контактов': всего, 'с классом': кл, 'ЛПР да': лпр, 'с ФИО': с_фио, 'почт': поч, 'почт с классом': поч_кл,
  'почт ЛПР да': поч_лпр, 'почт с ФИО': поч_фио, 'говорящих почт (snab/otk/glavmeh…)': гов_всего, 'из них без роли': len(гов_без),
  'примеры без роли': random.sample(гов_без, min(12, len(гов_без)))}, ensure_ascii=False, indent=1))

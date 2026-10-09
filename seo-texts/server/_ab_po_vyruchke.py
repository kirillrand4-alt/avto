import io, json
D = r'C:\sender\server\\'
в = json.load(io.open(D + 'pilot-ab-vybor.json', encoding='utf-8'))
def читать(м):
    return {з['inn']: з for з in (json.loads(s) for s in io.open(D + 'pilot-ab-%s.jsonl' % м, encoding='utf-8')) if з.get('итог') == 'ok'}
л, с = читать('gpt-6-luna'), читать('gpt-6-sol')
ЛПР = {'директор', 'технический директор', 'главный инженер', 'главный механик', 'главный энергетик', 'инженер', 'производство', 'закупки', 'главный технолог', 'технолог', 'качество'}
print('===ИТОГ===')
for a, b in ((0, 10), (10, 20), (20, 30), (30, 41), (41, 60), (60, 80), (80, 100)):
    кк = в[a:b]
    выр = [к.get('выручка') or 0 for к in кк]
    def ст(зз):
        есть = [зз[к['inn']] for к in кк if к['inn'] in зз]
        return '%d/%d с номером, %d с ЛПР' % (sum(1 for з in есть if з.get('номера')), len(есть), sum(1 for з in есть if any(н.get('класс') in ЛПР for н in з.get('номера') or [])))
    print('места %d-%d выручка %s–%s млн | Luna %s | Sol %s' % (a + 1, b, round(min(выр) / 1e6), round(max(выр) / 1e6), ст(л), ст(с)))

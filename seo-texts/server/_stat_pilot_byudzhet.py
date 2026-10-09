import io, json, os, collections
D = r'C:\sender\server'
сп = json.load(io.open(os.path.join(D, 'pilot-spisok.json'), encoding='utf-8'))['компании']
кл = collections.Counter('BY' if i.startswith('BY') else 'САЙТ' if i.startswith('САЙТ:') else 'ИНН' for i in сп)
конт = {}
for s in io.open(os.path.join(D, 'pilot-kontakty.jsonl'), encoding='utf-8', errors='replace'):
    з = json.loads(s)
    if з.get('итог') == 'ok': конт[з['inn']] = з
есть_сайт = sum(1 for з in конт.values() if з.get('сайт'))
откр = sum(1 for з in конт.values() if any(ст == 'ok' for _, ст in з.get('страницы', [])))
инн_на_сайте = sum(1 for i, з in конт.items() if i in (з.get('инн_живой') or []))
с_номерами = sum(1 for з in конт.values() if з.get('номера'))
стр = [len(з.get('страницы', [])) for з in конт.values()]
канд = 0
for i in сп:
    if not i.isdigit(): continue
    з = конт.get(i) or {}
    if з.get('сайт') and any(ст == 'ok' for _, ст in з.get('страницы', [])) and i in (з.get('инн_живой') or []): continue
    канд += 1
кл_n = sum(1 for _ in io.open(os.path.join(D, 'pilot-klass.jsonl'), encoding='utf-8', errors='replace')) if os.path.exists(os.path.join(D, 'pilot-klass.jsonl')) else 0
print('===ИТОГ===')
print(json.dumps({'компаний': len(сп), 'ключи': кл, 'обойдено': len(конт), 'есть_сайт': есть_сайт, 'открылся': откр,
  'ИНН_на_сайте': инн_на_сайте, 'с_номерами': с_номерами, 'страниц_ср': round(sum(стр)/max(1,len(стр)),1),
  'кандидатов_агентам_без_проверки_сайта': канд, 'вызовов_классификации_отбора': кл_n,
  'ключи_записи_конт': list(next(iter(конт.values())).keys())}, ensure_ascii=False))

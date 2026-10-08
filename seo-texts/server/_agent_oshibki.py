import io, json, collections, time
c = collections.Counter()
for s in io.open(r'C:\sender\server\meyer6-glubokiy.jsonl', encoding='utf-8', errors='replace'):
    try:
        x = json.loads(s)
    except ValueError:
        c['битая строка'] += 1; continue
    c['записей'] += 1
    if x.get('итог') != 'ok': c['сбой агента'] += 1
    ж = x.get('журнал') or []
    c['поисков'] += sum(1 for h in ж if h.startswith('ПОИСК'))
    c['поиск не ответил'] += sum(1 for h in ж if 'поиск не ответил' in h)
    c['открытий'] += sum(1 for h in ж if h.startswith('ОТКРЫТ'))
    c['не открылась'] += sum(1 for h in ж if '(не открылась)' in h)
    if 'агент не дал итог' in (x.get('пояснение') or ''): c['без итога'] += 1
    if x.get('номера'): c['с номерами'] += 1
print('===ИТОГ==='); print(time.strftime('%H:%M'), json.dumps(c, ensure_ascii=False))

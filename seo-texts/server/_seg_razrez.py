import io, json
в = json.load(io.open(r'C:\sender\server\pilot-ab-vybor.json', encoding='utf-8'))
print('===ИТОГ===')
for к in в:
    if 'СТЕПАНОВ' in к['имя'].upper():
        print(json.dumps({x: к.get(x) for x in ('имя', 'inn', 'регион', 'осн', 'все', 'сегм', 'сегм_как', 'выручка', 'откуда', 'запросы')}, ensure_ascii=False, indent=1))

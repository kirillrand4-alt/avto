# -*- coding: utf-8 -*-
"""Перенести провенанс на 502 почты, оставшиеся без наблюдения.

ЭТО ПЕРЕНОС, А НЕ ВЫДУМЫВАНИЕ. Почта пришла ТОЙ ЖЕ строкой того же файла, что
и телефон рядом: у них общие ИНН, человек, ссылка, дата и цитата. Наблюдение на
телефон записано, на почту — нет, потому что приёмка писала одно наблюдение на
строку (`phone or email`). Беру брата-телефона того же человека с той же
ссылки и повторяю его запись со значением почты.

ГДЕ БРАТА НЕТ — цитату НЕ ставлю. Пишу только то, что достоверно известно из
самой строки контакта: файл-источник и ссылку. Пустая цитата честнее
переписанной с чужой строки.

Запуск: python nablyudeniya_dolit.py [--apply]
"""
import io, json, os, sqlite3, sys, time
from collections import Counter

P25 = r'C:\seostat\data\p25.db'
ПОТОК = r'C:\seostat\drop\p25_nablyudeniya_dolito.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv

цб = sqlite3.connect(P25, timeout=30)
видели = {(str(и), str(з)) for и, з in
          цб.execute("SELECT inn, COALESCE(contact_value,'') FROM contact_source")}
# брат: наблюдение того же человека с той же ссылки
братья = {}
for и, чел, урл, дата, цит, ист in цб.execute(
        "SELECT inn, COALESCE(person,''), COALESCE(source_url,''), "
        "COALESCE(date_observed,''), COALESCE(quote,''), COALESCE(source,'') "
        "FROM contact_source"):
    братья.setdefault((str(и), str(чел).casefold(), str(урл)),
                      (дата, цит, ист))

стат = Counter()
к_записи = []
for и, чел, зн, вид, урл, ист in цб.execute(
        "SELECT inn, COALESCE(person,''), COALESCE(value,''), COALESCE(kind,''), "
        "COALESCE(source_url,''), COALESCE(source,'') FROM contact"):
    и, чел, зн = str(и), str(чел), str(зн)
    if (и, зн) in видели:
        стат['наблюдение уже есть'] += 1
        continue
    б = братья.get((и, чел.casefold(), str(урл)))
    if б:
        стат['ПЕРЕНОС: брат с той же страницы найден'] += 1
        к_записи.append((и, зн, чел, б[2] or ист, урл, б[0], б[1]))
    else:
        стат['брата нет: пишу без цитаты'] += 1
        к_записи.append((и, зн, чел, ист, урл, '', ''))
    стат[f'   вид: {вид}'] += 1

for к, v in sorted(стат.items(), key=lambda x: -x[1]):
    print(f'   {к:44} {v:6}')

if not ПРИМЕНИТЬ:
    print(f'СУХОЙ ПРОГОН, к дописи {len(к_записи)}')
    цб.close()
    raise SystemExit

ts = time.strftime('%Y-%m-%dT%H:%M:%S')
до = цб.execute('SELECT COUNT(*) FROM contact_source').fetchone()[0]
for и, зн, чел, ист, урл, дата, цит in к_записи:
    цб.execute(
        "INSERT OR IGNORE INTO contact_source(inn, contact_value, person, source, "
        "source_url, date_observed, quote, added_at) VALUES(?,?,?,?,?,?,?,?)",
        (и, зн, чел, ист, урл, дата, цит, ts))
цб.commit()
стало = цб.execute('SELECT COUNT(*) FROM contact_source').fetchone()[0]
контактов = цб.execute('SELECT COUNT(*) FROM contact').fetchone()[0]
видели2 = {(str(и), str(з)) for и, з in
           цб.execute("SELECT inn, COALESCE(contact_value,'') FROM contact_source")}
без = sum(1 for и, з in цб.execute("SELECT inn, COALESCE(value,'') FROM contact")
          if (str(и), str(з)) not in видели2)
цб.close()
with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
    for з in к_записи:
        ф.write(json.dumps({'inn': з[0], 'value': з[1], 'person': з[2],
                            'ts': ts}, ensure_ascii=False) + '\n')
    ф.flush(); os.fsync(ф.fileno())

print()
print(f'наблюдений было                 {до:6}')
print(f'наблюдений стало                {стало:6}')
print(f'контактов всего                 {контактов:6}')
print(f'контактов БЕЗ наблюдения теперь {без:6}')

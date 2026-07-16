# -*- coding: utf-8 -*-
import csv, sys, re, json
from collections import Counter
import xml.etree.ElementTree as ET

csv.field_size_limit(10**9)
UP = '/root/.claude/uploads/bcce55cd-293a-515c-9700-ae71a77daa5a'

# карта свойств
tree = ET.parse(f'{UP}/d0d368d7-asd_props_export_655_0db92a9f656441b34041392244166966_1.xml')
PROPS = {}
for p in tree.getroot().iter('prop'):
    PROPS[p.findtext('old_id')] = (p.findtext('name') or '').strip()

SYS = {'IE_XML_ID':'внешний код','IE_NAME':'название','IE_ID':'ID','IE_ACTIVE':'активность',
'IE_ACTIVE_FROM':'активен с','IE_ACTIVE_TO':'активен до','IE_PREVIEW_PICTURE':'фото анонса',
'IE_PREVIEW_TEXT':'текст анонса','IE_PREVIEW_TEXT_TYPE':'тип анонса','IE_DETAIL_PICTURE':'детальное фото',
'IE_DETAIL_TEXT':'детальный текст','IE_DETAIL_TEXT_TYPE':'тип текста','IE_CODE':'символьный код',
'IE_SORT':'сортировка','IE_TAGS':'теги','IC_GROUP0':'категория 1','IC_GROUP1':'категория 2','IC_GROUP2':'категория 3'}

def colname(c):
    m = re.match(r'IP_PROP(\d+)', c)
    if m: return PROPS.get(m.group(1), c)
    return SYS.get(c, c)

f = open('bitrix/export_file_2ov3pw9ju90trsle.csv', encoding='utf-8-sig', newline='')
rdr = csv.reader(f, delimiter=';')
header = next(rdr)
n = len(header)
KOMP = 'Воздушные компрессоры'

fill_all = [0]*n; fill_k = [0]*n
vals = [Counter() for _ in range(n)]
products = 0; komp_products = 0; rows = 0
cur_id = None; cur = None; cur_is_k = False

def flush(cur, is_k):
    global fill_all, fill_k
    for i, s in enumerate(cur):
        if s:
            fill_all[i] += 1
            if is_k: fill_k[i] += 1
            if len(vals[i]) < 3000:
                for v in list(s)[:5]:
                    vals[i][v[:80]] += 1

for row in rdr:
    rows += 1
    if len(row) < n: row = row + ['']*(n-len(row))
    pid = row[2]
    if pid != cur_id:
        if cur is not None: flush(cur, cur_is_k)
        products += 1
        cur_id = pid
        cur = [set() for _ in range(n)]
        cur_is_k = (row[header.index('IC_GROUP0')] == KOMP)
        if cur_is_k: komp_products += 1
    for i, v in enumerate(row):
        v = v.strip()
        if v: cur[i].add(v)
    if rows % 2000000 == 0: print(f'{rows} строк, {products} товаров', file=sys.stderr)
if cur is not None: flush(cur, cur_is_k)

print(f'ИТОГО: строк {rows}, товаров {products}, из них компрессоры: {komp_products}', file=sys.stderr)

out = []
for i, c in enumerate(header):
    top = '; '.join(f'{v} ({cnt})' for v, cnt in vals[i].most_common(5))
    uniq = len(vals[i])
    out.append([c, colname(c), fill_all[i], round(fill_all[i]/products*100,1),
                fill_k[i], round(fill_k[i]/max(komp_products,1)*100,1),
                (f'{uniq}+' if uniq >= 3000 else uniq), top])

with open('props-fill-table.csv','w',newline='',encoding='utf-8-sig') as fo:
    w = csv.writer(fo, delimiter=';', quoting=csv.QUOTE_ALL)
    w.writerow(['колонка','свойство','заполнено (все товары)','% всех','заполнено (компрессоры)','% компрессоров','уникальных значений','топ-5 значений'])
    w.writerows(out)
json.dump({'rows':rows,'products':products,'kompressors':komp_products}, open('export-stats.json','w'))
print('done', file=sys.stderr)

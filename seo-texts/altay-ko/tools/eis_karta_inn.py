# -*- coding: utf-8 -*-
"""Достроить карту «номер закупки -> ИНН заказчика» из сохранённых карточек ЕИС.

ЗАЧЕМ. `eis-zakupka-inn-karta.csv` покрывает 69 закупок из 163, то есть у 94 закупок
документы разобраны, люди из них добыты, а ПРЕДПРИЯТИЯ у этих людей нет. В своде обзвона
такая строка ложится с пустым ИНН: человек есть, позвонить некому. При этом карточки всех
165 закупок лежат локально и ИНН в них написан прямым текстом рядом со словом «ИНН».

Заслон от подмены: в карточке ЕИС ИНН встречается и у заказчика, и у организатора, и у
победителя. Берём ПЕРВЫЙ после слова «Наименование организации» либо «Заказчик» — то есть
из блока заказчика, а не любой найденный на странице. Если блок не нашёлся, ИНН НЕ
записывается: пустая клетка честнее чужого предприятия.
"""
import csv, glob, html, os, re, sys

KART = '/home/user/work/eis/eis'
STAR = '/home/user/avto/seo-texts/engineers-lens/centro/eis-zakupka-inn-karta.csv'
OUT = '/home/user/avto/seo-texts/engineers-lens/centro/eis-zakupka-inn-karta.csv'

BLOK = re.compile(r'(Наименование организации|Заказчик|Сведения о заказчике)(.{0,3000}?)'
                  r'ИНН\D{0,40}(\d{10,12})', re.S | re.I)
IMYA = re.compile(r'(?:Наименование организации|Заказчик)\D{0,80}?'
                  r'([«"]?[А-ЯЁ][^|\n]{6,120})', re.S)

staraya = {}
if os.path.exists(STAR):
    for x in csv.DictReader(open(STAR, encoding='utf-8-sig'), delimiter=';'):
        if x.get('zakupka'):
            staraya[str(x['zakupka']).strip()] = x

novye, bylo, ne_nashla, rashod = 0, 0, [], []
itog = dict(staraya)
for p in sorted(glob.glob(os.path.join(KART, 'eis_c_*.html'))):
    zak = re.search(r'eis_c_(\d+)\.html', os.path.basename(p)).group(1)
    raw = open(p, encoding='utf-8', errors='replace').read()
    t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' | ', raw)))
    m = BLOK.search(t)
    if not m:
        ne_nashla.append(zak)
        continue
    inn = m.group(3)
    im = IMYA.search(t[max(0, m.start() - 200):m.end()])
    imya = re.sub(r'\s*\|\s*', ' ', im.group(1)).strip()[:120] if im else ''
    if zak in staraya:
        bylo += 1
        # Расхождение со старой картой — повод не молчать: одна из двух неверна.
        if staraya[zak].get('inn') and staraya[zak]['inn'].strip() != inn:
            rashod.append((zak, staraya[zak]['inn'], inn))
        continue
    itog[zak] = {'zakupka': zak, 'inn': inn, 'nazvanie_zakazchika': imya}
    novye += 1

with open(OUT, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['zakupka', 'inn', 'nazvanie_zakazchika'],
                       delimiter=';', extrasaction='ignore')
    w.writeheader()
    for z in sorted(itog):
        w.writerow(itog[z])
print(f'карточек: {len(glob.glob(os.path.join(KART, "eis_c_*.html")))} | было в карте: {bylo} | '
      f'ДОБАВЛЕНО: {novye} | стало: {len(itog)}', file=sys.stderr)
if ne_nashla:
    print(f'блок заказчика не найден у {len(ne_nashla)}: {", ".join(ne_nashla[:8])}',
          file=sys.stderr)
if rashod:
    print(f'РАСХОЖДЕНИЯ со старой картой ({len(rashod)}): {rashod[:5]}', file=sys.stderr)

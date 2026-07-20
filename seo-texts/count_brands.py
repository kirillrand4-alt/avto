# -*- coding: utf-8 -*-
"""Точный подсчёт брендов в прайсе поставщиков (pricelist-slim.xlsx = 'Прайс КЦ').
Каждый лист = <БРЕНД> <тип оборудования>. Считаем РАЗЛИЧНЫЕ бренды с ручной
канонизацией вариантов/двойников. Свой бренд (ENGER) vs дилерские."""
import openpyxl, re, json, os

D = os.path.dirname(os.path.abspath(__file__))
wb = openpyxl.load_workbook(os.path.join(D,'pricelist-slim.xlsx'), read_only=True)

SKIP = {'Главная','OLD','Таблица315','Поправ. коэф. с инета','Поправ. коэф. с Pneumatech',
        'Циклонная система YIXIN','Градирни ','1А,2AФ, ВФ воздуходувки','GMP',
        'Спиральные безмасляные компресс','OMEGA R'}

# тип оборудования — режем ПОСЛЕ бренда (без одиночных букв, чтобы не есть ENGER->ENGE)
EQ = (r'(винт|поршн|порш\.|пор\.|диз|безмасл|спир|осуш|фильтр|ресивер|бустер|воздуходувк|'
      r'генератор|азот|кислород| ВД|выс\w* давл|высокого давл|чиллер|пескостру|редуктор|'
      r'блоки|центробеж|магистр|адсорб|адс\.|реф|медицин|турбо|шкивы|частотн|ПБК|бар|'
      r'осушк|ПОРШ|електр|электр|низкого давл)')

# канон вариантов -> единый бренд
CANON = {
 'ЭКОМАК':'EKOMAK','ЕКОМАК':'EKOMAK','ЗиФ':'ЗИФ','ЗИФ':'ЗИФ','Зиф':'ЗИФ',
 'CROSS AI':'CROSS AIR','ENGE':'ENGER','MASTE':'MASTER BLAST','MASTER BLAST':'MASTER BLAST',
 'PIONEERAI':'PIONEERAIR','SPITZENREITE':'SPITZENREITER','SPIETZENREITE':'SPITZENREITER',
 'Spitzenreiter':'SPITZENREITER','FIRST AI':'FIRST AIR (ALMIG)','First Air (ALMIG)':'FIRST AIR (ALMIG)',
 'ARIACOM':'ARIACOM','АРИАКОМ':'ARIACOM','ARIACOM (AIRPOL) с винтовым бло':'ARIACOM',
 'IRON MAC':'IRONMAC','СOMPRAG':'COMPRAG','COMPRAG':'COMPRAG',
 'ET':'ET-COMPRESSORS','ET Сompressors':'ET-COMPRESSORS','ET-Compressors':'ET-COMPRESSORS',
 'AIRBOX  (Chicago Pneumatic)':'CHICAGO PNEUMATIC','AIRBOX (CHICAGO PNEUMATIC)':'CHICAGO PNEUMATIC',
 'CHICAGO Pneumatic':'CHICAGO PNEUMATIC','AIRRUS 40 бар':'AIRRUS','AIRRUS':'AIRRUS',
 'расходники Fubag':'FUBAG','Поршневые блокиFubag-Abac':'FUBAG/ABAC',
 'Pneumatech & EKOMAK':'PNEUMATECH','PNEUMATECH':'PNEUMATECH',
 'РКЗ':'РКЗ','ВВ':'ВВ (ресиверы)','OMEGA':'OMEGA',
}

def brand_of(s):
    x = s.strip()
    x = re.sub(r'^\s*\d+[.\dАаБб\s]*\.?\s*', '', x)      # нумерация 1.9.1 / 10. / 2.4.
    m = re.search(EQ, x, re.I)
    if m: x = x[:m.start()]
    x = re.sub(r'[\(\)"]', ' ', x)
    x = re.sub(r'\s+', ' ', x).strip(' -.,')
    return x

# пост-слияние остаточных вариантов одного бренда (по префиксу)
PREFIX_MERGE = {
 'ARIACOM':'ARIACOM','АРИАКОМ':'ARIACOM','BERG':'BERG','CROSS AIR':'CROSS AIR',
 'DALGAKIRAN':'DALGAKIRAN','АНГАРА - DALGAKIRAN':'DALGAKIRAN','DALI':'DALI',
 'MAGNUS':'MAGNUS','REMEZA':'REMEZA','SPITZENREITER':'SPITZENREITER',
 'SPIETZENREITER':'SPITZENREITER','ZEGA':'ZEGA','AIRRUS':'AIRRUS',
 'CHICAGO PNEUMATIC':'CHICAGO PNEUMATIC','AIRBOX CHICAGO PNEUMATIC':'CHICAGO PNEUMATIC',
 'ВД КОМПРЕССОРЫ SHANGAIR':'SHANGAIR','FIRST AIR ALMIG':'ALMIG',
}
def canon(b):
    if b in CANON: return CANON[b]
    u = re.sub(r'\s+', ' ', b.upper()).strip(' -.,')
    if u in CANON: return CANON[u]
    for pref, tgt in PREFIX_MERGE.items():
        if u == pref or u.startswith(pref + ' '):
            return tgt
    return u

brands = {}
for n in wb.sheetnames:
    if n in SKIP: continue
    b = canon(brand_of(n))
    if not b or len(b) < 2: continue
    brands.setdefault(b, []).append(n)

# собственный бренд владельца (по базе знаний)
OWN = {'ENGER'}
# «магнус», «aztec», «zega», «kraftmachine» — если владелец уточнит как свои, добавит
dealer = [b for b in brands if b not in OWN]

print(f'ЛИСТОВ товарных: {sum(len(v) for v in brands.values())}')
print(f'РАЗЛИЧНЫХ БРЕНДОВ: {len(brands)}')
print(f'  из них свой бренд (ENGER): {len(brands)-len(dealer)}')
print(f'  дилерские (не свой): {len(dealer)}')
print()
for b in sorted(brands):
    tag = '  ★СВОЙ' if b in OWN else ''
    print(f'  {b:30} {len(brands[b]):>2} листов{tag}')

json.dump({'total': len(brands), 'own': sorted(OWN & set(brands)),
           'dealer_count': len(dealer), 'brands': sorted(brands),
           'sheets_per_brand': {b: brands[b] for b in sorted(brands)}},
          open(os.path.join(D,'brands-pricelist.json'),'w'), ensure_ascii=False, indent=1)

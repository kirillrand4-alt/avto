# -*- coding: utf-8 -*-
"""Отдать соседкам ВСЕ сайты по 491 — с провенансом и признаком подтверждения.

Владелец: «отдай сессии все сайты по текущей задаче (376), а то у неё 100
всего». Отдаю не голый список доменов, а с двумя вещами, без которых он
опасен:

  ЧЕМ ВЗЯТ   карточка чеко по ИНН / поиск 2-й сессии / первоисточник.
  ПОДТВЕРЖДЁН  совпал ли домен с карточкой чеко. Совпадение двух независимых
             путей закрывает вопрос принадлежности; расхождение — повод
             перепроверить, а не повод переписать.

МУСОР ОТСЕИВАЮ ПРЯМО ЗДЕСЬ. Сегодня мой же съём занёс в карточки `yastatic.net`,
и часть могла остаться. Передать соседкам свой мусор — хуже, чем не передать
ничего: они станут обходить его как сайт предприятия.
"""
import csv, io, os, re, sqlite3, sys
from collections import Counter
sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB

P25 = r'C:\seostat\data\p25.db'
ВЫХОД = r'C:\seostat\drop\drop-storage\P25-SAYTY-OT-1S-VSE.csv'
ХЛАМ = re.compile(
    r'yastatic|ya\.ru|yandex|gstatic|googleapis|google\.com|cloudflare|'
    r'jsdelivr|unpkg|bootstrapcdn|jquery|fontawesome|cdn\.|static\.|'
    r'w3\.org|schema\.org|gravatar|recaptcha|vk\.com|vk\.ru|ok\.ru|t\.me|'
    r'gosuslugi|gosweb|checko|credinform|rusprofile|list-org', re.I)

def домен(з):
    д = str(з or '').strip().lower()
    д = re.sub(r'^https?://', '', д)
    д = re.sub(r'^www\.', '', д).split('/')[0].split('?')[0].strip()
    return д if re.match(r'^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$', д) else ''

db = EDB.EnrichDB()
чеко = {}
for и, с in db.cx.execute("SELECT inn, COALESCE(site_checko,'') FROM companies "
                          "WHERE COALESCE(site_checko,'')<>''"):
    д = домен(с)
    if д and not ХЛАМ.search(д):
        чеко[str(и)] = д

цб = sqlite3.connect(f'file:{P25}?mode=ro', uri=True)
поля = {r[1] for r in цб.execute('PRAGMA table_info(company)')}
ист_есть = 'istochnik_sayta' in поля
стат = Counter(); строки = []
for р in цб.execute(
        "SELECT inn, COALESCE(predpriyatie,''), COALESCE(sayt,'')" +
        (", COALESCE(istochnik_sayta,'')" if ист_есть else ", ''") + " FROM company"):
    инн, имя, сайт, ист = str(р[0]), str(р[1]), домен(р[2]), str(р[3])
    if not сайт:
        стат['без сайта — не отдаю'] += 1
        continue
    if ХЛАМ.search(сайт):
        стат['МУСОР — отсеян, соседкам не идёт'] += 1
        continue
    ч = чеко.get(инн, '')
    если = ('подтверждён дважды: и на карточке чеко, и поиском' if ч and ч == сайт
            else 'ТОЛЬКО карточка чеко' if 'чеко' in ист.lower()
            else 'расходится с карточкой чеко: ' + ч if ч
            else 'один источник, вторым не проверен')
    стат[если.split(':')[0]] += 1
    строки.append({'inn': инн, 'predpriyatie': имя[:70], 'sayt': сайт,
                   'chem_vzyat': ист or 'поиск 2-й сессии',
                   'podtverzhdenie': если, 'sayt_na_kartochke_cheko': ч})
цб.close()

with io.open(ВЫХОД, 'w', encoding='utf-8-sig', newline='') as ф:
    п = csv.DictWriter(ф, fieldnames=list(строки[0]), delimiter=';')
    п.writeheader(); п.writerows(строки)
    ф.flush(); os.fsync(ф.fileno())

for з in строки[:6]:
    print(f"   {з['inn']} {з['sayt'][:28]:28} {з['podtverzhdenie'][:44]}")
print()
for к, v in sorted(стат.items()):
    print(f'{к:52} {v:5}')
print(f'{"ОТДАНО СТРОК":52} {len(строки):5}')
print('файл:', os.path.basename(ВЫХОД))

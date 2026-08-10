# -*- coding: utf-8 -*-
"""Приём контактов с КАРТОЧЕК ОРГАНИЗАЦИЙ ЕИС от 3-й сессии.

Чем это отличается от контактов с карточки закупки: там «ответственное должностное лицо»
конкретного извещения, здесь — контактное лицо самой организации на её странице в реестре
(`zakupki.gov.ru/epz/organization/view.../info.html?agencyId=`). Ссылка постоянная, лицо
чаще относится к предприятию в целом.

Осторожность та же, что и с checko: имя и почта попадают в contact_source ТОЛЬКО со
ссылкой на страницу, где они видны, и с цитатой должности. Ничего не пишем без адреса.

Запуск: python3 park_vlit_eis_org_3s.py [файл.jsonl]
"""
import collections, json, os, re, sqlite3, sys, importlib.util

D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)

FAYL = os.path.join(D, sys.argv[1] if len(sys.argv) > 1 else 'PARK-EIS-ORG-KONTAKTY-1S-3S.jsonl')
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()
park = {r[0] for r in cur.execute('select inn from predpriyatie')}


def cifry10(s):
    c = re.sub(r'\D', '', s or '')
    if len(c) >= 11 and c[0] in '78':
        c = c[1:]
    return c[-10:] if len(c) >= 10 else ''


pri = collections.Counter()
vs = fio = tel = mail = 0
for ln in open(FAYL, encoding='utf-8', errors='replace'):
    if not ln.strip():
        continue
    try:
        x = json.loads(ln)
    except Exception:
        pri['строка не разобралась'] += 1
        continue
    vs += 1
    inn = str(x.get('inn') or '').strip()
    if not re.fullmatch(r'\d{10}|\d{12}', inn):
        pri['ИНН не разобран'] += 1
        continue
    if inn not in park:
        pri['предприятия нет в парке'] += 1
        continue
    url = (x.get('istochniki') or '').split()[0] if x.get('istochniki') else ''
    raz = pb.razbor_url(url)
    if not raz:
        pri['ссылки нет или не разбирается'] += 1
        continue
    chel = (x.get('chelovek') or '').strip()[:200]
    dolzh = (x.get('dolzhnost') or 'контактное лицо организации (карточка ЕИС)')[:120]
    citata = 'карточка организации в реестре ЕИС: %s — %s' % (chel or '?', dolzh)
    obshch = (inn, raz[1], url, raz[0], raz[2], '', citata[:300],
              '3-я сессия, карточка организации ЕИС')
    if chel:
        cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                    'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto)'
                    ' values (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (inn, 'chelovek', chel, chel, dolzh) + obshch[1:])
        fio += 1
    c = cifry10(x.get('telefon'))
    if c:
        cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                    'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto)'
                    ' values (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (inn, 'telefon', c, chel, dolzh) + obshch[1:])
        tel += 1
    a = (x.get('pochta') or '').strip().strip('.,;')
    if '@' in a:
        cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                    'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto)'
                    ' values (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (inn, 'email', a, chel, dolzh) + obshch[1:])
        mail += 1

p.commit()
print('строк на входе %d | ФИО %d | телефонов %d | почт %d' % (vs, fio, tel, mail))
print('  пропуски:', dict(pri.most_common(6)))
print('наблюдений в contact_source:',
      cur.execute('select count(*) from contact_source').fetchone()[0])
p.close()

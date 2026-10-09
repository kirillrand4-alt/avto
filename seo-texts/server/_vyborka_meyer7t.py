# Проба meyer7t (владелец 09.10: «нам же хватит 100 разных… и по ним же сделать ± точный расчёт для полного прогона»):
# дальше по шагам — 110 самых разных компаний из списка отбора (3 614), выбор как в proba_100: по кругу «сегмент ->
# регион, которого в выборке меньше всего», обе страны (+10 на тех, кого доп. ОКВЭД выведет в «Не вошли»).
# Полный список — meyer7t-spisok-polnyy.json.
import collections, io, json, os, random, shutil, time
D = r'C:\sender\server'
сп_п = os.path.join(D, 'meyer7t-spisok.json')
полный = os.path.join(D, 'meyer7t-spisok-polnyy.json')
if not os.path.exists(полный):
    shutil.copyfile(сп_п, полный)
сп = json.load(io.open(полный, encoding='utf-8'))
комп = сп['компании']
N = 110
rnd = random.Random(7)
по_сегм = collections.defaultdict(list)
import re


def сегмент(с):
    """Сегмент без хвостов «— ИНН не определён», «(Беларусь)», «— по сайту…» и без номера группы: у сайтов без ИНН
    и белорусов сегмент — формулировка модели, иначе каждая шла бы отдельным «сегментом»."""
    с = re.split(r' — | \(Беларусь\)', с or '')[0]
    return re.sub(r'\s*\([^)]*\)\s*$', '', с).strip().lower() or 'не указан'


for i, к in комп.items():
    по_сегм[сегмент(к.get('сегм'))].append(i)
for v in по_сегм.values():
    rnd.shuffle(v)
выбор, регионы = [], collections.Counter()
while len(выбор) < N and any(по_сегм.values()):
    for с in sorted(по_сегм, key=lambda x: -len(по_сегм[x])):
        if not по_сегм[с] or len(выбор) >= N:
            continue
        v = по_сегм[с]
        j = min(range(len(v)), key=lambda j: регионы[комп[v[j]].get('регион')])
        i = v.pop(j)
        регионы[комп[i].get('регион')] += 1
        выбор.append(i)
сп['компании'] = {i: комп[i] for i in выбор}
сп['выборка_пробы'] = '%d самых разных из %d компаний отбора (сегмент -> регион), %s' % (len(выбор), len(комп), time.strftime('%H:%M'))
врем = сп_п + '.tmp'
with io.open(врем, 'w', encoding='utf-8') as f:
    json.dump(сп, f, ensure_ascii=False)
    f.flush(); os.fsync(f.fileno())
os.replace(врем, сп_п)
обойдены = set()
for s in io.open(os.path.join(D, 'meyer7t-kontakty.jsonl'), encoding='utf-8', errors='replace'):
    try: обойдены.add(json.loads(s)['inn'])
    except (ValueError, KeyError): pass
print('===ИТОГ==='); print(json.dumps({'выборка': сп['выборка_пробы'], 'сегментов': len({сегмент(комп[i].get('сегм')) for i in выбор}),
    'сегментов всего': len({сегмент(к.get('сегм')) for к in комп.values()}),
    'регионов': len({комп[i].get('регион') for i in выбор}), 'уже обойдены': len(обойдены & set(выбор)),
    'с выручкой от 500 млн': sum(1 for i in выбор if (комп[i].get('выручка') or 0) >= 5e8),
    '120-500 млн': sum(1 for i in выбор if 1.2e8 <= (комп[i].get('выручка') or 0) < 5e8),
    'Беларусь': sum(1 for i in выбор if i.startswith('BY') or комп[i].get('регион') == 'Беларусь'),
    'без ИНН (САЙТ:)': sum(1 for i in выбор if i.startswith('САЙТ:'))}, ensure_ascii=False, indent=0))

# -*- coding: utf-8 -*-
# Пилот Meyer (09.10): симуляция правил насыщения и рейтинг шаблонов по выдаче пилота (-> rang_shablonov.json).
#   python3 pilot_sim_nasyshchenie.py <папка с pilot-serp.jsonl, pilot-razbor.jsonl, pilot-spisok.json>
# Симуляция правила насыщения на выдаче пилота: поток = регион × группа сегментов; запросы по убыванию «агентов»;
# стоп, когда последние K запросов дали < M новых компаний списка. Глубина: стр.2 — если стр.1 дала >= P новых.
import json, collections, os, sys, urllib.parse, re, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
D = (sys.argv[1] if len(sys.argv) > 1 else '.').rstrip('/') + '/'  # папка с pilot-serp.jsonl, pilot-razbor.jsonl, pilot-spisok.json
from meyer_zaprosy_gen import АГЕНТЫ, СЕГМЕНТЫ
сег_аг = {'провайдер-%02d' % n: сс[0] for n, сс in АГЕНТЫ}
сег_аг['провайдер-25'] = 'косв'
ГРУППА = {1: 'экспорт/опт', 21: 'экспорт/опт', 2: 'семена/бобовые', 20: 'семена/бобовые', 3: 'пищевые', 19: 'пищевые', 18: 'пищевые',
          4: 'элеваторы/крупы', 13: 'элеваторы/крупы', 5: 'орехи/ягоды/сухофрукты', 6: 'орехи/ягоды/сухофрукты', 15: 'орехи/ягоды/сухофрукты',
          14: 'МЭЗ', 16: 'картофель', 17: 'кофе/чай/специи', 22: 'руды', 7: 'пластик/полимеры', 8: 'пластик/полимеры',
          9: 'нерудные/соли', 10: 'нерудные/соли', 11: 'стекло/вторсырьё', 12: 'стекло/вторсырьё', 26: 'стекло/вторсырьё', 23: 'дерево'}
кат = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'meyer-zaprosy', 'katalog.json')))['записи']
группа_запроса = {}
for з in кат:
    if not з['это_запрос']:
        continue
    гг = [ГРУППА.get(сег_аг.get(и), {'сессия-1': 'пищевые', 'сессия-2': 'пластик/полимеры', 'сессия-3': 'косв', 'сессия-4': 'беларусь',
                                     'сессия-5': 'пробелы'}.get(и, 'косв')) for и in з['источники']]
    группа_запроса[re.sub(r'\s+', ' ', з['запрос'].lower())] = collections.Counter(гг).most_common(1)[0][0]
def хост(u):
    h = (urllib.parse.urlsplit(u).hostname or '').lower(); return h[4:] if h.startswith('www.') else h
сайт_кл, кат_кл = collections.defaultdict(set), collections.defaultdict(set)
for s in open(D + 'pilot-razbor.jsonl', encoding='utf-8', errors='replace'):
    try: з = json.loads(s)
    except ValueError: continue
    if з.get('тип') == 'сайт':
        кл = {i for i, _ in з.get('инн') or []} | set(з.get('инн_база') or []) | set(з.get('инн_по_имени') or []) or {'BY' + у for у, _ in з.get('унп') or []}
        сайт_кл[з['домен']] |= кл
    else:
        кат_кл[з['url']] |= set(з.get('инн_url') or []) | set(з.get('инн') or [])
список = set(json.load(open(D + 'pilot-spisok.json'))['компании'])
выдачи = {}
for s in open(D + 'pilot-serp.jsonl', encoding='utf-8'):
    з = json.loads(s)
    if з.get('итог') != 'ok' or з['движок'] != 'yandex':
        continue
    кк = set()
    for д in з['доки']:
        кк |= сайт_кл.get(хост(д['url']), set()) | кат_кл.get(д['url'], set())
    выдачи[(з['запрос'], з['стр'])] = (кк & список, з)
# шаблон запроса без региона -> группа
def группа(q, рег):
    t = re.sub(r'\s+', ' ', q.lower().replace(рег.lower(), '{регион}')) if рег else q.lower()
    return группа_запроса.get(t, 'прочее')
потоки = collections.defaultdict(list)
for (q, стр), (кк, з) in выдачи.items():
    if стр == 1:
        потоки[(з['регион'] or 'РФ', группа(q, з['регион']))].append((з.get('агентов', 1), q))
все = set()
for кк, з in выдачи.values():
    все |= кк
def прогон(K, M, P):
    найдено, запросов = set(), 0
    for (рег, гр), qq in потоки.items():
        хвост = []
        for _, q in sorted(qq, key=lambda x: -x[0]):
            for стр in (1, 2, 3):
                if (q, стр) not in выдачи:
                    break
                кк = выдачи[(q, стр)][0]
                нов = кк - найдено
                найдено |= кк
                запросов += 1
                if стр == 1:
                    n1 = len(нов)
                if len(нов) < P:
                    break
            хвост.append(n1)
            if len(хвост) >= K and sum(хвост[-K:]) < M:
                break
    return запросов, len(найдено)
полный = sum(1 for _ in выдачи)
print('полный: запросов %d, компаний %d' % (полный, len(все)))
for K, M, P in [(10, 1, 99), (10, 2, 99), (10, 3, 99), (10, 2, 2), (10, 2, 3), (15, 2, 2), (5, 1, 2), (20, 3, 2), (10, 1, 1), (8, 2, 2)]:
    q, c = прогон(K, M, P)
    print('K=%2d M=%d стр2-3 если стр>=%-2s: запросов %5d (%.0f%%), компаний %5d (%.0f%%)' % (K, M, P if P < 99 else '—', q, 100 * q / полный, c, 100 * c / len(все)))

# --- обучение на пилоте: какие шаблоны вообще дают компании; жадное покрытие
шаблон_комп = collections.defaultdict(set); шаблон_запр = collections.Counter(); шаблон_вид = {}
for (q, стр), (кк, з) in выдачи.items():
    t = re.sub(r'\s+', ' ', q.lower().replace(з['регион'].lower(), '{регион}')) if з['регион'] else q.lower()
    шаблон_комп[t] |= кк; шаблон_запр[t] += 1; шаблон_вид[t] = з['вид']
нулевые = [t for t in шаблон_запр if not шаблон_комп[t]]
print('шаблонов/запросов без регион.: %d, из них без единой компании: %d (%.0f%%), запросов на них %d' % (
    len(шаблон_запр), len(нулевые), 100 * len(нулевые) / len(шаблон_запр), sum(шаблон_запр[t] for t in нулевые)))
осталось = dict(шаблон_комп); покрыто = set(); шаги = []
while осталось:
    t = max(осталось, key=lambda t: len(осталось[t] - покрыто) / шаблон_запр[t])
    нов = осталось.pop(t) - покрыто
    if not нов: break
    покрыто |= нов; шаги.append((t, len(нов), шаблон_запр[t]))
cum_q = 0; cum_c = 0
for n, (t, c, q) in enumerate(шаги, 1):
    cum_q += q; cum_c += c
    if n in (100, 200, 400, 600, 800, 1000, 1500, 2000) or n == len(шаги):
        print('топ-%4d шаблонов: запросов %5d (%.0f%%), компаний %5d (%.0f%%)' % (n, cum_q, 100 * cum_q / полный, cum_c, 100 * cum_c / len(все)))
for доля in (0.8, 0.9, 0.95):
    cq = cc = 0
    for t, c, q in шаги:
        cq += q; cc += c
        if cc >= доля * len(все):
            print('%.0f%% компаний — %d запросов (%.0f%% от полного)' % (100 * доля, cq, 100 * cq / полный)); break
json.dump([[t, c, q, шаблон_вид[t]] for t, c, q in шаги], open(D + 'rang_shablonov.json', 'w'), ensure_ascii=False)
# все шаблоны: компаний / запросов (без жадности) — для генератора экономных задач (pilot_zadachi.py экономный)
json.dump(sorted(([t, len(шаблон_комп[t]), шаблон_запр[t], шаблон_вид[t]] for t in шаблон_запр), key=lambda x: -x[1] / x[2]),
          open(D + 'rang_vse.json', 'w'), ensure_ascii=False)

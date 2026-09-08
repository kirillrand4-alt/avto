# -*- coding: utf-8 -*-
"""Фаза 3. Косвенный слой: две независимые линзы провайдера (технолог и скептик) по каждому юрлицу края без прямого факта.
Вход: AK-kandidaty.jsonl (с дропа). Выход: linzy-verdikty.jsonl (durable, резюм по (пачка, линза)), сводные вердикты linzy-itog.jsonl.
Контроли: в каждую 20-ю пачку подмешиваются выдуманные предприятия: офисные (ожидаем «нет») и заведомо воздушные (ожидаем «да»).
Запуск (из seo-texts/): python3 altay-ko/ak_linzy.py [--nitey 4] [--predel N] [--test]"""
import os, sys, re, json, time, threading, argparse, random
from concurrent.futures import ThreadPoolExecutor, as_completed
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
from gen_provider import make_client, call
MODEL = 'claude-fable-5'; PACHKA = 20
F_IN = os.path.join(HERE, 'AK-kandidaty.jsonl'); F_OUT = os.path.join(HERE, 'linzy-verdikty.jsonl'); F_ITOG = os.path.join(HERE, 'linzy-itog.jsonl')
_lock = threading.Lock()
ZADACHA = """Речь об Алтайском крае. Нужно понять, есть ли у предприятия в ТЕХНОЛОГИЧЕСКОМ ПРОЦЕССЕ компрессорное оборудование:
промышленные компрессоры (винтовые, поршневые, центробежные) для сжатого воздуха, компрессорные станции, воздуходувки/нагнетатели,
осушители сжатого воздуха, ресиверы, генераторы азота/кислорода, ВРУ. Промышленный холод (холодильные компрессоры) считать
ОТДЕЛЬНО и помечать в tip_mashin словом «холод». Бытовые/автомобильные компрессоры и кондиционеры не считаются.
Оценивай по профилю производства: где сжатый воздух технологически обязателен (пневмотранспорт зерна/муки, пневмоинструмент и
покраска, литьё и штамповка, ПЭТ-выдув, упаковка и розлив, ЧПУ-станки, пескоструй, аэротенки водоканалов, ТЭЦ и котельные,
шахты и карьеры, деревообработка, сушилки), где азот/кислород нужны (металлургия, лазерная резка, пищевая упаковка, медицина,
химия), и где он не нужен (офис, торговля без склада-производства, услуги, управление недвижимостью, сельхозрастениеводство
без сушки/переработки и т.п.). Данных мало - суди по ОКВЭД (всем кодам), названию, описанию деятельности, выручке и численности:
крупное производство почти всегда имеет сжатый воздух, микрофирма из трёх человек с торговым ОКВЭД - почти никогда."""
ROLI = {
 'технолог': 'Ты инженер-технолог машиностроительного и пищевого профиля, 20 лет проектировал пневмосети предприятий. Оцени честно и по существу.',
 'скептик': 'Ты придирчивый аудитор: твоя установка - НАЙТИ основания, почему у предприятия сжатого воздуха и компрессоров НЕТ. Если оснований нет - честно скажи «да».',
}
PROMPT = """{rol}

{zadacha}

Ниже {n} предприятий. По КАЖДОМУ верни вердикт:
  verdikt: "да" (в техпроцессе почти наверняка есть КО), "возможно" (зависит от масштаба/оснащения), "нет"
  uverennost: 0-100
  tehprocess: одна фраза, где именно и зачем нужен сжатый воздух/газ (или почему не нужен)
  tip_mashin: список из ["воздух", "азот", "кислород", "холод", "воздуходувка", "ресивер"] что ожидается; пустой если нет
Верни СТРОГО JSON: {{"otvety":[{{"inn":"...","verdikt":"...","uverennost":N,"tehprocess":"...","tip_mashin":[...]}}]}}

ПРЕДПРИЯТИЯ:
{spisok}"""
KONTROL = [
 {'inn': 'K-NET-1', 'nazvanie': 'ООО "ЮРИСТ-КОНСАЛТ АЛТАЙ"', 'okved_osn': '69.10', 'okved_vse': '69.10|69.20|70.22', 'gorod': 'Барнаул', 'fin': {'vyruchka': 4200000}, 'ssch': 3, 'activity': 'юридические и бухгалтерские услуги', 'ozhid': 'нет'},
 {'inn': 'K-NET-2', 'nazvanie': 'ООО "УПРАВЛЯЮЩАЯ КОМПАНИЯ ПРОСПЕКТ"', 'okved_osn': '68.32.1', 'okved_vse': '68.32.1|68.20', 'gorod': 'Бийск', 'fin': {'vyruchka': 31000000}, 'ssch': 12, 'activity': 'управление многоквартирными домами', 'ozhid': 'нет'},
 {'inn': 'K-NET-3', 'nazvanie': 'ИП МАГАЗИН ОДЕЖДЫ "СТИЛЬ"', 'okved_osn': '47.71', 'okved_vse': '47.71|47.72', 'gorod': 'Рубцовск', 'fin': {'vyruchka': 9000000}, 'ssch': 4, 'activity': 'розничная торговля одеждой', 'ozhid': 'нет'},
 {'inn': 'K-DA-1', 'nazvanie': 'ООО "АЛТАЙ-ПЭТ"', 'okved_osn': '22.22', 'okved_vse': '22.22|22.29|46.76', 'gorod': 'Новоалтайск', 'fin': {'vyruchka': 480000000}, 'ssch': 85, 'activity': 'производство ПЭТ-преформ и выдув бутылок', 'ozhid': 'да'},
 {'inn': 'K-DA-2', 'nazvanie': 'АО "ЗАВОД МЕТАЛЛОКОНСТРУКЦИЙ СИБИРЬ"', 'okved_osn': '25.11', 'okved_vse': '25.11|25.62|33.11', 'gorod': 'Барнаул', 'fin': {'vyruchka': 1200000000}, 'ssch': 320, 'activity': 'плазменная резка, сварка, окраска металлоконструкций', 'ozhid': 'да'},
]
def opis(k):
    fin = k.get('fin') or {}
    v = fin.get('vyruchka'); v = f'{v/1e6:.0f} млн руб ({fin.get("god","")})' if v else 'нет данных'
    sf = k.get('sayt_fakty') or {}
    sfs = ''
    if sf:
        sfs = ' | сайт: ' + '; '.join(x for x in [', '.join(sf.get('produkciya') or []), ('воздух точно: ' + ', '.join(sf['vozduh_tochno'])) if sf.get('vozduh_tochno') else '', ('воздух вероятно: ' + ', '.join(sf['vozduh_veroyatno'])) if sf.get('vozduh_veroyatno') else '', (sf.get('citata') or '')[:150]] if x)
    return (f'[{k["inn"]}] {k.get("nazvanie") or k.get("nazvanie_polnoe") or ""} | {k.get("gorod") or ""} | ОКВЭД осн. {k.get("okved_osn") or "?"}; все: {(k.get("okved_vse") or "")[:160]} | '
            f'выручка {v} | ССЧ {k.get("ssch") or "?"} | деятельность: {(k.get("activity") or "")[:200]}{sfs}')[:900]
def parse(msg):
    text = ''.join(b.text for b in msg.content if b.type == 'text').strip(); text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
    try: return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', text, re.S); return json.loads(m.group(0))
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--nitey', type=int, default=4); ap.add_argument('--predel', type=int, default=0); ap.add_argument('--test', action='store_true'); ap.add_argument('--svod', action='store_true'); a = ap.parse_args()
    if a.svod:
        svod(None); return
    kand = [json.loads(l) for l in open(F_IN, encoding='utf-8') if l.strip()]
    kand = [k for k in kand if not k.get('fakty')]   # с прямым фактом класс уже есть
    kand.sort(key=lambda k: -((k.get('fin') or {}).get('vyruchka') or 0))   # крупные первыми
    if a.predel: kand = kand[:a.predel]
    if a.test: kand = kand[:20]
    pachki = [kand[i:i + PACHKA] for i in range(0, len(kand), PACHKA)]
    rnd = random.Random(7)
    for i, p in enumerate(pachki):
        if i % 20 == 0: p.extend(rnd.sample(KONTROL, 2))
    gotovo = set()
    if os.path.exists(F_OUT):
        for l in open(F_OUT, encoding='utf-8'):
            try: d = json.loads(l); gotovo.add((d['pachka'], d['linza']))
            except Exception: pass
    zad = [(i, rol) for i in range(len(pachki)) for rol in ROLI if (i, rol) not in gotovo]
    print(f'кандидатов {len(kand)}, пачек {len(pachki)}, заданий {len(zad)} (готово {len(gotovo)})', flush=True)
    client = make_client()
    def odno(z):
        i, rol = z; p = pachki[i]
        spisok = '\n'.join(opis(k) for k in p)
        t = time.time()
        msg = call(client, [{'role': 'user', 'content': PROMPT.format(rol=ROLI[rol], zadacha=ZADACHA, n=len(p), spisok=spisok)}], model=MODEL, attempts=3)
        d = parse(msg); otv = {str(o.get('inn')): o for o in d.get('otvety', [])}
        rec = {'pachka': i, 'linza': rol, 'otvety': [otv.get(k['inn'], {'inn': k['inn'], 'verdikt': '', 'net_otveta': True}) for k in p], 'tok': msg.usage.output_tokens, 'sec': round(time.time() - t)}
        with _lock:
            with open(F_OUT, 'a', encoding='utf-8') as f: f.write(json.dumps(rec, ensure_ascii=False) + '\n'); f.flush(); os.fsync(f.fileno())
        return f'пачка {i} {rol}: ответов {len(otv)}/{len(p)}, {rec["sec"]} с'
    n_ok = n_err = 0
    with ThreadPoolExecutor(a.nitey) as ex:
        futs = {ex.submit(odno, z): z for z in zad}
        for f in as_completed(futs):
            try:
                r = f.result(); n_ok += 1
                if n_ok % 25 == 0 or a.test: print(r, flush=True)
            except Exception as e:
                n_err += 1; print('СБОЙ', futs[f], repr(e)[:150], flush=True)
    print(f'выполнено {n_ok}, сбоев {n_err}', flush=True)
    svod(pachki)
def svod(pachki):
    """Сведение двух линз в класс. Контроли считаются отдельно."""
    po = {}
    for l in open(F_OUT, encoding='utf-8'):
        try: d = json.loads(l)
        except Exception: continue
        for o in d['otvety']:
            po.setdefault(o.get('inn'), {})[d['linza']] = o
    ozhid = {k['inn']: k['ozhid'] for k in KONTROL}
    kontrol = {'ok': 0, 'ne_ok': 0}; itog = []
    for inn, ls in po.items():
        t = ls.get('технолог', {}); s = ls.get('скептик', {})
        vt, vs = t.get('verdikt', ''), s.get('verdikt', '')
        u = round(((t.get('uverennost') or 0) + (s.get('uverennost') or 0)) / 2)
        if vt == 'да' and vs == 'да': klass = 'косвенно'
        elif 'да' in (vt, vs) and 'возможно' in (vt, vs): klass = 'косвенно'; u = min(u, 70)
        elif vt == 'возможно' and vs == 'возможно': klass = 'кандидат'
        elif 'да' in (vt, vs) and 'нет' in (vt, vs): klass = 'кандидат (линзы разошлись)'
        elif 'возможно' in (vt, vs) and 'нет' in (vt, vs): klass = 'кандидат (слабый)'
        elif vt == 'нет' and vs == 'нет': klass = 'не наше'
        else: klass = 'без вердикта'
        rec = {'inn': inn, 'klass': klass, 'uverennost': u, 'tehnolog': vt, 'skeptik': vs, 'tehprocess': t.get('tehprocess') or s.get('tehprocess') or '', 'tehprocess_skeptik': s.get('tehprocess', ''),
               'tip_mashin': sorted(set((t.get('tip_mashin') or []) + (s.get('tip_mashin') or [])))}
        if inn in ozhid:
            ok = (ozhid[inn] == 'нет' and klass == 'не наше') or (ozhid[inn] == 'да' and klass == 'косвенно')
            kontrol['ok' if ok else 'ne_ok'] += 1; rec['kontrol'] = ozhid[inn]
        itog.append(rec)
    with open(F_ITOG, 'w', encoding='utf-8') as f:
        for r in itog: f.write(json.dumps(r, ensure_ascii=False) + '\n')
    from collections import Counter
    print('СВОД:', Counter(r['klass'] for r in itog if 'kontrol' not in r), '| контроли:', kontrol, flush=True)
if __name__ == '__main__':
    main()

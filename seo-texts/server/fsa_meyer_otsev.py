# -*- coding: utf-8 -*-
# 16.10, владелец: «если можем отсечь тех, кому точно не нужны ни ФТС, ни рентген, ни компрессоры — выкинуть». Изготовители из
# выкачки ФСА (fsa-meyer-decl.jsonl) -> (1) правило: ИП с 1–2 декларациями — микро (не тратим модель); (2) модель Luna по
# продукции (до 6 наименований) и числу деклараций: «нет» — точно не нужны (ни сортировка/рентген, ни сжатый воздух/азот на
# производстве), «да»/«возможно» — оставляем. Отсев только по «нет» и правилу. Durable: fsa-meyer-otsev.jsonl (fsync, резюм).
import collections, io, json, os, re, sys, threading, time
DIR = r'C:\sender\server'
sys.path.insert(0, DIR); sys.path.insert(0, r'C:\sender'); os.chdir(DIR)
os.environ.update({'PROVIDER_MODEL': 'gpt-6-luna', 'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna', 'KC_NABOR': 'meyer7'})
ВЫХ = os.path.join(DIR, 'fsa-meyer-otsev.jsonl')
_лок = threading.Lock()
# 16.10, выборка владельцу: ИП с профильной для ФТС продукцией — не по правилу, а в модель (кофе, специи, орехи…)
ПРОФИЛЬ = re.compile(r'орех|фундук|миндал|кешью|арахис|фисташ|семеч|подсолнеч|кофе|специ|пряност|перец|круп|греч|рис|пшено|'
                     r'сухофрукт|изюм|кураг|чернослив|фасол|горох|нут|чечевиц|кунжут|лён|льн|тыквен|кедр|какао', re.I)
ПР = ('Ниже производители (по декларациям соответствия ФСА) и их продукция. Наше оборудование: (А) фотосепараторы и рентген-'
      'инспекция для сортировки/контроля сыпучих и фасованных продуктов (зерно, крупы, орехи, семечки, сухофрукты, специи, мясо, '
      'кондитерка, фасовка); (Б) промышленные компрессоры, азотные генераторы (сжатый воздух на производстве, упаковка в газе). '
      'ВАЖНО: Б нужно ЛЮБОМУ промышленному производству с оборудованием (металлообработка, станки, бетон, пластик, химия, стекло, '
      'мебель, швейка и т.д.) — такие НЕ «нет», а «да»/«возможно», даже если продукция не пищевая.\n'
      'Для КАЖДОГО ответь: «нет» — ТОЧНО не нужно ни А, ни Б: торговля/перепродажа без своего производства, услуги, кустарное '
      'штучное изготовление вручную без оборудования (домашняя выпечка, ремесло, сувениры); «да» — нужно А или Б; «возможно». '
      'Сомневаешься — «возможно».\n'
      'Ответ — ТОЛЬКО JSON-массив: [{{"n":номер,"ответ":"да|нет|возможно","почему":"до 8 слов"}}]\n\n{б}')


def main():
    import kc_kontakty as KK
    изг = {}
    for s in io.open(os.path.join(DIR, 'fsa-meyer-decl.jsonl'), encoding='utf-8', errors='replace'):
        try:
            x = json.loads(s)
        except ValueError:
            continue
        i = re.sub(r'\D', '', x.get('manufacterInn') or '')
        if len(i) not in (10, 12) or 'беларус' in (x.get('manufacterAddress') or '').lower():
            continue
        z = изг.setdefault(i, {'имя': (x.get('manufacterName') or '')[:80], 'n': 0, 'прод': []})
        z['n'] += 1
        п = (x.get('productFullName') or '')[:90]
        if len(z['прод']) < 6 and п not in z['прод']:
            z['прод'].append(п)
    готово = set()
    if os.path.exists(ВЫХ):
        for s in io.open(ВЫХ, encoding='utf-8', errors='replace'):
            try:
                готово.add(json.loads(s)['инн'])
            except (ValueError, KeyError):
                pass
    def писать(r):
        with _лок, io.open(ВЫХ, 'a', encoding='utf-8') as f:
            f.write(json.dumps(r, ensure_ascii=False) + '\n'); f.flush(); os.fsync(f.fileno())
    модели = []
    for i, z in изг.items():
        if i in готово:
            continue
        if len(i) == 12 and z['n'] <= 2 and not ПРОФИЛЬ.search(' '.join(z['прод'])):
            писать({'инн': i, 'ответ': 'нет', 'почему': 'ИП, 1–2 декларации (микро)', 'как': 'правило'})
        else:
            модели.append((i, z))
    print('изготовителей', len(изг), '| уже', len(готово), '| в модель', len(модели), flush=True)

    def пачка(п_):
        б = '\n'.join('%d. %s (%d декл.): %s' % (j, z['имя'], z['n'], ' | '.join(z['прод'])) for j, (i, z) in enumerate(п_, 1))
        о = KK.модель(ПР.format(б=б), True) or {}
        for j, (i, z) in enumerate(п_, 1):
            y = о.get(j) or {}
            писать({'инн': i, 'ответ': y.get('ответ') or 'возможно', 'почему': y.get('почему') or 'нет ответа модели', 'как': 'модель'})
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.time()
    with ThreadPoolExecutor(12) as ex:
        for k, _ in enumerate(ex.map(пачка, [модели[a:a + 40] for a in range(0, len(модели), 40)]), 1):
            if k % 50 == 0:
                print('пачек', k, '%.0f мин' % ((time.time() - t0) / 60), flush=True)
    сч = collections.Counter()
    for s in io.open(ВЫХ, encoding='utf-8', errors='replace'):
        y = json.loads(s); сч['%s/%s' % (y['ответ'], y['как'])] += 1
    import shutil
    shutil.copyfile(ВЫХ, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХ)))
    print('===ИТОГ===', dict(сч), flush=True)


if __name__ == '__main__':
    if '--vnutri' not in sys.argv:
        import subprocess
        лог = os.path.join(DIR, 'fsa_otsev_%s.log' % time.strftime('%d%m-%H%M'))
        with open(лог, 'wb') as в:
            p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, 'fsa_meyer_otsev.py'), '--vnutri'], cwd=DIR,
                                 creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                                 close_fds=False, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        time.sleep(90)
        print('===ИТОГ==='); print(open(лог, encoding='utf-8', errors='replace').read()[-600:])
        sys.exit(0)
    main()

# -*- coding: utf-8 -*-
"""Ночной оркестратор (фон): ждёт генерацию вариаций → собирает пул → ревью+отбор
100 → заливает на дроп → запускает рассылку s1→s2 на сервере. Не требует MCP-триггеров.
При выходе будит сессию. Резюмируемо: пропускает уже сделанные шаги."""
import os, sys, time, json, glob, subprocess

D = '/home/user/avto/seo-texts'
os.chdir(D); sys.path.insert(0, D)
from gen_provider import env
E = env()
os.environ['DROP_URL'] = E['DROP_URL']; os.environ['DROP_TOKEN'] = E['DROP_TOKEN']
os.environ['PROVIDER_API_KEY'] = E.get('PROVIDER_API_KEY', '')
os.environ['PROVIDER_BASE_URL'] = E.get('PROVIDER_BASE_URL', 'https://router.cheap')
for line in open('/tmp/rs.env', encoding='utf-8'):
    if line.startswith('JOB_SECRET='):
        os.environ['JOB_SECRET'] = line.split('=', 1)[1].strip()

def log(m): print(f'[{time.strftime("%H:%M:%S")}] {m}', flush=True)

# 1) ждём достаточного числа бакетов (>=20 из 26) или 45 мин
deadline = time.time() + 45 * 60
while time.time() < deadline:
    n = len(glob.glob(f'{D}/variations-cache/b*.json'))
    log(f'бакетов в кэше: {n}/26')
    if n >= 20:
        break
    time.sleep(60)

# 2) собираем пул из кэша (даже частичный — хватит на 100)
if not os.path.exists(f'{D}/variations-pool.json') or True:
    pool = []
    for fn in sorted(glob.glob(f'{D}/variations-cache/b*.json')):
        d = json.load(open(fn))
        if isinstance(d, list):
            pool.extend(d)
    for i, v in enumerate(pool):
        v['id'] = i
    json.dump(pool, open(f'{D}/variations-pool.json', 'w'), ensure_ascii=False, indent=1)
    log(f'пул собран: {len(pool)} писем')

# 3) ревью + отбор 100 (если ещё не сделано)
if not os.path.exists(f'{D}/variations-100.json'):
    log('запуск review_variations.py ...')
    r = subprocess.run([sys.executable, f'{D}/review_variations.py'],
                       capture_output=True, text=True, timeout=5400)
    log('review stderr: ' + (r.stderr or '')[-400:])
picked = json.load(open(f'{D}/variations-100.json')) if os.path.exists(f'{D}/variations-100.json') else []
log(f'отобрано вариаций: {len(picked)}')

# 4) заливаем 100 на дроп
sys.path.insert(0, f'{D}/server')
import run_on_server as R  # noqa
R._req('PUT', 'variations-100.json', open(f'{D}/variations-100.json', 'rb').read())
log('variations-100.json → дроп')

# 5) запускаем рассылку на сервере (детач-процесс)
out = R.submit('spawn_campaign', {}, wait=False)
log(f'spawn_campaign отправлен: {out.get("submitted")}')

# 6) короткая проверка старта рассылки
time.sleep(40)
try:
    prog = json.loads(R._req('GET', 'campaign-progress.json'))
    log(f'старт рассылки: {prog.get("stats")}')
except Exception as e:
    log(f'прогресс ещё пуст ({str(e)[:50]}) — рассылка стартует')
log('=== ОРКЕСТРАТОР ЗАВЕРШЁН: рассылка запущена, прогресс в campaign-progress.json ===')

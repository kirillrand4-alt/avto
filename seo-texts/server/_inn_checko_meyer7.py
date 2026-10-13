# -*- coding: utf-8 -*-
# 13.10 (этап 5 поиска ИНН): выручка с checko.ru для надёжных ИНН, найденных по сайту, у которых её нет в нашей базе
# (организации; у ИП отчётности на checko нет). Прокси/бережный темп — cc_checko_proxy (3 с на прокси, ротация на 429).
# Итог: meyer7-inn-checko.jsonl (fsync, резюм) и выручка в meyer7-inn-sayt.jsonl (поле выручка_ист = Checko) + дроп.
# Лог: inn_checko_*.log.
import io, json, os, shutil, sys, time
DIR = r'C:\sender\server'
ВЫХ = os.path.join(DIR, 'meyer7-inn-checko.jsonl')
САЙТ_Ф = os.path.join(DIR, 'meyer7-inn-sayt.jsonl')
if __name__ == '__main__' and '--vnutri' not in sys.argv:
    import subprocess
    лог = os.path.join(DIR, 'inn_checko_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR, creationflags=0x08 | 0x200,
                             stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(30)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-600:]},
                     ensure_ascii=False))
    sys.exit(0)
sys.path.insert(0, DIR)
os.chdir(DIR)
import cc_checko_proxy as CP  # noqa: E402
CP.ВЫХОД = ВЫХ
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
строки = [json.loads(s) for s in io.open(САЙТ_Ф, encoding='utf-8') if s.strip()]
сделано = {}
if os.path.exists(ВЫХ):
    for s in io.open(ВЫХ, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
            if з.get('итог') == 'ok':
                сделано[з['inn']] = з
        except (ValueError, KeyError):
            pass
задачи = sorted({(x['инн'], x['огрн']) for x in строки if x['надёжность'] == 'надёжный' and not x.get('выручка')
                 and len(x.get('огрн') or '') == 13 and x['инн'] not in сделано})
прокси = [CP.Прокси(п) for п in json.load(open(os.path.join(DIR, 'checko-proxies.json')))]
живые = [п for п in прокси if п.get('https://checko.ru/')[0] == 200]
print(time.strftime('%H:%M:%S'), 'прокси живых', len(живые), 'из', len(прокси), '| задач', len(задачи), flush=True)


def одна(k_з):
    k, (инн, огрн) = k_з
    код, html = живые[k % len(живые)].get('https://checko.ru/company/%s' % огрн)
    з = {'inn': инн, 'ogrn': огрн, 'company': код}
    if код == 200:
        з['выручка'], з['выручка_год'] = CP.выручка(CP.текст(html))
    з['итог'] = 'ok' if код == 200 else 'ошибка'
    CP.записать(з)
    if з['итог'] == 'ok':
        сделано[инн] = з


if живые:
    t0 = time.time()
    with ThreadPoolExecutor(len(живые)) as ex:
        for k, _ in enumerate(ex.map(одна, enumerate(задачи)), 1):
            if k % 100 == 0:
                print(time.strftime('%H:%M:%S'), 'готово %d/%d за %.0f мин' % (k, len(задачи), (time.time() - t0) / 60), flush=True)
n = 0
with io.open(САЙТ_Ф + '.tmp', 'w', encoding='utf-8') as f:
    for x in строки:
        з = сделано.get(x['инн'])
        if not x.get('выручка') and з and з.get('выручка'):
            x['выручка'], x['выручка_год'], x['выручка_ист'] = з['выручка'], з.get('выручка_год') or '', 'Checko'
            n += 1
        f.write(json.dumps(x, ensure_ascii=False) + '\n')
    f.flush()
    os.fsync(f.fileno())
os.replace(САЙТ_Ф + '.tmp', САЙТ_Ф)
shutil.copyfile(САЙТ_Ф, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(САЙТ_Ф)))
print(time.strftime('%H:%M:%S'), '===ИТОГ CHECKO=== выручка добавлена', n, '| ok', len(сделано), flush=True)

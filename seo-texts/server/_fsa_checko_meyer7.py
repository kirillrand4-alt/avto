# -*- coding: utf-8 -*-
# 14.10, владелец: «делай» — выручка с checko.ru для новых компаний из реестра деклараций ФСА (meyer7-fsa-inn.txt), у которых
# её нет в нашей базе («Вертекс» 4,3 млрд стоял с нулём). Организации (ОГРН 13 знаков; у ИП отчётности нет). Прокси/темп —
# cc_checko_proxy. Итог: meyer7-fsa-checko.jsonl (fsync, резюм) и выручка в карточках списка (под замком, бэкап). Лог: fsa_checko_*.log.
import io, json, os, shutil, sys, time
DIR = r'C:\sender\server'
ВЫХ = os.path.join(DIR, 'meyer7-fsa-checko.jsonl')
if __name__ == '__main__' and '--vnutri' not in sys.argv:
    import subprocess
    лог = os.path.join(DIR, 'fsa_checko_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_fsa_checko_meyer7.py'), '--vnutri'], cwd=DIR, creationflags=0x08 | 0x200,
                             stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(30)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-400:]}, ensure_ascii=False))
    sys.exit(0)
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import cc_checko_proxy as CP  # noqa: E402
import zamok  # noqa: E402
CP.ВЫХОД = ВЫХ
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
ключи = set(io.open(os.path.join(DIR, 'meyer7-fsa-inn.txt'), encoding='utf-8').read().split())
СП = os.path.join(DIR, 'meyer7-spisok.json')
сп = json.load(io.open(СП, encoding='utf-8'))['компании']
сделано = {}
if os.path.exists(ВЫХ):
    for s in io.open(ВЫХ, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
            if з.get('итог') == 'ok':
                сделано[з['inn']] = з
        except (ValueError, KeyError):
            pass
задачи = sorted((i, сп[i].get('огрн') or '') for i in ключи if i in сп and not сп[i].get('выручка') and len(сп[i].get('огрн') or '') == 13
                and i not in сделано)
прокси = [CP.Прокси(п) for п in json.load(open(os.path.join(DIR, 'checko-proxies.json')))]
живые = [п for п in прокси if п.get('https://checko.ru/')[0] == 200]
print(time.strftime('%H:%M:%S'), 'прокси живых', len(живые), '| задач', len(задачи), '| ИП/без ОГРН пропущено',
      sum(1 for i in ключи if i in сп and not сп[i].get('выручка') and len(сп[i].get('огрн') or '') != 13), flush=True)


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
with zamok.замок(СП):
    весь = zamok.прочитать(СП)
    shutil.copyfile(СП, СП + '.bak-fsa-checko-' + time.strftime('%d%m-%H%M'))
    for i, з in сделано.items():
        к = весь['компании'].get(i)
        if к and not к.get('выручка') and з.get('выручка'):
            к['выручка'] = з['выручка']
            к['выручка_откуда'] = 'Checko%s' % ((' ' + з['выручка_год']) if з.get('выручка_год') else '')
            n += 1
    zamok.записать_атомарно(СП, весь)
shutil.copyfile(СП, r'C:\seostat\drop\drop-storage\meyer7-spisok.json')
print(time.strftime('%H:%M:%S'), '===ИТОГ CHECKO ФСА=== выручка добавлена', n, '| ok', len(сделано), flush=True)

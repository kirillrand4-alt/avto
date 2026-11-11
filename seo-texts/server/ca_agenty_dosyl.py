# -*- coding: utf-8 -*-
r"""Доделать агентов первой волны набора ca, вставших ночью по балансу xmlriver (10.11 16:05: Sol 780 / 1 760, хвост
Luna 3 776 не начат). 11.11, владелец пополнил xmlriver на 1 000 ₽: «а то, что остановилось из-за баланса ночью,
перезапустил?».

Последовательно: kc_agent_glubokiy на Sol (выручка от 500 млн), затем хвост на Luna (120–500 млн). Вход — прежний
ca-glubokiy-vhod.json (дроп), выход — ОБЩИЙ журнал ca-glubokiy.jsonl (резюм: сделанные пропускаются; вторая волна
потом тоже их не тронет). Порог баланса xmlriver 60 ₽ — как в конвейере. Не запускать одновременно с шагом агентов
второй волны (два писателя в один журнал): перед стартом каждого прохода проверяем, что другого kc_agent_glubokiy нет.
Низкий приоритет, замок. Статус: ca\ca-agenty-dosyl.json.
"""
import json, os, subprocess, sys, time

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')

if '--vnutri' not in sys.argv:
    лог = os.path.join(ПАПКА, 'ca_agenty_dosyl_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)
    time.sleep(20)
    print('===ИТОГ=== запущен', open(лог, encoding='utf-8', errors='replace').read()[-400:])
    sys.exit(0)
ЗАМОК = os.path.join(ПАПКА, 'ca_agenty_dosyl.lock')
try:
    _fd = os.open(ЗАМОК, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(_fd, str(os.getpid()).encode())
    os.close(_fd)
except FileExistsError:
    _pid = open(ЗАМОК).read().strip()
    if _pid and _pid in subprocess.run(['tasklist', '/FI', 'PID eq %s' % _pid], capture_output=True, text=True).stdout:
        print('уже запущен, pid', _pid)
        sys.exit(0)
    open(ЗАМОК, 'w').write(str(os.getpid()))


def отметка(**k):
    k['обновлено'] = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(os.path.join(ПАПКА, 'ca-agenty-dosyl.json'), 'w', encoding='utf-8') as f:
        json.dump(k, f, ensure_ascii=False)
    print(json.dumps(k, ensure_ascii=False), flush=True)


def чужой_агент():
    r = subprocess.run(['powershell', '-NoProfile', '-Command',
                        "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { $_.CommandLine -like "
                        "'*kc_agent_glubokiy*' } | ForEach-Object { $_.ProcessId }"], capture_output=True, text=True, timeout=120)
    return r.stdout.split()


БАЗА = dict(os.environ, KC_NABOR='ca', POISK_NABOR='ca', KC_CEL='kc', KC_AGENT_XML_MIN='60', KC_AGENT_POTOKOV='30',
            KC_BEZ_CHECKO='1', PROVIDER_FALLBACK_CHEAP='gpt-5.6-luna')
ПРОХОДЫ = [('Sol от 500 млн', dict(PROVIDER_MODEL='gpt-6-sol', KC_AGENT_OT='500e6')),
           ('Luna 120–500 млн', dict(PROVIDER_MODEL='gpt-6-luna', KC_AGENT_OT='120e6', KC_AGENT_DO='500e6'))]


def main():
    for имя, доп in ПРОХОДЫ:
        занят = чужой_агент()
        if занят:
            отметка(этап='стоп', причина='уже идёт другой kc_agent_glubokiy (PID %s) — не пишу вторым в журнал' % занят)
            return
        отметка(этап=имя)
        with open(os.path.join(ПАПКА, 'ca_agenty_dosyl_%s.log' % ('sol' if 'Sol' in имя else 'luna')), 'ab') as f:
            r = subprocess.run([sys.executable, '-u', os.path.join(DIR, 'kc_agent_glubokiy.py')], cwd=DIR,
                               env=dict(БАЗА, **доп), stdout=f, stderr=subprocess.STDOUT)
        отметка(этап=имя + ' — готово', код=r.returncode)
    отметка(этап='готово')


if __name__ == '__main__':
    try:
        main()
    finally:
        try:
            os.remove(ЗАМОК)
        except OSError:
            pass

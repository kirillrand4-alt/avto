# -*- coding: utf-8 -*-
"""Панель P25 должна жить на своём префиксе /p25, а не притворяться /obzvon.

ЧТО БЫЛО НЕ ТАК. Я пробросил /p25 → 8014 с переписыванием пути. Вход проходил,
но приложение отдаёт РЕДИРЕКТ и ссылки со своим префиксом `/obzvon`, и браузер
уходил на панель Центробежных. Переписывать ответ — полумера: ссылки внутри
страниц всё равно повели бы не туда.

ПРАВИЛЬНО: префикс задаётся переменной `OBZVON_ROOT_PATH` (её читает
`settings.obzvon_path`, от неё же строятся ссылки и редиректы). Ставлю службе
8014 значение `/p25` — тогда прокси работает без переписывания, а все ссылки
внутри страниц сразу верные.

ОСТОРОЖНО С ОКРУЖЕНИЕМ: правлю ОДНУ переменную, остальные переношу как есть.
Перед записью печатаю, сколько переменных было и стало — если число упало,
значит я что-то потерял, и это видно сразу.

Запуск: python p25_svoy_prefiks.py [--apply]
"""
import re, subprocess, sys, time

СЛУЖБА = 'p25obzvon'
ПРИМЕНИТЬ = '--apply' in sys.argv
# Проверял наличие через `nssm version` и получил «не найден», хотя `nssm get`
# работал весь час: у nssm код возврата на version не нулевой. Признак наличия —
# сам рабочий вызов, а не чужое соглашение о кодах.
NSSM = None
for exe in (r'C:\nssm.exe', r'C:\Windows\System32\nssm.exe'):
    try:
        п = subprocess.run([exe, 'get', СЛУЖБА, 'Application'],
                           capture_output=True, timeout=20)
        if (п.stdout or b'').replace(b'\x00', b'').strip():
            NSSM = exe
            break
    except Exception:
        continue
if not NSSM:
    print('nssm не найден'); raise SystemExit


def прочесть():
    сыр = subprocess.run([NSSM, 'get', СЛУЖБА, 'AppEnvironmentExtra'],
                         capture_output=True, timeout=25).stdout or b''
    for код in ('utf-16-le', 'utf-8', 'cp1251'):
        try:
            т = сыр.decode(код).replace('\x00', '')
            if '=' in т:
                return т
        except Exception:
            continue
    return ''


текст = прочесть()
строки = [s for s in re.split(r'[\r\n]+', текст) if '=' in s]
имена = [s.split('=', 1)[0] for s in строки]
было = len(строки)
текущее = next((s.split('=', 1)[1] for s in строки if s.split('=', 1)[0] == 'OBZVON_ROOT_PATH'), None)
print(f'переменных в службе: {было}')
print(f'OBZVON_ROOT_PATH сейчас: {текущее!r}')
if текущее == '/p25':
    print('уже /p25 — менять нечего'); raise SystemExit

новые = []
поставлено = False
for s in строки:
    к, _, v = s.partition('=')
    if к == 'OBZVON_ROOT_PATH':
        новые.append('OBZVON_ROOT_PATH=/p25')
        поставлено = True
    else:
        новые.append(s)
if not поставлено:
    новые.append('OBZVON_ROOT_PATH=/p25')
стало = len(новые)
print(f'переменных станет: {стало}')
if стало < было:
    print('ЧИСЛО ПЕРЕМЕННЫХ УПАЛО — не пишу, что-то потеряно'); raise SystemExit
if not ПРИМЕНИТЬ:
    print('имена:', ', '.join(имена))
    print('СУХОЙ ПРОГОН')
    raise SystemExit

subprocess.run([NSSM, 'set', СЛУЖБА, 'AppEnvironmentExtra'] + новые,
               capture_output=True, timeout=40)
проверка = прочесть()
теперь = next((s.split('=', 1)[1] for s in re.split(r'[\r\n]+', проверка)
               if s.startswith('OBZVON_ROOT_PATH=')), None)
n_после = len([s for s in re.split(r'[\r\n]+', проверка) if '=' in s])
print(f'после записи: переменных {n_после}, OBZVON_ROOT_PATH={теперь!r}')
if теперь != '/p25' or n_после < было:
    print('ЗАПИСЬ НЕ ПОДТВЕРЖДЕНА — службу не перезапускаю'); raise SystemExit
subprocess.run([NSSM, 'restart', СЛУЖБА], capture_output=True, timeout=90)
time.sleep(6)
сост = subprocess.run([NSSM, 'status', СЛУЖБА], capture_output=True, timeout=30).stdout or b''
for код in ('utf-16-le', 'utf-8'):
    try:
        print('состояние службы:', сост.decode(код).replace('\x00', '').strip()[:40]); break
    except Exception:
        pass

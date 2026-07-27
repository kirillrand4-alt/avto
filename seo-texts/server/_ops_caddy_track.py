# -*- coding: utf-8 -*-
"""Добавить в Caddyfile маршрут пикселя открытий /o/* -> 127.0.0.1:8082.

Только пиксель. Сервис отписки наружу НЕ выставляется (решение владельца 27.07:
ссылка отписки не нужна, повторных писем не ответившим не шлём).

Работа с файлом побайтовая: Caddyfile содержит кириллические комментарии,
перекодировка целиком испортила бы их. Вставляемый блок — только ASCII.

Запуск:
    python _ops_caddy_track.py            # сухой прогон, ничего не пишет
    python _ops_caddy_track.py apply      # бэкап + правка + caddy validate
"""
import json
import os
import subprocess
import sys
import time

CADDY = 'C:\\Caddyfile'
ANCHOR = b'reverse_proxy 127.0.0.1:8013'
# файл в CRLF — держим тот же перевод строки, чтобы не плодить смешанные концы
BLOCK = (b'\r\n\t# --- open-tracking pixel (only /o/*, unsub endpoint is NOT exposed) ---\r\n'
         b'\t@track path /o/*\r\n'
         b'\thandle @track {\r\n'
         b'\t\treverse_proxy 127.0.0.1:8082\r\n'
         b'\t}')


def find_caddy_exe():
    for p in ('C:\\caddy\\caddy.exe', 'C:\\Caddy\\caddy.exe', 'C:\\caddy.exe',
              'C:\\Program Files\\Caddy\\caddy.exe'):
        if os.path.exists(p):
            return p
    for root in ('C:\\', 'C:\\Program Files'):
        try:
            for dp, dn, fn in os.walk(root):
                if dp.count(os.sep) > 2:
                    dn[:] = []
                    continue
                if 'caddy.exe' in fn:
                    return os.path.join(dp, 'caddy.exe')
        except Exception:  # noqa: BLE001
            pass
    return None


def main():
    apply = len(sys.argv) > 1 and sys.argv[1] == 'apply'
    out = {'режим': 'ПРИМЕНЕНИЕ' if apply else 'сухой прогон'}

    raw = open(CADDY, 'rb').read()
    out['размер_исходного'] = len(raw)
    out['уже_настроен'] = b'@track' in raw
    if out['уже_настроен']:
        out['итог'] = 'маршрут /o/* уже есть, ничего не делаю'
        print(json.dumps(out, ensure_ascii=False))
        return

    i = raw.find(ANCHOR)
    if i < 0:
        out['итог'] = 'ОШИБКА: якорь (маршрут enrich) не найден, вставлять некуда'
        print(json.dumps(out, ensure_ascii=False))
        return
    j = raw.find(b'}', i)          # конец handle @enrich
    if j < 0:
        out['итог'] = 'ОШИБКА: не найден конец блока enrich'
        print(json.dumps(out, ensure_ascii=False))
        return
    j += 1
    new = raw[:j] + BLOCK + raw[j:]
    out['размер_нового'] = len(new)
    out['вставка_после'] = raw[max(0, i - 60):j].decode('utf-8', 'replace')
    out['фрагмент'] = new[j - 60:j + len(BLOCK) + 40].decode('utf-8', 'replace')

    caddy = find_caddy_exe()
    out['caddy_exe'] = caddy

    if not apply:
        out['итог'] = 'сухой прогон: файл НЕ изменён'
        print(json.dumps(out, ensure_ascii=False))
        return

    bak = f'{CADDY}.bak-{int(time.time())}'
    open(bak, 'wb').write(raw)
    out['бэкап'] = bak
    open(CADDY, 'wb').write(new)
    out['записан'] = True

    if caddy:
        r = subprocess.run([caddy, 'validate', '--config', CADDY,
                            '--adapter', 'caddyfile'],
                           capture_output=True, text=True, timeout=90)
        out['validate_rc'] = r.returncode
        out['validate'] = ((r.stdout or '') + (r.stderr or ''))[-700:]
        if r.returncode != 0:
            open(CADDY, 'wb').write(raw)      # откат
            out['итог'] = 'validate НЕ прошёл -> файл ОТКАЧЕН из бэкапа'
            print(json.dumps(out, ensure_ascii=False))
            return
    out['итог'] = 'файл изменён и проверен; reload делается отдельным шагом'
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()

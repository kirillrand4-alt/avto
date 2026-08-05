# -*- coding: utf-8 -*-
"""Разовый прогон приёма входящих на сервере (отбивки/отписки/ответы).

Запускается через panel_py: тот же процесс, что у раннера, — значит BOX*_PASSWORD
уже в окружении. Отправку не трогает: команда inbox-poll только читает ящики.

ARGS правится перед заливкой: --days N (добор задним числом), --no-drafts
(не жечь квоту провайдера на черновики ответов).
"""
import io
import os
import sys
import contextlib

ARGS = ['--config', r'C:\sender\sender.yaml', 'inbox-poll', '--days', '14',
        '--no-drafts', '--batch', '200']

sys.path.insert(0, r'C:\sender')

# Пароли ящиков: в окружении раннера они есть, но если запуск пришёл из другого
# контекста — дочитываем panel.env (значения не печатаем).
env_path = r'C:\sender\panel.env'
if os.path.exists(env_path):
    for line in open(env_path, encoding='utf-8', errors='replace').read().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))


def main():
    from sender.cli import main as cli_main
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            code = cli_main(ARGS)
        except SystemExit as e:  # argparse
            code = int(getattr(e, 'code', 1) or 0)
        except Exception as e:  # noqa: BLE001
            print(f'ИСКЛЮЧЕНИЕ: {type(e).__name__}: {e}')
            code = 1
    out = buf.getvalue()
    print(out[-6000:])
    print(f'--- код возврата: {code}')


if __name__ == '__main__':
    main()

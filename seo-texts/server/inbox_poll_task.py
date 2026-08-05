# -*- coding: utf-8 -*-
"""Приём входящих по расписанию: отбивки, отписки, ответы. НИЧЕГО НЕ ОТПРАВЛЯЕТ.

Живёт на сервере как C:\\sender\\inbox_poll_task.py, дёргается планировщиком
задач (RuspromInboxPoll). Раньше эту работу делал только тик оркестратора
(`sender run`), а он под холдом не запускается — отбивки и просьбы «отпишите
меня» не попадали в базу с 26.07.

Два решения, зафиксированные здесь намеренно:

* ``--keep-unread`` — ящики читает живой продажник, и пометить письма
  прочитанными значит спрятать от него новую почту. Флаги IMAP не трогаем;
  от повторной обработки защищает dedup_key события, а не флаг.
* ``--no-drafts`` — черновики ответов жгут квоту провайдера на каждом входящем.
  Приём отбивок/отписок от этого не зависит. Включить обратно = убрать флаг.
"""
import io
import os
import sys
import time
import contextlib

BASE = r'C:\sender'
ARGS = ['--config', os.path.join(BASE, 'sender.yaml'), 'inbox-poll',
        '--keep-unread', '--no-drafts', '--batch', '100']
LOG = os.path.join(BASE, 'logs', 'inbox_poll.log')

sys.path.insert(0, BASE)

env_path = os.path.join(BASE, 'panel.env')
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
        except SystemExit as e:
            code = int(getattr(e, 'code', 1) or 0)
        except Exception as e:  # noqa: BLE001 - падение прохода не должно ронять задачу
            print(f'ИСКЛЮЧЕНИЕ: {type(e).__name__}: {e}')
            code = 1
    out = buf.getvalue().strip()
    stamp = time.strftime('%Y-%m-%d %H:%M:%S')
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(f'[{stamp}] код={code}\n')
        for ln in out.splitlines():
            # в лог только строки с уловом: «пусто» по 17 ящикам каждые 15 минут
            # раздувает файл и прячет настоящие события
            if 'пусто' in ln or ln.startswith('ИТОГО: новых'):
                continue
            f.write(f'    {ln}\n')
        f.flush()
        os.fsync(f.fileno())
    print(out[-4000:])
    return code


if __name__ == '__main__':
    sys.exit(main())

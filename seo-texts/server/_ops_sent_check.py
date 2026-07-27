# -*- coding: utf-8 -*-
"""Есть ли сегодняшние письма в IMAP-папке «Отправленные» отправлявших ящиков.

Читает ТОЛЬКО количества и темы, тела не выгружает. readonly=True.
"""
import json
import sys

sys.path.insert(0, r'C:\sender')

# ящики, с которых реально ушли письма 27.07 (по sender.db)
BOXES = ['k.yashin@kompressor-pro-expert.ru',
         'a.balakirev@compressor-air-expert.ru']


def main():
    from sender.config import Config
    from sender.mailbrowser import MailBrowser
    from sender.store import Store

    cfg = Config.load(r'C:\sender\sender.yaml')
    store = Store(cfg.get('service.db_path', 'sender.db'))
    mb = MailBrowser(cfg)
    out = {}
    for box in BOXES:
        info = {}
        try:
            folders = mb.folders(box)
            info['папки'] = [{'имя': f['name'], 'роль': f.get('role')}
                             for f in folders]
            for f in folders:
                if f.get('role') in ('sent', 'inbox'):
                    try:
                        res = mb.messages(box, folder=f['name'], limit=5)
                        msgs = res.get('messages', []) if isinstance(res, dict) else []
                        info[f"{f['role']}:{f['name']}"] = {
                            'всего_в_папке': res.get('total') if isinstance(res, dict) else '?',
                            'темы': [(m.get('subject') if isinstance(m, dict) else str(m)[:60])
                                     for m in msgs][:5]}
                    except Exception as e:  # noqa: BLE001
                        info[f"{f['role']}:{f['name']}"] = f'ошибка: {str(e)[:120]}'
        except Exception as e:  # noqa: BLE001
            info['ошибка'] = str(e)[:200]
        out[box] = info

    # что говорит БД
    import sqlite3
    cx = sqlite3.connect(r'file:C:\sender\sender.db?mode=ro', uri=True, timeout=30)
    out['в_базе_27_07'] = [
        {'id': r[0], 'ящик': r[1], 'время': r[2], 'rfc': r[3]}
        for r in cx.execute(
            "select id, mailbox_id, sent_at, rfc_message_id from messages "
            "where sent_at like '2026-07-27%' order by sent_at")]
    print(json.dumps(out, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()

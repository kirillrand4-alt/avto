# -*- coding: utf-8 -*-
"""Что сгенерировали против того, что реально ушло. READ-ONLY.

Источники: confirm_reviews (текст на момент показа оператору + правки),
messages.body_rendered (то, что ушло в SMTP), send_log/events (факт отправки).
Ничего не меняет — только SELECT.

Запуск: python _ops_sent_diff.py [сколько]
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, r'C:\sender')


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    from sender.config import Config
    cfg = Config.load(os.environ.get('SENDER_CONFIG') or r'C:\sender\sender.yaml')
    cx = sqlite3.connect('file:' + cfg.get('service.db_path') + '?mode=ro', uri=True)
    cx.row_factory = sqlite3.Row

    out = {'всего': {}, 'письма': []}
    for k, q in (('events_sent', "SELECT COUNT(*) c FROM events WHERE event_type='sent'"),
                 ('send_log', "SELECT COUNT(*) c FROM send_log"),
                 ('reviews_sent', "SELECT COUNT(*) c FROM confirm_reviews WHERE status='sent'"),
                 ('reviews_edited', "SELECT COUNT(*) c FROM confirm_reviews WHERE COALESCE(edited_body,'')<>''"),
                 ('messages_sent', "SELECT COUNT(*) c FROM messages WHERE status='sent'")):
        try:
            out['всего'][k] = cx.execute(q).fetchone()['c']
        except Exception as e:  # noqa: BLE001
            out['всего'][k] = f'ошибка: {str(e)[:60]}'

    # режим: sent (последние отправленные) | edited (все с правкой оператора —
    # золотые пары «что сгенерировали / что человек переписал»)
    режим = sys.argv[2] if len(sys.argv) > 2 else 'sent'
    где = ("r.status='sent'" if режим == 'sent'
           else "COALESCE(r.edited_body,'')<>'' OR COALESCE(r.edited_subject,'')<>''")
    rows = cx.execute(
        "SELECT r.id, r.email, r.inn, r.status, r.kind, r.subject, r.body,"
        " r.edited_subject, r.edited_body, r.diff_text, r.panel_json,"
        " r.message_id, r.decided_by, r.decided_at"
        f" FROM confirm_reviews r WHERE {где}"
        " ORDER BY r.id DESC LIMIT ?", (n,)).fetchall()

    for r in rows:
        panel = {}
        try:
            panel = json.loads(r['panel_json'] or '{}')
        except Exception:  # noqa: BLE001
            pass
        msg = None
        if r['message_id']:
            try:
                msg = cx.execute(
                    "SELECT mailbox_id, subject, body_rendered, sent_at,"
                    " rfc_message_id FROM messages WHERE id=?",
                    (r['message_id'],)).fetchone()
            except Exception:  # noqa: BLE001
                msg = None
        def _cols(t):
            return {x['name'] for x in cx.execute(f'PRAGMA table_info({t})')}
        sl_cols = _cols('send_log') & {'outcome', 'ts', 'rfc_message_id', 'subject'}
        sl = cx.execute(
            f"SELECT {', '.join(sorted(sl_cols))} FROM send_log WHERE email=? "
            "ORDER BY id DESC LIMIT 1", (r['email'],)).fetchone() if sl_cols else None
        # ящик реальной отправки — из журнала событий по этому же письму
        ev = None
        if r['message_id']:
            ev = cx.execute(
                "SELECT mailbox_id, provider, event_ts FROM events "
                "WHERE event_type='sent' AND message_id=? "
                "ORDER BY id DESC LIMIT 1", (r['message_id'],)).fetchone()

        письмо_ген = (panel.get('letter') or {}).get('body') or ''
        out['письма'].append({
            'review_id': r['id'], 'email': r['email'], 'инн': r['inn'],
            'kind': r['kind'], 'решил': r['decided_by'], 'когда': r['decided_at'],
            'направление_компании': ((panel.get('company') or {}).get('division')),
            'направление_письма': panel.get('letter_division'),
            'ящик_панели': (panel.get('mailbox_id') or ''),
            'ящик_факт': (msg['mailbox_id'] if msg else None)
                          or (ev['mailbox_id'] if ev else None),
            'правка': bool(r['edited_body']),
            'diff': (r['diff_text'] or '')[:1500],
            'тема_очередь': r['subject'],
            'тема_ушла': (msg['subject'] if msg else None),
            'тело_в_панели_letter': письмо_ген[:2500],
            'тело_очередь': (r['body'] or '')[:2500],
            'тело_ушло': ((msg['body_rendered'] if msg else '') or '')[:3000],
            'правл_тема': r['edited_subject'],
            'правл_тело': (r['edited_body'] or '')[:3000],
            'rfc': (msg['rfc_message_id'] if msg else None),
            'send_log': (dict(sl) if sl else None),
            'схема': {t: sorted(_cols(t)) for t in
                      ('confirm_reviews', 'messages', 'send_log', 'events')},
        })
    # panel_py режет stdout до 6000 символов — полную выгрузку кладём файлом,
    # в stdout только сводка
    dst = r'C:\sender\_ops\sent-diff.json'
    with open(dst, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    print(json.dumps({'файл': dst, 'писем': len(out['письма']),
                      'всего': out['всего']}, ensure_ascii=False))


if __name__ == '__main__':
    main()

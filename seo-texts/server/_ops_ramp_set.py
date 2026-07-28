# -*- coding: utf-8 -*-
"""Выставить рамп-день ящикам (дневной лимит = ramp_curve[ramp_day]).

Лимит нельзя поднять из панели: send_limits работает только ВНИЗ
(sender._daily_limit), иначе прогрев теряет смысл. Легальная ручка — рамп-день.
Кривая yandex/mailru в конфиге: [3, 5, 8, 12, ...], то есть день 0 = 3 письма,
день 1 = 5. Новые ящики Meyer сидированы днём 0 и упирались в 3, тогда как у
КЦ уже 5 (владелец 28.07: «у мейера сделай тоже по 5 доступных отправок»).

Скрипт НЕ трогает счётчик отправленного и паузу — только ramp_day и день, к
которому он относится. Без `apply` печатает, что изменилось бы.

Запуск: python _ops_ramp_set.py <ramp_day> <ящик,ящик,...> [apply]
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, r'C:\sender')


def main():
    if len(sys.argv) < 3:
        print(json.dumps({'итог': 'нужно: <ramp_day> <ящики через запятую> [apply]'},
                         ensure_ascii=False))
        return
    ramp = int(sys.argv[1])
    boxes = [b.strip() for b in sys.argv[2].split(',') if b.strip()]
    apply = len(sys.argv) > 3 and sys.argv[3] == 'apply'

    from sender.config import Config
    from sender.store import Store
    from sender.dtos import MailboxState
    from sender.ramp import daily_send_limit

    cfg = Config.load(os.environ.get('SENDER_CONFIG') or r'C:\sender\sender.yaml')
    st = Store(cfg.get('service.db_path'))
    st.init_schema()
    провайдер = {m.mailbox_id: m.provider for m in cfg.mailboxes()}
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    out = {'режим': 'ПРИМЕНЕНИЕ' if apply else 'сухой прогон',
           'ramp_day': ramp, 'день': today, 'ящики': []}
    for mid in boxes:
        prov = провайдер.get(mid)
        if prov is None:
            out['ящики'].append({'ящик': mid, 'итог': 'нет в конфиге — пропущен'})
            continue
        s = st.get_mailbox_state(mid)
        было = None if s is None else {'ramp_day': s.ramp_day, 'день': s.day_key,
                                       'лимит': daily_send_limit(cfg, prov, s.ramp_day)}
        стало = {'ramp_day': ramp, 'день': today,
                 'лимит': daily_send_limit(cfg, prov, ramp)}
        if apply:
            st.upsert_mailbox_state(MailboxState(
                mailbox_id=mid, provider=prov, day_key=today,
                sent_today=(s.sent_today if s and s.day_key == today else 0),
                sent_total=(s.sent_total if s else 0),
                ramp_day=ramp, daily_limit=стало['лимит'],
                last_sent_at=(s.last_sent_at if s else None),
                paused=(bool(s.paused) if s else False),
                pause_reason=(s.pause_reason if s else None)))
        out['ящики'].append({'ящик': mid, 'было': было, 'стало': стало})
    out['итог'] = 'ГОТОВО' if apply else 'ничего не менял'
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()

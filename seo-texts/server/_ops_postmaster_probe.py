# -*- coding: utf-8 -*-
"""Проверка Постмастера Mail.ru после появления токена (см. sender/POSTMASTER-SETUP.md).

Три вызова по возрастанию: подтверждённые домены -> проблемы SPF/DKIM/DMARC
глазами Mail.ru -> суммарная статистика за неделю (там и доля «в спам»,
которой у нас своими метриками нет).

Запуск: python _ops_postmaster_probe.py [дней]
"""
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, r'C:\sender')


def main():
    дней = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    from sender.config import Config
    from sender.postoffice import PostofficeClient
    cfg = Config.load(os.environ.get('SENDER_CONFIG') or r'C:\sender\sender.yaml')
    cl = PostofficeClient(cfg)
    out = {'disabled': bool(getattr(cl, '_disabled', False)),
           'токен_получен': bool(getattr(cl, '_token', ''))}
    if out['disabled']:
        out['итог'] = ('клиент выключен: нет рабочего токена. '
                       'См. sender/POSTMASTER-SETUP.md, шаги 2-3.')
        print(json.dumps(out, ensure_ascii=False)); return

    домены = sorted({mb.mailbox_id.split('@')[1] for mb in cfg.mailboxes()})
    out['наши_домены'] = домены
    for имя, вызов in (('reg_list', cl.reg_list), ('troubles', cl.troubles)):
        try:
            out[имя] = вызов()
        except Exception as e:  # noqa: BLE001
            out[имя] = f'{type(e).__name__}: {str(e)[:160]}'
    подтверждены = set()
    if isinstance(out.get('reg_list'), list):
        for d in out['reg_list']:
            подтверждены.add(d.get('domain') if isinstance(d, dict) else str(d))
        out['не_подтверждены'] = [d for d in домены if d not in подтверждены]
    стат = {}
    for d in домены:
        if подтверждены and d not in подтверждены:
            continue
        try:
            стат[d] = cl.domain_summary(d)
        except Exception as e:  # noqa: BLE001
            стат[d] = f'{type(e).__name__}: {str(e)[:120]}'
    out['статистика'] = стат
    out['период'] = f"{(date.today() - timedelta(days=дней)).isoformat()}..{date.today().isoformat()}"
    print(json.dumps(out, ensure_ascii=False, default=str)[:5500])


main()

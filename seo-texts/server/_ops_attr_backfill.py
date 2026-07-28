# -*- coding: utf-8 -*-
"""Бэкфилл подписи и комплаенса в панелях очереди (владелец 28.07:
«атрибуция же есть», а карточка показывала красное «НЕТ»).

Причина была в ai_quota._signature_preview: после появления {brand} в шаблоне
подписи format() кидал KeyError, превью молча становилось пустым, и
_compliance_block считал атрибуцию по одному телу письма — где её и не должно
быть (подпись дописывает отправка). Код исправлен, но у карточек, собранных
раньше, panel_json уже лежит в БД с пустой подписью.

Здесь ПЕРЕСЧИТЫВАЕМ только два поля панели: letter.signature/final_body и
compliance. Текст письма, выбор ящика оператором и остальная панель — не
трогаются. LLM не вызывается (чистая арифметика по шаблону).

Запуск: python _ops_attr_backfill.py          # dry
        python _ops_attr_backfill.py apply
"""
import json
import os
import sys

sys.path.insert(0, r'C:\sender')


def main():
    apply = 'apply' in sys.argv[1:]
    from sender.config import Config
    from sender.store import Store
    from sender.ai_quota import AiQuota
    from sender.infopanel import _compliance_block

    cfg = Config.load(os.environ.get('SENDER_CONFIG') or r'C:\sender\sender.yaml')
    st = Store(cfg.get('service.db_path'))
    st.init_schema()
    q = AiQuota(st, db_path=cfg.get('service.db_path'), config=cfg)

    out = {'pending': 0, 'без_подписи': 0, 'исправлено': 0, 'ошибок': 0,
           'apply': apply, 'примеры': []}
    for r in st.confirm_list(status='pending', limit=5000):
        out['pending'] += 1
        panel = r.get('panel') if isinstance(r.get('panel'), dict) else {}
        letter = panel.get('letter') or {}
        if letter.get('signature'):
            continue
        out['без_подписи'] += 1
        if not apply:
            if len(out['примеры']) < 5:
                out['примеры'].append(r['id'])
            continue
        try:
            # panel['ai'] у части карточек — БУЛЕВ флаг, а не словарь
            # (исторические поколения панели): .get на нём падал и ронял
            # весь бэкфилл в 'bool' object has no attribute 'get'.
            ai = panel.get('ai')
            div = str((ai.get('division') if isinstance(ai, dict) else '')
                      or panel.get('letter_division') or 'kc')
            sig = q._signature_preview(div if div in ('kc', 'meyer') else 'kc')
            if not sig:
                raise RuntimeError('подпись не собралась (шаблон/конфиг)')
            # склейка ровно как в _letter_block/Sender._apply_signature: если
            # тело уже кончается на первой строке подписи («С уважением,»),
            # второй раз её не печатаем
            tail = (r.get('body') or '').rstrip()
            first = sig.split('\n')[0].rstrip()
            final = (tail + '\n' + '\n'.join(sig.split('\n')[1:]).lstrip('\n')
                     if first and tail.endswith(first) else tail + '\n\n' + sig)
            letter.update({'signature': sig, 'final_body': final,
                           'signature_note': 'подпись добавляется при отправке'})
            panel['letter'] = letter
            panel['compliance'] = _compliance_block(
                r.get('subject') or '', r.get('body') or '', sig)
            st.confirm_set_panel(int(r['id']), panel)
            out['исправлено'] += 1
        except Exception as e:  # noqa: BLE001 — одна карточка не роняет прогон
            out['ошибок'] += 1
            if len(out['примеры']) < 5:
                out['примеры'].append(f"{r['id']}: {type(e).__name__}: {str(e)[:90]}")
    print(json.dumps(out, ensure_ascii=False))


main()

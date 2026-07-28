# -*- coding: utf-8 -*-
"""Перегенерация pending-писем очереди подтверждений (владелец 28.07 «делай»).

Зачем: письма в очереди написаны СТАРЫМ промптом от ТОЩИХ сигналов (заголовки,
средний what 56 симв). После деплоя канона редактора (ai_letter, правило 19) и
re-enrich сигналов по полному тексту статьи каждое pending-письмо надо
пересобрать: regenerate_review берёт свежий дайджест из enrich.db и текущие
правила, кладёт новый текст В ТУ ЖЕ строку очереди (выбор ящика оператором
сохраняется — ревью #48). ОТПРАВКИ ЗДЕСЬ НЕТ: письмо остаётся pending, каждое
по-прежнему подтверждает оператор лично (холд по CLAUDE.md соблюдён).

Резюмируемо: done-файл (учёт и ok, и fail — систематический брак не молотим
повторно, оператор дожмёт из UI кнопкой). Лог — jsonl с fsync (durable).

Объём по согласованию с владельцем — NEWS-письма (у них тощий news_object и
старый заход); фильтр news отбирает письма, у которых свежий запрос даёт
news_object+city (тот же признак режима NEWS, что в _add_ideas_generic).

Запуск (panel_py, тот же питон/env, что у службы):
    python _ops_regen_queue.py                # dry: перечень + news/generic
    python _ops_regen_queue.py 15 apply news  # перегенерить чанк из 15 NEWS
    python _ops_regen_queue.py 15 apply       # чанк без фильтра (все виды)
"""
import json
import os
import sys
import time

sys.path.insert(0, r'C:\sender')

DONE = r'C:\sender\_ops\regen-done.json'
LOG = r'C:\sender\_ops\regen-queue-log.jsonl'


def main():
    лимит = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    apply = 'apply' in sys.argv[2:]
    from sender.config import Config
    from sender.store import Store
    from sender.ai_quota import build_ai_quota
    cfg = Config.load(os.environ.get('SENDER_CONFIG') or r'C:\sender\sender.yaml')
    st = Store(cfg.get('service.db_path'))
    st.init_schema()
    done = set()
    if os.path.exists(DONE):
        try:
            done = set(json.load(open(DONE, encoding='utf-8')))
        except Exception:  # noqa: BLE001
            done = set()
    only_news = 'news' in sys.argv[2:]
    q = build_ai_quota(st, cfg)
    pend = st.confirm_list(status='pending', limit=1000)
    cands = [r for r in pend if (r.get('kind') or 'outbound') != 'reply'
             and int(r['id']) not in done]

    def _is_news(row):
        """Тот же признак NEWS, что в _add_ideas_generic: свежий запрос даёт
        news_object И city. Дёшево - только sqlite, без LLM."""
        try:
            rc = st.get_recipient(row.get('recipient_id'))
            if rc is None:
                return False
            ex = q._request(rc).get('extra') or {}
            return bool(ex.get('news_object') and ex.get('city'))
        except Exception:  # noqa: BLE001
            return False

    news_ids = {int(r['id']) for r in cands if _is_news(r)}
    if only_news:
        cands = [r for r in cands if int(r['id']) in news_ids]
    out = {'pending': len(pend), 'candidates': len(cands),
           'news': len(news_ids), 'only_news': only_news,
           'chunk': min(лимит, len(cands)) if лимит else 0,
           'apply': apply, 'ok': 0, 'fail': 0, 'fails': []}
    if not apply or not лимит:
        out['ids'] = [int(r['id']) for r in cands][:80]
        print(json.dumps(out, ensure_ascii=False))
        return
    lg = open(LOG, 'a', encoding='utf-8')
    for r in cands[:лимит]:
        rid = int(r['id'])
        t0 = time.time()
        try:
            res = q.regenerate_review(rid)
        except Exception as e:  # noqa: BLE001 — один брак не роняет чанк
            res = {'ok': False, 'reason': f'{type(e).__name__}: {str(e)[:140]}'}
        rec = {'rid': rid, 'sec': round(time.time() - t0, 1),
               'ok': bool(res.get('ok')), 'subject': res.get('subject'),
               'reason': res.get('reason'), 'fails': res.get('fails')}
        lg.write(json.dumps(rec, ensure_ascii=False) + '\n')
        lg.flush()
        os.fsync(lg.fileno())
        if res.get('ok'):
            out['ok'] += 1
        else:
            out['fail'] += 1
            if len(out['fails']) < 8:
                out['fails'].append({'rid': rid,
                                     'reason': str(res.get('reason') or '')[:120]})
        done.add(rid)
        with open(DONE, 'w', encoding='utf-8') as f:
            json.dump(sorted(done), f)
    out['done_total'] = len(done)
    out['candidates_left'] = len(cands) - out['ok'] - out['fail']
    print(json.dumps(out, ensure_ascii=False))


main()

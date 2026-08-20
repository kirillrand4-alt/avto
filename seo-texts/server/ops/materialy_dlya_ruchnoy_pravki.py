# -*- coding: utf-8 -*-
"""Всё, что нужно, чтобы переписать письмо руками: сайт, паспорт, текст.

Владелец 20.08: «перепишешь руками?» — про четыре письма, которые гейт
бракует на каждой попытке. Чтобы писать самому, нужны те же исходники,
что и у модели: чем компания занимается по её сайту и что сейчас в
письме.
"""
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ИДЫ = [int(a) for a in sys.argv[1:] if a.isdigit()]
ЗНАКОВ = 1500
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
enr = sqlite3.connect(r"file:C:\sender\enrich.db?mode=ro", uri=True, timeout=15)

for rid in ИДЫ:
    row = store.confirm_get(rid) or {}
    инн = str(row.get("inn") or "").strip()
    print("=" * 78)
    print(f"#{rid} {row.get('company_name')} | ИНН {инн} | "
          f"кампания {row.get('campaign_id')} | {row.get('email')}")
    try:
        rec = store.get_recipient(int(row.get("recipient_id") or 0))
        print(f"ОКВЭД: {getattr(rec, 'okved', '')} | "
              f"город: {getattr(rec, 'city', '')}")
    except Exception:                                            # noqa: BLE001
        pass
    try:
        д = q._site_facts(инн) or {}
        print("ПАСПОРТ:", json.dumps(д, ensure_ascii=False)[:1400])
    except Exception as ex:                                      # noqa: BLE001
        print("паспорт не прочесть:", str(ex)[:90])
    try:
        r = enr.execute("SELECT text FROM site_text WHERE inn=?",
                        (инн,)).fetchone()
        print("ТЕКСТ САЙТА:", (r[0] if r else "")[:ЗНАКОВ] or "(пусто)")
    except Exception as ex:                                      # noqa: BLE001
        print("текста сайта нет:", str(ex)[:90])
    print("ТЕМА СЕЙЧАС:", row.get("subject"))
    print("ТЕЛО СЕЙЧАС:\n" + str(row.get("body") or "")[:1400])

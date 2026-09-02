# -*- coding: utf-8 -*-
"""Только чтение: прогоняем НАШЕ письмо кампании 12 через реальный
_apply_signature и печатаем, что получится у адресата. Ничего не шлём."""
import dataclasses
import inspect
import io
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config      # noqa: E402
from sender.store import Store        # noqa: E402
import sender.sender as SS            # noqa: E402

print("=== gender_agree: что делает с меткой ===")
т = io.open(r"C:\sender\sender\gender_agree.py", encoding="utf-8", errors="replace").read()
лн = т.splitlines()
н = next(i for i, л in enumerate(лн) if "МЕТКА_ИМЕНИ" in л)
for i in range(max(0, н - 4), min(len(лн), н + 26)):
    print("  %4d| %s" % (i + 1, лн[i][:100]))

print("\n=== RenderedMessage ===")
RM = getattr(SS, "RenderedMessage", None)
if RM and dataclasses.is_dataclass(RM):
    print("  поля: %s" % ", ".join(f.name for f in dataclasses.fields(RM)))

print("\n=== _apply_signature целиком ===")
исх = inspect.getsource(SS.Sender._apply_signature)
print(исх[:2600])

print("\n=== ШАБЛОН ПОДПИСИ ИЗ КОНФИГА ===")
cfg = Config.load(r"C:\sender\sender.yaml")
print("  signature_enabled = %s" % cfg.get("personalization.signature_enabled", None))
шбл = cfg.get("personalization.signature_template", None)
print("  signature_template:\n----\n%s\n----" % шбл)

print("\n=== НАШЕ ПИСЬМО ПОСЛЕ ОБРАБОТКИ ===")
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
р = c.execute("SELECT subject, body, email FROM confirm_reviews"
              " WHERE campaign_id=12 AND body LIKE '%ИМЯ_ОТПРАВИТЕЛЯ%'"
              " ORDER BY id LIMIT 1").fetchone()
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
камп = store.get_campaign(12)
snd = SS.Sender.__new__(SS.Sender)
snd.config = cfg
snd.store = store
готово = RM(subject=р["subject"], body=р["body"]) if RM else None
try:
    итог = snd._apply_signature(готово, "a.tyunin@sort-systems.ru", камп)
    тело = getattr(итог, "body", None) or getattr(итог, "text", None)
    print("  ящик: a.tyunin@sort-systems.ru (Артем Тюнин, Meyer)")
    print("  ---- ХВОСТ ПИСЬМА ----")
    print("\n".join(тело.splitlines()[-14:]))
    print("  ---- ПЕРВЫЙ АБЗАЦ ----")
    print("\n".join(тело.splitlines()[:5]))
    print("  метка осталась в тексте: %s" % ("ДА" if "ИМЯ_ОТПРАВИТЕЛЯ" in тело else "нет"))
except Exception as ex:
    print("  ошибка прогона: %s: %s" % (type(ex).__name__, str(ex)[:200]))

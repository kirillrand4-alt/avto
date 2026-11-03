# -*- coding: utf-8 -*-
"""Владелец 03.11: «Фишландия» (ИНН 2455042689) ответила «напишите на ea@min-rz.ru» —
ручное письмо на новый адрес, со ссылкой на переадресацию и цитатой первого письма.
Карточка в очередь подтверждения (pending), отправляет оператор. [--zavesti]"""
import json, sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402
ИНН, КОМУ, ПЕРВОЕ = "2455042689", "ea@min-rz.ru", 5165
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = st._conn
m = c.execute("SELECT mailbox_id, rfc_message_id, subject, body_rendered, recipient_id FROM messages WHERE id=?", (ПЕРВОЕ,)).fetchone()
к = c.execute("SELECT panel_json FROM confirm_reviews WHERE id=39490").fetchone()
mb = json.loads(к[0]).get("mailbox_id") or m[0]
print("ящик первого письма:", m[0], "| ящик напоминания:", mb)
print("тема первого:", m[2]); print("--- первое письмо ---\n" + (m[3] or "")[:1500])
if len(sys.argv) > 1 and sys.argv[1] == "--tekst":
    sys.exit(0)
ТЕМА = "Контроль включений в готовой продукции «Фишландии»"
ТЕКСТ = """Добрый день!

Коллеги из «Фишландии» подсказали обратиться к вам по вопросу контроля посторонних включений в готовой продукции.

Мой коллега Иван Бояркин писал о рентген-инспекции Meyer: она находит металл, стекло, керамику, камень и силикон прямо в закрытой упаковке, в том числе в ведёрной фасовке сельди и пресервов. Его письмо ниже.

Подскажите, как у вас сейчас проверяют готовую продукцию на включения? Если интересно, можем бесплатно проверить ваш образец на нашем оборудовании.

Буду благодарна за ответ."""
print("\n=== ПИСЬМО (с %s) ===\nТема: %s\n\n%s" % (mb, ТЕМА, ТЕКСТ))
if "--zavesti" in sys.argv:
    deps = build_deps(cfg, st, dry_run=True)
    р = deps.confirm.submit_reply(reply_to=КОМУ, subject=ТЕМА, body=ТЕКСТ, in_reply_to=m[1],
                                  thread_id="fishlandiya-ea-0311", recipient_id=None, inn=ИНН,
                                  panel={"mailbox_id": mb, "vruchnuyu": "Фишландия: переадресация на ea@min-rz.ru (03.11)"})
    print("карточка", р.review_id, р.status, "created", р.created)
if "--obnovit" in sys.argv:
    with c:
        print("обновлено", c.execute("UPDATE confirm_reviews SET body=? WHERE id=40526 AND status='pending'", (ТЕКСТ,)).rowcount)

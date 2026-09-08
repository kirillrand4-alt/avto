# -*- coding: utf-8 -*-
"""Отправить владельцу копию письма партии на два его адреса.

Текст берём БАЙТ В БАЙТ из живой карточки очереди, а не набираем заново -
иначе смотреть будем не то, что уходит хозяйствам. Подпись дописывает сам
движок (_apply_signature), то есть имя менеджера и юр-атрибуция с ИНН будут
ровно такие же.

ОДНО ОТЛИЧИЕ ОТ БОЕВОГО ПИСЬМА, и о нём надо знать: путь ручного ответа не
ставит заголовок List-Unsubscribe, который есть у рассылочных писем. Текст
и подпись идентичны, а вот попадание в «Спам» по этой копии судить нельзя -
у настоящего письма набор заголовков другой.

    python kopiya_vladelcu.py            # показать, что отправим
    python kopiya_vladelcu.py --primenit
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.gates import Gates                                  # noqa: E402
from sender.sender import Sender                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.suppression import Suppression                      # noqa: E402

ТЕМА_ПАРТИИ = "для качества: вопрос по сортировке зерна"
КУДА = ["kirillrand4@gmail.com", "martiushov@prokompressor.ru"]
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
snd = Sender(cfg, store, Suppression(store), Gates(cfg, store), dry_run=False)

with store._lock:
    р = store._conn.execute(
        "SELECT id, subject, body FROM confirm_reviews "
        " WHERE subject=? AND status='pending' ORDER BY id LIMIT 1",
        (ТЕМА_ПАРТИИ,)).fetchone()
if р is None:
    print("в очереди нет ни одной карточки партии — нечего копировать")
    raise SystemExit(1)
тема, тело = str(р["subject"]), str(р["body"])
print("копия карточки %s: тема %r, тело %d знаков" % (р["id"], тема, len(тело)))

# Ящик Meyer, у которого не сработал гейт. Пауза здесь не помеха: путь
# ручного ответа её не проверяет, и это осознанно - оператор отвечает
# живому человеку. Ящик владельца «в спаме, не использовать» пропускаем.
ящик = None
for mb in cfg.mailboxes():
    if str(getattr(mb, "division", "")).lower() != "meyer":
        continue
    st = store.get_mailbox_state(mb.mailbox_id)
    причина = str(getattr(st, "pause_reason", "") or "") if st else ""
    if "не использовать" in причина:
        continue
    if Gates(cfg, store).check_mailbox(mb.mailbox_id).tripped:
        continue
    ящик = mb.mailbox_id
    break
print("отправляем с ящика: %s" % ящик)
print("кому: %s" % ", ".join(КУДА))

if not ПРИМЕНИТЬ:
    print("")
    print("вхолостую. Отправить — --primenit")
    raise SystemExit(0)

for адрес in КУДА:
    try:
        рез = snd.send_reply(to_email=адрес, subject=тема, body=тело,
                             mailbox_id=ящик)
        print("   %-34s отправлено: %s"
              % (адрес, getattr(рез, "status", рез)))
    except Exception as ex:                                     # noqa: BLE001
        print("   %-34s НЕ УШЛО: %s: %s"
              % (адрес, type(ex).__name__, str(ex)[:120]))
print("")
print("=" * 74)
print("=== КОПИЯ ПИСЬМА ВЛАДЕЛЬЦУ ===")
print("ящик: %s; адресов: %d" % (ящик, len(КУДА)))

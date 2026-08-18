# -*- coding: utf-8 -*-
"""Возьмёт ли КЦ-письмо ящик Meyer, если ящики Meyer снять с паузы.

Вопрос владельца 18.08: «во время автоотправки они не будут использованы?
раньше отправлялись с этих почт письма КЦ из автоотправки».

Раньше — да, отправлялись: 17.08 нашли 181 письмо из 1012 без поля
letter_division, гейт направлений на них возвращал None («не знаю») и
пропускал любой ящик; 13 таких уже ушли, часть с Meyer-адресов за подписью
«Руспром Мейер». Дыру закрыли: пустое поле больше не пропуск, гейт добирает
направление из карточки компании и блокирует несовпадение.

Проверяем не словами, а тем же вызовом, которым пользуется подбор ящика:
для КАЖДОГО готового письма и КАЖДОГО ящика Meyer спрашиваем
Sender.division_block(). Пауза на результат не влияет - значит ответ верен и
для случая «ящики включили».

    python zapusk_svoego_skripta.py ops/mejer_yashchik_voznyot_kc.py
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.wiring import build_deps                             # noqa: E402


class _Письмо:
    """Заглушка message: гейту нужен только id, по нему он ищет карточку."""

    def __init__(self, mid):
        self.id = mid


cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)          # dry_run: ничего не шлём
snd = deps.sender

мейер = [m.mailbox_id for m in cfg.mailboxes() if (m.division or "") == "meyer"]
кц = [m.mailbox_id for m in cfg.mailboxes() if (m.division or "") == "kc"]
print(f"ящиков meyer: {len(мейер)}, ящиков кц: {len(кц)}")
print("гейт направлений активен:",
      bool(getattr(getattr(snd, "_cards", None), "active", False)))

with store._lock:
    готовые = store._conn.execute(
        "SELECT id, recipient_id, message_id, email FROM confirm_reviews "
        "WHERE status='approved'").fetchall()
print(f"готовых (approved) писем: {len(готовые)}\n")

причины = Counter()
пропущено_бы = []
без_сообщения = 0
for rid, recipient_id, message_id, email in готовые:
    r = store.get_recipient(int(recipient_id)) if recipient_id else None
    if r is None:
        причины["нет получателя"] += 1
        continue
    m = _Письмо(int(message_id)) if message_id else None
    if m is None:
        без_сообщения += 1
    for mb in мейер:
        причина = snd.division_block(r, mb, message=m)
        if причина is None:
            пропущено_бы.append((rid, email, mb))
            причины["ПРОПУСТИЛ БЫ"] += 1
        else:
            причины[причина.split(":")[0]] += 1

print("что ответил гейт на пары (готовое письмо × ящик Meyer):")
for п, n in причины.most_common():
    print(f"  {п}: {n}")
print(f"\nписем без привязанного message_id: {без_сообщения}")
if пропущено_бы:
    print(f"\nВНИМАНИЕ: {len(пропущено_бы)} пар прошли бы на ящик Meyer:")
    for rid, email, mb in пропущено_бы[:20]:
        print(f"  письмо #{rid} {email} -> {mb}")
else:
    print("\nНИ ОДНО готовое письмо не может уйти с ящика Meyer.")

# Контроль: те же письма на КЦ-ящиках гейт пропускать ОБЯЗАН, иначе мы
# доказали бы не безопасность, а то, что гейт глухой.
if кц:
    ок = сумма = 0
    for rid, recipient_id, message_id, email in готовые[:200]:
        r = store.get_recipient(int(recipient_id)) if recipient_id else None
        if r is None:
            continue
        m = _Письмо(int(message_id)) if message_id else None
        сумма += 1
        if snd.division_block(r, кц[0], message=m) is None:
            ок += 1
    print(f"\nконтроль на КЦ-ящике {кц[0]}: пропущено {ок} из {сумма} "
          "(должно быть почти всё)")

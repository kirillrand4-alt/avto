# -*- coding: utf-8 -*-
"""Десять сегодняшних мейеровских: убрать ссылку и отправить заново.

Эти письма Яндекс не принял с 554 5.7.1 «подозрение на спам» - они не
уходили вовсе, лежат в статусе failed. Владелец: «убрать ссылку из тела и
отправить без неё, видео предлагать в ответ, если попросят».

ВАЖНАЯ ПОПРАВКА К МОЕЙ ЖЕ ВЕРСИИ: ссылка есть только у четырёх из десяти.
Остальные шесть Яндекс отбил БЕЗ всякой ссылки - значит ссылка усиливает
подозрение, но не она одна его вызывает. Правим тех, у кого она есть,
остальных шлём как есть, и по итогу будет видно, помогло ли.

Вырезаем ПРЕДЛОЖЕНИЕ со ссылкой целиком, а не URL: обрубок вида «Вот
короткое видео с тестовой сортировкой:» хуже самой ссылки.

Сухой прогон по умолчанию. Отправка: --katit
"""
import re
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.dtos import RenderedMessage                             # noqa: E402
from sender.store import Store                                      # noqa: E402
from sender.wiring import build_deps                                # noqa: E402

КАТИТЬ = "--katit" in sys.argv
ИД = [3413, 3424, 3648, 3657, 3666, 3669, 3693, 3701, 3762, 3764]

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
cs = deps.confirm
живой = getattr(cs, "_sender", None)
if живой is None:
    print("живой отправитель не собран - стоп")
    raise SystemExit(1)


def без_ссылки(текст: str) -> str:
    """Убрать предложение со ссылкой; пустой абзац - тоже убрать."""
    абзацы = str(текст or "").split("\n\n")
    вышло = []
    for а in абзацы:
        if "http" not in а:
            вышло.append(а)
            continue
        # предложение = от начала/точки до ссылки включительно
        чисто = re.sub(r"(?:(?<=^)|(?<=[.!?]\s))[^.!?]*?https?://\S+[.!?]?\s*",
                       "", а).strip()
        чисто = re.sub(r"\s*https?://\S+\s*", " ", чисто).strip()
        if чисто:
            вышло.append(чисто)
    return "\n\n".join(x for x in вышло if x.strip())


правки = []
for рид in ИД:
    строка = cs.get(рид)
    тело = str(строка.get("edited_body") or строка.get("body") or "")
    тема = str(строка.get("edited_subject") or строка.get("subject") or "")
    новое = без_ссылки(тело) if "http" in тело else тело
    правки.append((рид, строка, тема, тело, новое))

print("=== что меняем ===")
for рид, строка, тема, тело, новое in правки:
    есть = "http" in тело
    print(f"\n#{рид} {строка.get('email')} ссылка: {'ДА' if есть else 'нет'}")
    if есть:
        # ПОКАЗЫВАЕМ АБЗАЦ ЦЕЛИКОМ. Обрезка первых 150 знаков прятала ровно
        # то место, где стояла ссылка, - «было» и «стало» выглядели
        # одинаково, и проверить правку было нечем.
        было = [с for с in тело.split("\n\n") if "http" in с]
        стало = [с for с in новое.split("\n\n")
                 if с not in тело.split("\n\n")]
        print(f"   БЫЛО:  {было[0] if было else ''}")
        print(f"   СТАЛО: {(стало[0] if стало else '(абзац убран целиком)')}")

if not КАТИТЬ:
    print("\nсухой прогон. Отправка - --katit")
    raise SystemExit(0)

ушло, сбой = 0, []
for рид, строка, тема, тело, новое in правки:
    if новое != тело:
        try:
            store.confirm_update_letter(int(рид), body=новое)
        except Exception as ex:                                    # noqa: BLE001
            with store.transaction() as conn:
                conn.execute("UPDATE confirm_reviews SET edited_body=? "
                             "WHERE id=?", (новое, int(рид)))
            print(f"  #{рид}: текст записан напрямую ({str(ex)[:50]})")
    ящик = cs._fallback_mailbox(inn=строка.get("inn"), prefer_division="meyer")
    напр = cs._division_of_mailbox(ящик) if ящик else None
    if напр != "meyer":
        сбой.append((рид, f"ящик {ящик or '-'} направления {напр or '?'}"))
        print(f"  НЕ шлём #{рид}: ящик {ящик or '-'} ({напр or '?'})")
        continue
    сообщение = store.get_message(int(строка["message_id"]))
    try:
        живой.send(сообщение, RenderedMessage(subject=тема, body=новое),
                   ящик, manual=True, to_email=строка.get("email"))
        ушло += 1
        print(f"  ушло #{рид} {строка.get('email')} <- {ящик}")
        try:
            store.confirm_decide(int(рид), status="sent",
                                 decided_by="владелец: без ссылки 21.08")
        except Exception:                                          # noqa: BLE001
            pass
    except Exception as ex:                                        # noqa: BLE001
        сбой.append((рид, f"{type(ex).__name__}: {str(ex)[:110]}"))
        print(f"  НЕ ушло #{рид}: {type(ex).__name__}: {str(ex)[:110]}")
print(f"\nотправлено: {ушло} | не ушло: {len(сбой)}")

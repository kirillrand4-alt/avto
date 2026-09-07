# -*- coding: utf-8 -*-
"""Показать письма партии «Агро зерно 2026» из очереди подтверждения — глазами.

Владелец 07.09: «проверь глазами выборочно штук 30, если будут ошибки
исправляй пока последняя проверка глазами не выдаст результат без ошибок».

    python glaza_agro.py [сколько=30] [--vse-podryad]
"""
import io, json, os, random, re, sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config                               # noqa: E402
from sender.gender_agree import agree_for_mailbox              # noqa: E402
from sender.sender import Sender, brand_for_division           # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\agro-ochered.jsonl"
СКОЛЬКО = 30
for а in sys.argv[1:]:
    if а.startswith(("сколько=", "skolko=")):
        try:
            СКОЛЬКО = int(а.split("=", 1)[1])
        except ValueError:
            pass
ПОДРЯД = "--vse-podryad" in sys.argv
# КРАТКО: тело письма у всей партии одно, меняется одна фраза. Показываем
# её и подпись, а целиком - каждое десятое: так тридцать писем читаются
# глазами за раз, и при этом видно, что текст вокруг не поехал.
КРАТКО = "--kratko" in sys.argv

# ПИСЬМО ГЛАЗАМИ - ЭТО ТО, ЧТО УВИДИТ АДРЕСАТ, а не то, что лежит в очереди.
# В очереди стоит метка ИМЯ_ОТПРАВИТЕЛЯ и нет подписи: имя и юр-атрибуцию
# дописывает отправка, когда уже выбран ящик. Проверять текст без них -
# значит не проверить ровно те две строки, которыми письмо начинается и
# заканчивается. Собираем здесь так же, как Sender._apply_signature.
cfg = Config.load(r"C:\sender\sender.yaml")
ЯЩИКИ = []
try:
    for м in (cfg.get("mailboxes", None) or []):
        имя = str((м or {}).get("from_name") or "")
        if имя and "meyer" in str((м or {}).get("division") or "meyer").lower():
            ЯЩИКИ.append((str((м or {}).get("id") or ""), имя))
except Exception:                                              # noqa: BLE001
    pass
if not ЯЩИКИ:
    ЯЩИКИ = [("", "Ирина Кузнецова")]
_ШАБЛОН = (cfg.get("personalization.signature_template", None)
           or Sender._DEFAULT_SIGNATURE)
try:
    _ИНН = str(getattr(cfg.legal(), "inn", "") or "")
except Exception:                                              # noqa: BLE001
    _ИНН = ""


def как_уйдёт(тело, ящик_id, имя_ящика):
    тело = agree_for_mailbox(тело, имя_ящика, cfg, ящик_id)
    подпись = _ШАБЛОН.format(name=имя_ящика, inn=_ИНН,
                             role="Менеджер по продажам",
                             brand=brand_for_division(cfg, "meyer"))
    хвост = тело.rstrip()
    строки_п = подпись.split("\n")
    if строки_п and хвост.endswith(строки_п[0].rstrip()):
        подпись = "\n".join(строки_п[1:]).lstrip("\n")
        return хвост + "\n" + подпись if подпись else хвост
    return хвост + "\n\n" + подпись


# ЧИТАЕМ БАЗУ, А НЕ ЖУРНАЛ. Журнал хранит текст на момент постановки, а
# правила подстановки по ходу проверки менялись и карточки переписывались
# (ops/perepisat_ochered_agro.py). Проверка по журналу показывала бы текст,
# которого в очереди уже нет - то есть проверяла бы не то письмо.
from sender.store import Store                                 # noqa: E402
ид = []
if os.path.exists(ЖУРНАЛ):
    for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
        с = с.strip()
        if not с:
            continue
        try:
            z = json.loads(с)
        except Exception:                                      # noqa: BLE001
            continue
        if z.get("review_id"):
            ид.append((int(z["review_id"]), z.get("имя_реестра") or ""))
store = Store(r"C:\sender\sender.db")
строки = []
with store._lock:
    for rid, реестр in ид:
        р = store._conn.execute(
            "SELECT id, inn, email, subject, body, status "
            "  FROM confirm_reviews WHERE id=?", (rid,)).fetchone()
        if р is None or str(р["status"]) != "pending":
            continue
        строки.append({"review_id": р["id"], "inn": р["inn"],
                       "почта": р["email"], "тема": р["subject"],
                       "тело": р["body"], "имя_реестра": реестр})
print("писем в очереди (pending): %d" % len(строки))
if not строки:
    raise SystemExit(0)
выбор = строки[:СКОЛЬКО] if ПОДРЯД else random.sample(
    строки, min(СКОЛЬКО, len(строки)))
for n, z in enumerate(выбор, 1):
    ящик_id, имя_ящика = ЯЩИКИ[(n - 1) % len(ЯЩИКИ)]
    готово = как_уйдёт(z.get("тело") or "", ящик_id, имя_ящика)
    if КРАТКО and n % 10 != 1:
        фраза = [л for л in готово.splitlines() if "выращивает зерновые" in л
                 or "Ваше хозяйство" in л]
        print("   %2d %-30s | %s" % (n, str(z.get("имя_реестра"))[:30],
                                     (фраза[0] if фраза else "!! ФРАЗЫ НЕТ")[:100]))
        continue
    print("")
    print("#" * 78)
    print("# %d/%d  review %s | ИНН %s | %s | ящик %s"
          % (n, len(выбор), z.get("review_id"), z.get("inn"), z.get("почта"),
             имя_ящика))
    print("# реестр: %s" % z.get("имя_реестра"))
    print("#" * 78)
    print("Тема: %s" % z.get("тема"))
    print("")
    print(готово)

# -*- coding: utf-8 -*-
"""Поставить письмо на ЗАПАСНОЙ адрес хозяйствам, у которых основной оказался ЦЗН.

Снятые письма центров занятости (ops/ubrat_czn_iz_ocheredi.py) забрали с
собой сами хозяйства: компания в партии была, а писать стало некуда. У
большинства в карточке Чеко есть второй адрес, уже свой. Заводим его
отдельным получателем и ставим то же письмо.

Отдельный получатель, а не правка старого: recipients уникальны по адресу,
и подмена почты в существующей строке стёрла бы след, что ЦЗН-адрес у этой
компании вообще был. Тот же приём уже применялся - источник vtoroy_adres.

    python zapasnoy_adres_agro.py            # показать, кому и на какой адрес
    python zapasnoy_adres_agro.py --primenit
"""
import io
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import date

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sender.ai_quota import build_ai_quota                      # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.confirm import ConfirmSend                          # noqa: E402
from sender.dtos import RecipientIn                             # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.suppression import Suppression                      # noqa: E402
from imya_v_pismo import итоговое_имя                           # noqa: E402
from zona_po_innu import зона_по_inn                           # noqa: E402

ТЕМА = "для качества: вопрос по сортировке зерна"
ГРУППА = "Агро зерно 2026"
ИСТОЧНИК = "чеко-агро-2026-второй"
КАМПАНИЯ = 11
НАПРАВЛЕНИЕ = "meyer"
ЖУРНАЛ = r"C:\sender\_ops\agro-ochered.jsonl"
ИМЕНА = r"C:\sender\_ops\agro-imena.jsonl"
ПРИЗНАК_СНЯТИЯ = "адрес центра занятости"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv

ТЕЛО = """Добрый день!

Меня зовут ИМЯ_ОТПРАВИТЕЛЯ, представляю компанию «Руспром Meyer». Работаю с зерновыми хозяйствами по вопросам оптической сортировки зерна.

{зачин} выращивает зерновые культуры, поэтому обращаюсь по теме доведения товарных партий до требуемого качества.

Для таких задач применяется фотосепаратор: машина отбраковывает минеральные, сорные, зерновые примеси, проросшие, повреждённые зёрна. Наше оборудование быстро перенастраивается в зависимости от культуры и задачи двумя кнопками.

Мы проводим тестовые сортировки в наших демо залах в любом удобном формате - лично или дистанционно (предоставляя видеоматериал сортировки).

Подскажите, актуальна ли для вас сейчас задача по очистке сырья или подготовке семенного материала?

С уважением,"""

# Тот же невод, что и при снятии: запасной адрес не должен оказаться вторым
# ЦЗН-ящиком той же службы.
НЕВОД = ("czn", "szn", "zanyat", "zanyatost", "trud", "rabota", "vsem",
         "stavzan", "cznz")
АДРЕС = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def занятость(адрес):
    а = str(адрес or "").lower()
    лок, _, дом = а.partition("@")
    for ч in re.split(r"[.\-_+]", лок) + дом.split("."):
        if ч in НЕВОД:
            return True
    return any(сл in дом for сл in НЕВОД)


def _в_журнал(запись):
    with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
        f.write(json.dumps(запись, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _с_ожиданием(зовём):
    посл = None
    for поп in range(6):
        try:
            return зовём(), None
        except Exception as ex:                                 # noqa: BLE001
            посл = ex
            if "locked" not in str(ex).lower() and поп >= 2:
                break
            time.sleep(2 + поп * 3)
    return None, посл


имена = {}
for с in io.open(ИМЕНА, encoding="utf-8", errors="replace"):
    с = с.strip()
    if с:
        try:
            z = json.loads(с)
            if z.get("сыро"):
                имена[z["сыро"]] = (z.get("имя"), bool(z.get("человек")))
        except Exception:                                       # noqa: BLE001
            pass

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))
день = date.today().isoformat()

занятые = set()
with store._lock:
    for (а,) in store._conn.execute("SELECT email FROM recipients"):
        занятые.add(str(а or "").lower())

счёт = Counter()
цели = []
with store._lock:
    снятые = store._conn.execute(
        "SELECT recipient_id, email FROM confirm_reviews "
        " WHERE subject=? AND reason LIKE ?",
        (ТЕМА, "%" + ПРИЗНАК_СНЯТИЯ + "%")).fetchall()
for р in снятые:
    счёт["снятых карточек"] += 1
    if not р["recipient_id"]:
        счёт["нет получателя"] += 1
        continue
    rec = store.get_recipient(int(р["recipient_id"]))
    if rec is None:
        счёт["карточки получателя нет"] += 1
        continue
    extra = dict(getattr(rec, "extra", None) or {})
    запас = [str(x).strip().lower() for x in (extra.get("pochty_eshchyo") or [])]
    запас = [x for x in запас if АДРЕС.match(x) and not занятость(x)
             and x != str(getattr(rec, "email", "")).lower()]
    if not запас:
        счёт["запасного адреса нет"] += 1
        continue
    адрес = запас[0]
    if адрес in занятые:
        счёт["запасной адрес уже есть в базе"] += 1
        continue
    сыро = " ".join(str(getattr(rec, "company_name", "") or "").split())
    пара = имена.get(сыро)
    if not пара:
        счёт["названия нет в разборе"] += 1
        continue
    подл, _вид = итоговое_имя(пара[0], пара[1])
    занятые.add(адрес)
    новая = dict(extra)
    новая["gruppy"] = [ГРУППА]
    новая["osnovnoy_adres"] = str(getattr(rec, "email", "") or "")
    новая["pochemu_zapasnoy"] = ("основной адрес компании оказался ящиком "
                                 "центра занятости")
    новая["pochty_eshchyo"] = [x for x in запас[1:]] or None
    цели.append((RecipientIn(
        email=адрес,
        domain=адрес.split("@", 1)[1],
        inn=str(getattr(rec, "inn", "") or "") or None,
        company_name=getattr(rec, "company_name", ""),
        segment=НАПРАВЛЕНИЕ,
        source=ИСТОЧНИК,
        region=getattr(rec, "region", None),
        tz=зона_по_inn(getattr(rec, "inn", "")),
        extra=новая), подл, str(getattr(rec, "email", "") or "")))
    счёт["К ПОСТАНОВКЕ"] += 1

поставлено = отказ = 0
причины = Counter()
if ПРИМЕНИТЬ:
    for р, подл, старый in цели:
        тело = ТЕЛО.format(зачин=подл)
        зап = {"inn": р.inn, "почта": р.email, "имя_реестра": р.company_name,
               "имя_в_письме": подл, "день": день, "тема": ТЕМА, "тело": тело,
               "вместо_адреса": старый}
        rid, сбой = _с_ожиданием(lambda: store.upsert_recipient(р))
        if not rid:
            зап["брак"] = "получатель не завёлся: %s" % str(сбой)[:100]
            причины["получатель не завёлся"] += 1
            отказ += 1
            _в_журнал(зап)
            continue
        зап["recipient_id"] = rid
        rec = store.get_recipient(rid)
        пара, сбой = _с_ожиданием(lambda: q._ensure_message(КАМПАНИЯ, rid))
        mid = почему = None
        if пара is not None:
            mid, _шаг, почему = пара
        if not mid:
            зап["брак"] = "нет message_id: %s" % (почему or str(сбой)[:100])
            причины["нет message_id"] += 1
            отказ += 1
            _в_журнал(зап)
            continue
        письмо = {"subject": ТЕМА, "body": тело, "division": НАПРАВЛЕНИЕ,
                  "division_reason": "ОКВЭД 01.11/01.11.1, партия «%s»" % ГРУППА,
                  "rounds": []}
        try:
            panel = q._panel(rec, письмо, день, {})
        except Exception as ex:                                 # noqa: BLE001
            panel = {"ai": False, "letter_division": НАПРАВЛЕНИЕ}
            зап["панель_упала"] = str(ex)[:120]
        r, сбой = _с_ожиданием(lambda: cs.submit(
            email=р.email, subject=ТЕМА, body=тело, inn=р.inn,
            campaign_id=КАМПАНИЯ, recipient_id=rid, message_id=mid,
            panel=panel))
        if r is None:
            зап["брак"] = "очередь не приняла: %s" % str(сбой)[:100]
            причины["очередь не приняла"] += 1
            отказ += 1
        else:
            зап["review_id"] = getattr(r, "review_id", None)
            зап["статус"] = str(getattr(r, "status", "") or "")
            зап["причина"] = str(getattr(r, "reason", "") or "")
            if зап["статус"] == "pending":
                поставлено += 1
            else:
                отказ += 1
                причины["%s: %s" % (зап["статус"], зап["причина"][:50])] += 1
        _в_журнал(зап)

for р, подл, старый in цели:
    print("   %-30s → %-30s %s"
          % (старый[:30], р.email[:30], str(р.company_name)[:26]))
print("")
print("=" * 74)
print("=== ЗАПАСНОЙ АДРЕС: %s ==="
      % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
for к, в in счёт.most_common():
    print("   %-34s %5d" % (к, в))
if ПРИМЕНИТЬ:
    print("")
    print("поставлено в очередь: %d; не приняты: %d" % (поставлено, отказ))
    for к, в in причины.most_common(6):
        print("   %-46s %4d" % (к, в))
else:
    print("")
    print("вхолостую. Поставить — --primenit")

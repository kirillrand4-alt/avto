# -*- coding: utf-8 -*-
"""Ярус C (Meyer, кампания 18): починить в забракованном письме ТОЛЬКО то, за что
забраковали (владелец 29.10: «запускай починку 390 писем»). Основа — dopisat_kc1.py.
Техсбои («прогон упал») сюда не идут — их перегенерирует дирижёр v4c_pachki.
«Не покупатель» не чиним. Чиним правила текста: как работает машина, предприятие
не названо, тема «своя/чужая», регламент как повод, «компоненты», «кость»,
длинный перечень культур, «по цвету/форме». Модель правит только указанное место,
механический гейт канона Meyer проверяет заново; чистое — в «Подтвердить отправку»
штатным ConfirmSend.submit. Журнал _ops/dopisannye-v4c.jsonl (резюм).
    dopisat_v4c.py [потолок] [--katit]"""
import io
import json
import os
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
import gen_provider as GP                                        # noqa: E402
from sender.ai_letter import gate, load_facts                    # noqa: E402
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.confirm import ConfirmSend                           # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.suppression import Suppression                       # noqa: E402

if "--zapusk" in sys.argv:   # отсоединённо: раннер режет на 900 с; лог _ops/dopisat-v4c.log
    import subprocess
    л = io.open(r"C:\sender\_ops\dopisat-v4c.log", "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__)] + [a for a in sys.argv[1:] if a != "--zapusk"],
                         cwd=r"C:\sender", stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(5)
    print("починка запущена, pid %d, жив %s" % (п.pid, п.poll() is None))
    raise SystemExit(0)
ЖУРНАЛ = r"C:\sender\_ops\gen-v4c.jsonl"
СВОЙ = r"C:\sender\_ops\dopisannye-v4c.jsonl"
МОДЕЛЬ = os.environ.get("GEN_CHECKER_MODEL", "claude-sonnet-4-6")
КАТИТЬ = "--katit" in sys.argv
ПОТОЛОК = int(next((a for a in sys.argv[1:] if a.isdigit()), "1000"))
КАМП = 18
ЧИНИМ = ("как именно работает машина", "предприятие не названо", "тему не делим", "регламент как причина",
         "компоненты", "кость", "перечень культур", "по цвету/форме", "канцелярит", "израсходован", "оборот")
НЕ_ЧИНИМ = ("не покупатель", "прогон упал", "переставить на kc", "http 403")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))
факты = load_facts(division="meyer")
уже = set()
if os.path.exists(СВОЙ):
    for s in io.open(СВОЙ, encoding="utf-8"):
        try:
            уже.add(int(json.loads(s)["recipient_id"]))
        except Exception:  # noqa: BLE001
            pass
с_письмом = {str(r[0]) for r in store._conn.execute(
    "SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    "WHERE m.status IN ('pending_review','scheduled','sending','sent') AND r.inn IS NOT NULL")}
записи = []
for s in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
    try:
        записи.append(json.loads(s))
    except ValueError:
        pass
последняя = {}
for z in записи:
    if z.get("inn"):
        последняя[str(z["inn"])] = z
счёт, работа = Counter(), []
for инн, z in последняя.items():
    if z.get("ок") or инн in с_письмом:
        continue
    if not z.get("тело_брака"):
        счёт["нет черновика"] += 1
        continue
    if int(z.get("recipient_id") or 0) in уже:
        счёт["уже чинили"] += 1
        continue
    п = " ".join(str(x) for x in (z.get("брак") or [])).lower()
    if any(w in п for w in НЕ_ЧИНИМ):
        счёт["не чиним (не покупатель/техсбой)"] += 1
        continue
    if not any(w in п for w in ЧИНИМ):
        счёт["причина не из списка"] += 1
        continue
    работа.append(z)
работа = работа[:ПОТОЛОК]
print("к починке:", len(работа), dict(счёт))
if not работа or not КАТИТЬ:
    print("СУХОЙ ПРОГОН. Катить — --katit")
    raise SystemExit(0)
СИСТЕМА = (
    "Ты редактор холодных B2B-писем Meyer (фотосепараторы, рентген-инспекция). Тебе дают письмо и "
    "причину, по которой его забраковала проверка. Исправь ТОЛЬКО это место, остальное письмо не трогай "
    "ВООБЩЕ: ни слова, ни порядка абзацев.\n"
    "- «как именно работает машина» или «по цвету/форме описывает работу машины»: убери описание принципа "
    "работы, оставь, ЧТО машина убирает или находит;\n"
    "- «предприятие не названо»: назови компанию в теме или в первом абзаце;\n"
    "- «тему не делим на свою и чужую»: перепиши просьбу о контакте просто: «Если вопрос не к вам, буду "
    "благодарен(на) за контакт коллеги»;\n"
    "- «регламент как причина» (ХАССП, аудиты сетей, сертификация): убери регламент как повод письма;\n"
    "- «компоненты»: замени на конкретное название их продукции из письма;\n"
    "- «кость»: убери упоминание кости;\n"
    "- «перечень культур длинный»: оставь 4-5 главных;\n"
    "- «канцелярит»/«оборот израсходован»: перепиши только эту фразу простыми словами.\n"
    "Без длинных тире, без новых фактов и цифр. Подпись не добавляй, письмо заканчивается «С уважением,».\n"
    "Ответь строго JSON: {\"pisma\":[{\"id\":1,\"subject\":\"...\",\"body\":\"...\"}]}")
замок = threading.Lock()
итоги = Counter()
день = date.today().isoformat()


def одно(z):
    rid = int(z["recipient_id"])
    inn = str(z.get("inn") or "")
    rec = store.get_recipient(rid)
    if not rec:
        with замок:
            итоги["получателя нет"] += 1
        return
    запрос = ("ПРИЧИНА БРАКА: %s\n\n=== ПИСЬМО id=1\nКОМПАНИЯ: %s\nТЕМА: %s\n%s\n\nОТВЕТЬ ТОЛЬКО JSON, БЕЗ РАССУЖДЕНИЙ."
              % ("; ".join(str(x) for x in (z.get("брак") or []))[:400], z.get("имя"), z.get("тема_брака"), z.get("тело_брака")))
    тема = тело = ""
    for _ in range(3):
        try:
            m = GP._raw_stream([{"role": "user", "content": запрос}], МОДЕЛЬ, 4000, thinking=False, effort="low", system=СИСТЕМА)
            т = m if isinstance(m, str) else "".join(getattr(b, "text", "") for b in getattr(m, "content", []) or [])
            вх = [x.start() for x in re.finditer(r'\{\s*"pisma"', т)]
            д = json.JSONDecoder(strict=False).raw_decode(т[вх[-1]:])[0] if вх else {}
            L = (д.get("pisma") or [{}])[0]
            тема = str(L.get("subject") or z.get("тема_брака") or "").strip()
            тело = str(L.get("body") or "").strip()
            if тело:
                break
        except Exception:  # noqa: BLE001
            continue
    if len(тело) < 200:
        with замок:
            итоги["модель не дала текст"] += 1
        return
    if "С уважением," not in тело:
        тело = тело.rstrip() + "\n\nС уважением,"
    try:
        req = q._request(rec)
    except Exception:  # noqa: BLE001
        req = {"mode": "GENERIC", "extra": {}}
    fails = gate(тема, тело, mode=req.get("mode") or "GENERIC", extra=req.get("extra") or {}, facts=факты, division="meyer")
    строка = {"recipient_id": rid, "inn": inn, "имя": z.get("имя"), "причина": (z.get("брак") or [""])[0][:200],
              "было_тема": z.get("тема_брака"), "было": z.get("тело_брака"), "тема": тема, "тело": тело,
              "гейт": [str(f)[:120] for f in (fails or [])[:3]], "день": день}
    if fails:
        with замок:
            итоги["гейт снова забраковал"] += 1
    else:
        try:
            пара = q._ensure_message(КАМП, rid)
            mid = пара[0] if пара else None
            panel = q._panel(rec, {"subject": тема, "body": тело}, день, req)
            panel = dict(panel or {}, letter_division="meyer")
            r = cs.submit(email=str(getattr(rec, "email", "") or ""), subject=тема, body=тело, inn=inn, campaign_id=КАМП,
                          recipient_id=rid, message_id=mid, panel=panel)
            строка["review_id"] = getattr(r, "review_id", None)
            строка["статус"] = getattr(r, "status", "")
        except Exception as ex:  # noqa: BLE001
            строка["очередь"] = "%s: %s" % (type(ex).__name__, str(ex)[:110])
        with замок:
            итоги["починено и в очереди" if строка.get("review_id") else "очередь не приняла"] += 1
    with замок, io.open(СВОЙ, "a", encoding="utf-8") as f:
        f.write(json.dumps(строка, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


t0 = time.time()
with ThreadPoolExecutor(max_workers=6) as pool:
    list(pool.map(одно, работа))
print("готово за %.0f с" % (time.time() - t0))
for k, n in итоги.most_common():
    print("  %4d  %s" % (n, k))

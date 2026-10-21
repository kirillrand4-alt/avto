# -*- coding: utf-8 -*-
"""КЦ-1 (канон августа): починить в забракованном письме ТОЛЬКО то, за что
забраковали (владелец 21.10: «можем починить только ошибку в письме, не трогая
остальное?»). Основа — dopisat_zabrakovannye.py (19.08, зачины).

Чиним: зачин/оборот израсходован, канцелярит, нет «С уважением,». Модель правит
только указанное место; концовку КЦ (строка отказа + просьба о контакте) после
правки пришивает код канона августа. Проверка — механический гейт канона августа.
Очередь — кампания 17, штатный ConfirmSend.submit.

Исходно: дописать забракованные письма: переписать зачин, не платя за круг заново.

Владелец 19.08: «а письма при этом сохраняются? ты можешь их вручную
дописать?».

Типичный отказ волны - «заход "от профиля" израсходован на партии» или
«анти-штамп: оборот израсходован». Претензия к ПЕРВОЙ ФРАЗЕ; остальное
письмо написано, проверено верификатором и линзами и стоило денег. Полный
круг генерации - $0.16, переписать зачин дешёвой моделью - меньше цента.

Что делает прогон:
  * берёт из журнала партии черновики брака (тема_брака/тело_брака);
  * оставляет только те, чья причина - зачин/оборот (остальные это claim о
    компании, их зачином не спасти);
  * просит модель попроще заменить ПЕРВЫЙ абзац, не трогая остальное;
  * прогоняет письмо через тот же механический гейт, что и генерация;
  * чистое кладёт в очередь штатным путём (ConfirmSend.submit).

Журнал durable. Без аргумента - сухой прогон.

    python zapusk_svoego_skripta.py ops/dopisat_zabrakovannye.py
    python zapusk_svoego_skripta.py ops/dopisat_zabrakovannye.py 40 --катить
"""
import io
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402
import importlib.util as _iu                                     # noqa: E402
import sender as _sender                                         # noqa: E402
_сп = _iu.spec_from_file_location("sender.ai_letter", r"C:\sender\server\ops\ai_letter_avgust.py")
_A = _iu.module_from_spec(_сп)
sys.modules["sender.ai_letter"] = _A
_сп.loader.exec_module(_A)
_sender.ai_letter = _A
from sender.ai_letter import gate, load_facts, zashit_kontsovku  # noqa: E402
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.confirm import ConfirmSend                           # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.suppression import Suppression                       # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\gen-kc1-avgust.jsonl"
СВОЙ = r"C:\sender\_ops\dopisannye-kc1.jsonl"
МОДЕЛЬ = os.environ.get("GEN_CHECKER_MODEL", "claude-sonnet-4-6")
КАТИТЬ = "--катить" in sys.argv or "--katit" in sys.argv
ПОТОЛОК = int(next((a for a in sys.argv[1:] if a.isdigit()), "40"))
КАМПАНИЯ = {"kc": 17, "meyer": 18}
ПРО_ЗАЧИН = ("израсходован", "анти-штамп", "зачин", "первая фраза", "канцелярит", "финал не", "оборот")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))
_факты = {"kc": load_facts(division="kc"),
          "meyer": load_facts(division="meyer")}

уже = set()
if os.path.exists(СВОЙ):
    for s in io.open(СВОЙ, encoding="utf-8", errors="replace"):
        try:
            уже.add(int(json.loads(s)["recipient_id"]))
        except Exception:                                        # noqa: BLE001
            pass

# ПОВТОР КЦ <30 ДНЕЙ — НЕ ЧИНИМ (как в spisok_kc1.py): заслон панели решает по
# extra.division и пропускает повторы КЦ, поэтому отсекаем по факту отправок.
from datetime import datetime as _dt, timedelta as _td  # noqa: E402
_гр = (_dt.utcnow() - _td(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
_кц_камп = {r[0] for r in store._conn.execute("SELECT id, name FROM campaigns")
            if r[0] in (1, 5, 6, 9, 10) or "КЦ" in str(r[1] or "")}
_недавно = set()
for _i, _e, _cid in store._conn.execute("SELECT inn, lower(email), campaign_id FROM send_log WHERE outcome='sent' AND ts>=?", (_гр,)):
    if _cid in _кц_камп:
        _недавно.add(str(_i or ""))
        _недавно.add(str(_e or ""))
_в_работе = {str(r[0]) for r in store._conn.execute(
    "SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.campaign_id IN (15,16,17) "
    "AND m.status IN ('pending_review','scheduled','approved','sending','sent')")}
работа, счёт = [], Counter()
готовые_инн = set()
записи = []
for s in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
    try:
        записи.append(json.loads(s))
    except Exception:                                            # noqa: BLE001
        continue
for z in записи:
    if z.get("ок") or z.get("тело"):
        готовые_инн.add(str(z.get("inn") or ""))
for z in записи:
    if not z.get("тело_брака"):
        continue
    rid = z.get("recipient_id")
    if rid is None or int(rid) in уже:
        счёт["уже дописано"] += 1
        continue
    if str(z.get("inn") or "") in готовые_инн:
        счёт["письмо этой фирмы уже есть"] += 1
        continue
    if str(z.get("inn") or "") in _недавно or str(z.get("inn") or "") in _в_работе:
        счёт["компании уже писали КЦ <30 дней или письмо уже в работе"] += 1
        continue
    причина = " ".join(str(x) for x in (z.get("брак") or [])).lower()
    if not any(сл in причина for сл in ПРО_ЗАЧИН):
        счёт["претензия не к зачину"] += 1
        continue
    работа.append(z)
# ОДИН ПОЛУЧАТЕЛЬ - ОДИН ЧЕРНОВИК. В журнале у компании бывает несколько
# записей брака (повторные попытки в разных чанках), и первый прогон 19.08
# взял #3000 дважды: два вызова модели, две отправки в очередь на один
# адрес. Оставляем последний черновик - он свежее.
_по_получателю = {}
for z in работа:
    _по_получателю[int(z["recipient_id"])] = z
работа = list(_по_получателю.values())[:ПОТОЛОК]
print(f"черновиков брака в журнале: "
      f"{sum(1 for z in записи if z.get('тело_брака'))}")
print(f"к дописыванию: {len(работа)}")
for k, n in счёт.most_common():
    print(f"  {k}: {n}")
if not работа or not КАТИТЬ:
    print("\nсухой прогон: ничего не тронуто. Катить — аргумент --катить"
          if работа else "дописывать нечего")
    raise SystemExit(0)

СИСТЕМА = (
    "Ты редактор холодных B2B-писем. Тебе дают письмо и ОДНУ причину, по которой "
    "его забраковала проверка. Исправь ТОЛЬКО это место, остальное письмо не "
    "трогай ВООБЩЕ - ни слова, ни порядка абзацев.\n\n"
    "Как чинить по причине:\n"
    "- «заход/зачин израсходован» или «оборот»: замени только ПЕРВЫЙ абзац после "
    "приветствия, сохранив смысл и факты. Не начинай с «Смотрел профиль», «Смотрел "
    "сайт», «Изучил», «Видел, что вы», «Ознакомился»; начни с процесса, участка, "
    "продукции или задачи компании;\n"
    "- «канцелярит»: перепиши только фразу с указанным оборотом простыми словами;\n"
    "- «финал не «С уважением,»»: ничего не переписывай, просто верни письмо.\n"
    "Без длинных тире, без рекламных оборотов, без новых фактов и цифр.\n\n"
    "Ответь строго JSON: {\"pisma\":[{\"id\":N,\"subject\":\"...\","
    "\"body\":\"...\"}]}")

замок = __import__("threading").Lock()
итоги = Counter()
день = date.today().isoformat()


def одно(z):
    rid = int(z["recipient_id"])
    inn = str(z.get("inn") or "")
    div = str(z.get("направление") or "kc")
    rec = store.get_recipient(rid)
    if not rec:
        with замок:
            итоги["получателя нет"] += 1
        return
    куски = (f"ПРИЧИНА БРАКА: {'; '.join(str(x) for x in (z.get('брак') or []))[:300]}\n\n"
             f"=== ПИСЬМО id=1\nКОМПАНИЯ: {z.get('имя')}\n"
             f"ТЕМА: {z.get('тема_брака')}\n{z.get('тело_брака')}")
    тема, тело, посл = "", "", None
    # Три попытки: модель иногда отдаёт битый JSON (кавычки в тексте письма).
    for _п in range(3):
        try:
            m = GP._raw_stream([{"role": "user", "content": куски}], МОДЕЛЬ, 1500,
                               thinking=False, system=СИСТЕМА)
            т = m if isinstance(m, str) else "".join(
                getattr(b, "text", "") for b in getattr(m, "content", []) or [])
            j = __import__("re").search(r"\{.*\}", т, __import__("re").S)
            d = json.loads(j.group(0)) if j else {}
            L = (d.get("pisma") or [{}])[0]
            тема = str(L.get("subject") or z.get("тема_брака") or "").strip()
            тело = str(L.get("body") or "").strip()
            # Концовка КЦ — кодом, как в генерации (строка отказа + просьба о контакте).
            тело = zashit_kontsovku(тело, "kc") if тело else тело
            if тело:
                break
        except Exception as ex:                                  # noqa: BLE001
            посл = ex
    if not тело:
        with замок:
            итоги[f"сбой модели: {type(посл).__name__ if посл else 'пусто'}"] += 1
        return
    if len(тело) < 200:
        with замок:
            итоги["ответ пустой"] += 1
        return
    try:
        req = q._request(rec)
    except Exception:                                            # noqa: BLE001
        req = {"mode": "GENERIC", "extra": {}}
    fails = gate(тема, тело, mode=req.get("mode") or "GENERIC",
                 extra=req.get("extra") or {}, facts=_факты.get(div, {}),
                 division=div)
    строка = {"recipient_id": rid, "inn": inn, "имя": z.get("имя"),
              "направление": div, "тема": тема, "тело": тело,
              "гейт": [str(f)[:120] for f in (fails or [])[:3]],
              "день": день}
    if fails:
        with замок:
            итоги["гейт снова забраковал"] += 1
            with io.open(СВОЙ, "a", encoding="utf-8") as f:
                f.write(json.dumps(строка, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        return
    cid = КАМПАНИЯ.get(div, 10)
    try:
        пара = q._ensure_message(cid, rid)
        mid = пара[0] if пара else None
        panel = q._panel(rec, {"subject": тема, "body": тело}, день, req)
        r = cs.submit(email=str(getattr(rec, "email", "") or ""),
                      subject=тема, body=тело, inn=inn, campaign_id=cid,
                      recipient_id=rid, message_id=mid, panel=panel)
        строка["review_id"] = getattr(r, "review_id", None)
        строка["статус"] = getattr(r, "status", "")
    except Exception as ex:                                      # noqa: BLE001
        строка["очередь"] = f"{type(ex).__name__}: {str(ex)[:110]}"
    with замок:
        итоги["дописано и в очереди" if строка.get("review_id")
              else "очередь не приняла"] += 1
        with io.open(СВОЙ, "a", encoding="utf-8") as f:
            f.write(json.dumps(строка, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())


t0 = time.time()
with ThreadPoolExecutor(max_workers=8) as pool:
    list(pool.map(одно, работа))
print(f"\nготово за {time.time() - t0:.0f}с")
for k, n in итоги.most_common():
    print(f"  {n:>4}  {k}")

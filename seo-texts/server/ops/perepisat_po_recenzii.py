# -*- coding: utf-8 -*-
"""Переписать письма, забракованные рецензентом за непроверенные утверждения.

Владелец 19.08: «разбери очередь: перекинь в отправку на завтра годные
письма, не годные перепиши».

Чем это отличается от dopisat_zabrakovannye.py: тот меняет ПЕРВУЮ ФРАЗУ,
когда претензия к зачину, и claim-претензии сознательно не берёт. А в
очереди сейчас ровно claim: «письмо утверждает X, а сайт этого не
подтверждает». Лечится это не зачином, а заменой самого утверждения на то,
что сайт подтверждает.

Порядок на каждое письмо:
  1. снимаем текст сайта (тем же способом, что рецензент);
  2. просим модель переписать ТОЛЬКО оспоренные места, не трогая остальное;
  3. гоняем через механический гейт генерации;
  4. ПЕРЕПРОВЕРЯЕМ рецензентом заново - иначе одобрим непроверенное;
  5. годно -> кладём правку в очередь как 'edited' и ставим слот отправки;
     не годно -> оставляем pending и пишем причину в журнал.

Журнал durable (jsonl + fsync). Без --katit - сухой прогон.
"""
import gzip
import io
import json
import os
import re
import sys
import threading
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402
from sender.ai_letter import ZNAKOMSTVO, gate, load_facts        # noqa: E402
from sender.auto_send import (next_slot, recipient_tz_name,      # noqa: E402
                              window_from)
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

РЕЦЕНЗИИ = r"C:\sender\_ops\rezenzii-pisem.jsonl"
ЖУРНАЛ = r"C:\sender\_ops\perepisano-po-recenzii.jsonl"
ЗНАКОВ_САЙТА = 6000
ПОТОКОВ = 8
МОДЕЛЬ_ПРАВКИ = "claude-sonnet-4-6"
МОДЕЛЬ_РЕЦЕНЗИИ = "claude-opus-4-8"
КАТИТЬ = "--katit" in sys.argv or "--катить" in sys.argv
ПОТОЛОК = int(next((a for a in sys.argv[1:] if a.isdigit()), "40"))
КАМПАНИИ = "10,11"
for _а in sys.argv[1:]:
    if _а.startswith("кампания="):
        КАМПАНИИ = _а.split("=", 1)[1]

ПРАВКА_СИСТЕМА = """Ты редактор холодных B2B-писем. Тебе дают ПИСЬМО, список
ПРЕТЕНЗИЙ проверяющего и ТЕКСТ САЙТА компании.

Задача: переписать в письме ТОЛЬКО те места, к которым есть претензия, так
чтобы каждое утверждение о компании подтверждалось текстом сайта. Всё
остальное — зачин, структуру, вопрос, подпись — оставить дословно.

Правила:
- утверждение, которого сайт не подтверждает, ЗАМЕНИТЬ на то, что сайт
  подтверждает, либо убрать вовсе и не выдумывать замену;
- не добавлять новых фактов, цифр и названий, которых нет на сайте;
- не писать про опубликованные кейсы и проекты и не обещать прислать их
  подборку;
- без длинных тире, только дефис;
- объём остаётся прежним (плюс-минус 15 слов).

ОТВЕТ — СТРОГО JSON без текста вокруг:
{"letters":[{"id":N,"subject":"...","body":"..."}]}"""

# МЕРКА ПЕРЕПРОВЕРКИ — ТА ЖЕ, ЧТО У ИСХОДНОГО РЕЦЕНЗЕНТА.
# Своя, написанная наспех («не годно, если есть хотя бы одно
# неподтверждённое утверждение»), оказалась заметно строже: она бракует
# ровно то, что оригинал разрешает — элементы типового техпроцесса рядом с
# подтверждённым занятием и отраслевые общие места с оговоркой. На первом
# прогоне из-за этого зря отвергнуты 74 письма из 151. Импортируем текст
# оригинала, чтобы мерки не разъезжались впредь.
def _merka_originala():
    """Текст мерки исходного рецензента — из его же файла.

    Вырезаем по БАЛАНСУ СКОБОК, а не по «до пустой строки»: первый вариант
    прихватывал код после присваивания и падал на нём.
    """
    import io as _io
    т = _io.open(r"C:\sender\_ops\rezenzent_pisem.py", encoding="utf-8").read()
    н = т.index("СИСТЕМА = (")
    i = т.index("(", н)
    глубина = 0
    for j in range(i, len(т)):
        if т[j] == "(":
            глубина += 1
        elif т[j] == ")":
            глубина -= 1
            if глубина == 0:
                ns = {}
                exec(т[н:j + 1], ns)
                return ns["СИСТЕМА"]
    raise ValueError("не нашёл конец СИСТЕМА")


try:
    РЕЦ_СИСТЕМА = _merka_originala()
except Exception as _ex:            # noqa: BLE001
    print(f"мерка оригинала не прочиталась ({str(_ex)[:70]}) — прогон "
          "остановлен: судить своей меркой уже пробовали")
    raise SystemExit(2)


def взять(url, таймаут=25):
    try:
        r = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept-Encoding": "gzip"})
        with urllib.request.urlopen(r, timeout=таймаут) as o:
            b = o.read(2_000_000)
            if o.headers.get("Content-Encoding") == "gzip":
                b = gzip.decompress(b)
            return b.decode("utf-8", "replace")
    except Exception:                                            # noqa: BLE001
        return ""


def сайт(база):
    if not база:
        return ""
    if not база.startswith("http"):
        база = "http://" + база
    сыро = взять(база)
    if not сыро:
        return ""
    дом = re.match(r"https?://[^/]+", база)
    дом = дом.group(0) if дом else база
    ссылки = []
    for m in re.finditer(r'href="([^"]+)"', сыро):
        u = m.group(1)
        if u.startswith("/"):
            u = дом + u
        if u.startswith(дом) and re.search(
                r"(?i)(uslug|servic|produkc|product|proizvod|about|company|"
                r"katalog|catalog|oborud|tehn)", u) and u not in ссылки:
            ссылки.append(u.split("#")[0])
    т = " ".join([сыро] + [взять(u, 18) for u in ссылки[:6]])
    т = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", т)
    т = re.sub(r"<[^>]+>", " ", т)
    return re.sub(r"\s+", " ", т)[:ЗНАКОВ_САЙТА]


def _json(т):
    m = re.search(r"\{.*\}", т or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:                                            # noqa: BLE001
        return None


def зов(система, тело, модель, потолок=3000):
    m = GP._raw_stream([{"role": "user", "content": тело}], модель, потолок,
                       thinking=False, system=система)
    return "".join(getattr(b, "text", "")
                   for b in getattr(m, "content", []) or [])


# ---- что берём ----------------------------------------------------------- #
верд = {}
for s in io.open(РЕЦЕНЗИИ, encoding="utf-8"):
    try:
        z = json.loads(s)
        верд[int(z["id"])] = z
    except Exception:                                            # noqa: BLE001
        pass
ПЕРЕСУДИТЬ = "--peresudit" in sys.argv
уже = set()
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            z = json.loads(s)
        except Exception:                                        # noqa: BLE001
            continue
        итог = str(z.get("итог") or "")
        # С --peresudit заново берём тех, кого отвергла ПРЕЖНЯЯ, слишком
        # строгая мерка: их отказ был про мою формулировку, а не про письмо.
        if ПЕРЕСУДИТЬ and "не годно" in итог:
            continue
        уже.add(int(z["id"]))

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
окно = window_from(store, cfg)
сейчас = datetime.now(timezone.utc)
факты = {"kc": load_facts(division="kc"), "meyer": load_facts(division="meyer")}

with store._lock:
    строки = store._conn.execute(
        f"SELECT c.id, c.campaign_id, c.subject, c.body, c.recipient_id, "
        f"       c.message_id, c.email, r.company_name, r.okved, r.domain "
        f"FROM confirm_reviews c LEFT JOIN recipients r ON r.id=c.recipient_id "
        f"WHERE c.campaign_id IN ({КАМПАНИИ}) AND c.status='pending'"
    ).fetchall()

работа = []
for r in строки:
    z = верд.get(int(r["id"])) or {}
    if str(z.get("verdict") or "") != "не годно":
        continue
    if int(r["id"]) in уже:
        continue
    пр = z.get("pretenzii") or []
    работа.append({
        "id": int(r["id"]), "камп": int(r["campaign_id"]),
        "тема": r["subject"] or "", "тело": r["body"] or "",
        "фирма": r["company_name"] or "", "оквэд": str(r["okved"] or ""),
        "url": str(z.get("url") or r["domain"] or ""),
        "rid": r["recipient_id"], "mid": r["message_id"],
        "претензии": [str(x) for x in пр] if isinstance(пр, list) else [str(пр)],
    })
работа = работа[:ПОТОЛОК]
print(f"к переписыванию: {len(работа)} (уже переписано раньше: {len(уже)})")
if not работа:
    raise SystemExit(0)

t0 = time.time()
with ThreadPoolExecutor(max_workers=ПОТОКОВ) as pool:
    тексты = list(pool.map(lambda г: сайт(г["url"]), работа))
for г, т in zip(работа, тексты):
    г["сайт"] = т
print(f"сайты сняты за {time.time()-t0:.0f}с; с текстом "
      f"{sum(1 for г in работа if г['сайт'])} из {len(работа)}")

замок = threading.Lock()
счёт = Counter()


def в_журнал(z):
    with замок:
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
            f.write(json.dumps(z, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())


def один(г):
    напр = "meyer" if г["камп"] == 11 else "kc"
    if not г["сайт"]:
        счёт["сайт не открылся - пропуск"] += 1
        в_журнал({"id": г["id"], "итог": "сайт не открылся"})
        return
    # СЛОВА ЗНАКОМСТВА РАЗНЫЕ И ЗДЕСЬ. Иначе сто девятнадцать спасённых
    # писем лягут в очередь с одинаковым «Смотрел профиль» — ровно тот след
    # серии, который мы вычищаем из генерации.
    _зн = ZNAKOMSTVO[г["id"] % len(ZNAKOMSTVO)]
    зпр = (f"ЕСЛИ В ПИСЬМЕ ЕСТЬ ФРАЗА О ТОМ, ЧТО ТЫ СМОТРЕЛ КОМПАНИЮ, "
           f"замени её на «{_зн}…», сохранив смысл предложения.\n\n"
           f"=== ПИСЬМО id={г['id']} ===\nКОМПАНИЯ: {г['фирма']} · ОКВЭД "
           f"{г['оквэд']}\nТЕМА: {г['тема']}\n{г['тело']}\n"
           f"--- ПРЕТЕНЗИИ ПРОВЕРЯЮЩЕГО ---\n"
           + "\n".join(f"- {p}" for p in г["претензии"])
           + f"\n--- ТЕКСТ САЙТА ({г['url']}) ---\n{г['сайт']}\n")
    try:
        d = _json(зов(ПРАВКА_СИСТЕМА, зпр, МОДЕЛЬ_ПРАВКИ))
    except Exception as ex:                                      # noqa: BLE001
        счёт["сбой правки"] += 1
        в_журнал({"id": г["id"], "итог": f"сбой правки: {str(ex)[:120]}"})
        return
    письма = (d or {}).get("letters") or []
    if not письма:
        счёт["правка без JSON"] += 1
        в_журнал({"id": г["id"], "итог": "правка без JSON"})
        return
    нов_тема = str(письма[0].get("subject") or г["тема"])
    нов_тело = str(письма[0].get("body") or "")
    if len(нов_тело) < 200:
        счёт["правка пустая"] += 1
        в_журнал({"id": г["id"], "итог": "правка пустая"})
        return
    брак = gate(нов_тема, нов_тело, mode="GENERIC", facts=факты[напр],
                division=напр)
    if брак:
        счёт["гейт после правки"] += 1
        в_журнал({"id": г["id"], "итог": "гейт после правки",
                  "брак": [str(b)[:160] for b in брак],
                  "тема": нов_тема, "тело": нов_тело})
        return
    # ПЕРЕПРОВЕРКА. Без неё правка одобряется на веру, а именно на вере
    # письма и попадали в брак.
    рпр = (f"=== ПИСЬМО id={г['id']} ===\nКОМПАНИЯ: {г['фирма']}\n"
           f"ТЕМА: {нов_тема}\n{нов_тело}\n"
           f"--- ТЕКСТ САЙТА ---\n{г['сайт']}\n")
    try:
        rd = _json(зов(РЕЦ_СИСТЕМА, рпр, МОДЕЛЬ_РЕЦЕНЗИИ, 1500))
    except Exception as ex:                                      # noqa: BLE001
        счёт["сбой перепроверки"] += 1
        в_журнал({"id": г["id"], "итог": f"сбой перепроверки: {str(ex)[:120]}",
                  "тема": нов_тема, "тело": нов_тело})
        return
    # КЛЮЧ ОТВЕТА — «pisma», а не «reviews». Когда я подменил свою мерку на
    # мерку исходного рецензента, формат ответа сменился вместе с ней, а
    # разбор остался прежним: код читал отсутствующий ключ, получал пустой
    # вердикт и считал его отказом. 69 писем были «забракованы», ни разу не
    # будучи прочитанными, и я успел объяснить это тем, что «сайт не даёт
    # фактов на замену» — объяснение поверх собственной поломки.
    # Читаем оба ключа и НЕ МОЛЧИМ, если не нашли ни одного.
    рец = (((rd or {}).get("pisma") or (rd or {}).get("reviews") or [{}]))[0]
    вер = str(рец.get("verdict") or "")
    if not вер:
        счёт["перепроверка без вердикта (разбор ответа)"] += 1
        в_журнал({"id": г["id"], "итог": "перепроверка без вердикта",
                  "сырое": str(rd)[:300], "тема": нов_тема, "тело": нов_тело})
        return
    if вер == "нечем проверить":
        счёт["нечем проверить после правки"] += 1
        в_журнал({"id": г["id"], "итог": "нечем проверить после правки",
                  "тема": нов_тема, "тело": нов_тело})
        return
    if вер != "годно":
        счёт["после правки всё ещё не годно"] += 1
        в_журнал({"id": г["id"], "итог": "после правки не годно",
                  "pretenzii": рец.get("pretenzii"),
                  "тема": нов_тема, "тело": нов_тело})
        return
    счёт["ГОДНО ПОСЛЕ ПРАВКИ"] += 1
    в_журнал({"id": г["id"], "итог": "годно после правки",
              "тема": нов_тема, "тело": нов_тело, "было": г["тело"][:400]})
    if not КАТИТЬ:
        return
    try:
        ок = store.confirm_decide(
            г["id"], status="edited", edited_subject=нов_тема,
            edited_body=нов_тело,
            diff_text="переписано по претензиям рецензента (19.08)",
            decided_by="переписчик по рецензии")
        if ок is False:
            счёт["карточка уже решена"] += 1
            return
        rec = store.get_recipient(г["rid"])
        if г["mid"] and rec is not None:
            store.reschedule_message(
                int(г["mid"]), next_slot(окно, recipient_tz_name(окно, rec),
                                         сейчас))
        счёт["в очередь на отправку"] += 1
    except Exception as ex:                                      # noqa: BLE001
        счёт["не легло в очередь"] += 1
        print(f"  #{г['id']}: {str(ex)[:110]}")


t1 = time.time()
with ThreadPoolExecutor(max_workers=ПОТОКОВ) as pool:
    list(pool.map(один, работа))
print(f"\nготово за {time.time()-t1:.0f}с")
for k, v in счёт.most_common():
    print(f"  {v:>4}  {k}")
print(f"\nжурнал: {ЖУРНАЛ}")
if not КАТИТЬ:
    print("СУХОЙ ПРОГОН: правки посчитаны, но в очередь не положены (--katit)")

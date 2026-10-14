# -*- coding: utf-8 -*-
"""Наскрести Meyer среди «кц» (владелец 14.10: «запусти предклассификатор, который
на КЦ переставили, может оттуда наскребём чего под мейер»).

Кандидаты: компании групп «Россия 9000»/«Белорусь 1000» с вердиктом «кц» от
предклассификатора или гейта (решения линзы не трогаем: она видела письмо).
Вопрос модели ОБРАТНЫЙ обычному: не «куда отнести», а «подходит ли хоть один
станок Meyer», по правилам владельца (зерно не только переработка, пластик с
гранулой, нерудные с 12.10). «да» -> вердикт «оба» (КЦ сохраняется) + «+meyer»
в метку базы обзвона, если там только kc (иначе панель не даст ящик Meyer).
Журнал _ops/meyer-iz-kc.jsonl (fsync) — по нему и резюм, и откат.

    meyer_iz_kc.py            — сколько кандидатов
    meyer_iz_kc.py --zapusk   — в фоне
    meyer_iz_kc.py --hod      — итог
"""
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault("PROVIDER_THINKING_FIELD", "omit")
ЖУР = r"C:\sender\_ops\meyer-iz-kc.jsonl"
ЛОГ = r"C:\sender\_ops\meyer-iz-kc.log"
ГР = ("Россия 9000", "Белорусь 1000")

if "--hod" in sys.argv:
    з = [json.loads(с) for с in io.open(ЖУР, encoding="utf-8")] if os.path.exists(ЖУР) else []
    print("проверено: %d; ответы: %s" % (len(з), dict(Counter(x["meyer"] for x in з))))
    for x in [x for x in з if x["meyer"] == "да"][-int(os.environ.get("HOD_N", "25")):]:
        print("   + %s %s — %s" % (x["inn"], x.get("имя", "")[:30], x.get("почему", "")[:80]))
    try:
        print("лог: " + io.open(ЛОГ, encoding="utf-8", errors="replace").read()[-300:])
    except Exception:  # noqa: BLE001
        pass
    print("=== MEYER ИЗ КЦ: ХОД ===")
    sys.exit(0)

ЩЕБЕНЬ = re.compile(r"щеб|песок|песк|пгс|гравий|гравия|асфальт|бутов|бетон|строительн\w* камн|фракци|инертн|дробильно|гранит|металлолом|лом[аы]? |скрап|дозатор", re.I)

if "--stop" in sys.argv or "--otkat-shcheben" in sys.argv:
    у = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*meyer_iz_kc.py*--rabota*' }"
                        " | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"],
                       capture_output=True, text=True, timeout=60).stdout.split()
    print("остановлено: %s" % (у or "не шло"))
if "--otkat-shcheben" in sys.argv:
    # Владелец 14.10: «щебень не нужен». «да» по строительному нерудному
    # откатываем: вердикт обратно «кц», метку обзвона — какой была; в журнале
    # строка становится «нет» (повторно не спрашиваем).
    import sqlite3 as _sq
    ew = _sq.connect(r"C:\sender\enrich.db", timeout=60)
    o = _sq.connect(r"C:\sender\obzvon-index.db", timeout=60)
    стр = [json.loads(с) for с in io.open(ЖУР, encoding="utf-8")]
    n = 0
    for з in стр:
        if з["meyer"] == "да" and ЩЕБЕНЬ.search(з.get("почему", "") + " " + з.get("что", "")) \
                and not re.search(r"кварц|стекл|каолин|шпат|доломит|сол[ьи]|мрамор|тко|вторсыр", з.get("почему", ""), re.I):
            ew.execute("UPDATE companies SET verdikt_napr='кц', verdikt_istochnik='предкласс', "
                       "verdikt_pochemu='откат 14.10: строительный щебень/песок не Meyer' "
                       "WHERE inn=? AND verdikt_istochnik='перепроверка meyer 14.10'", (з["inn"],))
            if "было_метка" in з:
                o.execute("UPDATE obzvon SET division=? WHERE inn=?", (з["было_метка"], з["inn"]))
            з["meyer"], з["откат"] = "нет", "щебень"
            n += 1
    ew.commit()
    o.commit()
    with io.open(ЖУР + ".tmp", "w", encoding="utf-8") as ж:
        for з in стр:
            ж.write(json.dumps(з, ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
    os.replace(ЖУР + ".tmp", ЖУР)
    print("откачено щебня/песка: %d из %d «да»" % (n, n + sum(1 for з in стр if з["meyer"] == "да")))
    print("=== MEYER ИЗ КЦ: ОТКАТ ===")
    sys.exit(0)
if "--stop" in sys.argv:
    print("=== MEYER ИЗ КЦ: СТОП ===")
    sys.exit(0)

if "--zapusk" in sys.argv:
    п = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--rabota"], cwd=r"C:\sender",
                         stdout=io.open(ЛОГ, "a"), stderr=subprocess.STDOUT, creationflags=0x00000008 | 0x00000200)
    time.sleep(8)
    print("запущено, pid %d, жив %s" % (п.pid, п.poll() is None))
    print("=== MEYER ИЗ КЦ: ЗАПУЩЕНО ===")
    sys.exit(0)

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
from sender.ai_quota import build_ai_quota  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
q = build_ai_quota(Store(cfg.get("service.db_path", r"C:\sender\sender.db")), cfg)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
группа = {}
for inn, ex in c.execute("SELECT inn, extra_json FROM recipients WHERE inn IS NOT NULL"):
    for г in ГР:
        if г in str(ex or ""):
            группа.setdefault(str(inn), г)
готово = {json.loads(с)["inn"] for с in io.open(ЖУР, encoding="utf-8")} if os.path.exists(ЖУР) else set()
канд = []
for inn, name, okved, napr, ист in e.execute(
        "SELECT inn, name, okved, verdikt_napr, verdikt_istochnik FROM companies WHERE verdikt_napr='кц'"):
    inn = str(inn)
    if inn in группа and inn not in готово and (ист or "") in ("предкласс", "гейт", ""):
        канд.append((inn, name or "", okved or ""))
print("кандидатов «кц» (предкласс/гейт) в группах: %d, уже проверено: %d" % (len(канд), len(готово)))
if "--rabota" not in sys.argv:
    print("=== MEYER ИЗ КЦ: СУХОЙ ПРОГОН ===")
    sys.exit(0)

import gen_provider  # noqa: E402

СИСТЕМА = """Ты отбираешь компании для Meyer - направления фотосепараторов и рентген-инспекции.
Все компании ниже уже отнесены к компрессорному направлению. Твоя задача - найти среди них тех,
кому ВДОБАВОК подходит хоть один станок Meyer. Отвечай «да» только при реальном применении:

ФОТОСЕПАРАТОР (сортировка сыпучего потока по цвету/форме):
- зерно, масличные, бобовые, крупы, семена: переработка, элеваторы, зернотрейдеры, терминалы
  перевалки зерна, хозяйства с зерноочистительным комплексом/сушилкой/складом/лабораторией или
  землями от тысячи гектаров; семеноводство;
- орехи, сухофрукты, ягоды, овощи, кофе, специи, чай;
- пластик: переработка во флексу/дроблёнку/гранулу, производители гранулы, компаундов,
  мастербатчей, ПЭТ-преформ на вторичных хлопьях; производители изделий (плёнка, трубы, тара,
  профиль, литьё), которые берут вторичное сырьё или дробят свой брак и возвращают дроблёнку в
  производство - там сортируют по цвету и убирают посторонние включения;
- стеклобой; нерудные минералы как СЫРЬЁ для дальнейшей переработки: кварц, кварцевый песок
  для стекла, известняк для извести и химии, доломит, соль, каолин, полевой шпат, мрамор;
  щепа, пеллеты; сортировка ТКО и вторсырья.
- СТРОИТЕЛЬНЫЙ щебень, песок, ПГС, гравий, бутовый камень, асфальт и бетон - НЕТ (владелец
  14.10: «щебень не нужен»), даже если карьер известняковый, а щебень сортируют по фракциям.
РЕНТГЕН (контроль посторонних включений в готовом упакованном пищевом продукте): мясо и
птица, молочка, кондитерка, снеки, хлеб, готовая еда, консервы, замороженные полуфабрикаты.

«нет»: металлообработка, машиностроение, металлургия, руда и уголь (кроме нерудки), стройка,
энергетика, нефтегаз, химия без сыпучего сырья, лесопилка без щепы, торговля без своей
переработки, услуги, жидкие напитки и масло без фасовки и без сортировки сырья.
Сомневаешься - «нет».

Ответ строго JSON: {"firmy":[{"inn":"...","meyer":"да|нет","chto":"фотосепаратор|рентген|",
"pochemu":"до 12 слов"}]}"""
замок = threading.Lock()
o = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60, check_same_thread=False)
ew = sqlite3.connect(r"C:\sender\enrich.db", timeout=60, check_same_thread=False)


def паспорт(inn):
    try:
        d = q._site_facts(inn) or {}
    except Exception:  # noqa: BLE001
        return ""
    return "\n".join("%s: %s" % (k, (v if isinstance(v, str) else "; ".join(map(str, v)))[:240])
                     for k in ("цитата", "продукция", "сырьё", "оборудование_линии", "упаковка_фасовка", "масштаб")
                     if (v := d.get(k)))[:1000]


def пачка(кусок):
    блоки = ["ИНН %s · %s · ОКВЭД %s\n%s" % (a, b, ок, паспорт(a) or "(паспорта сайта нет)") for a, b, ок in кусок]
    д = {}
    for попытка in range(3):
        try:
            m = gen_provider._raw_stream([{"role": "user", "content": "Компании:\n\n" + "\n\n".join(блоки)}],
                                         "claude-sonnet-4-6", 6000, thinking=False, system=СИСТЕМА)
            т = "".join(getattr(b, "text", "") for b in getattr(m, "content", []) or [])
            мм = re.search(r"\{.*\}", т, re.S)
            д = json.loads(мм.group(0)) if мм else {}
            if not д.get("firmy"):
                raise ValueError("пустой разбор: " + т[:60])
            break
        except Exception as е:  # noqa: BLE001
            д = {}
            print("пачка: попытка %d: %s" % (попытка + 1, str(е)[:90]), flush=True)
            time.sleep(10)
    имена = {a: b for a, b, _ in кусок}
    записи = []
    for v in д.get("firmy") or []:
        inn = "".join(ч for ч in str(v.get("inn") or "") if ч.isdigit())
        if inn in имена:
            записи.append({"inn": inn, "имя": имена[inn], "meyer": "да" if str(v.get("meyer")).strip().lower() == "да" else "нет",
                           "что": v.get("chto") or "", "почему": str(v.get("pochemu") or "")[:150]})
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    with замок:
        for з in записи:
            if з["meyer"] != "да":
                continue
            з["было_метка"] = (o.execute("SELECT division FROM obzvon WHERE inn=?", (з["inn"],)).fetchone() or [None])[0]
            ew.execute("UPDATE companies SET verdikt_napr='оба', verdikt_istochnik='перепроверка meyer 14.10', "
                       "verdikt_pochemu=?, verdikt_ts=? WHERE inn=? AND verdikt_napr='кц'",
                       ("Meyer тоже: %s — %s" % (з["что"], з["почему"]), ts, з["inn"]))
            м = з["было_метка"]
            if м is not None and "meyer" not in м:
                o.execute("UPDATE obzvon SET division=? WHERE inn=?",
                          ("+".join(x for x in [м.strip("+"), "meyer"] if x), з["inn"]))
        ew.commit()
        o.commit()
        with io.open(ЖУР, "a", encoding="utf-8") as ж:
            for з in записи:
                ж.write(json.dumps(з, ensure_ascii=False) + "\n")
            ж.flush()
            os.fsync(ж.fileno())
    print("пачка %d: да %d" % (len(кусок), sum(1 for з in записи if з["meyer"] == "да")), flush=True)


куски = [канд[i:i + 15] for i in range(0, len(канд), 15)]
with ThreadPoolExecutor(3) as пул:
    list(пул.map(пачка, куски))
print("готово", flush=True)

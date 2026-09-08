# -*- coding: utf-8 -*-
"""Заменить текст письма партии «Агро зерно 2026» ВЕЗДЕ, где он ещё живой.

Владелец 08.09: «давай этим заменим письмо, включая подтверждённые».

Текст письма лежит в трёх местах, и у подтверждённой карточки в четвёртом:
  confirm_reviews.body            - отсюда его берёт отправка
  panel_json.letter.body          - это видит оператор
  panel_json.letter.final_body    - он же, с дописанной подписью
  messages.body_rendered          - у ПОДТВЕРЖДЁННОГО письма текст уже
                                    скопирован сюда, и отправка возьмёт его.
Правка только карточки оставила бы 681 одобренное письмо со старым текстом.

Отправленные не трогаем ни в каком виде: письмо ушло, менять в базе его
текст значит соврать самим себе о том, что получил адресат.

    python zamena_teksta_agro.py            # вхолостую
    python zamena_teksta_agro.py --primenit
"""
import io
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ТЕМА = "Для качества: вопрос по сортировке зерна"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv
СНИМОК = (r"C:\sender\_ops\agro-tekst-do-zameny-"
          + time.strftime("%m%d-%H%M%S") + ".jsonl")

# Текст владельца. Правлено механическое, и только оно: длинные тире в
# списке заменены на дефисы (правило писем, ai_letter.py:67 - «БЕЗ длинных
# тире, только дефис»), и абзац про переход между программами отделён
# пустой строкой - в плоском письме он слипался с предыдущим.
ТЕЛО = """Добрый день!

Меня зовут ИМЯ_ОТПРАВИТЕЛЯ, представляю компанию «Руспром Meyer». Мы внедряем фотосепараторы для сортировки зерновых, масличных, бобовых и других сельскохозяйственных культур.

Оборудование решает задачи, когда механической очистки недостаточно: примеси близки к основному продукту по размеру и другим физическим свойствам, но незначительно отличаются по цвету, форме или другим оптическим признакам.

В разных регионах и хозяйствах задачи отличаются. Среди примеров применения фотосепараторов Meyer:

- удаление дикой редьки из гречихи;
- разделение ячменя и пшеницы;
- удаление пшеницы из красной чечевицы;
- удаление склероциев из подсолнечника;
- удаление эгилопса и овсюга из пшеницы;
- очистка различных культур от семян сорных растений: рыжика, амброзии, сурепицы, щирицы, повилики и других.

Один фотосепаратор можно использовать для разных культур и задач. Оборудование подходит для подготовки семенного материала, доработки партий на экспорт и под требования трейдеров и переработчиков.

По опыту наших заказчиков, в отдельных проектах оборудование окупалось менее чем за месяц. Срок зависит от задачи, производительности, загрузки оборудования и требований к готовому продукту.

Переход между заранее настроенными программами сортировки занимает буквально несколько минут.

Можем провести тестовую сортировку вашего сырья, чтобы оценить качество очистки и выход годного продукта. Можно приехать в наш демо-зал лично, можно дистанционно - пришлём видео процесса и результат.

Подскажите, актуальна ли сейчас задача по очистке зерна или подготовке семян? Если да, достаточно назвать культуру и примерный объём - предложу подходящее оборудование и формат теста."""

assert "\u2014" not in ТЕЛО, "в тексте осталось длинное тире"


def собрать_final(тело, подпись):
    """Как в infopanel._letter_block: подпись через пустую строку, а если
    тело уже кончается её первой строкой - не печатать эту строку дважды."""
    подпись = (подпись or "").strip()
    хвост = (тело or "").rstrip()
    if not подпись:
        return тело or ""
    первая = подпись.split("\n")[0].rstrip()
    if первая and хвост.endswith(первая):
        return хвост + "\n" + "\n".join(подпись.split("\n")[1:]).lstrip("\n")
    return хвост + "\n\n" + подпись


store = Store(r"C:\sender\sender.db")
счёт = Counter()
правки = []
with store._lock:
    строки = store._conn.execute(
        """SELECT c.id AS cid, c.status AS cst, c.body, c.panel_json,
                  m.id AS mid, m.status AS mst, m.body_rendered
             FROM confirm_reviews c LEFT JOIN messages m
                  ON c.message_id = m.id
            WHERE c.subject=?""", (ТЕМА,)).fetchall()

for р in строки:
    счёт["карточек всего"] += 1
    mst = str(р["mst"] or "нет письма")
    if str(р["cst"]) == "sent" or mst == "sent":
        счёт["УЖЕ ОТПРАВЛЕНО — не трогаем"] += 1
        continue
    if str(р["body"] or "") == ТЕЛО:
        счёт["уже новый текст"] += 1
        continue
    try:
        панель = json.loads(р["panel_json"] or "{}")
    except Exception:                                           # noqa: BLE001
        панель = {}
    письмо = панель.get("letter")
    if isinstance(письмо, dict):
        низ = ТЕЛО.lower()
        новое = dict(письмо)
        новое["body"] = ТЕЛО
        новое["final_body"] = собрать_final(ТЕЛО, письмо.get("signature"))
        новое["highlights"] = [h for h in (письмо.get("highlights") or [])
                               if isinstance(h, dict)
                               and str(h.get("text") or "").lower() in низ]
        панель["letter"] = новое
        новая_панель = json.dumps(панель, ensure_ascii=False)
    else:
        новая_панель = None
        счёт["в панели нет блока letter"] += 1
    # тело письма переписываем только у СОЗРЕВШЕГО (одобренного) письма:
    # у pending_review оно пустое и соберётся из карточки на подтверждении
    менять_письмо = bool(р["mid"]) and mst not in ("sent", "нет письма") \
        and str(р["body_rendered"] or "").strip()
    правки.append((int(р["cid"]), новая_панель,
                   int(р["mid"]) if менять_письмо else None,
                   str(р["body"] or ""), str(р["panel_json"] or ""),
                   str(р["body_rendered"] or "")))
    счёт["К ЗАМЕНЕ (карточка %s / письмо %s)" % (str(р["cst"]), mst)] += 1

if ПРИМЕНИТЬ and правки:
    with io.open(СНИМОК, "w", encoding="utf-8") as ф:
        for cid, _нп, mid, тело_до, панель_до, письмо_до in правки:
            ф.write(json.dumps({"review_id": cid, "message_id": mid,
                                "тело_до": тело_до,
                                "panel_json_до": панель_до,
                                "body_rendered_до": письмо_до},
                               ensure_ascii=False) + "\n")
        ф.flush()
        os.fsync(ф.fileno())
    счёт["снимок сохранён"] = len(правки)
    карточек = писем = 0
    for нач in range(0, len(правки), 400):
        кусок = правки[нач:нач + 400]
        for _ in range(20):
            try:
                with store.transaction() as conn:
                    for cid, нп, mid, _т, _п, _в in кусок:
                        if нп is not None:
                            conn.execute(
                                "UPDATE confirm_reviews SET body=?, "
                                "       panel_json=?, updated_at=datetime('now')"
                                " WHERE id=? AND status<>'sent'",
                                (ТЕЛО, нп, cid))
                        else:
                            conn.execute(
                                "UPDATE confirm_reviews SET body=?, "
                                "       updated_at=datetime('now')"
                                " WHERE id=? AND status<>'sent'", (ТЕЛО, cid))
                        карточек += 1
                        if mid:
                            conn.execute(
                                "UPDATE messages SET body_rendered=?, "
                                "       updated_at=datetime('now') "
                                " WHERE id=? AND status NOT IN "
                                "       ('sent','failed')", (ТЕЛО, mid))
                            писем += 1
                break
            except Exception as ex:                             # noqa: BLE001
                if "locked" not in str(ex) and "busy" not in str(ex):
                    print("   кусок не лёг: %s" % str(ex)[:110], flush=True)
                    break
                time.sleep(3.0)
    счёт["ПЕРЕПИСАНО карточек"] = карточек
    счёт["ПЕРЕПИСАНО тел писем"] = писем

print("=" * 74)
print("=== ЗАМЕНА ТЕКСТА ПАРТИИ: %s ==="
      % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
for к, в in счёт.most_common(20):
    print("   %-48s %5d" % (к, в))
if not ПРИМЕНИТЬ:
    print("")
    print("вхолостую. Заменить — --primenit")

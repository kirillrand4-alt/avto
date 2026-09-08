# -*- coding: utf-8 -*-
"""Подтянуть ответ Чистозерья в ленту и связать с компанией.

Событие 350305: Юлия Гнездалова <gnezdalova@yandex.ru> написала 07.09 на
ящик a.miroshnichenko@optic-sort.ru «Вопрос для нас актуален и интересен».
Разбор положил его в 'other' без привязки: письмо пришло НЕ по треду (нет
In-Reply-To и References, тема своя «Чистозерье»), а адрес отвечавшего
личный яндексовый, в базе его нет.

Компания опознана по тексту подписи: ООО ТД «Чистозерье», ИНН 5405089983,
recipient 33093 (sales.client@chistozerie.ru), которому 03.09 ушло письмо
14165 кампании 11 с того же ящика Мирошниченко.

Делаем то же, что делает боевой разбор: событие -> reply с привязкой,
лид через штатный leaddesk.push_warm_lead (он сам считает dedup и SLA).

По умолчанию СУХОЙ ПРОГОН. Запуск: python podtyanut_chistozerie_0907.py [--primenit]
"""
import json
import sqlite3
import sys
from types import SimpleNamespace

sys.path.insert(0, r"C:\sender")

СОБЫТИЕ = 350305
ПОЛУЧАТЕЛЬ = 33093
ПИСЬМО = 14165
КАМПАНИЯ = 11
ОТВЕТИЛ = "gnezdalova@yandex.ru"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv

from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.leaddesk import LeadDesk                              # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
путь = cfg.get("service.db_path", r"C:\sender\sender.db")
store = Store(путь)

c = sqlite3.connect("file:%s?mode=ro" % путь, uri=True, timeout=90)
c.row_factory = sqlite3.Row
соб = c.execute("SELECT * FROM events WHERE id=?", (СОБЫТИЕ,)).fetchone()
пол = c.execute("SELECT * FROM recipients WHERE id=?", (ПОЛУЧАТЕЛЬ,)).fetchone()
было_лидов = c.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
c.close()

d = json.loads(соб["detail_json"] or "{}")
h = d.get("headers") or {}
текст = " ".join(str(d.get("snippet") or "").split())

# МЕТКА ПОСТАВЛЕНА РУКАМИ, И ВОТ ПОЧЕМУ. Боевой классификатор на этом
# тексте даёт neutral: у него нет ни «пришлите», ни «сколько стоит», ни
# других своих ключей. Но человек написал «Вопрос для нас актуален и
# интересен» — это ровно interested, и продавец должен увидеть карточку
# такой. Вердикт классификатора не выбрасываем, кладём рядом в detail.
метка = "interested"
метка_машины = ""
try:
    from sender.reply_classify import classify_reply                # noqa: E402
    с = classify_reply(str(h.get("Subject") or ""), текст, h)
    метка_машины = getattr(с, "kind", "") or ""
except Exception as ex:                                             # noqa: BLE001
    метка_машины = "классификатор недоступен: %s" % str(ex)[:60]

шаги = []
if ПРИМЕНИТЬ:
    d["reply_kind"] = метка
    d["reply_kind_klassifikator"] = метка_машины
    d["privyazka_ruchnaya"] = {
        "kem": "ops/podtyanut_chistozerie_0907.py",
        "pochemu": "письмо вне треда с личного адреса, компания опознана "
                   "по подписи в тексте",
        "recipient_id": ПОЛУЧАТЕЛЬ, "message_id": ПИСЬМО,
    }
    with store.transaction() as conn:
        conn.execute(
            "UPDATE events SET event_type='reply', recipient_id=?,"
            " message_id=?, campaign_id=?, detail_json=? WHERE id=?",
            (ПОЛУЧАТЕЛЬ, ПИСЬМО, КАМПАНИЯ,
             json.dumps(d, ensure_ascii=False), СОБЫТИЕ))
    шаги.append("событие %d: other -> reply, привязано к получателю %d, "
                "письму %d, кампании %d" % (СОБЫТИЕ, ПОЛУЧАТЕЛЬ, ПИСЬМО,
                                            КАМПАНИЯ))

    import inspect
    шаги.append("подпись push_warm_lead%s"
                % str(inspect.signature(LeadDesk.push_warm_lead))[:150])
    шаги.append("подпись LeadDesk%s"
                % str(inspect.signature(LeadDesk.__init__))[:160])
    desk = LeadDesk(store=store, config=cfg)
    кто = SimpleNamespace(id=пол["id"], email=пол["email"],
                          company_name=пол["company_name"], inn=пол["inn"])
    лид = desk.push_warm_lead(кто, None, "[%s] %s" % (метка, текст),
                              otvetil=ОТВЕТИЛ)
    шаги.append("push_warm_lead -> лид %s" % лид)
else:
    шаги.append("сухой прогон: ничего не меняю")

c = sqlite3.connect("file:%s?mode=ro" % путь, uri=True, timeout=90)
c.row_factory = sqlite3.Row
после = c.execute("SELECT * FROM events WHERE id=?", (СОБЫТИЕ,)).fetchone()
лиды = list(c.execute("SELECT * FROM leads WHERE email=? OR inn=?",
                      (ОТВЕТИЛ, пол["inn"])))
стало_лидов = c.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
видимых = c.execute(
    "SELECT COUNT(*) FROM leads WHERE status NOT IN"
    " ('deleted','not_interested','in_bitrix','unqualified')").fetchone()[0]
c.close()

print("=" * 74)
print("=== ПОДТЯГИВАЕМ ОТВЕТ ЧИСТОЗЕРЬЯ В ЛЕНТУ ===")
print("режим: %s" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
print("")
print("от кого:   %s" % str(h.get("From"))[:60])
print("кому:      %s" % str(h.get("To"))[:60])
print("тема:      %s   дата: %s" % (str(h.get("Subject"))[:30],
                                    str(h.get("Date"))[:35]))
print("текст:     %s" % текст[:150])
print("метка:     %s (классификатор давал: %s)" % (метка, метка_машины))
print("компания:  %s, ИНН %s, получатель %s"
      % (пол["company_name"], пол["inn"], пол["id"]))
print("письмо:    %d (кампания %d), ящик %s"
      % (ПИСЬМО, КАМПАНИЯ, соб["mailbox_id"]))
print("")
for с in шаги:
    print("   " + с)
print("")
print("событие сейчас: тип=%s получатель=%s письмо=%s кампания=%s"
      % (после["event_type"], после["recipient_id"], после["message_id"],
         после["campaign_id"]))
for л in лиды:
    print("лид %s: %s | %s | ИНН %s | статус %s | метка %s | ящик ответа %s"
          % (л["id"], л["email"], str(л["company_name"])[:32], л["inn"],
             л["status"], л["reply_kind"], л["reply_mailbox"]))
if not лиды:
    print("лидов по этой компании нет")
print("")
print("лидов всего: было %d, стало %d; видно в ленте %d"
      % (было_лидов, стало_лидов, видимых))

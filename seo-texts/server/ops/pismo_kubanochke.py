# -*- coding: utf-8 -*-
"""Письмо «Кубаночке Ставрополья» на адрес, который назвали в ответе.

Компания ответила с export@kubanochka.ru: «прошу ваш запрос направить на
электронную почту nfo@kubanochka.ru». В адресе опечатка - на их сайте стоит
info@kubanochka.ru (подтвердил владелец), туда и пишем.

Кладём в очередь подтверждений тем же путём, что и панельная кнопка «новое
письмо» (api /confirm/novoe): заводим строку получателя по образцу прежней,
подписываем ящик отправителя из первого письма, ставим status=pending.
Отправка - только по нажатию оператора.
"""
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.avtootvet import завести_получателя               # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

СОЗДАТЬ = "--sozdat" in sys.argv
АДРЕС = "info@kubanochka.ru"
ОБРАЗЕЦ = 31787                      # export@kubanochka.ru, кому писали
ЯЩИК = "y.kuzmin@optic-sort.ru"      # с него ушло первое письмо
ИНН = "2615015936"
КАМПАНИЯ = 11

ТЕМА = "Вопрос по контролю включений в продукции «Кубаночка Ставрополья»"
ТЕЛО = """Добрый день!

Меня зовут ИМЯ_ОТПРАВИТЕЛЯ, веду направление рентген-инспекции Meyer. Коллега из экспортного отдела «Кубаночки Ставрополья» попросил направить вопрос на этот адрес.

Речь о контроле посторонних включений в готовой упаковке: детектор находит металл, стекло и камень уже в закрытой банке, не вскрывая её. На консервном производстве эта задача обычно приходит вместе с требованиями сетей и экспортных аудитов.

Подскажите, актуален ли для вас контроль включений? Если да, то на какой линии - консервы или соусы? Если этим участком занимается коллега, перенаправьте ему, пожалуйста, письмо.

Если тема неактуальна, буду признателен за короткий ответ, чтобы вас не отвлекать.

С уважением,"""

print("=== ПИСЬМО ===")
print("   кому:  %s" % АДРЕС)
print("   от:    %s" % ЯЩИК)
print("   тема:  %s (%d слов)" % (ТЕМА, len(ТЕМА.split())))
print("   слов в теле: %d" % len(ТЕЛО.split()))
print("   знаков вопроса: %d" % ТЕЛО.count("?"))
print("   ---")
for с in ТЕЛО.splitlines():
    print("   | %s" % с)

# механический гейт - тот же, что на генерации
try:
    from sender.ai_letter import gate, load_facts
    брак = gate(ТЕМА, ТЕЛО, mode="GENERIC",
                extra={"company_name": "Кубаночка Ставрополья"},
                facts=load_facts(division="meyer"), division="meyer")
    print("\n=== МЕХАНИЧЕСКИЙ ГЕЙТ ===")
    print("   %s" % ("ЧИСТО" if not брак else "; ".join(брак)))
except Exception as e:                                        # noqa: BLE001
    print("\n   гейт не отработал: %s" % str(e)[:120])

if not СОЗДАТЬ:
    print("\n[сухой прогон] положить в очередь — с ключом --sozdat")
    raise SystemExit(0)

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
rid_получателя = завести_получателя(store, адрес=АДРЕС, образец_id=ОБРАЗЕЦ)
print("\nстрока получателя: %s" % rid_получателя)

обзор, создано = store.confirm_submit(
    email=АДРЕС, subject=ТЕМА, body=ТЕЛО, inn=ИНН, campaign_id=КАМПАНИЯ,
    recipient_id=rid_получателя, status="pending",
    reason="просили писать на этот адрес (ответ с export@kubanochka.ru)",
    panel={"ruchnoe_pismo": True, "operator": "avto-a5",
           "mailbox_id": ЯЩИК,
           "povod": "в ответе назвали nfo@kubanochka.ru, на сайте info@"},
    dedup_key="ruchnoe:kubanochka:%s:%d" % (АДРЕС, int(time.time())))
print("карточка очереди: id=%s, создана=%s" % (обзор, создано))

# срочная проба адреса, чтобы к моменту подтверждения был вердикт
try:
    from sender.addr_probe import build_addr_probe
    from sender.probe_sync import build_probe_sync
    п = getattr(build_addr_probe(store, cfg), "probe_", None)
    ц = build_probe_sync(store, п, cfg)
    print("срочная проба: %s" % ц.срочно([АДРЕС]))
except Exception as e:                                        # noqa: BLE001
    print("срочная проба не вышла: %s" % str(e)[:120])

print("\n=== ИТОГ ===")
print("письмо лежит в очереди подтверждений со статусом pending.")
print("отправится ТОЛЬКО когда ты нажмёшь одобрить в панели.")

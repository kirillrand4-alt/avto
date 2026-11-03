# -*- coding: utf-8 -*-
"""Статистика напоминаний: отправлено / ответы людей / автоответы / отбивки / интерес —
по версии (шаблон/заход), по теме (re_ab), по заходу, по почтовику получателя.
Ответ = событие reply/reply_auto/bounce по адресу карточки ПОСЛЕ её отправки."""
import collections, json, sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
ев = collections.defaultdict(list)
for em, et, ts in c.execute("SELECT lower(r.email), e.event_type, e.event_ts FROM events e JOIN recipients r ON r.id=e.recipient_id "
                            "WHERE e.event_type IN ('reply','reply_auto','bounce') AND e.event_ts >= '2026-10-26'"):
    ев[em].append((et, ts))
лид = {}
for em, st in c.execute("SELECT lower(r.email), l.status FROM leads l JOIN recipients r ON r.id=l.recipient_id"):
    лид[em] = st
def почтовик(e):
    д = e.split("@")[-1]
    if д in ("mail.ru", "inbox.ru", "list.ru", "bk.ru", "internet.ru"): return "mail.ru"
    if д in ("yandex.ru", "ya.ru", "yandex.com"): return "yandex"
    if д in ("gmail.com",): return "gmail"
    if д in ("rambler.ru",): return "rambler"
    return "корпоративный"
группы = collections.defaultdict(lambda: collections.Counter())
люди = []
for i, em, d, п, тм in c.execute("SELECT id, lower(email), decided_at, panel_json, subject FROM confirm_reviews WHERE kind='reply' AND status='sent' "
                             "AND panel_json LIKE '%napominanie%' AND decided_at IS NOT NULL"):
    п = json.loads(п or "{}")
    if "спам-тест" in str(п.get("vruchnuyu", "")) or "владельцу" in str(п.get("vruchnuyu", "")):
        continue
    день = d[:10]
    волна = "пилот 26.10" if день < "2026-11-01" else "03.11"
    версия = "заход" if "заходы" in str(п.get("vruchnuyu", "")) else ("пилот-заход" if волна.startswith("пилот") else "шаблон")
    после = [et for et, ts in ев.get(em, []) if ts >= d]
    исход = "отбивка" if "bounce" in после else ("ответ" if "reply" in после else ("автоответ" if "reply_auto" in после else "тишина"))
    ключи = [("волна", волна), ("версия", волна + " / " + версия), ("тема", волна + " / " + str(п.get("re_ab", "до деления"))),
             ("почтовик", волна + " / " + почтовик(em)), ("фактическая тема", "все / " + ("с Re:" if (тм or "").lower().startswith("re:") else "без Re:")), ("фактическая тема", волна + " / " + ("с Re:" if (тм or "").lower().startswith("re:") else "без Re:")), ("заход", волна + " / " + str(п.get("napominanie")))]
    for к in ключи:
        группы[к]["отправлено"] += 1
        группы[к][исход] += 1
        if исход == "ответ":
            группы[к]["интерес"] += лид.get(em) in ("new", "perepiska", "in_bitrix")
    if исход == "ответ":
        люди.append((волна, версия, em, лид.get(em)))
for раздел in ("волна", "версия", "тема", "фактическая тема", "почтовик", "заход"):
    print("\n== по: %s" % раздел)
    print("   %-38s %6s %6s %6s %7s %7s %6s" % ("", "ушло", "ответ", "%", "автоотв", "отбивка", "интер."))
    for (р, к), сч in sorted(группы.items()):
        if р != раздел: continue
        print("   %-38s %6d %6d %5.1f%% %7d %7d %6d" % (к[:38], сч["отправлено"], сч["ответ"], 100.0 * сч["ответ"] / max(1, сч["отправлено"]), сч["автоответ"], сч["отбивка"], сч["интерес"]))
print("\n== ответы людей (волна 03.11):")
for x in люди:
    if x[0] == "03.11": print("  ", x[1:])

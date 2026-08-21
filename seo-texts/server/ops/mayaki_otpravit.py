# -*- coding: utf-8 -*-
"""Отправить маякам КОПИЮ настоящего письма и запомнить, что проверять.

Замер стоит чего-то, только если письмо то же самое: заголовки, подпись,
ссылки и отправитель влияют на папку не меньше текста. Поэтому берём
последнее реально отправленное письмо нужного направления и шлём его на
свои маяки тем же путём и с того же ящика.

Служебная кампания заводится один раз, её номер кладётся в настройки
(mayaki_kampaniya) - аналитика вычитает её из счётчиков, чтобы маяки не
разбавляли статистику отправки.

Запуск: mayaki_otpravit.py [kc|meyer] [--katit]
"""
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.dtos import (CampaignIn, MessageIn, RecipientIn,          # noqa: E402
                         RenderedMessage, SequenceStepIn)
from sender.mayaki import КАМПАНИЯ, nastroyki, spisok                # noqa: E402
from sender.store import Store                                       # noqa: E402
from sender.wiring import build_deps                                 # noqa: E402

НАПРАВЛЕНИЕ = next((а for а in sys.argv[1:] if а in ("kc", "meyer")), "meyer")
КАТИТЬ = "--katit" in sys.argv

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
живой = getattr(deps.confirm, "_sender", None)

н = nastroyki(cfg)
маяки = spisok(cfg)
print(f"маяки: включены={н['включены']}, в партию {н['в_партию']}, "
      f"проверка через {н['задержка_мин']} мин; заведено {len(маяки)}")
for м in маяки:
    print(f"  {м.email:<34} {м.provayder:<10} imap={м.imap_host} "
          f"пароль из {м.parol_env}: {'есть' if м.parol() else 'НЕТ'}")
if not маяки:
    print("\nСписок пуст. Заведи ящики у mail.ru/Яндекса/Gmail и опиши их в")
    print("sender.yaml -> mayaki.spisok (пароль - только именем переменной).")
    raise SystemExit(0)
if живой is None:
    print("живой отправитель не собран - слать нечем")
    raise SystemExit(1)

# письмо-образец: последнее ушедшее по этому направлению
камп = (9, 10) if НАПРАВЛЕНИЕ == "kc" else (7, 8, 11)
места = ",".join("?" for _ in камп)
with store._lock:
    р = store._conn.execute(
        f"SELECT m.id, m.subject, m.body_rendered, m.mailbox_id, "
        f"       substr(m.sent_at,1,16) когда "
        f"  FROM messages m WHERE m.status='sent' AND m.campaign_id IN ({места}) "
        f"   AND COALESCE(m.body_rendered,'') <> '' "
        f" ORDER BY m.sent_at DESC LIMIT 1", камп).fetchone()
if not р:
    print(f"нет отправленных писем с телом по направлению {НАПРАВЛЕНИЕ}")
    raise SystemExit(1)
print(f"\nобразец: письмо {р['id']} от {р['когда']} с {р['mailbox_id']}")
print(f"  тема: {р['subject']}")

if not КАТИТЬ:
    print("\nсухой прогон. Слать - --katit")
    raise SystemExit(0)

# СЛУЖЕБНАЯ КАМПАНИЯ И ЕЁ ШАГ. Письму обязателен sequence_step_id - это
# не наша прихоть, а схема messages. Шаблоны шага при этом не работают:
# текст мы передаём готовым (RenderedMessage), тем же, что ушёл боевым.
номер = store.get_setting("mayaki_kampaniya", None)
шаг = store.get_setting("mayaki_shag", None)
if not номер:
    номер = store.create_campaign(CampaignIn(
        name=КАМПАНИЯ, legal_entity=str(cfg.legal().entity),
        legal_inn=str(cfg.legal().inn), provider_pool="pool_fallback",
        config={"служебная": True, "зачем": "замер папки у почтовика"}))
    store.set_setting("mayaki_kampaniya", int(номер))
    print(f"заведена служебная кампания {номер}")
    шаг = None
номер = int(номер)
if not шаг:
    шаг = store.add_step(SequenceStepIn(
        campaign_id=номер, step_index=1, delay_hours=0,
        subject_tmpl="{subject}", body_tmpl="{body}"))
    store.set_setting("mayaki_shag", int(шаг))
шаг = int(шаг)

сейчас = datetime.now(timezone.utc)
метка = сейчас.strftime("%d.%m %H:%M")
тема = f"{р['subject']} [маяк {метка}]"
ушло = []
for м in маяки[:н["в_партию"] or len(маяки)]:
    rid = store.upsert_recipient(RecipientIn(
        email=м.email, domain=м.email.split("@")[-1],
        company_name=f"МАЯК {м.provayder}", inn=None,
        source="маяк"))
    mid, _ = store.enqueue_message(MessageIn(
        campaign_id=номер, recipient_id=int(rid), sequence_step_id=шаг,
        idempotency_key=f"mayak|{м.email}|{int(сейчас.timestamp())}",
        scheduled_at=сейчас), status="pending_review")
    # тема письма живёт в самом письме, а не в шаблоне шага
    with store.transaction() as conn:
        conn.execute("UPDATE messages SET subject=? WHERE id=?", (тема, int(mid)))
    try:
        живой.send(store.get_message(int(mid)),
                   RenderedMessage(subject=тема, body=str(р["body_rendered"])),
                   str(р["mailbox_id"]), manual=True, to_email=м.email)
        ушло.append((м.email, тема))
        print(f"  ушло на {м.email} с {р['mailbox_id']}")
    except Exception as ex:                                         # noqa: BLE001
        print(f"  НЕ ушло на {м.email}: {type(ex).__name__}: {str(ex)[:100]}")

store.set_setting("mayaki_poslednyaya_tema", тема)
store.set_setting("mayaki_poslednyaya_otpravka", сейчас.isoformat())
print(f"\nотправлено маякам: {len(ушло)}")
print(f"через {н['задержка_мин']} мин запусти mayaki_proverit.py")

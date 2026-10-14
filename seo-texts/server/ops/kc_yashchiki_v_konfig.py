# -*- coding: utf-8 -*-
"""Ящики КЦ в sender.yaml (владелец 14.10: «заведи почты для КЦ»).

Заводим только ящики, чей пароль уже лежит в окружении (иначе Config.load
падает на старте службы). Каждый: provider yandex, division kc, pool pool_kc.
pool_kc — отдельный пул, в routing его НЕТ: автоотправка (pick_mailbox берёт
ящики только из маршрутизируемых пулов) ящики КЦ не возьмёт, пока владелец не
скажет запускать КЦ. mailbox_gender: m. Бэкап, Config.load на проверку, откат.

    kc_yashchiki_v_konfig.py [--primenit]
"""
import io
import os
import re
import shutil
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402

П = r"C:\sender\sender.yaml"
ПРИМ = "--primenit" in sys.argv
# адрес, env, имя для подписи
ЯЩИКИ = [
    ("v.melnikov@compressor-air-expert.ru", "BOX34_PASSWORD", "Владислав Мельников"),
    ("vladislav.melnikov@compressor-pro-systems.ru", "BOX35_PASSWORD", "Владислав Мельников"),
    ("melnikov.v@kompressor-air-trade.ru", "BOX36_PASSWORD", "Владислав Мельников"),
    ("i.lyapin@compressor-pro-systems.ru", "BOX37_PASSWORD", "Игорь Ляпин"),
    ("igor.lyapin@kompressor-air-trade.ru", "BOX38_PASSWORD", "Игорь Ляпин"),
    ("lyapin.i@kompressor-pro-expert.ru", "BOX39_PASSWORD", "Игорь Ляпин"),
    ("k.yashin@kompressor-air-trade.ru", "BOX40_PASSWORD", "Кирилл Яшин"),
    ("kirill.yashin@kompressor-pro-expert.ru", "BOX41_PASSWORD", "Кирилл Яшин"),
    ("yashin.k@kompressor-pro-trade.ru", "BOX42_PASSWORD", "Кирилл Яшин"),
    ("o.tseyzer@kompressor-pro-expert.ru", "BOX43_PASSWORD", "Олег Цейзер"),
    ("oleg.tseyzer@kompressor-pro-trade.ru", "BOX44_PASSWORD", "Олег Цейзер"),
    ("tseyzer.o@compressor-air-expert.ru", "BOX45_PASSWORD", "Олег Цейзер"),
    ("a.balakirev@kompressor-pro-trade.ru", "BOX46_PASSWORD", "Антон Балакирев"),
    ("anton.balakirev@compressor-air-expert.ru", "BOX47_PASSWORD", "Антон Балакирев"),
    ("balakirev.a@compressor-pro-systems.ru", "BOX48_PASSWORD", "Антон Балакирев"),
    ("v.prokhorov@compressor-air-expert.ru", "BOX49_PASSWORD", "Вячеслав Прохоров"),
    ("vyacheslav.prokhorov@compressor-pro-systems.ru", "BOX50_PASSWORD", "Вячеслав Прохоров"),
    ("prokhorov.v@kompressor-air-trade.ru", "BOX51_PASSWORD", "Вячеслав Прохоров"),
    ("a.dmitriev@compressor-pro-systems.ru", "BOX52_PASSWORD", "Александр Дмитриев"),
    ("aleksandr.dmitriev@kompressor-air-trade.ru", "BOX53_PASSWORD", "Александр Дмитриев"),
    ("dmitriev.a@kompressor-pro-expert.ru", "BOX54_PASSWORD", "Александр Дмитриев"),
    ("p.novoseltsev@kompressor-air-trade.ru", "BOX55_PASSWORD", "Павел Новосельцев"),
    ("pavel.novoseltsev@kompressor-pro-expert.ru", "BOX56_PASSWORD", "Павел Новосельцев"),
    ("novoseltsev.p@kompressor-pro-trade.ru", "BOX57_PASSWORD", "Павел Новосельцев"),
    ("m.pavlov@kompressor-pro-expert.ru", "BOX58_PASSWORD", "Максим Павлов"),
    ("maksim.pavlov@kompressor-pro-trade.ru", "BOX59_PASSWORD", "Максим Павлов"),
    ("pavlov.m@compressor-air-expert.ru", "BOX60_PASSWORD", "Максим Павлов"),
    ("n.kirchatov@kompressor-pro-trade.ru", "BOX61_PASSWORD", "Никита Кирчатов"),
    ("nikita.kirchatov@compressor-air-expert.ru", "BOX62_PASSWORD", "Никита Кирчатов"),
    ("kirchatov.n@compressor-pro-systems.ru", "BOX63_PASSWORD", "Никита Кирчатов"),
]
т = io.open(П, encoding="utf-8").read()
уже = {м for м in re.findall(r'mailbox_id:\s*"?([^"\s]+)', т)}
есть_env = [я for я in ЯЩИКИ if os.environ.get(я[1])]
нет_env = [я[0] for я in ЯЩИКИ if not os.environ.get(я[1])]
новые = [я for я in есть_env if я[0] not in уже]
print("в справке %d; с паролем в окружении %d; уже в конфиге %d; к заведению %d"
      % (len(ЯЩИКИ), len(есть_env), len([я for я in ЯЩИКИ if я[0] in уже]), len(новые)))
print("без пароля (не заводим):", нет_env)
if not ПРИМ or not новые:
    print("=== ЯЩИКИ КЦ В КОНФИГ: %s ===" % ("нечего" if not новые else "сухой прогон"))
    sys.exit(0)
блок = "".join(
    '  - mailbox_id: "%s"\n    provider: yandex\n    smtp_host: smtp.yandex.ru\n    smtp_port: 465\n'
    '    imap_host: imap.yandex.ru\n    imap_port: 993\n    login: "%s"\n    password_env: %s\n'
    '    from_name: "%s, Компрессор Центр"\n    pool: pool_kc\n    division: kc\n' % (а, а, env, имя)
    for а, env, имя in новые)
стр = т.splitlines(True)
i_mb = next(i for i, с in enumerate(стр) if re.match(r"^mailboxes:\s*$", с))
стр.insert(i_mb + 1, блок)
т2 = "".join(стр)
# пул pool_kc рядом с pool_fallback (в routing не добавляем)
м = re.search(r"^(\s*)pool_fallback:\s*\[[^\]]*\]\s*\n", т2, re.M)
все_kc = [я[0] for я in ЯЩИКИ if я[0] in уже] + [я[0] for я in новые]
if re.search(r"^\s*pool_kc:", т2, re.M):
    т2 = re.sub(r"^(\s*)pool_kc:\s*\[[^\]]*\]", lambda x: x.group(1) + "pool_kc: [" + ", ".join(все_kc) + "]", т2, flags=re.M)
else:
    т2 = т2[:м.end()] + м.group(1) + "pool_kc: [" + ", ".join(все_kc) + "]\n" + т2[м.end():]
# пол для согласования «рад/рада»
мг = re.search(r"^(\s*)mailbox_gender:\s*\n", т2, re.M)
if мг:
    отступ = мг.group(1) + "  "
    т2 = т2[:мг.end()] + "".join("%s%s: m\n" % (отступ, а) for а, _, _ in новые) + т2[мг.end():]
бэкап = П + ".bak-%d" % int(time.time())
shutil.copy2(П, бэкап)
io.open(П, "w", encoding="utf-8").write(т2)
try:
    cfg = Config.load(П)
    kc = [m.mailbox_id for m in cfg.mailboxes() if getattr(m, "division", None) == "kc"]
    me = [m.mailbox_id for m in cfg.mailboxes() if getattr(m, "division", None) == "meyer"]
    маршр = cfg.get("provider_split.routing", {}) or {}
    print("Config.load OK: ящиков kc %d, meyer %d; routing: %s" % (len(kc), len(me), маршр))
    пулы = cfg.get("provider_split.pools", {}) or {}
    for имя_п, члены in пулы.items():
        print("  пул %-14s всего %3d, из них kc %d" % (имя_п, len(члены), sum(1 for x in члены if x in kc)))
    print("бэкап: %s" % бэкап)
except Exception as е:  # noqa: BLE001
    shutil.copy2(бэкап, П)
    print("ОТКАТ: %s" % str(е)[:300])
print("=== ЯЩИКИ КЦ В КОНФИГ: ПРИМЕНЕНО ===")

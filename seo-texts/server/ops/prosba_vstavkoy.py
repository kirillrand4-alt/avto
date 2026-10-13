# -*- coding: utf-8 -*-
"""ai_letter: нет просьбы перенаправить — вставляем фразу перед подписью, а не бракуем
(157 писем брака за 13.10). Правка по якорям, бэкап, py_compile, откат."""
import io
import py_compile
import shutil
import sys
import time
ПУТЬ = r"C:\\sender\\sender\\ai_letter.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
if "def vstavit_prosbu" in т:
    print("=== ПРОСЬБА ВСТАВКОЙ: УЖЕ БЫЛО ===")
    sys.exit(0)
ПАРЫ = [('_ТИРЕ_RE = re.compile(r\'[ \\t]*[—–][ \\t]*\')\n\n\ndef bez_dlinnogo_tire(t: str) -> str:\n    """«завод — крупный» → «завод - крупный». Дефис вместо длинного тире:\n', '_ТИРЕ_RE = re.compile(r\'[ \\t]*[—–][ \\t]*\')\n\n\n# ПРОСЬБУ ПЕРЕНАПРАВИТЬ ВСТАВЛЯЕМ, А НЕ БРАКУЕМ (разбор 13.10). Модель\n# упорно её пропускает: за день 157 писем, во всём остальном годных, ушли в\n# брак после трёх кругов правки. Правится механически, как длинное тире:\n# одна фраза перед подписью. Формы - из эталонов редактора, разные, чтобы\n# партия не звучала одинаково; выбор по тексту письма, повторяемый.\n_PROSBA_VARIANTY = (\n    \'Если вопрос не к вам, буду благодарен за контакт коллеги - обращусь напрямую.\',\n    \'Если этим занимается другой специалист, перешлите, пожалуйста, письмо ему.\',\n    \'Если вопрос ведёт кто-то из коллег, подскажите, к кому лучше обратиться.\',\n    \'Если это не ваша зона, передайте, пожалуйста, письмо тому, кто занимается качеством продукции.\',\n)\n\n\ndef vstavit_prosbu(body: str) -> str:\n    """Вставить просьбу перенаправить перед «С уважением» (или в конец)."""\n    т = str(body or \'\')\n    if _prosba_perenapravit(т):\n        return т\n    фраза = _PROSBA_VARIANTY[sum(map(ord, т[:400])) % len(_PROSBA_VARIANTY)]\n    м = re.search(r\'\\n\\s*С\\s+уважением\', т)\n    if м:\n        return т[:м.start()].rstrip() + \'\\n\\n\' + фраза + \'\\n\\n\' + т[м.start():].lstrip()\n    return т.rstrip() + \'\\n\\n\' + фраза\n\n\ndef bez_dlinnogo_tire(t: str) -> str:\n    """«завод — крупный» → «завод - крупный». Дефис вместо длинного тире:\n'), ("                fails = gate(L['subject'], L['body'], mode=_rec['mode'],\n                             extra=_extra,\n                             facts=self.facts_for(div), division=div)\n                if fails:\n                    bad[i] = fails\n", "                fails = gate(L['subject'], L['body'], mode=_rec['mode'],\n                             extra=_extra,\n                             facts=self.facts_for(div), division=div)\n                if 'нет просьбы перенаправить письмо ответственному' in fails:\n                    L['body'] = vstavit_prosbu(L['body'])\n                    fails = gate(L['subject'], L['body'], mode=_rec['mode'],\n                                 extra=_extra,\n                                 facts=self.facts_for(div), division=div)\n                if fails:\n                    bad[i] = fails\n")]
for с, _н in ПАРЫ:
    if т.count(с) != 1:
        print("якорь (%d): %r" % (т.count(с), с[:120]))
        print("=== ПРОСЬБА ВСТАВКОЙ: НЕ ПРИМЕНЕНО ===")
        sys.exit(0)
бэкап = ПУТЬ + ".bak-%d" % int(time.time())
shutil.copy2(ПУТЬ, бэкап)
for с, н in ПАРЫ:
    т = т.replace(с, н)
io.open(ПУТЬ, "w", encoding="utf-8").write(т)
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as е:  # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print("сбой, откат: %s" % е)
    print("=== ПРОСЬБА ВСТАВКОЙ: ОТКАТ ===")
    sys.exit(0)
print("бэкап: %s" % бэкап)
print("=== ПРОСЬБА ВСТАВКОЙ: ПРИМЕНЕНО ===")

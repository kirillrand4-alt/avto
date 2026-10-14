# -*- coding: utf-8 -*-
"""confirm.py: ящик чужого направления не выдаётся нигде (подбор, ответы, ручная отправка,
выбор оператора) — перед заведением ящиков КЦ 14.10. Правка по якорям, бэкап, py_compile, откат."""
import io
import py_compile
import shutil
import sys
import time
ПУТЬ = r"C:\\sender\\sender\\confirm.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
if "def _campaign_division_of" in т:
    print("=== ЯЩИК СВОЕГО НАПРАВЛЕНИЯ: УЖЕ БЫЛО ===")
    sys.exit(0)
ПАРЫ = [('            mailbox_id = self._fallback_mailbox(inn=row.get("inn"),\n                                                prefer_mailbox=prefer)\n            if mailbox_id is None:\n                raise ConfirmBlockedError(\n                    "нет доступного ящика НУЖНОГО НАПРАВЛЕНИЯ для ответа "', '            # НАПРАВЛЕНИЕ ОТВЕТА (ящики КЦ, 14.10): ящик ветки задаёт направление;\n            # нет ящика ветки — направление кампании письма. Ответ Meyer-клиенту\n            # с компрессорного ящика (и наоборот) не уходит никогда.\n            нужно = (self._division_of_mailbox(prefer) if prefer else None) \\\n                or self._campaign_division_of(row) or self.letter_division(row)\n            mailbox_id = self._fallback_mailbox(inn=row.get("inn"),\n                                                prefer_mailbox=prefer,\n                                                prefer_division=нужно)\n            if mailbox_id is None:\n                raise ConfirmBlockedError(\n                    "нет доступного ящика НУЖНОГО НАПРАВЛЕНИЯ для ответа "'), ('                свой = self._fallback_mailbox(inn=row.get("inn"),\n                                              prefer_division=letter_div)\n                if свой:\n                    mailbox_id = свой', '                свой = self._fallback_mailbox(inn=row.get("inn"),\n                                              prefer_division=letter_div)\n                # своего свободного нет — НЕ шлём с чужого (ящики КЦ, 14.10)\n                mailbox_id = свой or None'), ('        # 1) ящик из треда\n        if prefer_mailbox and any(mb.mailbox_id == prefer_mailbox for mb in boxes) \\\n                and _ok(prefer_mailbox):\n            return prefer_mailbox', '        def _div(mid):\n            return next((getattr(mb, "division", None) for mb in boxes\n                         if mb.mailbox_id == mid), None)\n\n        # 1) ящик из треда — только своего направления (ящики КЦ, 14.10)\n        if prefer_mailbox and any(mb.mailbox_id == prefer_mailbox for mb in boxes) \\\n                and _ok(prefer_mailbox) \\\n                and (not prefer_division or _div(prefer_mailbox) == prefer_division):\n            return prefer_mailbox'), ('                if свои:\n                    return self._next_in_rotation(свои)\n            if годные:\n                return self._next_in_rotation(годные)', '                if свои:\n                    return self._next_in_rotation(свои)\n                # направление письма известно, своего ящика нет — чужой не\n                # подставляем (ящики КЦ, 14.10): оператор увидит причину\n                return None\n            if годные:\n                return self._next_in_rotation(годные)'), ('            if свои:\n                return self._next_in_rotation(свои)\n        return self._next_in_rotation(свободные)', '            if свои:\n                return self._next_in_rotation(свои)\n            return None   # нужное направление известно — чужой ящик не берём\n        return self._next_in_rotation(свободные)'), ('        if mailbox_id not in ids:\n            raise ValidationError(f"ящик {mailbox_id!r} не настроен")', '        if mailbox_id not in ids:\n            raise ValidationError(f"ящик {mailbox_id!r} не настроен")\n        # ящик чужого направления выбрать нельзя (ящики КЦ, 14.10)\n        нужно = self.letter_division(row) or self._campaign_division_of(row)\n        его = self._division_of_mailbox(mailbox_id)\n        if нужно and его and его != нужно:\n            raise ValidationError(f"ящик {mailbox_id!r} направления {его}, "\n                                  f"а письмо — {нужно}: выбрать нельзя")'), ('    def _division_of_mailbox(self, mailbox_id: str) -> Optional[str]:', '    def _campaign_division_of(self, row: dict) -> Optional[str]:\n        """Направление кампании карточки (kc|meyer) или None."""\n        try:\n            cid = row.get("campaign_id")\n            if not cid:\n                return None\n            from sender.company_card import campaign_division\n            camp = self._store.get_campaign(int(cid))\n            return campaign_division(camp) if camp else None\n        except Exception:  # noqa: BLE001\n            return None\n\n    def _division_of_mailbox(self, mailbox_id: str) -> Optional[str]:')]
for с, _н in ПАРЫ:
    if т.count(с) != 1:
        print("якорь (%d): %r" % (т.count(с), с[:120]))
        print("=== ЯЩИК СВОЕГО НАПРАВЛЕНИЯ: НЕ ПРИМЕНЕНО ===")
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
    print("=== ЯЩИК СВОЕГО НАПРАВЛЕНИЯ: ОТКАТ ===")
    sys.exit(0)
print("бэкап: %s" % бэкап)
print("=== ЯЩИК СВОЕГО НАПРАВЛЕНИЯ: ПРИМЕНЕНО ===")

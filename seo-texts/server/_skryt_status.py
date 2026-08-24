# -*- coding: utf-8 -*-
r"""Как лента прячет «не интересно»: ищем правило в store.list_leads."""
import json
import re

п = r'C:\sender\sender\store.py'
т = open(п, encoding='utf-8', errors='replace').read()
м = re.search(r'def list_leads.{0,6000}?(?=\n    def )', т, re.S)
кусок = м.group(0) if м else ''
строки = кусок.splitlines()
инт = [(i, s) for i, s in enumerate(строки)
       if re.search(r'not_interested|status|by_status|скрыт|hidden', s, re.I)]
print(json.dumps({'найдено': ['%d: %s' % (i, s.strip()[:130])
                              for i, s in инт][:30]},
                 ensure_ascii=False, indent=1)[:3000])

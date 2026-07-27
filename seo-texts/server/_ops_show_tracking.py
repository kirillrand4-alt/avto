# -*- coding: utf-8 -*-
"""Показать секцию tracking боевого sender.yaml (только чтение, без секретов)."""
import json
import re

CFG = r'C:\sender\sender.yaml'


def main():
    raw = open(CFG, encoding='utf-8', errors='replace').read()
    out = {}
    m = re.search(r'^tracking:\s*$(.*?)^(?=\S)', raw, re.M | re.S)
    out['секция_tracking'] = m.group(1) if m else '(не разобрана)'
    # где вообще встречается base_url
    out['все_base_url'] = []
    for mm in re.finditer(r'^(\s*)base_url\s*:\s*(.+)$', raw, re.M):
        line_no = raw[:mm.start()].count('\n') + 1
        out['все_base_url'].append({'строка': line_no, 'отступ': len(mm.group(1)),
                                    'значение': mm.group(2).strip()[:80]})
    # к какой секции относится каждый
    for item in out['все_base_url']:
        idx = 0
        sec = '?'
        for i, ln in enumerate(raw.splitlines(), 1):
            if i >= item['строка']:
                break
            if ln and not ln[0].isspace() and ln.rstrip().endswith(':'):
                sec = ln.strip().rstrip(':')
        item['секция'] = sec
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()

import re
т = open(r'C:\Caddyfile', encoding='utf-8', errors='replace').read()
print('===ИТОГ===')
for м in re.finditer(r'[^\n]*(@obzvon\b|/obzvon\b|/obzvon/\*|obzvon_main|handle_path /obzvon)[^\n]*(\n[^\n]*){0,4}', т):
    print(re.sub(r'(basic_?auth[^\n]*\n(?:\s*\S+\s+)\S+)', '<basicauth скрыт>', м.group(0)), '\n---')

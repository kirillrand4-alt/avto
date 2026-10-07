# -*- coding: utf-8 -*-
"""Проверка: видна ли новая кнопка «Статистика» продавцу.

Если ссылка на распределение в centro.html обёрнута условием «только админ», моя вставка
попала внутрь условия и всё хорошо. Если нет — продавец получит кнопку, которая отдаёт
403, то есть я добавлю ему неработающий элемент. Смотрю окружение, а не предполагаю.
"""
import io
import re

PUT = r'C:\centro2\app\templates\centro.html'
t = io.open(PUT, encoding='utf-8').read()

i = t.find('/centro/stats')
print('позиция ссылки на статистику: %d из %d' % (i, len(t)))
okno = t[max(0, i - 700):i + 300]
print('\n--- окружение (700 знаков до, 300 после) ---')
for l in okno.splitlines():
    if l.strip():
        print('   %s' % l.strip()[:150])

print('\n--- условия Jinja до ссылки ---')
# Считаю открытые if/endif до места вставки: если баланс положительный, ссылка внутри условия
do = t[:i]
ify = re.findall(r'\{%-?\s*(if|endif|else|elif)([^%]*)%\}', do)
balans = 0
poslednie = []
for kl, telo in ify:
    if kl == 'if':
        balans += 1
        poslednie.append(telo.strip()[:80])
    elif kl == 'endif':
        balans -= 1
        if poslednie:
            poslednie.pop()
print('открытых if на месте ссылки: %d' % balans)
print('какие именно: %s' % (' | '.join(poslednie) if poslednie else 'ни одного'))

print('\n===== ИТОГ =====')
if balans > 0 and any('admin' in p or 'role' in p for p in poslednie):
    print('ссылка ВНУТРИ условия про роль — продавец её не увидит: %s' % poslednie)
elif balans > 0:
    print('ссылка внутри условия, но про роль там ничего нет: %s' % poslednie)
else:
    print('ссылка ВНЕ условий — её увидит и продавец, а маршрут отдаст ему 403.'
          ' Нужна обёртка.')

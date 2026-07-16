# -*- coding: utf-8 -*-
"""Прототип фото-блока: Fable через API вставляет проектное фото в готовый текст."""
import json, re

from gen_provider import make_client, call

d = json.load(open('gen/r2-fable-5/result-el-hansmann.json'))

PROMPT = """Ты дорабатываешь готовый SEO-текст каталожной страницы (HTML ниже). Задача: вставить
ОДИН фото-блок с реального проекта в самое уместное место (рядом с упоминанием проектов/опыта
поставок, НЕ в начало текста и НЕ внутрь FAQ).

Данные фото:
- src: /upload/medialibrary/1d6/jzeqt8xzk7vr75d3v44o214b6enx04gb.jpeg
- проект: поставка винтового компрессора Hansmann RSA 7,5-10 для ООО «Русская Аграрная Группа», Рязань
- ссылка проекта: /projects/pishchevoe-proizvodstvo/vintovoy-kompressor-hansmann-rsa-7-5-10-dlya-ooo-russkaya-agrarnaya-gruppa/

Шаблон блока (используй ровно эту вёрстку, только инлайн-стили, НИКАКИХ <style>/<script>):
<p style="margin:24px 0 6px; text-align:center;"><img src="SRC" alt="ALT" style="width:100%; max-width:860px; height:auto; border-radius:6px;"></p>
<p style="text-align:center; font-size:14px; color:#777; margin:0 0 20px;">ПОДПИСЬ с <a href="URL">ссылкой на проект</a></p>

Требования:
- alt: человеческое описание с моделью и городом (без слова «фото», без переспама)
- подпись: 1 короткая строка, модель + заказчик + город, ссылка ведёт на страницу проекта
- если в тексте уже есть ссылка на этот проект - сохрани её, это не дубль
- остальной текст НЕ МЕНЯЙ ни на символ
- длинное тире запрещено

Текст:
{html}

Ответь ОДНИМ JSON: {{"text_html": "<полный обновлённый HTML>"}}"""

client = make_client()
msg = call(client, [{'role': 'user', 'content': PROMPT.format(html=d['text_html'])}], 'claude-fable-5')
text = ''.join(b.text for b in msg.content if b.type == 'text').strip()
m = re.search(r'\{.*\}', text, re.S)
new_html = json.loads(m.group(0))['text_html'].replace('—', '-')
d2 = dict(d, text_html=new_html)
json.dump(d2, open('gen/r2-fable-5/result-el-hansmann-FOTO.json', 'w'), ensure_ascii=False, indent=1)
print('фото-блок вставлен:', 'medialibrary/1d6' in new_html, '| длина была/стала:', len(d['text_html']), len(new_html))

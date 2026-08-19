# -*- coding: utf-8 -*-
"""Проверка сборки письма с вложением — на копии модуля, боевое не трогаем."""
import email
import importlib.util
import io
import json
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender')
сп = importlib.util.spec_from_file_location('sender_novyy', r'C:\sender\_tmp\sender_novyy.py')
м = importlib.util.module_from_spec(сп)
sys.modules['sender_novyy'] = м
сп.loader.exec_module(м)
from sender.dtos import RenderedMessage  # noqa: E402

пример = os.path.join(tempfile.gettempdir(), 'kp-primer.pdf')
io.open(пример, 'wb').write(b'%PDF-1.4 proba vlozheniya\n')
# собираем письмо как это делает send_reply
class Пустой(м.Sender):
    def __init__(self):
        pass
s = Пустой()
байты = s._build_mime({'From': 'a@b.ru', 'To': 'c@d.ru', 'Subject': 'Проба'},
                      RenderedMessage(subject='Проба', body='Текст письма'),
                      vlozheniya=[{'name': 'КП Руспром.pdf', 'path': пример}])
msg = email.message_from_bytes(байты)
части = []
for ч in msg.walk():
    части.append({'тип': ч.get_content_type(),
                  'имя_файла': ч.get_filename(),
                  'байт': len(ч.get_payload(decode=True) or b'')})
print(json.dumps({'multipart': msg.is_multipart(), 'части': части,
                  'размер_письма': len(байты)}, ensure_ascii=False, indent=1))

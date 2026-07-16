# -*- coding: utf-8 -*-
"""Маскирование персданных перед отправкой писем в API: email, телефоны, URL-трекеры.
ФИО из подписей режем по маркерам («С уважением, ...»)."""
import re

def scrub(text):
    t = re.sub(r'[\w.+-]+@[\w-]+\.[\w.]+', '[EMAIL]', text)
    t = re.sub(r'(\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}', '[PHONE]', t)
    t = re.sub(r'(с уважением|best regards|искренне ваш)[^,\n]*[,\n]+\s*([А-ЯЁA-Z][а-яёa-z]+(\s+[А-ЯЁA-Z][а-яёa-z]+){0,2})',
               lambda m: m.group(0).replace(m.group(2), '[NAME]'), t, flags=re.I)
    t = re.sub(r'https?://\S*(utm_|clck|ysclid)\S*', '[URL]', t)
    return t

if __name__ == '__main__':
    demo = 'Добрый день! С уважением, Иванов Пётр, +7 (912) 345-67-89, petr@zavod.ru'
    print(scrub(demo))

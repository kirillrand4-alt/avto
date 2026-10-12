# -*- coding: utf-8 -*-
"""Отличить бан IP сервера от общей беды Яндекса: smtp.yandex.ru:465 через
прокси (другой выходной IP). Только TCP-соединение через туннель, без SMTP-
команд и без авторизации у Яндекса. Учётки прокси не печатаются.
"""
import base64
import os
import socket
import struct
import time
import urllib.parse

ЦЕЛИ = (("smtp.yandex.ru", 465), ("smtp.yandex.ru", 587), ("smtp.mail.ru", 465),
        ("mx.yandex.ru", 25))


def socks5(px, хост, порт):
    s = socket.create_connection((px.hostname, px.port or 1080), timeout=15)
    s.settimeout(30)
    if px.username:
        s.sendall(b"\x05\x01\x02")
        if s.recv(2) != b"\x05\x02":
            raise RuntimeError("socks: метод auth не принят")
        u, p = urllib.parse.unquote(px.username).encode(), urllib.parse.unquote(px.password or "").encode()
        s.sendall(b"\x01" + bytes([len(u)]) + u + bytes([len(p)]) + p)
        if s.recv(2)[1:2] != b"\x00":
            raise RuntimeError("socks: auth отказ")
    else:
        s.sendall(b"\x05\x01\x00")
        s.recv(2)
    h = хост.encode()
    s.sendall(b"\x05\x01\x00\x03" + bytes([len(h)]) + h + struct.pack(">H", порт))
    отв = s.recv(10)
    s.close()
    if len(отв) < 2 or отв[1] != 0:
        raise RuntimeError("socks rep=%s" % (отв[1] if len(отв) > 1 else "?"))


def http_connect(px, хост, порт):
    s = socket.create_connection((px.hostname, px.port or 80), timeout=15)
    s.settimeout(30)
    заг = "CONNECT %s:%d HTTP/1.1\r\nHost: %s:%d\r\n" % (хост, порт, хост, порт)
    if px.username:
        к = base64.b64encode(("%s:%s" % (urllib.parse.unquote(px.username),
                                          urllib.parse.unquote(px.password or ""))).encode()).decode()
        заг += "Proxy-Authorization: Basic %s\r\n" % к
    s.sendall((заг + "\r\n").encode())
    отв = s.recv(200).decode("latin1", "replace").split("\r\n")[0]
    s.close()
    if " 200" not in отв:
        raise RuntimeError("http: %s" % отв[:40])


итог = []
for var in ("PROXY_URL", "PROXY_URLV2", "PROXY_URLV3"):
    raw = os.environ.get(var, "")
    if not raw:
        print("%s: нет в окружении" % var)
        continue
    px = urllib.parse.urlsplit(raw if "://" in raw else "http://" + raw)
    print("%s: схема=%s" % (var, px.scheme))
    for хост, порт in ЦЕЛИ:
        t = time.time()
        try:
            (socks5 if px.scheme.startswith("socks") else http_connect)(px, хост, порт)
            р = "ОК %.1fс" % (time.time() - t)
        except Exception as e:  # noqa: BLE001
            р = "СБОЙ %.0fс %s" % (time.time() - t, str(e)[:50].replace(px.hostname or "#", "<proxy>"))
        print("   -> %s:%d %s" % (хост, порт, р))
        итог.append("%s %s:%d %s" % (var, хост, порт, р[:4]))
print("=== ЧЕРЕЗ ПРОКСИ: " + "; ".join(итог))

// Локальный прокси-мост на Node (без внешних бинарников — Defender не трогает).
// Слушает на 127.0.0.1:PORT БЕЗ авторизации и форвардит весь трафик в вышестоящий
// HTTP-прокси с логином/паролем. Нужен потому, что Chromium плохо авторизуется
// на HTTPS-прокси напрямую (ERR_TUNNEL_CONNECTION_FAILED / ERR_INVALID_AUTH_CREDENTIALS).
//
// Запуск:
//   node src/proxybridge.mjs "http://user:pass@host:port" [localPort]
// затем в панели укажи прокси:  http://127.0.0.1:<localPort>  (логин/пароль пустые)

import net from 'node:net';
import http from 'node:http';

const upstreamUrl = process.argv[2] || process.env.UPSTREAM_PROXY;
const localPort = parseInt(process.argv[3] || process.env.BRIDGE_PORT || '11561', 10);
const localHost = '127.0.0.1';

if (!upstreamUrl) {
  console.error('Укажи вышестоящий прокси: node src/proxybridge.mjs "http://user:pass@host:port" [port]');
  process.exit(1);
}

const up = new URL(upstreamUrl);
const upHost = up.hostname;
const upPort = parseInt(up.port, 10) || 80;
const auth = (up.username || up.password)
  ? 'Basic ' + Buffer.from(`${decodeURIComponent(up.username)}:${decodeURIComponent(up.password)}`).toString('base64')
  : null;

const server = http.createServer();

// Обычный HTTP-запрос (http:// сайты) — пересобираем и шлём в вышестоящий прокси.
server.on('request', (req, res) => {
  const u = net.connect(upPort, upHost, () => {
    let head = `${req.method} ${req.url} HTTP/1.1\r\n`;
    for (let i = 0; i < req.rawHeaders.length; i += 2) {
      const k = req.rawHeaders[i];
      if (/^proxy-/i.test(k)) continue;
      head += `${k}: ${req.rawHeaders[i + 1]}\r\n`;
    }
    if (auth) head += `Proxy-Authorization: ${auth}\r\n`;
    head += '\r\n';
    u.write(head);
    req.pipe(u);
    u.pipe(res.socket);
  });
  u.on('error', () => res.destroy());
});

// HTTPS-туннель (метод CONNECT) — основной путь для google/GSC.
server.on('connect', (req, clientSocket, head) => {
  const u = net.connect(upPort, upHost, () => {
    let line = `CONNECT ${req.url} HTTP/1.1\r\nHost: ${req.url}\r\n`;
    if (auth) line += `Proxy-Authorization: ${auth}\r\n`;
    line += '\r\n';
    u.write(line);
  });

  let established = false;
  let buf = Buffer.alloc(0);
  u.on('data', (d) => {
    if (established) return;
    buf = Buffer.concat([buf, d]);
    const idx = buf.indexOf('\r\n\r\n');
    if (idx === -1) return;
    const header = buf.slice(0, idx).toString();
    if (/^HTTP\/\d\.\d 200/.test(header)) {
      established = true;
      clientSocket.write('HTTP/1.1 200 Connection Established\r\n\r\n');
      const rest = buf.slice(idx + 4);
      if (rest.length) clientSocket.write(rest);
      if (head && head.length) u.write(head);
      u.pipe(clientSocket);
      clientSocket.pipe(u);
    } else {
      clientSocket.end('HTTP/1.1 502 Bad Gateway\r\n\r\n');
      u.destroy();
    }
  });
  u.on('error', () => clientSocket.destroy());
  clientSocket.on('error', () => u.destroy());
});

server.on('clientError', (_e, socket) => socket.destroy());
server.listen(localPort, localHost, () => {
  console.log(`Мост запущен: http://${localHost}:${localPort}  ->  ${upHost}:${upPort}${auth ? ' (auth)' : ''}`);
});

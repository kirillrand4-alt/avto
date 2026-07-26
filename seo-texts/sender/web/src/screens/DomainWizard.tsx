import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import { useToast } from "../components/Toast";
import { Spinner, ErrorBox, Card } from "../components/ui";

type Provider = "yandex" | "mailru";

interface DnsRecord {
  type: string;
  name: string;
  value: string;
  note?: string;
}

export function DomainWizard() {
  const toast = useToast();
  const [domain, setDomain] = useState("mail2.parsercompressor.online");
  const [provider, setProvider] = useState<Provider>("yandex");
  const [boxCount, setBoxCount] = useState(2);
  const [baseName, setBaseName] = useState("s");
  const [dkimSelector, setDkimSelector] = useState("mail");
  const [checkDomain, setCheckDomain] = useState("");
  const [dnsReport, setDnsReport] = useState<any>(null);

  const checkMutation = useMutation({
    mutationFn: (d: string) => api.domainDns(d),
    onSuccess: (data) => {
      setDnsReport(data.dns);
      toast("success", "DNS проверен");
    },
    onError: (err: any) => {
      toast("error", err.message || "Ошибка проверки DNS");
    },
  });

  const getDnsRecords = (): DnsRecord[] => {
    const records: DnsRecord[] = [];
    if (provider === "yandex") {
      records.push({ type: "MX", name: "@", value: "10 mx.yandex.net." });
      records.push({ type: "TXT", name: "@", value: "v=spf1 redirect=_spf.yandex.net" });
      records.push({
        type: "TXT",
        name: `${dkimSelector}._domainkey`,
        value: "<значение из админки Яндекс360>",
        note: "Скопируйте DKIM-ключ из раздела «Домены» в админке Яндекс360",
      });
      records.push({
        type: "TXT",
        name: "_dmarc",
        value: `v=DMARC1; p=none; rua=mailto:dmarc@${domain}`,
      });
    } else {
      records.push({ type: "MX", name: "@", value: "10 emx.mail.ru." });
      records.push({ type: "TXT", name: "@", value: "v=spf1 redirect=_spf.mail.ru" });
      records.push({
        type: "TXT",
        name: `${dkimSelector}._domainkey`,
        value: "<значение из админки biz.mail.ru>",
        note: "Скопируйте DKIM-ключ из настроек домена в biz.mail.ru",
      });
      records.push({
        type: "TXT",
        name: "_dmarc",
        value: `v=DMARC1; p=none; rua=mailto:dmarc@${domain}`,
      });
    }
    return records;
  };

  const generateYaml = (): string => {
    const smtpHost = provider === "yandex" ? "smtp.yandex.ru:465" : "smtp.mail.ru:465";
    const imapHost = provider === "yandex" ? "imap.yandex.ru:993" : "imap.mail.ru:993";
    const envPrefix = domain.replace(/\./g, "_").toUpperCase();
    
    let yaml = "";
    for (let i = 1; i <= boxCount; i++) {
      yaml += `  - mailbox_id: "${baseName}${i}@${domain}"\n`;
      yaml += `    provider: "${provider}"\n`;
      yaml += `    smtp_host: "${smtpHost}"\n`;
      yaml += `    imap_host: "${imapHost}"\n`;
      yaml += `    password_env: "${envPrefix}_BOX${i}_PASSWORD"\n`;
      yaml += `    from_name: "Менеджер"\n`;
      yaml += `    is_warmup_node: true\n`;
      if (i < boxCount) yaml += "\n";
    }
    return yaml;
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text).then(() => {
      toast("success", `${label} скопирован`);
    });
  };

  const records = getDnsRecords();
  const yaml = generateYaml();

  return (
    <div>
      <div className="page-head">
        <h1>Мастер добавления домена рассылки</h1>
      </div>

      <div className="notice muted" style={{ marginBottom: "1.5rem", padding: "1rem", background: "#f8f9fa", borderRadius: "4px" }}>
        Мастер не меняет конфиг сервера: вставьте сниппет в sender.yaml, задайте env-пароли и перезапустите службу — домен появится в списке доменов.
      </div>

      <Card title="Параметры домена">
        <div style={{ display: "grid", gap: "1rem", maxWidth: "600px" }}>
          <label>
            Домен рассылки
            <input
              type="text"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder="mail2.parsercompressor.online"
            />
          </label>

          <label>
            Провайдер почтовых ящиков
            <select value={provider} onChange={(e) => setProvider(e.target.value as Provider)}>
              <option value="yandex">Яндекс360</option>
              <option value="mailru">Mail.ru для бизнеса</option>
            </select>
          </label>

          <label>
            Количество ящиков
            <input
              type="number"
              min="1"
              max="5"
              value={boxCount}
              onChange={(e) => setBoxCount(Math.min(5, Math.max(1, parseInt(e.target.value) || 1)))}
            />
            <span className="muted small">От 1 до 5</span>
          </label>

          <label>
            Базовое имя ящика
            <input
              type="text"
              value={baseName}
              onChange={(e) => setBaseName(e.target.value)}
              placeholder="s"
            />
            <span className="muted small">Пример: s → s1@{domain}, s2@{domain}, ...</span>
          </label>

          <label>
            DKIM-селектор
            <input
              type="text"
              value={dkimSelector}
              onChange={(e) => setDkimSelector(e.target.value)}
              placeholder="mail"
            />
            <span className="muted small">По умолчанию "mail" для Яндекс360</span>
          </label>
        </div>
      </Card>

      <Card title="Шаг 1. DNS-записи у регистратора">
        <p className="muted small" style={{ marginBottom: "1rem" }}>
          Добавьте следующие записи в настройках DNS вашего домена
        </p>
        <table className="data-table">
          <thead>
            <tr>
              <th>Тип</th>
              <th>Имя</th>
              <th>Значение</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {records.map((rec, i) => (
              <tr key={i}>
                <td><code>{rec.type}</code></td>
                <td><code>{rec.name}</code></td>
                <td>
                  <code style={{ fontSize: "0.85em" }}>{rec.value}</code>
                  {rec.note && <div className="muted small" style={{ marginTop: "0.25rem" }}>{rec.note}</div>}
                </td>
                <td>
                  <button
                    className="btn-sm"
                    onClick={() => copyToClipboard(rec.value, `${rec.type} запись`)}
                  >
                    Копировать
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Шаг 2. Сниппет для config/sender.yaml">
        <p className="muted small" style={{ marginBottom: "1rem" }}>
          Добавьте этот блок в секцию mailboxes:
        </p>
        <div style={{ position: "relative" }}>
          <pre style={{ background: "#f5f5f5", padding: "1rem", borderRadius: "4px", overflow: "auto" }}>
            {yaml}
          </pre>
          <button
            className="btn-sm"
            style={{ position: "absolute", top: "0.5rem", right: "0.5rem" }}
            onClick={() => copyToClipboard(yaml, "YAML")}
          >
            Скопировать YAML
          </button>
        </div>
        <p className="muted small" style={{ marginTop: "0.5rem" }}>
          ⚠️ Пароли приложений — ТОЛЬКО в env-переменных службы, не в конфиг и не в чат.
        </p>
      </Card>

      <Card title="Шаг 3. Проверка DNS">
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem", maxWidth: "600px" }}>
          <input
            type="text"
            value={checkDomain || domain}
            onChange={(e) => setCheckDomain(e.target.value)}
            placeholder="Домен для проверки"
            style={{ flex: 1 }}
          />
          <button
            onClick={() => checkMutation.mutate(checkDomain || domain)}
            disabled={checkMutation.isPending}
          >
            {checkMutation.isPending ? "Проверяю..." : "Проверить DNS"}
          </button>
        </div>

        {checkMutation.isPending && <Spinner />}
        {checkMutation.error && <ErrorBox error={checkMutation.error} />}
        
        {dnsReport && (
          <div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Проверка</th>
                  <th>Статус</th>
                  <th>Детали</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>MX записи</td>
                  <td>{dnsReport.mx_ok === true ? "✓" : dnsReport.mx_ok === false ? "✗" : "?"}</td>
                  <td className="muted small">—</td>
                </tr>
                <tr>
                  <td>SPF</td>
                  <td>{dnsReport.spf === true ? "✓" : dnsReport.spf === false ? "✗" : "?"}</td>
                  <td className="muted small">{dnsReport.spf_record || "—"}</td>
                </tr>
                <tr>
                  <td>DKIM</td>
                  <td>{dnsReport.dkim === true ? "✓" : dnsReport.dkim === false ? "✗" : "?"}</td>
                  <td className="muted small">—</td>
                </tr>
                <tr>
                  <td>DMARC</td>
                  <td>{dnsReport.dmarc === true ? "✓" : dnsReport.dmarc === false ? "✗" : "?"}</td>
                  <td className="muted small">{dnsReport.dmarc_policy || "—"}</td>
                </tr>
              </tbody>
            </table>

            {dnsReport.issues && dnsReport.issues.length > 0 && (
              <div style={{ marginTop: "1rem" }}>
                <h4>Проблемы:</h4>
                <ul className="muted">
                  {dnsReport.issues.map((issue: string, i: number) => (
                    <li key={i}>{issue}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}

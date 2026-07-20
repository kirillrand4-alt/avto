// Форматтеры и PII-маскирование (data-minimization по роли — SITE-DESIGN p8).

/** Маска email: u***@dom.ru (комплаенс-экраны, лента для продажника до «Взять»). */
export function maskEmail(email: string | null | undefined): string {
  if (!email) return "—";
  const [local, domain] = email.split("@");
  if (!domain) return "***";
  const head = local.slice(0, 1);
  return `${head}${"*".repeat(Math.max(2, local.length - 1))}@${domain}`;
}

/** Маска телефона: +7·····34 (последние 2 цифры). */
export function maskPhone(phone: string | null | undefined): string {
  if (!phone) return "—";
  const digits = phone.replace(/\D/g, "");
  if (digits.length < 2) return "***";
  return `+7·····${digits.slice(-2)}`;
}

/** Нормализация телефона в +7XXXXXXXXXX (кнопка «Нормализовать» на карточке). */
export function normalizePhone(phone: string | null | undefined): string | null {
  if (!phone) return null;
  const d = phone.replace(/\D/g, "");
  const ten = d.length >= 10 ? d.slice(-10) : null;
  return ten ? `+7${ten}` : null;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ru-RU", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

/** Сколько времени прошло — для колонки «без движения» (жёлтый >2ч, красный >4ч). */
export function ageHours(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  return (Date.now() - t) / 3_600_000;
}

export function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${v.toFixed(2)}%`;
}

/** Значок классификации ответа. */
export function replyBadge(kind: string | null): { icon: string; label: string; cls: string } {
  switch (kind) {
    case "hot": return { icon: "🔥", label: "горячий", cls: "hot" };
    case "interested": return { icon: "⭐", label: "интерес", cls: "interested" };
    case "auto_reply": return { icon: "🤖", label: "автоответ", cls: "muted" };
    case "not_interested": return { icon: "❌", label: "отказ", cls: "muted" };
    case "unsub_request": return { icon: "🚫", label: "отписка", cls: "danger" };
    default: return { icon: "•", label: kind || "—", cls: "muted" };
  }
}

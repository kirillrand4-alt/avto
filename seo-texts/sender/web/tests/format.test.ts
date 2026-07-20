import { describe, it, expect } from "vitest";
import { maskEmail, maskPhone, normalizePhone, replyBadge, ageHours } from "../src/lib/format";

describe("PII-маскирование (data-minimization ФЗ-152 / p8)", () => {
  it("маскирует email до первой буквы", () => {
    expect(maskEmail("director@zavod.ru")).toBe("d*******@zavod.ru");
    expect(maskEmail(null)).toBe("—");
    expect(maskEmail("a@b.ru")).toBe("a**@b.ru");
  });
  it("маскирует телефон до последних 2 цифр", () => {
    expect(maskPhone("+7 495 123 45 67")).toBe("+7·····67");
    expect(maskPhone(null)).toBe("—");
  });
});

describe("нормализация телефона", () => {
  it("приводит к +7XXXXXXXXXX", () => {
    expect(normalizePhone("8 (495) 123-45-67")).toBe("+74951234567");
    expect(normalizePhone("+7 495 1234567")).toBe("+74951234567");
    expect(normalizePhone("123")).toBeNull();
    expect(normalizePhone(null)).toBeNull();
  });
});

describe("бейдж классификации", () => {
  it("hot помечается красным", () => {
    expect(replyBadge("hot").cls).toBe("hot");
    expect(replyBadge("unsub_request").cls).toBe("danger");
    expect(replyBadge(null).label).toBe("—");
  });
});

describe("возраст лида", () => {
  it("считает часы с created_at", () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 3600_000).toISOString();
    const h = ageHours(twoHoursAgo);
    expect(h).toBeGreaterThan(1.9);
    expect(h).toBeLessThan(2.1);
    expect(ageHours(null)).toBeNull();
  });
});

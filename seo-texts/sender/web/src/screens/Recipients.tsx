import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useToast } from "../components/Toast";
import { Spinner, ErrorBox, Empty, Card } from "../components/ui";

export function Recipients() {
  const [segment, setSegment] = useState("");
  const [validStatus, setValidStatus] = useState("");
  const [q, setQ] = useState("");
  const [sortPxr, setSortPxr] = useState<"none" | "desc" | "asc">("none");

  const [file, setFile] = useState<File | null>(null);
  const [uploadSegment, setUploadSegment] = useState("");
  const [importId, setImportId] = useState<string | null>(null);
  const [importProgress, setImportProgress] = useState<{ total_rows: number; imported: number; skipped_invalid: number } | null>(null);

  const queryClient = useQueryClient();
  const toast = useToast();

  const recipients = useQuery({
    queryKey: ["recipients", segment, validStatus, q],
    queryFn: () => api.recipients({
      segment: segment || undefined,
      valid_status: validStatus || undefined,
      // бэкенд ищет по domain_like ИЛИ inn: цифры трактуем как ИНН
      inn: /^\d{5,}$/.test(q.trim()) ? q.trim() : undefined,
      domain_like: q.trim() && !/^\d{5,}$/.test(q.trim()) ? q.trim() : undefined,
      limit: 200,
    }),
  });

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Файл не выбран");
      return api.importRecipients(file, uploadSegment);
    },
    onSuccess: (data) => {
      setImportId(data.import_id);
      toast("success", "Импорт запущен");
    },
    onError: (err: any) => {
      toast("error", `Ошибка импорта: ${err.message}`);
    },
  });

  useEffect(() => {
    if (!importId) return;
    const interval = setInterval(async () => {
      try {
        const status = await api.importStatus(importId);
        setImportProgress({ total_rows: status.total_rows, imported: status.imported, skipped_invalid: status.skipped_invalid });
        if (status.done) {
          clearInterval(interval);
          if (status.error) {
            toast("error", `Импорт завершён с ошибкой: ${status.error}`);
          } else {
            toast("success", `Импорт завершён: ${status.imported} записей`);
            queryClient.invalidateQueries({ queryKey: ["recipients"] });
          }
          setImportId(null);
          setFile(null);
          setUploadSegment("");
          setImportProgress(null);
        }
      } catch (err: any) {
        clearInterval(interval);
        toast("error", `Ошибка проверки статуса: ${err.message}`);
        setImportId(null);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [importId, queryClient, toast]);

  const rows = recipients.data?.recipients ?? [];
  const sortedRows = sortPxr === "none" ? rows : [...rows].sort((a, b) => {
    const va = a.pxr ?? -Infinity;
    const vb = b.pxr ?? -Infinity;
    return sortPxr === "desc" ? vb - va : va - vb;
  });

  const cycleSortPxr = () => {
    setSortPxr((s) => s === "none" ? "desc" : s === "desc" ? "asc" : "none");
  };

  return (
    <div>
      <div className="page-head">
        <h1>База получателей</h1>
        <div className="muted">{recipients.data?.count.total ?? 0} шт.</div>
      </div>

      <div className="filterbar">
        <label>
          Сегмент
          <input list="segments" value={segment} onChange={(e) => setSegment(e.target.value)} placeholder="все" />
          <datalist id="segments">
            <option value="кц" />
            <option value="meyer" />
          </datalist>
        </label>
        <label>
          Валидность
          <select value={validStatus} onChange={(e) => setValidStatus(e.target.value)}>
            <option value="">все</option>
            <option value="valid">valid</option>
            <option value="invalid">invalid</option>
            <option value="unknown">unknown</option>
          </select>
        </label>
        <label>
          Поиск (домен/ИНН)
          <input type="text" value={q} onChange={(e) => setQ(e.target.value)} placeholder="example.com, 7701234567" />
        </label>
      </div>

      {recipients.isLoading ? <Spinner /> : recipients.error ? <ErrorBox error={recipients.error} /> :
        sortedRows.length === 0 ? <Empty /> : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Компания (ИНН)</th>
                <th>Сегмент</th>
                <th>Провайдер</th>
                <th>Валидность</th>
                <th>Балл</th>
                <th onClick={cycleSortPxr} style={{ cursor: "pointer", userSelect: "none" }}>
                  PxR {sortPxr === "desc" ? "↓" : sortPxr === "asc" ? "↑" : ""}
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((r) => (
                <tr key={r.id}>
                  <td>{r.email}</td>
                  <td>
                    {r.company_name || "—"}
                    {r.inn && <span className="muted"> ({r.inn})</span>}
                  </td>
                  <td>{r.segment ?? "—"}</td>
                  <td>{r.mx_provider ?? "—"}</td>
                  <td>{r.valid_status}</td>
                  <td>{r.priority_max ?? "—"}</td>
                  <td>{r.pxr != null ? Math.round(r.pxr) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

      <Card title="Загрузить CSV">
        <div className="field">
          <label>
            Файл .csv
            <input type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} disabled={!!importId} />
          </label>
        </div>
        <div className="field">
          <label>
            Сегмент для загрузки
            <input
              list="segments-upload"
              value={uploadSegment}
              onChange={(e) => setUploadSegment(e.target.value)}
              placeholder="кц / meyer"
              disabled={!!importId}
            />
            <datalist id="segments-upload">
              <option value="кц" />
              <option value="meyer" />
            </datalist>
          </label>
          {uploadSegment === "" && <p className="danger small">Сегмент пустой — колонка сегмента должна быть в CSV</p>}
        </div>
        <button className="btn" onClick={() => uploadMutation.mutate()} disabled={!file || !!importId}>
          Импортировать
        </button>
        {importId && importProgress && (
          <p className="muted small">
            Обработано {importProgress.total_rows} строк, импортировано {importProgress.imported}, пропущено {importProgress.skipped_invalid}
          </p>
        )}
        <p className="muted small">
          Импортёр сам детектит кодировку/разделитель/колонки (email, инн, сегмент, баллы приоритета из базы обзвона). Дедуп по email.
        </p>
      </Card>
    </div>
  );
}

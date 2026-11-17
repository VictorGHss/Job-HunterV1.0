export function formatLocalDate(iso: string | null | undefined): string {
  if (!iso) return "Não informada";
  try {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso;
    return dt.toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

export function formatLocalDateTime(iso: string | null | undefined): string {
  if (!iso) return "Não informada";
  try {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso;
    return dt.toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function formatLocalTime(iso: string | null | undefined): string {
  if (!iso) return "--:--";
  try {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso;
    return dt.toLocaleTimeString("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function toLocalDateTimeInputValue(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return "";
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(
      dt.getHours()
    )}:${pad(dt.getMinutes())}`;
  } catch {
    return "";
  }
}

export function fromLocalDateTimeInputValue(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
}

export function getLocalDayKey(iso: string): string {
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso.slice(0, 10);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
}

export function formatLocalDayHeading(dayKey: string): string {
  const [y, m, d] = dayKey.split("-").map(Number);
  if (!y || !m || !d) return dayKey;
  const dt = new Date(y, m - 1, d);
  return dt.toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
  });
}

export function isSameLocalToday(iso: string): boolean {
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return false;
  return getLocalDayKey(iso) === getLocalDayKey(new Date().toISOString());
}

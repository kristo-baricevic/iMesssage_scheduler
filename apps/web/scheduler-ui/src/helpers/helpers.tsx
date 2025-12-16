export function formatUSPhone(value: string) {
  const digits = value.replace(/\D/g, "");

  const ten =
    digits.length === 10
      ? digits
      : digits.length === 11 && digits[0] === "1"
      ? digits.slice(1)
      : "";

  if (ten.length !== 10) return value;

  const a = ten.slice(0, 3);
  const b = ten.slice(3, 6);
  const c = ten.slice(6);
  return `+1 (${a}) ${b}-${c}`;
}

export function formatDate(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(d);
}

export function pillClasses(status: string) {
  const base =
    "inline-block rounded-full border bg-white px-2 py-[3px] text-xs text-slate-800";

  switch (status) {
    case "QUEUED":
      return `${base} border-slate-400`;
    case "ACCEPTED":
      return `${base} border-sky-600`;
    case "SENT":
    case "DELIVERED":
    case "RECEIVED":
      return `${base} border-green-600`;
    case "FAILED":
      return `${base} border-red-600`;
    case "CANCELED":
      return `${base} border-orange-600`;
    default:
      return `${base} border-slate-300`;
  }
}

export function toIsoFromDatetimeLocal(value: string) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

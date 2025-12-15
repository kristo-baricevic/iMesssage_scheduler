import { useEffect, useMemo, useState, type FormEvent } from "react";
import { cancelMessage, createMessage, getMessage, listMessages } from "./api";
import type { ScheduledMessage, MessageStatus } from "./api";
import { IconSend, IconPhone, IconClock } from "@tabler/icons-react";

const STATUSES: (MessageStatus | "")[] = [
  "",
  "QUEUED",
  "ACCEPTED",
  "SENT",
  "DELIVERED",
  "RECEIVED",
  "FAILED",
  "CANCELED",
];

function toIsoFromDatetimeLocal(value: string) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

function formatUSPhone(value: string) {
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

function formatDate(iso: string) {
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

function pillClasses(status: string) {
  const base =
    "inline-block rounded-full border bg-[#0b1220] px-2 py-[3px] text-xs";

  switch (status) {
    case "QUEUED":
      return `${base} border-slate-600`;
    case "ACCEPTED":
      return `${base} border-sky-600`;
    case "SENT":
    case "DELIVERED":
    case "RECEIVED":
      return `${base} border-green-500`;
    case "FAILED":
      return `${base} border-red-500`;
    case "CANCELED":
      return `${base} border-orange-500`;
    default:
      return `${base} border-slate-700`;
  }
}

function btnBase(disabled: boolean) {
  return [
    "rounded-xl border px-3 py-2 text-slate-200",
    "bg-slate-900 border-slate-700",
    "cursor-pointer",
    disabled ? "opacity-60 cursor-not-allowed" : "hover:bg-slate-800",
  ].join(" ");
}

export default function App() {
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [messages, setMessages] = useState<ScheduledMessage[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<ScheduledMessage | null>(null);

  const [filterStatus, setFilterStatus] = useState<string>("");
  const [filterPhoneNumber, setFilterPhoneNumber] = useState<string>("");
  const [filterFrom, setFilterFrom] = useState<string>("");
  const [filterTo, setFilterTo] = useState<string>("");

  const [phoneNumber, setPhoneNumber] = useState<string>("");
  const [body, setBody] = useState<string>("");
  const [scheduledForLocal, setScheduledForLocal] = useState(() => {
    const d = new Date(Date.now() + 60_000);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(
      d.getDate()
    )}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  });

  const listParams = useMemo(
    () => ({
      status: filterStatus || undefined,
      to_handle: filterPhoneNumber || undefined,
      scheduled_from: filterFrom || undefined,
      scheduled_to: filterTo || undefined,
    }),
    [filterStatus, filterPhoneNumber, filterFrom, filterTo]
  );

  async function refresh() {
    setErr(null);
    setLoading(true);
    try {
      const data = await listMessages(listParams);
      setMessages(data);
      if (selectedId) {
        const found = data.find((m) => m.id === selectedId);
        if (!found) {
          setSelectedId(null);
          setSelected(null);
        }
      }
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function loadSelected(id: string) {
    setErr(null);
    setSelectedId(id);
    try {
      const full = await getMessage(id);
      setSelected(full);
    } catch (e: any) {
      setErr(e?.message || String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setErr(null);

    const iso = toIsoFromDatetimeLocal(scheduledForLocal);
    if (!iso) {
      setErr("Scheduled time is invalid");
      return;
    }

    setLoading(true);
    try {
      await createMessage({
        to_handle: phoneNumber?.trim() as string,
        body,
        scheduled_for: iso,
      });
      await refresh();
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function onCancel(id: string) {
    setErr(null);
    setLoading(true);
    try {
      await cancelMessage(id);
      await refresh();
      if (selectedId === id) {
        const full = await getMessage(id);
        setSelected(full);
      }
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  const inputBase =
    "w-full rounded-[10px] border border-slate-300 bg-slate-100 px-2.5 py-2 text-slate-900 outline-none focus:border-slate-600 placeholder:text-slate-500";

  const labelSpan = "mb-1.5 block text-xs text-slate-800";
  const card =
    "rounded-xl border border-slate-200 bg-slate-100 text-slate-800 p-3.5 shadow-xl";
  const mono = "font-mono text-xs text-slate-800";

  return (
    <div className="min-h-screen bg-blue-100 text-slate-200">
      <div className="mx-auto max-w-300 p-6 font-sans">
        <header className="mb-4.5 flex items-center justify-between gap-4">
          <div>
            <h1 className="m-0 text-[22px] text-slate-800 font-semibold">
              iMessage Scheduler
            </h1>
            <div className="mt-1 text-[13px] text-slate-800">
              Create and manage scheduled messages
            </div>
          </div>

          <button
            className={btnBase(loading)}
            onClick={refresh}
            disabled={loading}
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </header>

        {err ? (
          <div className="mb-3.5 rounded-xl border border-red-900 bg-[#2b0b10] px-3 py-2.5 text-red-200">
            {err}
          </div>
        ) : null}

        <div className="grid gap-4 xl:grid-cols-[1fr_1fr_420px]">
          <section className={card}>
            <form onSubmit={onCreate} className="space-y-2.5">
              <label className="block">
                <span className={labelSpan}>Phone Number</span>
                <input
                  className={inputBase}
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                  onBlur={() => {
                    if (phoneNumber.trim())
                      setPhoneNumber(formatUSPhone(phoneNumber));
                  }}
                  placeholder="Enter Phone Number"
                  required
                />
              </label>

              <label className="block">
                <span className={labelSpan}>Message</span>
                <textarea
                  className={`${inputBase} resize-y`}
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  placeholder="Enter message"
                  rows={4}
                  required
                />
              </label>

              <label className="block">
                <span className={labelSpan}>Scheduled for (local)</span>
                <input
                  className={inputBase}
                  type="datetime-local"
                  value={scheduledForLocal}
                  onChange={(e) => setScheduledForLocal(e.target.value)}
                  required
                />
                <div className="mt-1.5 text-xs text-slate-900">
                  Converted to UTC when sent to the API.
                </div>
              </label>

              <button
                className={[
                  "flex flex-row items-center justify-center rounded-xl border px-3 py-2 text-slate-50 w-full",
                  "border-blue-900 bg-linear-to-r from-blue-600 to-indigo-600",
                  loading
                    ? "opacity-60 cursor-not-allowed"
                    : "hover:from-blue-500 hover:to-indigo-500 cursor-pointer",
                ].join(" ")}
                type="submit"
                disabled={loading}
              >
                <IconSend className="mr-2" />
                Schedule Message
              </button>
            </form>
          </section>

          {/* <section className={card}>
            <h2 className="mb-2.5 text-slate-800 font-semibold">Filters</h2>

            <div className="space-y-2.5">
              <label className="block">
                <span className={labelSpan}>Status</span>
                <select
                  className={inputBase}
                  value={filterStatus}
                  onChange={(e) => setFilterStatus(e.target.value)}
                >
                  {STATUSES.map((s) => (
                    <option key={s || "any"} value={s}>
                      {s || "(any)"}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block">
                <span className={labelSpan}>To handle contains</span>
                <input
                  className={inputBase}
                  value={filterPhoneNumber}
                  onChange={(e) => setFilterPhoneNumber(e.target.value)}
                  placeholder="+1555"
                />
              </label>

              <label className="block">
                <span className={labelSpan}>Scheduled from (ISO UTC)</span>
                <input
                  className={inputBase}
                  value={filterFrom}
                  onChange={(e) => setFilterFrom(e.target.value)}
                  placeholder="2025-12-14T00:00:00Z"
                />
              </label>

              <label className="block">
                <span className={labelSpan}>Scheduled to (ISO UTC)</span>
                <input
                  className={inputBase}
                  value={filterTo}
                  onChange={(e) => setFilterTo(e.target.value)}
                  placeholder="2025-12-15T00:00:00Z"
                />
              </label>
            </div>

            <div className="mt-2.5 flex gap-2.5">
              <button
                className={btnBase(loading)}
                onClick={refresh}
                disabled={loading}
                type="button"
              >
                Apply
              </button>

              <button
                className={btnBase(loading)}
                onClick={() => {
                  setFilterStatus("");
                  setFilterPhoneNumber("");
                  setFilterFrom("");
                  setFilterTo("");
                  setTimeout(refresh, 0);
                }}
                disabled={loading}
                type="button"
              >
                Clear
              </button>
            </div>
          </section> */}

          <section className="xl:col-span-2">
            <div className="flex flex-row items-center justify-between">
              <h2 className="mb-2.5 font-semibold text-slate-800">
                <span className="text-blue-600">•</span> Scheduled Messages
              </h2>
              <div className="text-slate-400">({messages.length})</div>
            </div>

            {messages.length === 0 ? (
              <div className={`${card} text-slate-500`}>No messages</div>
            ) : (
              <div className="space-y-3">
                {messages.map((m) => {
                  const isSelected = m.id === selectedId;

                  return (
                    <div
                      key={m.id}
                      onClick={() => loadSelected(m.id)}
                      className={[
                        card,
                        "cursor-pointer transition-colors",
                        isSelected
                          ? "ring-2 ring-blue-400"
                          : "hover:bg-slate-50",
                      ].join(" ")}
                    >
                      <div className="flex flex-col gap-3 min-h-27.5">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-start gap-2">
                            <div className="bg-blue-100 text-blue-500 p-1 rounded-md">
                              <IconPhone />
                            </div>

                            <div className="min-w-0">
                              <div className="text-sm font-semibold text-slate-900">
                                {formatUSPhone(m.to_handle)}
                              </div>

                              <div className="mt-2 flex flex-col gap-2 text-xs text-slate-700">
                                <div className={mono}>{m.body}</div>

                                <div className="flex items-center font-mono text-xs text-slate-400">
                                  <IconClock className="mr-2" />
                                  {formatDate(m.scheduled_for)}
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>

                        <div className="mt-auto flex justify-end">
                          <button
                            className={[
                              "rounded-xl border px-3 py-2 text-xs",
                              "border-slate-300 bg-white text-slate-900",
                              loading
                                ? "opacity-60 cursor-not-allowed"
                                : "hover:bg-slate-100 cursor-pointer",
                            ].join(" ")}
                            onClick={(e) => {
                              e.stopPropagation();
                              onCancel(m.id);
                            }}
                            disabled={loading}
                            type="button"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* <section className={card}>
            <h2 className="mb-2.5 text-base font-semibold">Selected</h2>

            {!selected ? (
              <div className="text-slate-400">
                Click a message row to see details.
              </div>
            ) : (
              <div>
                <div className="mb-2.5 grid grid-cols-[80px_1fr] gap-2">
                  <div className="text-xs text-slate-400">ID</div>
                  <div className={mono}>{selected.id}</div>
                </div>

                <div className="mb-2.5 grid grid-cols-[80px_1fr] gap-2">
                  <div className="text-xs text-slate-400">To</div>
                  <div>{selected.to_handle}</div>
                </div>

                <div className="mb-2.5 grid grid-cols-[80px_1fr] gap-2">
                  <div className="text-xs text-slate-400">Status</div>
                  <div>{selected.status}</div>
                </div>

                <div className="mb-2.5 grid grid-cols-[80px_1fr] gap-2">
                  <div className="text-xs text-slate-400">Body</div>
                  <div className={mono}>{selected.body}</div>
                </div>

                <h3 className="mb-2 mt-3.5 text-sm font-semibold text-slate-200">
                  Events
                </h3>

                <div className="flex flex-col gap-2.5">
                  {selected.events?.length ? (
                    selected.events.map((ev) => (
                      <div
                        key={ev.id}
                        className="rounded-xl border border-slate-800 bg-slate-950 p-2.5"
                      >
                        <div className="mt-0 flex gap-2.5">
                          <span className={pillClasses(ev.status)}>
                            {ev.status}
                          </span>
                          <span className="font-mono text-xs text-slate-400">
                            {ev.timestamp}
                          </span>
                        </div>

                        <pre className="mt-2 overflow-auto rounded-[10px] border border-slate-800 bg-[#0b1220] p-2.5 text-xs">
                          {JSON.stringify(ev.detail, null, 2)}
                        </pre>
                      </div>
                    ))
                  ) : (
                    <div className="text-slate-400">No events</div>
                  )}
                </div>
              </div>
            )}
          </section> */}
        </div>
      </div>
    </div>
  );
}

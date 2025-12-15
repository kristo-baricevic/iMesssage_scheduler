export type MessageStatus =
  | "QUEUED"
  | "ACCEPTED"
  | "SENT"
  | "DELIVERED"
  | "RECEIVED"
  | "FAILED"
  | "CANCELED";

export type MessageEvent = {
  id: number;
  status: MessageStatus;
  timestamp: string;
  detail: any;
};

export type ScheduledMessage = {
  id: string;
  to_handle: string;
  body: string;
  scheduled_for: string;
  status: MessageStatus;
  created_at: string;
  updated_at: string;
  claimed_at: string | null;
  claimed_by: string | null;
  attempt_count: number;
  last_error: string | null;
  events: MessageEvent[];
};

async function readJsonOrText(res: Response) {
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return res.json();
  return res.text();
}

export async function listMessages(params: {
  status?: string;
  to_handle?: string;
  scheduled_from?: string;
  scheduled_to?: string;
}): Promise<ScheduledMessage[]> {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.to_handle) qs.set("to_handle", params.to_handle);
  if (params.scheduled_from) qs.set("scheduled_from", params.scheduled_from);
  if (params.scheduled_to) qs.set("scheduled_to", params.scheduled_to);

  const url = `/api/messages/${qs.toString() ? `?${qs.toString()}` : ""}`;
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`List failed: ${res.status} ${await readJsonOrText(res)}`);

  const data = await res.json();
  return Array.isArray(data) ? data : data.results || [];
}

export async function getMessage(id: string): Promise<ScheduledMessage> {
  const res = await fetch(`/api/messages/${id}/`, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`Get failed: ${res.status} ${await readJsonOrText(res)}`);
  return res.json();
}

export async function createMessage(payload: {
  to_handle: string;
  body: string;
  scheduled_for: string;
}): Promise<ScheduledMessage | null> {
  const res = await fetch(`/api/messages/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) throw new Error(`Create failed: ${res.status} ${await readJsonOrText(res)}`);
  return res.status === 204 ? null : res.json();
}

export async function cancelMessage(id: string): Promise<ScheduledMessage> {
  const res = await fetch(`/api/messages/${id}/cancel/`, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`Cancel failed: ${res.status} ${await readJsonOrText(res)}`);
  return res.json();
}

export async function fetchMessageStatusStats() {
    const res = await fetch("/api/stats/messages-by-status/");
    if (!res.ok) throw new Error("Failed to load stats");
    return res.json();
  }
  
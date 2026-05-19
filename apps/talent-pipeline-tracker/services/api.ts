import type {
  ErrorResponse,
  GetRecordsParams,
  NoteCreate,
  NoteOut,
  NotesResponse,
  RecordCreate,
  RecordOut,
  RecordPatch,
  RecordsResponse,
} from "@/types/candidates";

const API_BASE_URL = "https://playground.4geeks.com/tracker/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly payload?: ErrorResponse | unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function buildUrl(path: string, query?: Record<string, string | number | undefined>): string {
  const url = new URL(`${API_BASE_URL}${path}`);

  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
  }

  return url.toString();
}

async function request<TResponse, TBody = unknown>(
  path: string,
  init?: {
    method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
    query?: Record<string, string | number | undefined>;
    body?: TBody;
  },
): Promise<TResponse> {
  const response = await fetch(buildUrl(path, init?.query), {
    method: init?.method ?? "GET",
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
    },
    body: init?.body ? JSON.stringify(init.body) : undefined,
  });

  if (response.status === 204) {
    return undefined as TResponse;
  }

  const raw = (await response.json().catch(() => null)) as unknown;

  if (!response.ok) {
    const payload = raw as ErrorResponse | unknown;
    const message =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? String((payload as ErrorResponse).detail)
        : `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status, payload);
  }

  return raw as TResponse;
}

export async function getRecords(params?: GetRecordsParams): Promise<RecordsResponse> {
  return request<RecordsResponse>("/records", { method: "GET", query: params });
}

export async function getRecordById(id: string): Promise<RecordOut> {
  return request<RecordOut>(`/records/${id}`, { method: "GET" });
}

export async function createRecord(payload: RecordCreate): Promise<RecordOut> {
  return request<RecordOut, RecordCreate>("/records", {
    method: "POST",
    body: payload,
  });
}

export async function replaceRecord(id: string, payload: RecordCreate): Promise<RecordOut> {
  return request<RecordOut, RecordCreate>(`/records/${id}`, {
    method: "PUT",
    body: payload,
  });
}

export async function patchRecord(id: string, payload: RecordPatch): Promise<RecordOut> {
  return request<RecordOut, RecordPatch>(`/records/${id}`, {
    method: "PATCH",
    body: payload,
  });
}

export async function getRecordNotes(id: string): Promise<NotesResponse> {
  return request<NotesResponse>(`/records/${id}/notes`, { method: "GET" });
}

export async function createRecordNote(id: string, payload: NoteCreate): Promise<NoteOut> {
  return request<NoteOut, NoteCreate>(`/records/${id}/notes`, {
    method: "POST",
    body: payload,
  });
}

export async function deleteRecordNote(id: string, noteId: string): Promise<void> {
  return request<void>(`/records/${id}/notes/${noteId}`, {
    method: "DELETE",
  });
}

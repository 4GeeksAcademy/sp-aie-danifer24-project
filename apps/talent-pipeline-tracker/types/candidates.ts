export type RecordStatus = "received" | "in_progress" | "selected" | "discarded" | (string & {});

export type RecordStage =
  | "pending"
  | "review"
  | "personal_interview"
  | "technical_interview"
  | "offer_presented"
  | (string & {});

export interface RecordCreate {
  full_name: string;
  email: string;
  phone: string;
  position: string;
  linkedin_url?: string | null;
  cv_url?: string | null;
  experience_years: number;
}

export interface RecordPatch {
  status?: string | null;
  stage?: string | null;
}

export interface RecordOut {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  position: string;
  linkedin_url: string | null;
  cv_url: string | null;
  status: RecordStatus;
  stage: RecordStage;
  experience_years: number;
  notes_count: number;
  applied_at: string;
  updated_at: string;
}

export interface NoteCreate {
  title: string;
  content: string;
}

export interface NoteOut {
  id: string;
  title: string;
  content: string;
}

export interface ErrorResponse {
  detail: string;
  status: number;
  title: string;
  type: string;
}

export interface HTTPValidationError {
  errors: Array<string | number>;
  detail: string;
  status: number;
  title: string;
  type: string;
}

export interface GetRecordsParams {
  status?: RecordStatus;
  stage?: RecordStage;
  search?: string;
  page?: number;
  limit?: number;
}

export interface PaginatedResponse<T> {
  data: T[];
  page?: number;
  limit?: number;
  total?: number;
  pages?: number;
}

export type RecordsResponse = RecordOut[] | PaginatedResponse<RecordOut>;
export type NotesResponse = NoteOut[] | PaginatedResponse<NoteOut>;

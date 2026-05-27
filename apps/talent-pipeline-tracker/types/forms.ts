export type SubmitState = "idle" | "loading" | "success" | "error";

export type ControlState = "idle" | "loading" | "success" | "error";

export interface CreateFormData {
  full_name: string;
  email: string;
  phone: string;
  position: string;
  linkedin_url: string;
  cv_url: string;
  experience_years: string;
}

export type CreateFormErrors = Partial<Record<keyof CreateFormData, string>>;

export interface EditFormData {
  full_name: string;
  email: string;
  phone: string;
  position: string;
  linkedin_url: string;
  cv_url: string;
  experience_years: string;
}

export type EditFormErrors = Partial<Record<keyof EditFormData, string>>;

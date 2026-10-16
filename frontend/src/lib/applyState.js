// Shared constants and starting values for the applicant form.
// Copied from the old static/app.js so field names and defaults stay identical.

export const STEPS = ["History", "About you", "The loan", "Result"];

export const COUNT_KEYS = ["on_time", "slight", "late", "very_late"];

export const initialApplication = () => ({
  mode: null,            // "manual" | "first" (the applicant chooses, a lookup is staff-only)
  ref: null,             // reference number returned after a successful submit
  historyVersion: 0,     // bumped to force the number boxes to refresh
  // No pre-filled personal details: each signed-in applicant enters their own,
  // so accounts can never end up sharing one sample applicant's profile.
  history: {
    on_time: 0, slight: 0, late: 0, very_late: 0,
    avg_late: 0, max_late: 0, avg_amount: 5000, avg_term: 30,
  },
  profile: { dob: "", employment: "", bank: "", account: "" },
  amount: 10000,
  term: 30,
});

// The exact body the old app sent to /api/score and /api/submit.
export const buildPayload = (a) => ({
  mode: a.mode,
  history: a.mode === "first" ? null : a.history,
  ...a.profile,
  amount: a.amount,
  term: a.term,
});

// Currency: the Kenyan Shilling. The model was trained on Nigerian source data,
// so the numeric amounts are unchanged; only the display symbol is Kenyan.
// One shared helper is used everywhere money is shown (see README "Currency").
export const CURRENCY_CODE = "KES";
export const CURRENCY_SYMBOL = "KSh";
export const fmt = (n) => Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
export const ksh = (n) => `${CURRENCY_SYMBOL} ${fmt(n)}`;

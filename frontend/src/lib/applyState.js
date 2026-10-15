// Shared constants and starting values for the applicant form.
// Copied from the old static/app.js so field names and defaults stay identical.

export const STEPS = ["History", "About you", "The loan", "Result"];

export const COUNT_KEYS = ["on_time", "slight", "late", "very_late"];

export const initialApplication = () => ({
  mode: null,            // "lookup" | "manual" | "first"
  found: false,          // true after a successful record lookup
  cid: "",               // customer ID that was found
  historyVersion: 0,     // bumped after a lookup so the number boxes refresh
  ref: null,             // reference number returned after a successful submit
  history: {
    on_time: 3, slight: 0, late: 0, very_late: 0,
    avg_late: 0, max_late: 0, avg_amount: 15000, avg_term: 30,
  },
  profile: { dob: "1992-01-01", employment: "Permanent", bank: "Access Bank", account: "Savings" },
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

export const fmt = (n) => Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
export const naira = (n) => "₦" + fmt(n);

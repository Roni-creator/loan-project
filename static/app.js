"use strict";
/* Applicant portal front end. Talks to the Flask API; all scoring happens server-side.
   DOM is built with h() / textContent (never innerHTML) so server strings can't inject markup. */

const $ = (s, el = document) => el.querySelector(s);
const fmt = n => Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
const ksh = n => "KSh " + fmt(n);

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null) el.append(kid.nodeType ? kid : document.createTextNode(kid));
  return el;
}

const STEPS = ["History", "About you", "The loan", "Result"];
const OUTCOME = { likely: "Looks good", review: "Closer look", refer: "Review" };
const S = {
  meta: null, step: 1, mode: null, found: false,
  history: { on_time: 3, slight: 0, late: 0, very_late: 0, avg_late: 0, max_late: 0, avg_amount: 15000, avg_term: 30 },
  profile: { dob: "1992-01-01", employment: "Permanent", bank: "Access Bank", account: "Savings" },
  amount: 10000, term: 30, result: null, ref: null,
};

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Something went wrong. Please try again.");
  return data;
}

const payload = () => ({
  mode: S.mode, history: S.mode === "first" ? null : S.history,
  ...S.profile, amount: S.amount, term: S.term,
});

function go(step) { S.step = step; render(); window.scrollTo({ top: 0, behavior: "smooth" }); }

function renderSteps() {
  const ol = $("#steps"); ol.replaceChildren(...STEPS.map((t, i) =>
    h("li", { class: i + 1 === S.step ? "on" : i + 1 < S.step ? "done" : "" }, `${i + 1}. ${t}`)));
}

function render() {
  renderSteps();
  const v = $("#view"); v.replaceChildren();
  [null, step1, step2, step3, step4][S.step](v);
}

/* ---------- inputs bound to state ---------- */
function numField(label, key, o = {}) {
  return h("label", { class: "f" }, label, o.hint ? h("small", {}, o.hint) : null,
    h("input", { type: "number", min: o.min, max: o.max, step: o.step ?? 1, value: S.history[key],
      onchange: e => { S.history[key] = e.target.value === "" ? 0 : Number(e.target.value); } }));
}
function selectField(label, key, options) {
  return h("label", { class: "f" }, label,
    h("select", { onchange: e => { S.profile[key] = e.target.value; } },
      options.map(o => h("option", { value: o, selected: S.profile[key] === o }, o))));
}

/* ---------- step 1: history ---------- */
function historyGrid() {
  return h("div", {},
    h("h3", {}, "How did you repay your previous loans?"),
    h("div", { class: "grid" },
      numField("On time or early", "on_time", { min: 0, max: 60 }),
      numField("1\u20133 days late", "slight", { min: 0, max: 60 }),
      numField("4\u201330 days late", "late", { min: 0, max: 60 }),
      numField("Over 30 days late", "very_late", { min: 0, max: 60 })),
    h("div", { class: "grid", style: "margin-top:12px" },
      numField("Typical days vs. due date", "avg_late", { min: -30, max: 120, step: 0.5, hint: "Negative = you usually pay early" }),
      numField("Longest delay (days)", "max_late", { min: -30, max: 400 }),
      numField("Typical past loan (KSh)", "avg_amount", { min: 5000, max: 100000, step: 1000 }),
      numField("Typical past period (days)", "avg_term", { min: 7, max: 120 })));
}

function step1(v) {
  const modes = [
    ...(S.meta.lookup ? [["lookup", "I'm a returning customer", "We'll find your record using your customer ID."]] : []),
    ["manual", "I'll enter my history myself", "Tell us how you repaid your earlier loans."],
    ["first", "This is my first loan", "No history needed."],
  ];
  const msg = h("p", { class: "msg", id: "msg" });
  const panel = h("div", { id: "panel" });

  const fillPanel = () => {
    panel.replaceChildren();
    if (S.mode === "lookup") {
      const input = h("input", { type: "text", id: "cid", placeholder: "Paste your customer ID", autocomplete: "off", value: S.cid || "" });
      const find = async () => {
        msg.className = "msg"; msg.textContent = "Looking\u2026";
        try {
          const rec = await api("/api/lookup", { customer_id: input.value });
          S.cid = input.value.trim(); S.found = true; Object.assign(S.history, rec.history);
          for (const k of ["dob", "employment", "bank", "account"]) if (rec[k]) S.profile[k] = rec[k];
          const n = ["on_time", "slight", "late", "very_late"].reduce((a, k) => a + rec.history[k], 0);
          msg.className = "msg ok"; msg.textContent = `Found your record: ${n} previous loan(s). Adjust anything that looks wrong.`;
          fillPanel();
        } catch (e) { S.found = false; msg.className = "msg err"; msg.textContent = e.message; fillPanel(); }
      };
      panel.append(h("div", { class: "row" },
        h("label", { class: "f grow" }, "Customer ID", input),
        h("button", { type: "button", onclick: find }, "Find my record"),
        h("button", { type: "button", title: "Demo: picks a random customer", onclick: async () => {
          try { input.value = (await api("/api/sample-id")).customer_id; find(); } catch (e) { msg.className = "msg err"; msg.textContent = e.message; }
        } }, "Use a sample ID")));
      if (S.found) panel.append(historyGrid());
    } else if (S.mode === "manual") {
      panel.append(historyGrid());
    } else if (S.mode === "first") {
      panel.append(h("p", { class: "msg" }, "No borrowing history needed. Note: the models learned almost entirely from returning borrowers, so a first-loan result is less certain."));
    }
  };

  v.append(h("h2", {}, "Your borrowing history"), h("p", { class: "sub" }, "Your past repayments are the strongest signal of your willingness to repay."),
    h("div", { class: "opts" }, modes.map(([val, title, desc]) =>
      h("label", { class: "opt" + (S.mode === val ? " sel" : "") },
        h("input", { type: "radio", name: "mode", value: val, checked: S.mode === val, onchange: () => {
          S.mode = val; document.querySelectorAll(".opt").forEach(o => o.classList.toggle("sel", o.querySelector("input").value === val));
          msg.textContent = ""; fillPanel(); } }),
        h("div", {}, h("b", {}, title), h("span", {}, desc))))),
    panel, msg,
    h("div", { class: "nav" }, h("span"), h("button", { class: "primary", type: "button", onclick: () => {
      if (!S.mode) { msg.className = "msg err"; msg.textContent = "Choose an option to continue."; return; }
      if (S.mode === "lookup" && !S.found) { msg.className = "msg err"; msg.textContent = "Find your record first, or enter your history yourself."; return; }
      if (S.mode !== "first" && ["on_time", "slight", "late", "very_late"].reduce((a, k) => a + S.history[k], 0) === 0) {
        msg.className = "msg err"; msg.textContent = "Enter at least one previous loan, or choose 'This is my first loan'."; return; }
      go(2);
    } }, "Continue")));
  fillPanel();
}

/* ---------- step 2: about you ---------- */
function step2(v) {
  const max = new Date(); max.setFullYear(max.getFullYear() - 18);
  const msg = h("p", { class: "msg err" });
  v.append(h("h2", {}, "About you"), h("p", { class: "sub" }, "These help us put your request in context."),
    h("div", { class: "grid" },
      h("label", { class: "f" }, "Date of birth", h("input", { type: "date", value: S.profile.dob, min: "1940-01-01",
        max: max.toISOString().slice(0, 10), onchange: e => { S.profile.dob = e.target.value; } })),
      selectField("Employment status", "employment", S.meta.employment),
      selectField("Your bank", "bank", S.meta.banks),
      selectField("Account type", "account", S.meta.accounts)),
    msg,
    h("div", { class: "nav" }, h("button", { type: "button", onclick: () => go(1) }, "Back"),
      h("button", { class: "primary", type: "button", onclick: () => {
        if (!S.profile.dob) { msg.textContent = "Enter your date of birth."; return; }
        go(3); } }, "Continue")));
}

/* ---------- step 3: loan ---------- */
function step3(v) {
  const interest = () => S.meta.interest[S.term] ?? 0;
  const metrics = h("div", { class: "sum" });
  const warn = h("p", { class: "msg" });
  const refresh = () => {
    metrics.replaceChildren(
      h("div", { class: "metric" }, h("small", {}, "You borrow"), h("b", {}, ksh(S.amount))),
      h("div", { class: "metric" }, h("small", {}, `You repay (${Math.round(interest() * 100)}% interest)`), h("b", {}, ksh(S.amount * (1 + interest())))),
      h("div", { class: "metric" }, h("small", {}, "Within"), h("b", {}, `${S.term} days`)));
    const seen = S.meta.pairs.some(([t, a]) => t === S.term && a === S.amount);
    warn.textContent = seen ? "" : "\u26A0\uFE0F This amount and period combination is uncommon, so the result may be less reliable.";
  };
  const chips = (values, key, label) => h("div", { class: "chips" }, values.map(val =>
    h("button", { type: "button", class: "chip" + (S[key] === val ? " sel" : ""), onclick: e => {
      S[key] = val; e.target.parentNode.querySelectorAll(".chip").forEach(c => c.classList.remove("sel"));
      e.target.classList.add("sel"); refresh(); } }, label(val))));
  v.append(h("h2", {}, "The loan you want"),
    h("h3", {}, "Amount"), chips(S.meta.amounts, "amount", ksh),
    h("h3", {}, "Repayment period"), chips(S.meta.terms, "term", t => `${t} days`),
    metrics, warn,
    h("div", { class: "nav" }, h("button", { type: "button", onclick: () => go(2) }, "Back"),
      h("button", { class: "primary", type: "button", onclick: () => go(4) }, "Check my application")));
  refresh();
}

/* ---------- step 4: result ---------- */
function factorRows(factors) {
  const max = Math.max(...factors.map(f => Math.abs(f.value)), 0.01);
  return factors.map(f => {
    const w = Math.abs(f.value) / max * 50;
    const bar = h("div", { class: "bar", style: `width:${w}%;${f.value >= 0 ? "left:50%" : `right:50%`};background:${f.driver === "willingness" ? "var(--gold)" : "var(--teal)"}` });
    return h("div", { class: "fac", title: `${f.value >= 0 ? "Helps" : "Works against"} your application` },
      h("span", {}, f.factor), h("div", { class: "track" }, bar));
  });
}
function whatIf(title, items, fmtVal) {
  return h("div", {}, h("h4", {}, title), items.map(i =>
    h("span", { class: "wchip" + (i.current ? " cur" : "") }, h("i", { class: "dot " + i.outcome }), fmtVal(i.value), " \u2013 " + OUTCOME[i.outcome] + (i.current ? " (you)" : ""))));
}

async function step4(v) {
  v.append(h("div", { class: "spin" }, "Checking your application\u2026"));
  let r;
  try { r = S.result = await api("/api/score", payload()); }
  catch (e) {
    v.replaceChildren(h("h2", {}, "We couldn't check that"), h("p", { class: "msg err" }, e.message),
      h("div", { class: "nav" }, h("button", { type: "button", onclick: () => go(1) }, "Review my answers"), h("span")));
    return;
  }
  const msg = h("p", { class: "msg" });
  const submit = h("button", { class: "primary", type: "button", disabled: true }, "Submit application");
  const consent = h("input", { type: "checkbox", onchange: e => { submit.disabled = !e.target.checked; } });
  submit.addEventListener("click", async () => {
    submit.disabled = true;
    try { S.ref = (await api("/api/submit", { ...payload(), consent: true })).reference; done(); }
    catch (e) { msg.className = "msg err"; msg.textContent = e.message; submit.disabled = false; }
  });
  const foot = h("div", {});
  const done = () => foot.replaceChildren(h("div", { class: "banner likely" }, h("b", {}, "Application submitted"),
    h("p", {}, "Your reference is ", h("b", { style: "display:inline" }, S.ref), ". A loan officer will be in touch.")));
  if (S.ref) done(); else foot.append(
    h("label", { class: "consent" }, consent, "I confirm these details are correct and agree to them being used to review my application."), submit, msg);

  v.replaceChildren(
    h("h2", {}, "Your indicative result"),
    h("div", { class: "banner " + r.tier }, h("b", {}, r.headline), h("p", {}, r.message)),
    h("div", { class: "sum" },
      h("div", { class: "metric" }, h("small", {}, "You borrow"), h("b", {}, ksh(r.loan.amount))),
      h("div", { class: "metric" }, h("small", {}, `You repay (${Math.round(r.loan.interest * 100)}% interest)`), h("b", {}, ksh(r.loan.repay))),
      h("div", { class: "metric" }, h("small", {}, "Within"), h("b", {}, `${r.loan.term} days`))),
    ...(r.notes.length ? [h("ul", { class: "notes" }, r.notes.map(n => h("li", {}, n)))] : []),
    h("h3", {}, "Why this result"),
    ...factorRows(r.factors),
    h("div", { class: "axis" }, h("span", {}, "\u2190 works against you"), h("span", {}, "helps you \u2192")),
    h("div", { class: "legend" },
      h("span", {}, h("i", { class: "dot", style: "background:var(--gold)" }), "Willingness to pay (how you've repaid before)"),
      h("span", {}, h("i", { class: "dot", style: "background:var(--teal)" }), "Ability to pay / profile (the loan and your circumstances)")),
    h("p", { class: "fine", style: "text-align:left" }, "Bars show how strongly each answer moved the Logistic Regression model. They describe model behaviour, not cause."),
    h("h3", {}, "What if I change my request?"),
    h("div", { class: "wi" }, whatIf(`Different amount, ${r.loan.term} days`, r.what_if.amounts, ksh),
      whatIf(`Different period, ${ksh(r.loan.amount)}`, r.what_if.terms, t => `${t} days`)),
    h("details", {}, h("summary", {}, "Technical details"),
      h("p", {}, "Scores are P(Good) from each model. A request is flagged when the score is below that model's tuned cut-off. Scores are rankings, not calibrated probabilities of repayment."),
      h("table", {}, h("tr", {}, ["Model", "P(Good)", "Cut-off", "Predicts Good"].map(t => h("th", {}, t))),
        Object.entries(r.scores).map(([m, s]) => h("tr", {}, h("td", {}, m), h("td", {}, s.p_good.toFixed(3)), h("td", {}, s.threshold.toFixed(3)), h("td", {}, s.good ? "Yes" : "No"))))),
    h("hr", { style: "border:0;border-top:1px solid var(--line);margin:22px 0" }),
    foot,
    h("div", { class: "nav" }, h("button", { type: "button", onclick: () => go(3) }, "Change my request"),
      h("button", { type: "button", onclick: () => { Object.assign(S, { step: 1, mode: null, found: false, cid: "", result: null, ref: null }); render(); } }, "Start over")));
}

(async function init() {
  try { S.meta = await api("/api/meta"); render(); }
  catch (e) { $("#view").append(h("p", { class: "msg err" }, "The portal couldn't start: " + e.message)); }
})();
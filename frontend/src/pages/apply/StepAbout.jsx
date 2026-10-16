import { useState } from "react";
import { SelectField } from "../../components/Fields.jsx";

export default function StepAbout({ meta, app, setProfileValue, onBack, onNext }) {
  const [error, setError] = useState("");
  // Latest allowed birth date = today minus 18 years (same rule as the old page).
  const max = new Date();
  max.setFullYear(max.getFullYear() - 18);

  // Every personal field is the signed-in applicant's own choice; nothing is
  // pre-filled from a shared sample record.
  const next = () => {
    if (!app.profile.dob) return setError("Enter your date of birth.");
    if (!app.profile.employment) return setError("Choose your employment status.");
    if (!app.profile.bank) return setError("Choose your bank.");
    if (!app.profile.account) return setError("Choose your account type.");
    setError("");
    onNext();
  };

  return (
    <>
      <h2>About you</h2>
      <p className="sub">These help us put your request in context.</p>
      <div className="grid">
        <label className="f">
          Date of birth
          <input
            type="date" value={app.profile.dob} min="1940-01-01" max={max.toISOString().slice(0, 10)}
            onChange={(e) => setProfileValue("dob", e.target.value)}
          />
        </label>
        <SelectField label="Employment status" value={app.profile.employment} options={meta.employment}
          onValue={(v) => setProfileValue("employment", v)} />
        <SelectField label="Your bank" value={app.profile.bank} options={meta.banks}
          onValue={(v) => setProfileValue("bank", v)} />
        <SelectField label="Account type" value={app.profile.account} options={meta.accounts}
          onValue={(v) => setProfileValue("account", v)} />
      </div>
      <p className="msg err">{error}</p>
      <div className="nav">
        <button type="button" onClick={onBack}>Back</button>
        <button className="primary" type="button" onClick={next}>
          Continue
        </button>
      </div>
    </>
  );
}

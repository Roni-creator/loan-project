// Number box. Uncontrolled on purpose so you can type values like "0.5" or "-3" freely.
// An empty box counts as 0, same as the old app.
export function NumField({ label, hint, min, max, step = 1, value, onValue }) {
  return (
    <label className="f">
      {label}
      {hint ? <small>{hint}</small> : null}
      <input
        type="number" min={min} max={max} step={step} defaultValue={value}
        onChange={(e) => onValue(e.target.value === "" ? 0 : Number(e.target.value))}
      />
    </label>
  );
}

export function SelectField({ label, value, options, onValue }) {
  return (
    <label className="f">
      {label}
      <select value={value} onChange={(e) => onValue(e.target.value)}>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </label>
  );
}

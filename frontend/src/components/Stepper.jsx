import { STEPS } from "../lib/applyState.js";

export default function Stepper({ step }) {
  return (
    <ol className="steps" aria-label="Progress">
      {STEPS.map((title, i) => (
        <li key={title} className={i + 1 === step ? "on" : i + 1 < step ? "done" : ""}>
          {i + 1}. {title}
        </li>
      ))}
    </ol>
  );
}

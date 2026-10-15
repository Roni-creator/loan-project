const STATUS = {
  submitted: ["submitted", "Submitted"],
  assigned: ["assigned", "In review"],
  more_info: ["more_info", "More info needed"],
  approved: ["approved", "Approved"],
  declined: ["declined", "Declined"],
};

const TIER = {
  likely: ["likely", "Likely to repay"],
  review: ["review", "Needs a closer look"],
  refer: ["refer", "Needs review"],
};

export function StatusBadge({ status }) {
  const [cls, label] = STATUS[status] || ["submitted", status];
  return <span className={`badge ${cls}`}>{label}</span>;
}

export function TierBadge({ tier }) {
  const [cls, label] = TIER[tier] || ["review", tier];
  return <span className={`badge ${cls}`}>{label}</span>;
}

export function overallPercentAllowed(args: {
  weightingModeled: boolean;
  overallPercent: number | null | undefined;
}): number | null {
  if (!args.weightingModeled) return null;
  if (args.overallPercent == null || Number.isNaN(args.overallPercent)) return null;
  return args.overallPercent;
}

export function gradeRowHonesty(status: string, pointsEarned: number | null): {
  pending: boolean;
  label: string;
} {
  const pending = pointsEarned == null || status === "pending" || status === "submitted" || status === "ungraded";
  return {
    pending,
    label: pending ? "Waiting for a grade" : status,
  };
}

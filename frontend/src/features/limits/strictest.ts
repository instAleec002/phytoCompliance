// The market whose limit is strictly lower than every other market with a value; none when the lowest is shared
// (three markets at 4 mg/kg have no strictest one).

interface LimitLike {
  market: string;
  status: string;
  value_mg_kg: number | null;
}

export function strictestMarket(limits: (LimitLike | undefined)[]): string | null {
  const numeric = limits.filter((l): l is LimitLike => !!l && l.value_mg_kg !== null && l.status !== "no_data");
  if (numeric.length < 2) return null;
  const lowest = Math.min(...numeric.map((l) => l.value_mg_kg!));
  const atLowest = numeric.filter((l) => l.value_mg_kg === lowest);
  return atLowest.length === 1 ? atLowest[0]!.market : null;
}

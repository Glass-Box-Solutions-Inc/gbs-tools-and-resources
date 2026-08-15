export type ReclaimEnvironment = Readonly<Record<string, string | undefined>>;

export function integerEnvironment(
  name: string,
  fallback: number,
  allowZero: boolean,
  environment: ReclaimEnvironment = process.env,
): number {
  const raw = environment[name];
  if (raw === undefined) {
    return fallback;
  }
  const normalized = raw.trim();
  if (!/^\d+$/.test(normalized)) {
    throw new Error(`invalid_${name}`);
  }
  const value = Number(normalized);
  if (!Number.isSafeInteger(value) || value < (allowZero ? 0 : 1)) {
    throw new Error(`invalid_${name}`);
  }
  return value;
}

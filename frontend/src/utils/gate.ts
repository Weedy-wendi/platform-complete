export interface GateRule {
  name: string;
  expected: string;
  actual: string;
  passed: boolean;
  evidenceRef: string;
}

export interface GateSummary {
  total: number;
  passed: number;
  failed: number;
  allPassed: boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function asText(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function asPassed(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") return value.toLowerCase() === "passed" || value.toLowerCase() === "true";
  return false;
}

/**
 * Normalize the gate result payload (`{passed, rules}`) into table rows. The
 * API uses snake_case, but a few deployment variants return camelCase.
 */
export function normalizeGateRules(payload: unknown): GateRule[] {
  if (!isRecord(payload)) return [];
  const source = payload.rules ?? payload.items;
  if (!Array.isArray(source)) return [];
  return source.map((entry, index) => {
    const rule = isRecord(entry) ? entry : {};
    return {
      name: asText(rule.name ?? rule.rule ?? rule.rule_name ?? `#${index + 1}`),
      expected: asText(rule.expected ?? rule.expected_value ?? rule.target),
      actual: asText(rule.actual ?? rule.actual_value ?? rule.value),
      passed: asPassed(rule.passed ?? rule.pass ?? rule.status),
      evidenceRef: asText(rule.evidence_ref ?? rule.evidenceRef ?? rule.evidence),
    };
  });
}

export function gateSummary(rules: GateRule[]): GateSummary {
  const passed = rules.filter((rule) => rule.passed).length;
  return {
    total: rules.length,
    passed,
    failed: rules.length - passed,
    allPassed: rules.length > 0 && passed === rules.length,
  };
}

export function gateRowClass(rule: GateRule): string {
  return rule.passed ? "" : "gate-row-failed";
}

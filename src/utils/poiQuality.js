import rules from '../config/poi-quality-rules.json' with { type: 'json' }

// Preserve provider text. Hints are evidence for review, never operating-status verdicts.
export function getPoiNameHints(name = '') {
  return Object.entries(rules).flatMap(([group, definitions]) =>
    definitions
      .filter((rule) => rule.tokens.some((token) => name.includes(token)))
      .map((rule) => ({ group, label: rule.label })),
  )
}

export function auditMatchesSummary(audit, summary) {
  return (
    !!audit &&
    !!summary &&
    audit.schemaVersion === 1 &&
    audit.readOnly === true &&
    audit.stationCount === summary.storedCount &&
    audit.runId === summary.latestRun?.id &&
    Date.parse(audit.sourceUpdatedAt) === Date.parse(summary.updatedAt)
  )
}

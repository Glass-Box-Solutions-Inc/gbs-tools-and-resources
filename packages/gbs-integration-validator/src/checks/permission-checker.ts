// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Permission checker aggregator. Collects permission results from all
// validators and produces a unified summary of which scopes are present
// and which are missing across the entire GBS platform.

import type { PermissionResult, SystemName } from "../types/index.js";

export interface AggregatedPermissions {
  timestamp: string;
  totalSystems: number;
  configuredSystems: number;
  fullyAuthorized: number;
  partiallyAuthorized: number;
  unauthorized: number;
  systems: PermissionResult[];
  allMissingScopes: Array<{
    systemName: SystemName;
    scope: string;
  }>;
}

export function aggregatePermissions(
  results: PermissionResult[],
): AggregatedPermissions {
  const allMissingScopes: Array<{ systemName: SystemName; scope: string }> =
    [];

  let fullyAuthorized = 0;
  let partiallyAuthorized = 0;
  let unauthorized = 0;

  for (const result of results) {
    for (const scope of result.missingScopes) {
      allMissingScopes.push({ systemName: result.systemName, scope });
    }

    if (result.hasAccess && result.missingScopes.length === 0) {
      fullyAuthorized++;
    } else if (result.scopes.length > 0) {
      partiallyAuthorized++;
    } else {
      unauthorized++;
    }
  }

  return {
    timestamp: new Date().toISOString(),
    totalSystems: results.length,
    configuredSystems: results.filter(
      (r) => r.scopes.length > 0 || r.missingScopes.length > 0,
    ).length,
    fullyAuthorized,
    partiallyAuthorized,
    unauthorized,
    systems: results,
    allMissingScopes,
  };
}

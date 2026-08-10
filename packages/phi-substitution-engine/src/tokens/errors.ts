import type { OperationId } from "../core/brands";

/**
 * Fixed, PHI-free failure signals for the token/reversal boundary.
 *
 * Per CONTRACT-phase1 §7 these carry only the operation id and a fixed code.
 * They never contain input text, matched text, tokens paired with values,
 * variants, excerpts, offsets, or encryption material.
 */

export const REVERSAL_FAILED = "REVERSAL_FAILED";
export const DIAG_REVERSAL_HANDLE_NOT_SERIALIZABLE = "REVERSAL_HANDLE_NOT_SERIALIZABLE";

export class ReversalFailedError extends Error {
  readonly code: typeof REVERSAL_FAILED = REVERSAL_FAILED;
  readonly operationId: OperationId | null;
  constructor(operationId: OperationId | null = null) {
    super("reversal_failed");
    this.name = "ReversalFailedError";
    this.operationId = operationId;
  }
}

export class ReversalHandleNotSerializableError extends Error {
  readonly diagnostic: typeof DIAG_REVERSAL_HANDLE_NOT_SERIALIZABLE =
    DIAG_REVERSAL_HANDLE_NOT_SERIALIZABLE;
  constructor() {
    super("reversal_handle_not_serializable");
    this.name = "ReversalHandleNotSerializableError";
  }
}

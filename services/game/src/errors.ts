/**
 * One error vocabulary for the whole service.
 *
 * The codes exist so the client can branch on *meaning* rather than on prose, and
 * so a test can assert the class of failure without matching a message. Two of
 * them carry more weight than the rest:
 *
 *   `stale_revision`      the caller acted on a view of the session that has since
 *                         moved. Refusing is the whole point: a professor who
 *                         double-clicks "close round" must not resolve it twice.
 *   `idempotency_conflict` the same idempotency key arrived with a *different*
 *                         body. That is not a retry, it is a client bug, and
 *                         silently accepting it would apply one request twice
 *                         under one key.
 */

export type ErrorCode =
  | "bad_request"
  | "not_found"
  | "forbidden"
  | "unauthenticated"
  | "conflict"
  | "stale_revision"
  | "illegal_phase"
  | "validation_failed"
  | "idempotency_conflict"
  | "engine_unavailable"
  | "internal";

const STATUS: Record<ErrorCode, number> = {
  bad_request: 400,
  unauthenticated: 401,
  forbidden: 403,
  not_found: 404,
  conflict: 409,
  stale_revision: 409,
  illegal_phase: 409,
  idempotency_conflict: 409,
  validation_failed: 422,
  engine_unavailable: 502,
  internal: 500,
};

export class AppError extends Error {
  readonly code: ErrorCode;
  readonly status: number;
  readonly details: unknown;

  constructor(code: ErrorCode, message: string, details?: unknown) {
    super(message);
    this.name = "AppError";
    this.code = code;
    this.status = STATUS[code];
    this.details = details;
  }

  toBody(): { error: ErrorCode; detail: string; details?: unknown } {
    const body: { error: ErrorCode; detail: string; details?: unknown } = {
      error: this.code,
      detail: this.message,
    };
    if (this.details !== undefined) body.details = this.details;
    return body;
  }
}

export const badRequest = (m: string, d?: unknown) => new AppError("bad_request", m, d);
export const notFound = (m: string) => new AppError("not_found", m);
export const forbidden = (m: string) => new AppError("forbidden", m);
export const unauthenticated = (m = "sign in first") =>
  new AppError("unauthenticated", m);
export const conflict = (m: string) => new AppError("conflict", m);
export const staleRevision = (expected: number, actual: number) =>
  new AppError(
    "stale_revision",
    `this session has moved on (you sent revision ${expected}, current is ${actual}); reload and try again`,
    { expected, actual },
  );
export const illegalPhase = (m: string) => new AppError("illegal_phase", m);
export const validationFailed = (m: string, d?: unknown) =>
  new AppError("validation_failed", m, d);

/** Best-effort classification of an unexpected throw, for the HTTP boundary. */
export function asAppError(err: unknown): AppError {
  if (err instanceof AppError) return err;
  const message = err instanceof Error ? err.message : String(err);
  return new AppError("internal", message);
}

/** Browser-safe sanitization helpers for frontend telemetry. */

const SAFE_ERROR_NAMES = new Set([
  "Error",
  "TypeError",
  "RangeError",
  "ReferenceError",
  "SyntaxError",
  "URIError",
  "EvalError",
]);

/**
 * Hash only a fixed error class and source bundle basenames extracted from stack
 * frames. Never hash error messages, full paths, URLs, or arbitrary stack text.
 */
export async function createErrorFingerprint(error: unknown): Promise<string | null> {
  if (typeof window === "undefined" || !globalThis.crypto?.subtle) return null;

  const errorName = error instanceof Error && SAFE_ERROR_NAMES.has(error.name)
    ? error.name
    : "Error";
  const stack = error instanceof Error ? error.stack ?? "" : "";
  const frames = stack
    .split("\n")
    .slice(1)
    .map((line) => {
      // Only retain a source filename ending in a known code extension; discard
      // the path, URL, query string, line/column, and function text entirely.
      const match = line.match(/(?:^|[/\\])([^/\\?:]+\.(?:js|mjs|cjs|ts|tsx))(?:\?[^\s)]*)?(?::\d+){0,2}/i);
      if (!match) return null;
      const basename = match[1]
        .replace(/[a-f0-9]{8,}/gi, "HASH")
        .replace(/\d+/g, "N")
        .replace(/[^a-zA-Z_.-]/g, "_")
        .slice(0, 100);
      return basename;
    })
    .filter((frame): frame is string => Boolean(frame))
    .slice(0, 3);
  const fingerprintSource = `${errorName}|${frames.join("|") || "unknown_frame"}`;

  try {
    const digest = await globalThis.crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(fingerprintSource),
    );
    return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  } catch {
    return null;
  }
}

/** Build revisions are optional in local development, but required by schema. */
export function getTelemetryAppVersion(): string | null {
  const revision = process.env.NEXT_PUBLIC_BUILD_SHA ?? process.env.NEXT_PUBLIC_BUILD_ID ?? "";
  return /^[a-f0-9]{7,40}$/i.test(revision) ? revision.toLowerCase() : null;
}

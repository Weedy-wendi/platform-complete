/**
 * Turn a server-returned share path into an absolute URL. The helper never
 * adds credentials: authentication for share creation stays in the request
 * header and is not part of the copyable link.
 */
export function absoluteShareUrl(
  path: string,
  origin: string = typeof window === "undefined" ? "" : window.location.origin,
): string {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  return `${origin.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;
}

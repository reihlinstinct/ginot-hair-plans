// RFC 9116 security.txt, served by every Worker at /.well-known/security.txt.
// Contact is the repo's private vulnerability reporting form (no personal email).
export const SECURITY_TXT = [
  "Contact: https://github.com/reihlinstinct/ginot-hair-plans/security/advisories/new",
  "Expires: 2027-10-01T00:00:00.000Z",
  "Preferred-Languages: he, en",
  "Policy: https://github.com/reihlinstinct/ginot-hair-plans/blob/main/SECURITY.md",
  "Canonical: https://github.com/reihlinstinct/ginot-hair-plans/blob/main/SECURITY.md",
  "",
].join("\n");

export const SECURITY_PATH = "/.well-known/security.txt";

export function securityTxtResponse(request) {
  if (new URL(request.url).pathname !== SECURITY_PATH) return null;
  if (request.method !== "GET" && request.method !== "HEAD") return null;
  return new Response(request.method === "HEAD" ? null : SECURITY_TXT, {
    status: 200,
    headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "public, max-age=3600", "access-control-allow-origin": "*" },
  });
}

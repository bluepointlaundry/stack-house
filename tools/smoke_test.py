"""Check a running Stack House site from the outside.

    python tools/smoke_test.py https://stackhouse.alsalemkuwait.com

Optional: also log in and check the account pages. The password is read from the
environment, never from the command line, and is never printed:

    set STACKHOUSE_USER=yourname
    set STACKHOUSE_PASS=yourpassword
    python tools/smoke_test.py https://stackhouse.alsalemkuwait.com
"""
import http.cookiejar
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"[{'ok' if ok else 'FAIL'}] {name}{' - ' + detail if detail else ''}")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch(opener, url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "stackhouse-smoke-test", **(headers or {})})
    try:
        resp = opener.open(req, timeout=20)
        return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    base = sys.argv[1].rstrip("/")
    parts = urllib.parse.urlsplit(base)
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    print(f"Checking {base}\n")

    # 1. reachable over https with a valid certificate (urllib verifies certificates)
    try:
        status, headers, body = fetch(opener, base + "/healthz")
    except (urllib.error.URLError, ssl.SSLError, OSError) as e:
        check("site reachable", False, f"{e} (DNS not ready, certificate not issued yet, or this network blocks the site)")
        return 1
    check("site reachable" + (" with a valid https certificate" if parts.scheme == "https" else ""), status == 200,
          f"/healthz returned {status}")

    # 2. plain http goes to https
    if parts.scheme == "https":
        plain = urllib.request.build_opener(NoRedirect)
        try:
            s, h, _ = fetch(plain, f"http://{parts.netloc}/")
            loc = h.get("Location", "")
            check("http:// redirects to https://", s in (301, 302, 307, 308) and loc.startswith("https://"), f"{s} -> {loc or 'no redirect'}")
        except (urllib.error.URLError, OSError) as e:
            check("http:// redirects to https://", False, str(e))

    # 3. the app itself
    status, headers, body = fetch(opener, base + "/")
    check("home page loads", status == 200 and b"Stack House" in body, f"status {status}")
    check("security headers present", bool(headers.get("Content-Security-Policy")) and headers.get("X-Content-Type-Options") == "nosniff")
    if parts.scheme == "https":
        check("HSTS header present", "max-age" in (headers.get("Strict-Transport-Security") or ""))

    status, headers, body = fetch(opener, base + "/api/bootstrap")
    try:
        boot = json.loads(body)
    except ValueError:
        boot = {}
    check("API answers", status == 200 and "setupNeeded" in boot, f"status {status}")
    if boot.get("setupNeeded"):
        print("       note: no admin account yet - open the site and create it.")

    # 4. installable app + notifications plumbing
    status, headers, body = fetch(opener, base + "/manifest.webmanifest")
    check("app manifest", status == 200 and b"Stack House" in body, f"status {status}")
    status, headers, body = fetch(opener, base + "/sw.js")
    check("service worker", status == 200 and "javascript" in (headers.get("Content-Type") or ""), headers.get("Content-Type", ""))
    status, headers, body = fetch(opener, base + "/static/icons/icon-192.png")
    check("app icon", status == 200 and body[:4] == b"\x89PNG", f"status {status}")

    # 5. optional login
    user, password = os.environ.get("STACKHOUSE_USER"), os.environ.get("STACKHOUSE_PASS")
    if user and password:
        status, headers, body = fetch(opener, base + "/api/login", json.dumps({"username": user, "password": password}).encode(),
                                      {"Content-Type": "application/json"})
        check("log in", status == 200, f"status {status}")
        cookie = headers.get("Set-Cookie") or ""
        if parts.scheme == "https":
            check("login cookie is Secure and HttpOnly", "Secure" in cookie and "HttpOnly" in cookie)
        status, headers, body = fetch(opener, base + "/api/bootstrap")
        boot = json.loads(body) if status == 200 else {}
        check("account loads", bool(boot.get("user")), boot.get("user", {}).get("name", "") if boot.get("user") else "")
        key = boot.get("vapidPublicKey") or ""
        check("push notification key", len(key) in (86, 87), f"{len(key)} characters")
        if boot.get("settings"):
            print(f"       kitchen timezone: {boot['settings']['timezone']}, kitchen today: {boot.get('today')}, "
                  f"open now: {boot['kitchen']['open']}")
        status, _, _ = fetch(opener, base + "/api/poll")
        check("live updates (poll)", status == 200, f"status {status}")
    else:
        print("       (set STACKHOUSE_USER and STACKHOUSE_PASS to also test logging in)")

    failed = results.count(False)
    print(f"\n{len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

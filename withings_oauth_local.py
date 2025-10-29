#!/usr/bin/env python3
import base64, hashlib, os, sys, threading, webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs

# ==== Fyll i följande värden ====
CLIENT_ID = "7c76b74bc866d1cf4eeac0fd6e374cef93fd83f75e19e8030094782695de1c7f"
CLIENT_SECRET = "0585996ecb672758d2142b69645d5665617c9412be0b9b9ad0572fde388e778d"  # behövs vid token-exchange (inte i authorize-URL)
REDIRECT_URI = "http://127.0.0.1:8765/withings_callback"
SCOPES = "user.metrics"  # kontrollera exakt scope i Withings-dokumentationen
AUTH_URL_BASE  = "https://account.withings.com/oauth2_user/authorize2"  # verifiera i docs
TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"  # verifiera i docs
# ================================

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

# PKCE (S256)
CODE_VERIFIER = b64url(os.urandom(32))  # 43–128 tecken
print("code_verifier:", CODE_VERIFIER)
CODE_CHALLENGE = b64url(hashlib.sha256(CODE_VERIFIER.encode()).digest())

# CSRF-skydd
STATE = b64url(os.urandom(16))

AUTH_PARAMS = {
    "response_type": "code",
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "scope": SCOPES,
    "state": STATE,
    "code_challenge": CODE_CHALLENGE,
    "code_challenge_method": "S256",
}

authorize_url = AUTH_URL_BASE + "?" + urlencode(AUTH_PARAMS)

# Enkel HTTP-handler som fångar code+state
RESULT = {"code": None, "state": None, "error": None}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if urlparse(self.path).path != "/callback":
            self.send_response(404); self.end_headers(); return
        qs = parse_qs(urlparse(self.path).query)
        RESULT["code"] = (qs.get("code") or [None])[0]
        RESULT["state"] = (qs.get("state") or [None])[0]
        RESULT["error"] = (qs.get("error") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<h1>Withings auth klar</h1><p>Du kan stanga detta fonstrer.</p>")
    def log_message(self, fmt, *args):  # tystare server
        return

def serve_once():
    host, port = "127.0.0.1", 8765
    httpd = HTTPServer((host, port), Handler)
    # Kör i bakgrundstråd så vi kan öppna webbläsare parallellt
    t = threading.Thread(target=httpd.handle_request, daemon=True)
    t.start()
    return httpd, t

def main():
    print(">> Startar lokal lyssnare pa", REDIRECT_URI)
    httpd, t = serve_once()
    print(">> Oppnar authorize-URL i webblasaren:\n", authorize_url)
    try:
        webbrowser.open(authorize_url)
    except Exception:
        print("(!) Kunde inte oppna webblasare. Kopiera URL:en ovan och klistra i en webblasare.")
    # Vänta tills vi fått ett callback eller 180 s
    t.join(timeout=180)
    httpd.server_close()

    if RESULT["error"]:
        print("Auth error:", RESULT["error"]); sys.exit(1)
    if not RESULT["code"]:
        print("Ingen code mottagen. Kontrollera redirect_uri eller prova igen."); sys.exit(2)
    if RESULT["state"] != STATE:
        print("STATE mismatch! Avbryter."); sys.exit(3)

    print("\n=== OK, fick authorization code ===")
    print("code:", RESULT["code"])
    print("state:", RESULT["state"])
    print("\nSpara CODE_VERIFIER for PKCE:")
    print("code_verifier:", CODE_VERIFIER)

    # Visa exempel for token-exchange (du kan kora detta med curl eller i din fetcher)
    print("\nExempel POST for token-exchange (kolla Withings docs for exakta parametrar):")
    print("POST", TOKEN_URL)
    print({
        "action": "requesttoken",             # Withings anvander 'action' i v2 endpoint (verifiera i docs)
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": "***REDACTED***",
        "code": RESULT["code"],
        "redirect_uri": REDIRECT_URI,
        "code_verifier": CODE_VERIFIER,
    })

if __name__ == "__main__":
    main()

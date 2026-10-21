"""Bounded DNS, hosting and TLS I/O. Never follow a customer URL redirect."""
import hashlib
import hmac
import http.client
import ipaddress
import json
import secrets
import shlex
import socket
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from django.conf import settings


class DomainCheckError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _json_request(url, *, method="GET", body=None, headers=None):
    request = Request(url, data=json.dumps(body).encode() if body is not None else None,
                      headers={"Accept": "application/json", "Content-Type": "application/json", **(headers or {})}, method=method)
    with build_opener(NoRedirect).open(request, timeout=5) as response:
        data = response.read(131073)
        if len(data) > 131072:
            raise DomainCheckError("The provider returned an oversized response. Try again later.")
        return json.loads(data) if data else {}


def dns_records(hostname, kind):
    # Fixed public resolver endpoint, not a customer-supplied HTTP destination.
    try:
        result = _json_request("https://cloudflare-dns.com/dns-query?" + urlencode({"name": hostname, "type": kind}),
                               headers={"Accept": "application/dns-json"})
        if result.get("Status") not in (0, 3):
            raise DomainCheckError("DNS could not be checked. Please try again later.")
        code = {"TXT": 16, "CNAME": 5, "A": 1, "AAAA": 28}[kind]
        values = [row["data"] for row in result.get("Answer", []) if row.get("type") == code]
        return ["".join(shlex.split(value)) for value in values] if kind == "TXT" else [value.rstrip(".").lower() for value in values]
    except (OSError, ValueError, KeyError, URLError) as exc:
        raise DomainCheckError("DNS could not be checked. Please try again later.") from exc


def public_addresses(hostname):
    addresses = set(dns_records(hostname, "A") + dns_records(hostname, "AAAA"))
    try:
        valid = bool(addresses) and all(ipaddress.ip_address(value).is_global for value in addresses)
    except ValueError:
        valid = False
    if not valid:
        raise DomainCheckError("The domain must resolve only to public internet addresses.")
    return addresses


def check_destination(hostname, target, apex_ipv4):
    addresses = public_addresses(hostname)
    if target in dns_records(hostname, "CNAME"):
        return addresses
    expected = public_addresses(target)
    if apex_ipv4:
        try:
            if not ipaddress.ip_address(apex_ipv4).is_global:
                raise ValueError
        except ValueError as exc:
            raise DomainCheckError("The platform's root-domain address needs administrator configuration.") from exc
        expected.add(apex_ipv4)
    if not addresses.issubset(expected):
        raise DomainCheckError("DNS does not point to the required hosting destination yet.")
    return addresses


def _render(method, path, body=None):
    try:
        return _json_request("https://api.render.com/v1/" + path, method=method, body=body,
                             headers={"Authorization": "Bearer " + settings.RENDER_API_KEY})
    except HTTPError as exc:
        if method == "DELETE" and exc.code == 404:
            return {}
        raise DomainCheckError("Hosting setup could not finish. Ask your platform administrator to check the hosting connection.") from exc
    except (OSError, ValueError, URLError) as exc:
        # Never surface API response bodies, tokens, or customer identifiers.
        raise DomainCheckError("Hosting setup could not finish. Ask your platform administrator to check the hosting connection.") from exc


def register_render(hostname, provider_id=""):
    if not settings.RENDER_API_KEY or not settings.RENDER_SERVICE_ID:
        raise DomainCheckError("Your platform administrator needs to connect Render before this domain can go live.")
    path = "services/" + quote(settings.RENDER_SERVICE_ID, safe="") + "/custom-domains"
    if not provider_id:
        # Reconcile before creation: a previous request may have succeeded before a timeout.
        cursor = ""
        for _ in range(10):
            rows = _render("GET", path + "?" + urlencode({"limit": 100, **({"cursor": cursor} if cursor else {})}))
            if not isinstance(rows, list):
                raise DomainCheckError("Hosting returned an unexpected response. Ask your platform administrator to check the connection.")
            for row in rows:
                domain = row.get("customDomain", {})
                if domain.get("name") == hostname:
                    provider_id = domain.get("id", "")
                    break
            if provider_id or len(rows) < 100:
                break
            cursor = rows[-1].get("cursor", "")
            if not cursor:
                break
        else:
            raise DomainCheckError("Hosting has too many domains to reconcile. Ask your platform administrator for help.")
        if not provider_id:
            result = _render("POST", path, {"name": hostname})
            provider_id = result.get("id", "") or result.get("customDomain", {}).get("id", "")
        if not provider_id:
            raise DomainCheckError("Hosting setup is pending. Check the connection again shortly.")
    return provider_id


def verify_render(provider_id):
    path = "services/" + quote(settings.RENDER_SERVICE_ID, safe="") + "/custom-domains/" + quote(provider_id, safe="") + "/verify"
    _render("POST", path)


def remove_render(provider_id):
    if not settings.RENDER_API_KEY or not settings.RENDER_SERVICE_ID:
        raise DomainCheckError("Your platform administrator needs to connect Render before this domain can be removed from hosting.")
    path = "services/" + quote(settings.RENDER_SERVICE_ID, safe="") + "/custom-domains/" + quote(provider_id, safe="")
    _render("DELETE", path)


def domain_proof(hostname, token, nonce):
    return hmac.new(settings.SECRET_KEY.encode(), (hostname + ":" + token + ":" + nonce).encode(), hashlib.sha256).hexdigest()


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname, address):
        super().__init__(hostname, timeout=5, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Use the already-checked IP, but verify TLS against the actual hostname.
        # No second DNS resolution (including after an attacker changes DNS).
        sock = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def check_https(hostname, token, addresses):
    nonce = secrets.token_hex(16)
    # Validate every answer, even those beyond the bounded probe budget.
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise DomainCheckError("Private network destinations are not allowed.")
    # Cover IPv4 and IPv6 without letting a large DNS answer monopolize a worker.
    ordered = sorted(addresses, key=lambda value: (ipaddress.ip_address(value).version, value))
    candidates = [next((value for value in ordered if ipaddress.ip_address(value).version == version), None) for version in (4, 6)]
    for address in filter(None, candidates):
        connection = PinnedHTTPSConnection(hostname, address)
        try:
            connection.request("GET", "/.well-known/seerkitchen-domain?" + urlencode({"nonce": nonce}), headers={"Host": hostname})
            response = connection.getresponse()
            payload = response.read(2049)
            if response.status != 200 or len(payload) > 2048:
                continue
            data = json.loads(payload)
            if hmac.compare_digest(str(data.get("proof", "")), domain_proof(hostname, token, nonce)):
                return
        except (OSError, ValueError, http.client.HTTPException):
            continue
        finally:
            connection.close()
    raise DomainCheckError("HTTPS is not ready at this application yet. Allow hosting verification and certificate issuance to finish, then check again.")

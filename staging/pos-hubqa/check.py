#!/usr/bin/env python3
"""Read-only POS/Hub stage acceptance preflight. Never prints tokens or secrets."""
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

STAGE_NET = "v79pos-hubqa-20261109_stage_internal"

def ensure(ok, msg):
    if not ok:
        raise RuntimeError("PRIVATE_STAGE_CHECK_FAILED: " + msg)

def inspect(name):
    data = subprocess.check_output(["docker", "inspect", name], text=True)
    return json.loads(data)[0]

def env(container):
    return dict(s.split("=", 1) for s in container["Config"]["Env"] if "=" in s)

def binding(container, internal, expected):
    ports = container["NetworkSettings"]["Ports"].get(internal) or []
    return len(ports) == 1 and (
        ports[0].get("HostIp"), ports[0].get("HostPort")
    ) == expected

def http_status(url):
    try:
        with urllib.request.urlopen(url, timeout=7) as result:
            return result.status, result.read(1024)
    except urllib.error.HTTPError as error:
        return error.code, b""

def main():
    prod = inspect("v79-pos")
    stage_pos = inspect("v79-pos-hubqa-api")
    stage_hub = inspect("v79-hub-pos-hubqa")
    stage_db = inspect("v79-pos-hubqa-db")
    net = json.loads(subprocess.check_output(
        ["docker", "network", "inspect", STAGE_NET], text=True))[0]

    ensure(prod["Config"]["Image"] == "localhost/v79-brand-pos:20261106-r1",
           "Live POS image changed unexpectedly")
    ensure(prod["State"].get("Health", {}).get("Status") == "healthy",
           "Live POS is not healthy")
    ensure(net["Internal"] is True, "The staging Docker bridge is not internal")
    ensure(stage_pos["Config"]["Image"] == "v79pos:hubqa-2590623",
           "Stage POS image mismatch")
    ensure(stage_hub["Config"]["Image"] == "v79hub:pos-hubqa-20261109",
           "Stage Hub image mismatch")
    ensure(set(stage_pos["NetworkSettings"]["Networks"]) == {STAGE_NET},
           "Stage POS has access to a second network")
    ensure(set(stage_hub["NetworkSettings"]["Networks"]) == {STAGE_NET},
           "Stage Hub has access to a second network")
    ensure(stage_pos["State"].get("Health", {}).get("Status") == "healthy",
           "Stage POS is not healthy")
    ensure(stage_hub["State"].get("Health", {}).get("Status") == "healthy",
           "Stage Hub is not healthy")
    ensure(binding(stage_pos, "8080/tcp", ("127.0.0.1", "18081")),
           "Stage POS API is not loopback-only")
    ensure(binding(stage_hub, "3040/tcp", ("127.0.0.1", "18082")),
           "Stage Hub is not loopback-only")
    ensure(env(stage_db).get("POSTGRES_DB") == "v79pos_hubqa",
           "POS stage has wrong database")
    ps, hs, live = env(stage_pos), env(stage_hub), env(prod)
    ensure(ps.get("AUTH_MODE") == "hub", "Stage POS auth bypass is enabled")
    ensure(ps.get("V79_ENTITLEMENT_RECHECK_ENABLED") == "1",
           "Stage entitlement rechecks are disabled")
    ensure(hs.get("V79_REQUIRE_ADMIN_MFA") == "1", "Stage Hub MFA is not required")
    ensure(hs.get("V79_HUB_STORE_BACKEND") == "json", "Stage Hub store is unexpected")
    ensure(ps.get("HUB_INTERNAL_URL") == "http://v79-hub-pos-hubqa:3040",
           "Stage POS points away from isolated Hub")
    ensure(ps.get("HUB_JWKS_URL") ==
           "http://v79-hub-pos-hubqa:3040/.well-known/jwks.json",
           "Stage POS JWKS points away from isolated Hub")
    ensure(ps.get("JWT_ISSUER") == "http://127.0.0.1:18082",
           "Stage issuer mismatch")
    ensure(hs.get("POS_BASE_URL") == "http://v79-pos-hubqa-api:8080",
           "Stage Hub could write outside staging")
    ensure(hs.get("POS_PUBLIC_URL") == "http://127.0.0.1:18081",
           "Stage Hub redirects to the wrong POS")
    ensure(hs.get("APP_URL") == "http://127.0.0.1:18082",
           "Stage Hub browser origin mismatch")
    ensure(hs.get("RESEND_API_KEY", "") == "",
           "Staging has a live transactional email key")
    ensure(hs.get("WIPAY_ENABLED") == "0",
           "Staging billing is enabled")
    pos_secret = ps.get("V79_PLATFORM_SHARED_SECRET", "")
    hub_secret = hs.get("V79_POS_PLATFORM_SHARED_SECRET", "")
    ensure(len(pos_secret) >= 32 and pos_secret == hub_secret,
           "Stage Hub/POS service signatures do not match")
    ensure(pos_secret == ps.get("V79_POS_PLATFORM_SHARED_SECRET"),
           "POS stage launch/entitlement signature contract mismatch")
    ensure(pos_secret == hs.get("V79_PLATFORM_SHARED_SECRET"),
           "Hub stage launch/entitlement signature contract mismatch")
    ensure(pos_secret != live.get("V79_PLATFORM_SHARED_SECRET") and
           pos_secret != live.get("V79_POS_PLATFORM_SHARED_SECRET"),
           "Staging reused live POS HMAC credentials")
    ensure(hs.get("V79_HUB_SECURITY_KEY") != pos_secret,
           "Hub MFA encryption and service signing key must be different")

    hub_code, _ = http_status("http://127.0.0.1:18082/api/health")
    pos_code, pos_body = http_status("http://127.0.0.1:18081/ready")
    unauth_code, _ = http_status("http://127.0.0.1:18081/v1/me")
    ensure(hub_code == 200, "Stage Hub health endpoint is failing")
    ensure(pos_code == 200 and b'"database":"ok"' in pos_body,
           "Stage POS readiness check failed")
    ensure(unauth_code == 401,
           "Unauthenticated access to staging POS was not denied")
    print("PRODUCTION_UNCHANGED=PASS")
    print("PRIVATE_STAGING_NETWORK=PASS")
    print("UNIQUE_KEYS_AND_MFA=PASS")
    print("ISOLATED_HUB_POS_ROUTING=PASS")
    print("STAGING_HEALTH_AND_UNAUTH_DENIAL=PASS")
    print("FULL_BROWSER_MFA_SSO=NOT_YET_VERIFIED")

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(str(error)) from None

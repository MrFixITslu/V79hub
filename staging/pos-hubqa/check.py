#!/usr/bin/env python3
"""Read-only POS/Hub stage acceptance preflight. Never prints tokens or secrets."""
import json
import ipaddress
import re
import stat
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

STAGE_NET = "v79pos-hubqa-20261109_stage_internal"
HUB_ROOT = Path("/home/firelion/v79-hub-pos-hubqa-20261109")

def ensure(ok, msg):
    if not ok:
        raise RuntimeError("PRIVATE_STAGE_CHECK_FAILED: " + msg)

def inspect(name):
    data = subprocess.check_output(["docker", "inspect", name], text=True)
    return json.loads(data)[0]

def env(container):
    return dict(s.split("=", 1) for s in container["Config"]["Env"] if "=" in s)

def binding(container, internal, expected):
    # Docker on this stage host sometimes retains the loopback PortBindings
    # declaration while failing to install the port publisher. The stage is
    # accessed via its private Docker IP over an owner-only SSH tunnel.
    declared = (container["HostConfig"].get("PortBindings") or {}).get(internal) or []
    actual = (container["NetworkSettings"].get("Ports") or {}).get(internal) or []
    expected_value = {"HostIp": expected[0], "HostPort": expected[1]}
    return len(declared) == 1 and all(
        item.get("HostIp") == expected_value["HostIp"] and
        item.get("HostPort") == expected_value["HostPort"]
        for item in declared + actual
    )


def private_address(container):
    address = container["NetworkSettings"]["Networks"][STAGE_NET].get("IPAddress", "")
    try:
        ip = ipaddress.ip_address(address)
        ensure(ip.version == 4 and ip.is_private, "Stage has no private IPv4")
    except ValueError:
        ensure(False, "Stage IP is invalid")
    return str(ip)


def approved_hub_image(stage_hub):
    visual = HUB_ROOT / "approved-dashboard-visual.json"
    dashboard = HUB_ROOT / "approved-dashboard-alignment.json"
    perms = HUB_ROOT / "approved-login-assets-perms.json"
    if visual.exists():
        ensure(visual.is_file() and not visual.is_symlink() and
               stat.S_IMODE(visual.stat().st_mode) == 0o600 and
               not dashboard.exists() and
               perms.is_file() and not perms.is_symlink() and
               stat.S_IMODE(perms.stat().st_mode) == 0o600,
               "Visual dashboard and parent image pins are not private/exclusive")
        pin = json.loads(visual.read_text())
        parent = json.loads(perms.read_text())
        tag = "v79hub:pos-hubqa-dashboard-visual-20261109-r1"
        source = "localhost/v79-hub-login-connected:20261109-r1"
        base = "v79hub:pos-hubqa-ui-v3-styled-perms-20261109-r1"
        approved_image = json.loads(subprocess.check_output(
            ["docker", "image", "inspect", tag], text=True))[0]
        candidate = json.loads(subprocess.check_output(
            ["docker", "image", "inspect", source], text=True))[0]
        expected_visual = {
            "src/components/HubOverview.tsx":
                "b00c05056dd7a8dfcfb6055425644d26ac6880472b714b17461995b16a381096",
            "src/components/Sidebar.tsx":
                "c690df486b7f43d606ce50486bb94e077eccd33a8ed090e1009920537de5cce0",
        }
        source_map = pin.get("changed_files_sha256")
        protected_map = pin.get("protected_file_sha256")
        expected_protected = (
            "src/App.tsx",
            "src/components/Login.tsx",
            "src/index.css",
            "src/types.ts",
            "src/lib/appLaunch.ts",
            "src/lib/dashboardTruth.ts",
            "src/components/AdminConsole.tsx",
            "src/components/OwnerAssistant.tsx",
            "src/components/WorkforceActionPanel.tsx",
        )
        ensure(pin.get("dashboard_image") == tag and
               pin.get("base_stage_image") == base and
               pin.get("base_stage_image_id") == parent.get("image_id") and
               pin.get("dashboard_source_image") == source and
               pin.get("dashboard_source_image_id") == candidate["Id"] and
               stage_hub["Config"]["Image"] == tag and
               stage_hub["Image"] == pin.get("image_id") and
               approved_image["Id"] == pin.get("image_id") and
               source_map == expected_visual and
               isinstance(protected_map, dict) and
               set(protected_map) == set(expected_protected),
               "Visual stage image or immutable component source pin mismatch")
        for path, sha in {**source_map, **protected_map}.items():
            ensure(isinstance(sha, str) and
                   re.fullmatch("[a-f0-9]{64}", sha) is not None,
                   "Invalid visual stage hash")
            actual = subprocess.check_output(
                ["docker", "exec", "v79-hub-pos-hubqa", "sha256sum",
                 "/app/" + path], text=True).split()[0]
            ensure(actual == sha,
                   "Visual stage source changed: " + path)
        return

    if dashboard.exists():
        ensure(dashboard.is_file() and not dashboard.is_symlink() and
               stat.S_IMODE(dashboard.stat().st_mode) == 0o600 and
               perms.is_file() and not perms.is_symlink() and
               stat.S_IMODE(perms.stat().st_mode) == 0o600,
               "Dashboard/previous login stage pins unsafe")
        record = json.loads(dashboard.read_text())
        parent = json.loads(perms.read_text())
        tag = "v79hub:pos-hubqa-dashboard-aligned-20261109-r1"
        source = "localhost/v79-hub-login-connected:20261109-r1"
        base = "v79hub:pos-hubqa-ui-v3-styled-perms-20261109-r1"
        identity = record.get("image_id")
        actual_image = json.loads(subprocess.check_output(
            ["docker", "image", "inspect", tag], text=True))[0]
        approved_source = json.loads(subprocess.check_output(
            ["docker", "image", "inspect", source], text=True))[0]
        sha_map = record.get("changed_files_sha256")
        files = ("src/App.tsx", "src/components/HubOverview.tsx",
                 "src/components/Sidebar.tsx")
        ensure(record.get("dashboard_image") == tag and
               record.get("base_stage_image") == base and
               record.get("base_stage_image_id") == parent.get("image_id") and
               record.get("dashboard_source_image") == source and
               record.get("dashboard_source_image_id") == approved_source["Id"] and
               isinstance(identity, str) and
               re.fullmatch(r"sha256:[a-f0-9]{64}", identity) and
               stage_hub["Config"]["Image"] == tag and
               stage_hub["Image"] == identity and
               actual_image["Id"] == identity and
               isinstance(sha_map, dict) and set(sha_map) == set(files),
               "Stage dashboard image identity/source pin mismatch")
        for path in files:
            expected = sha_map[path]
            ensure(isinstance(expected, str) and
                   re.fullmatch(r"[a-f0-9]{64}", expected),
                   "Invalid dashboard component fingerprint")
            actual = subprocess.check_output(
                ["docker", "exec", "v79-hub-pos-hubqa", "sha256sum",
                 "/app/" + path], text=True).split()[0]
            ensure(actual == expected,
                   "Stage dashboard component differs: " + path)
        return

    perms = HUB_ROOT / "approved-login-assets-perms.json"
    styled = HUB_ROOT / "approved-login-style.json"
    if perms.exists():
        ensure(not styled.exists() and perms.is_file() and
               not perms.is_symlink() and
               stat.S_IMODE(perms.stat().st_mode) == 0o600,
               "Private login product-image pin is missing or unsafe")
        approved = json.loads(perms.read_text())
        tag = "v79hub:pos-hubqa-ui-v3-styled-perms-20261109-r1"
        previous = "v79hub:pos-hubqa-ui-v3-20261109"
        source = "v79hub:pos-hubqa-ui-v3-styled-20261109"
        css_hash = "ea182c2656cea2979412e611bf1e704d4068512f72d6d2db5eba33f80d5c544c"
        login_hash = "cb250f00742c5bc3f40f119cbc51f626a1fb94f542f254e27b0d3c6884b4c49b"
        image_id = approved.get("image_id")
        source_id = approved.get("derived_from_id")
        ensure(approved.get("image") == tag and
               approved.get("derived_from") == source and
               approved.get("previous_staging_image") == previous and
               approved.get("approved_css_sha256") == css_hash and
               approved.get("approved_login_sha256") == login_hash and
               isinstance(image_id, str) and
               re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) and
               isinstance(source_id, str) and
               re.fullmatch(r"sha256:[0-9a-f]{64}", source_id),
               "Unexpected styled login image pin")
        overlay = HUB_ROOT / "approved-login-overlay.json"
        ensure(overlay.is_file() and not overlay.is_symlink() and
               stat.S_IMODE(overlay.stat().st_mode) == 0o600,
               "Previous login overlay pin unavailable")
        parent = json.loads(overlay.read_text())
        ensure(approved.get("previous_staging_image_id") ==
               parent.get("overlay_image_id"),
               "Original stage image differs from preserved login overlay")
        built = json.loads(subprocess.check_output(
            ["docker", "image", "inspect", tag], text=True))[0]
        broken = json.loads(subprocess.check_output(
            ["docker", "image", "inspect", source], text=True))[0]
        ensure(stage_hub["Config"]["Image"] == tag and
               stage_hub["Image"] == image_id and
               built["Id"] == image_id and broken["Id"] == source_id,
               "Running stage image differs from exact validated permission repair")
        return

    overlay = HUB_ROOT / "approved-login-overlay.json"
    live_pin = HUB_ROOT / "approved-live-image.json"
    if styled.exists():
        ensure(not live_pin.exists() and overlay.is_file() and
               not overlay.is_symlink() and styled.is_file() and
               not styled.is_symlink() and
               stat.S_IMODE(styled.stat().st_mode) == 0o600 and
               stat.S_IMODE(overlay.stat().st_mode) == 0o600,
               "Stage presentation pin/parent login pin unsafe")
        record = json.loads(styled.read_text())
        parent = json.loads(overlay.read_text())
        style_tag = "v79hub:pos-hubqa-ui-v3-styled-20261109"
        source_tag = "localhost/v79-hub-login-connected:20261109-r1"
        css_hash = "ea182c2656cea2979412e611bf1e704d4068512f72d6d2db5eba33f80d5c544c"
        styled_id = record.get("styled_image_id")
        expected_source_id = record.get("source_image_id")
        ensure(record.get("styled_image") == style_tag and
               record.get("previous_image") == "v79hub:pos-hubqa-ui-v3-20261109" and
               record.get("previous_image_id") == parent.get("overlay_image_id") and
               record.get("source_image") == source_tag and
               expected_source_id == parent.get("source_image_id") and
               record.get("stylesheet_sha256") == css_hash and
               isinstance(styled_id, str) and
               re.fullmatch(r"sha256:[0-9a-f]{64}", styled_id) and
               stage_hub["Config"]["Image"] == style_tag and
               stage_hub["Image"] == styled_id,
               "Stage styled image identity or candidate style does not match")
        styled_image = json.loads(subprocess.check_output(
            ["docker", "image", "inspect", style_tag], text=True))[0]
        candidate = json.loads(subprocess.check_output(
            ["docker", "image", "inspect", source_tag], text=True))[0]
        ensure(styled_image["Id"] == styled_id and
               candidate["Id"] == expected_source_id,
               "Approved CSS image source was retagged")
        return

    # Prefer the reviewed 9 Nov frontend-only overlay; its underlying image
    # keeps the original private Hub backend, store and MFA configuration.
    overlay = HUB_ROOT / "approved-login-overlay.json"
    pin = HUB_ROOT / "approved-live-image.json"
    if overlay.exists():
        ensure(not pin.exists() and overlay.is_file() and
               not overlay.is_symlink() and
               stat.S_IMODE(overlay.stat().st_mode) == 0o600,
               "Conflicting or unsafe staging UI pin")
        record = json.loads(overlay.read_text())
        expected = "v79hub:pos-hubqa-ui-v3-20261109"
        expected_source = "localhost/v79-hub-login-connected:20261109-r1"
        image_id = record.get("overlay_image_id")
        source_id = record.get("source_image_id")
        ensure(record.get("overlay_image") == expected and
               record.get("source_image") == expected_source and
               isinstance(image_id, str) and
               re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) and
               isinstance(source_id, str) and
               re.fullmatch(r"sha256:[0-9a-f]{64}", source_id) and
               record.get("base_stage_image") == "v79hub:pos-hubqa-20261109",
               "Unexpected frontend overlay source or image ID")
        ensure(stage_hub["Config"]["Image"] == expected and
               stage_hub["Image"] == image_id,
               "Stage Hub did not run the exact pinned login overlay")
        built = json.loads(subprocess.check_output(
            ["docker", "image", "inspect", expected], text=True))[0]
        source = json.loads(subprocess.check_output(
            ["docker", "image", "inspect", expected_source], text=True))[0]
        ensure(built["Id"] == image_id and source["Id"] == source_id,
               "Overlay source or built image tags changed")
        return

    if not pin.exists():
        ensure(stage_hub["Config"]["Image"] == "v79hub:pos-hubqa-20261109",
               "Unpinned Hub staging image mismatch")
        return
    ensure(pin.is_file() and not pin.is_symlink() and
           stat.S_IMODE(pin.stat().st_mode) == 0o600,
           "Approved UI image pin is unsafe")
    data = json.loads(pin.read_text())
    tag, image_id = data.get("stage_image_tag"), data.get("production_image_id")
    ensure(isinstance(tag, str) and
           re.fullmatch(r"v79hub:pos-hubqa-live-[0-9a-f]{12}", tag) is not None and
           isinstance(image_id, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", image_id)
           is not None and tag.endswith(image_id[7:19]),
           "Approved UI image pin is invalid")
    ensure(stage_hub["Config"]["Image"] == tag and
           stage_hub["Image"] == image_id,
           "Stage Hub image differs from exact pinned live source")
    referenced = json.loads(subprocess.check_output(
        ["docker", "image", "inspect", tag], text=True))[0]
    ensure(referenced["Id"] == image_id, "Pinned staging image tag was replaced")

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
    approved_hub_image(stage_hub)
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

    # HTTP checks use the stage-only private bridge, where the running API
    # was confirmed reachable; host-loopback publication is not reliable.
    # Browser acceptance uses a private Acer SSH tunnel to these IPs.
    hub_code, _ = http_status("http://" + private_address(stage_hub) + ":3040/api/health")
    pos_url = "http://" + private_address(stage_pos) + ":8080"
    pos_code, pos_body = http_status(pos_url + "/ready")
    unauth_code, _ = http_status(pos_url + "/v1/me")
    ensure(hub_code == 200, "Stage Hub health endpoint is failing")
    ensure(pos_code == 200 and b'"database":"ok"' in pos_body,
           "Stage POS readiness check failed")
    ensure(unauth_code == 401,
           "Unauthenticated access to staging POS was not denied")
    if ((HUB_ROOT / "approved-dashboard-alignment.json").exists() or
            (HUB_ROOT / "approved-login-assets-perms.json").exists()):
        for name in ("academy", "ffpro", "marketing", "pos", "tiquet"):
            image_code, image_bytes = http_status(
                "http://" + private_address(stage_hub) +
                ":3040/assets/login-products/" + name + ".png")
            ensure(image_code == 200 and
                   image_bytes.startswith(bytes.fromhex("89504e470d0a1a0a")),
                   "Staging login product PNG inaccessible: " + name)
        print("STAGING_LOGIN_PRODUCT_IMAGES=PASS")
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

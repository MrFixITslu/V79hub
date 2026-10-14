#!/usr/bin/env python3
"""Build tested G3 commits and run synthetic isolated smoke tests; never deploy."""
import datetime
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import uuid

HUB = ("V79hub", "c42f671f4ccd4b268f6701989cceba0ba27b5dbd",
       "19ac2c136889bc9f3139a8545298e18c86e60aaa", "v79-hub-g3:c42f671f4ccd")
MARKETING = ("V79Marketing", "b7934c03f0e3fd91f826af52e68b62422ef55616",
             "fbf0c80efa6c605178a2b1b4941f7c5cfd1e2919", "v79-marketing-g3:b7934c03f0e3")
NODE_BASE = "public.ecr.aws/docker/library/node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402"
LIVE = {
    "v79marketing-app": "sha256:0d6f09ef37d73f2826900a8e3232a6f5ef4839614c1f92b42455ef03acf2cbf3",
    "v79-hub": "sha256:26e959fbc07ace5cf20a1d3ea001229911014346c6eb1c89d629d88993bbca8a",
    "v79-business-agent": "sha256:3d5f280fb5c8703b4a429e7541cbd8a079dea0cbb26e67df291ce9dee25e334f",
    "v79-hub-postgres": "sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24",
    "v79-tiquet-manager": "sha256:ee3deff332977160d66e0dbb448aef1e1e6d4418eac333e1feaf8a07c044715b",
    "tiquet-postgres": "sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685",
}
SOURCE = {
    "../server.ts": "378d018bf465b4280436e3a514f99f338821f0d1f23a184d9f9c75521aec39f6",
    "../src/lib/db.ts": "9ce563e77c218833222ae6b151c10dd87ffbec852bc70d7f3c4438d4be84ebae",
    "../src/lib/agentCampaignDrafts.ts": "13affd3e7980abf39e911519075344300de70a05a1afeb0bf4b821a992f3c03e",
    "../src/lib/constants.ts": "93d4d281882192cca2f256e4dc9fcb76c3b9a8474c4dbbe8d17a67edf8e17f7c",
    "../src/lib/agentHubDrafts.ts": "068a5887d83dbb0995eff199328c449d582f9796271ca21c5f423a933efbd486",
    "../src/lib/auth.ts": "ff031f6fa243592e7bb2ac79a9b218a123f60f427092bdfde0c94dd5095a9058",
    "../src/lib/hubEntitlement.ts": "09386940de2df40b0d303a5afe476e56c67fc8aca97e5576e404b41f9cc2650b",
    "../src/lib/hubManagedLink.ts": "0803bd482b80a41d5a034dcfa9abd8a3aef74d20a3b644a940fe3fadeab6c842",
    "../src/lib/creditService.ts": "77ee5e0a9990c785ce5e9476ccabb706795566085f816f26063951e5bacc0e67",
    "../src/lib/publisherEntitlement.ts": "7f64336f0aadc85bc1771d1a3bc5eb05eabb35d57327e8858c4c0bfe7f2a6421",
    "../src/lib/tokenVault.ts": "53093532bdbb2c38a832243abaef4b4f4b862a8090a2b9b38b569fb48a39b35b",
    "../src/lib/socialProviders.ts": "a4239cabd27255a6a6019c33c767e052d299fd2a8113e4309a2672206b27c6c7",
    "../src/lib/publisher.ts": "7339623a00cf019d5d0aa5cd2a64bb9c8c29056909052a8358dc3a946c28849c",
    "../src/lib/platform.ts": "7c3d91d5502de13cf282b8ac5f87089a2f57984876c5334ea495a21aaf84173c",
    "../src/lib/hubIdentityBoundary.ts": "c3008c2ff288bcc390923e05c148145306b454b103ed37f1e9f7a5e2bd92f251",
    "../src/lib/hubProvisioning.ts": "6afafc9264bba3a6d69c0fa9ebfe86c1ba2e0349d2d7408263882b8eb2d5ea96",
    "../src/lib/platformEvents.ts": "30201a5e8890f9c45f9362cf0a8625b7ae502962012642ca92c264bd4b7d90c8",
}
NODE_SOURCE = r"""
const fs=require('node:fs'),crypto=require('node:crypto');
const b=fs.readFileSync('/app/dist/server.cjs.map');
if(b.length>2097152)throw Error('Source map too large');
const m=JSON.parse(b),out={};
for(let i=0;i<m.sources.length;i++)if(!m.sources[i].includes('node_modules')&&typeof m.sourcesContent?.[i]==='string')
  out[m.sources[i]]=crypto.createHash('sha256').update(m.sourcesContent[i]).digest('hex');
console.log(JSON.stringify(out));
"""


def run(args, *, cwd=None, visible=False, timeout=30):
    r = subprocess.run(args, cwd=cwd, stdout=None if visible else subprocess.PIPE,
                       stderr=None if visible else subprocess.PIPE, timeout=timeout)
    if r.returncode:
        raise RuntimeError("Command failed; sensitive output withheld")
    return r.stdout


def live():
    result = {}
    for name, expected in LIVE.items():
        info = json.loads(run(["docker", "inspect", name]))[0]
        state = info["State"]
        if info["Image"] != expected or not state.get("Running") or state.get("Health", {}).get("Status") != "healthy":
            raise RuntimeError("Live image/health drift: " + name)
        result[name] = {"id": info["Id"], "image": info["Image"], "started_at": state["StartedAt"]}
    return result


def normalize_public_checkout(checkout):
    """Public source is readable in a non-root image; the parent stays private."""
    for directory, dirs, files in os.walk(checkout, followlinks=False):
        dirs[:] = [name for name in dirs if name != ".git"]
        p = pathlib.Path(directory)
        if p.is_symlink():
            raise RuntimeError("Unexpected source directory symlink")
        p.chmod(0o755)
        for name in dirs:
            if (p / name).is_symlink():
                raise RuntimeError("Unexpected source directory symlink")
        for name in files:
            file = p / name
            if file.is_symlink() or not file.is_file():
                raise RuntimeError("Unexpected non-regular source file")
            file.chmod(0o755 if file.stat().st_mode & 0o111 else 0o644)


def smoke_program(repo):
    versions = {"proxy-addr": "2.0.8", "source-map-js": "1.2.2"}
    if repo == HUB[0]:
        files = ["tests/marketing-production-routes.test.mjs", "tests/workforce-actions.test.mjs",
                 "tests/workforce-action-routes.test.mjs", "tests/workforce-release-worker.test.mjs"]
        child_args = ["--test"] + files
    elif repo == MARKETING[0]:
        versions["ip-address"] = "10.7.4"
        files = ["dist/production-renderer-smoke.mjs"]
        child_args = files
    else:
        raise RuntimeError("Unknown candidate repository")
    return ("const fs=require('node:fs'),cp=require('node:child_process');"
            "for(const[p,v]of Object.entries(" + json.dumps(versions) + "))"
            "if(require('/app/node_modules/'+p+'/package.json').version!==v)throw Error('Runtime dependency version mismatch');"
            "for(const f of " + json.dumps(files) + ")fs.accessSync(f,fs.constants.R_OK);"
            "console.log('NONROOT_SOURCE_READABILITY_AND_PATCHED_RUNTIME_DEPENDENCIES_PASS');"
            "cp.execFileSync(process.execPath," + json.dumps(child_args) + ",{stdio:'inherit',timeout:120000});")


def main():
    os.umask(0o077)
    if run(["hostname", "-s"]).decode().strip() != "v79sl":
        raise RuntimeError("Wrong server")
    before = live()
    compose = pathlib.Path("/home/firelion/V79Marketing/docker-compose.yml")
    if hashlib.sha256(compose.read_bytes()).hexdigest() != "306916c23ffdfe2349cee27091cf09672f1ed29dd5045dfcd743ac4276cc58ab":
        raise RuntimeError("Marketing Compose drift")
    current = json.loads(run(["docker", "exec", "v79marketing-app", "node", "-e", NODE_SOURCE]))
    if current != SOURCE:
        raise RuntimeError("Live Marketing source drift")
    if shutil.disk_usage("/home/firelion").free < 8 * 1024 ** 3:
        raise RuntimeError("Insufficient free disk for isolated candidate builds")
    print("EXACT_LIVE_SOURCE_AND_IMAGE_BASELINE_PASS", flush=True)
    root = pathlib.Path(tempfile.mkdtemp(prefix="v79-g3-build-", dir="/home/firelion"))
    print("BUILD_DIRECTORY=" + str(root), flush=True)
    candidates = {}
    for repo, commit, tree, tag in (HUB, MARKETING):
        print("STAGE=build-" + repo, flush=True)
        checkout = root / repo
        checkout.mkdir()
        run(["git", "init", "--quiet", str(checkout)])
        run(["git", "-C", str(checkout), "fetch", "--depth", "1",
             "https://github.com/MrFixITslu/" + repo + ".git", commit], timeout=180)
        run(["git", "-C", str(checkout), "checkout", "--quiet", "--detach", "FETCH_HEAD"])
        if run(["git", "-C", str(checkout), "rev-parse", "HEAD"]).decode().strip() != commit:
            raise RuntimeError("Candidate commit mismatch")
        if run(["git", "-C", str(checkout), "rev-parse", "HEAD^{tree}"]).decode().strip() != tree:
            raise RuntimeError("Candidate tree mismatch")
        normalize_public_checkout(checkout)
        run(["docker", "build", "--build-arg", "NODE_BASE=" + NODE_BASE,
             "--label", "org.opencontainers.image.revision=" + commit,
             "--tag", tag, str(checkout)], visible=True, timeout=1800)
        image = json.loads(run(["docker", "image", "inspect", tag]))[0]
        if image.get("Config", {}).get("Labels", {}).get("org.opencontainers.image.revision") != commit:
            raise RuntimeError("Candidate revision label mismatch")
        candidates[repo] = {"image": image["Id"], "commit": commit, "tree": tree, "tag": tag}

    owner = str(uuid.uuid4())
    owned = []
    try:
        for repo in (HUB[0], MARKETING[0]):
            name = "v79-g3-candidate-smoke-" + repo.lower() + "-" + owner
            owned.append(name)
            args = ["docker", "run", "--rm", "--name", name, "--label", "v79.g3.build-owner=" + owner,
                    "--network", "none", "--read-only", "--user", "node", "--cap-drop", "ALL",
                    "--security-opt", "no-new-privileges", "--memory", "768m", "--cpus", "2",
                    "--tmpfs", "/tmp:rw,nosuid,nodev,size=192m", "--entrypoint", "node"]
            if repo == HUB[0]:
                args += ["--env", "NODE_OPTIONS=--import=./tests/isolated-env.mjs"]
            args += [candidates[repo]["image"], "--input-type=commonjs", "-e", smoke_program(repo)]
            print("STAGE=isolated-smoke-" + repo, flush=True)
            run(args, visible=True, timeout=180)
    finally:
        for name in owned:
            r = subprocess.run(["docker", "inspect", name], capture_output=True, timeout=30)
            if r.returncode == 0:
                info = json.loads(r.stdout)[0]
                if (info.get("Config", {}).get("Labels") or {}).get("v79.g3.build-owner") != owner:
                    raise RuntimeError("Owned scratch identity mismatch; container not removed")
                run(["docker", "rm", "--force", name])
    if live() != before:
        raise RuntimeError("Live containers changed during build; stop for reconciliation")
    receipt = {"created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "mode": "build-and-synthetic-isolated-smoke-only", "deployment_performed": False,
               "candidates": candidates, "live_containers": before, "live_identity_unchanged": True}
    (root / "candidate-build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"build_directory": str(root), "candidates": candidates}, indent=2), flush=True)
    print("G3_CANDIDATES_BUILT_ISOLATED_SMOKES_PASS_LIVE_SERVICES_UNCHANGED", flush=True)
    print("ENCRYPTED_BACKUP_RESTORE_AND_CUTOVER_STILL_REQUIRED", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("STOP: candidate build interrupted; no live recreation requested", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print("STOP: candidate build failed; no live recreation requested", file=sys.stderr)
        if isinstance(exc, RuntimeError):
            print(str(exc), file=sys.stderr)
        sys.exit(1)

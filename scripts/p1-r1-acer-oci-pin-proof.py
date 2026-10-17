#!/usr/bin/env python3
"""Acer-only read-only OCI manifest-vs-config identity proof for Docker 29.

Fully streams one already-verified GPG Docker-save OCI TAR, holds ONLY small
image manifests/config blobs in bounded process memory, and counts links:
pinned Docker image ID -> OCI manifest digest -> config digest -> Podman config.
Never emits unknown hashes, manifest contents, image names/tags/env/secrets;
never imports, tags, pulls, starts containers, writes plain files or uses SSH.
No release authority is conferred; NO-GO unless independent final restore.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tarfile

EXPECTED = {
    "v79-hub": "d0dfba263dbfec8a08e6c46995c2172daf234206fe8d0f6484bb98b938cd3c65",
    "v79-tiquet-manager": "5e69de603794f0e318c75a10eefd0f62d1d80f75fb40979658416292ce44ec42",
    "v79-hub-postgres": "b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24",
    "tiquet-postgres": "cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685",
}
ROLLBACK = "4a9f5868b8c5b7df818225478fc56836e9e6acf9e19c2a8c6faeebe58cec1698"
PINS = set(EXPECTED.values()) | {ROLLBACK}
HEX = re.compile(r"[0-9a-f]{64}\Z")
OCI_BLOB = re.compile(r"blobs/sha256/([0-9a-f]{64})\Z")
DOCKER_JSON = re.compile(r"([0-9a-f]{64})\.json\Z")
IMAGE_ARCHIVE = "exact-images-and-rollback.tar.gpg"

class Stop(Exception):
    pass

def need(condition, reason):
    if not condition:
        raise Stop(reason)

def digest(raw):
    if not isinstance(raw, str):
        return None
    h = raw.removeprefix("sha256:")
    return h if HEX.fullmatch(h) else None

def config_paths(manifest):
    need(isinstance(manifest, list) and len(manifest) == 5,
         "OCI_DOCKER_MANIFEST_COUNT_INVALID")
    seen = set()
    for item in manifest:
        need(isinstance(item, dict), "OCI_CONFIG_REFERENCE_INVALID")
        p = item.get("Config")
        need(isinstance(p, str), "OCI_CONFIG_REFERENCE_INVALID")
        match = OCI_BLOB.fullmatch(p.removeprefix("./")) or DOCKER_JSON.fullmatch(p.removeprefix("./"))
        need(match is not None, "OCI_CONFIG_REFERENCE_FORMAT_INVALID")
        need(match.group(1) not in seen, "OCI_CONFIG_DIGEST_DUPLICATE")
        seen.add(match.group(1))
    return seen

def manifest_link(doc):
    if not isinstance(doc, dict) or doc.get("schemaVersion") != 2:
        return None
    config = doc.get("config")
    layers = doc.get("layers")
    if not isinstance(config, dict) or not isinstance(layers, list):
        return None
    target = digest(config.get("digest"))
    return target

def index_links(doc):
    if not isinstance(doc, dict) or not isinstance(doc.get("manifests"), list):
        return None
    results = []
    for d in doc["manifests"]:
        if not isinstance(d, dict):
            return None
        candidate = digest(d.get("digest"))
        if not candidate:
            return None
        results.append(candidate)
    return results

def prep(root):
    need(socket.gethostname() == "firelion-Aspire-A315-51", "RUN_ONLY_ON_ACER")
    need(os.getuid() != 0 and os.geteuid() != 0, "ROOT_REJECTED")
    need(not any(os.environ.get(k) for k in ("CONTAINER_HOST", "DOCKER_HOST")),
         "REMOTE_CONTAINER_CONTEXT_REJECTED")
    need(shutil.which("gpg"), "GPG_UNAVAILABLE")
    root = root.expanduser().absolute()
    need(root.is_dir() and not root.is_symlink() and (root.stat().st_mode & 0o077) == 0,
         "ORIGINAL_ARCHIVE_DIRECTORY_INVALID")
    need(not (root / "CAPTURE_INCOMPLETE").exists(), "ARCHIVE_SET_INCOMPLETE")
    mf = root / "ciphertext-manifest.json"
    need(mf.is_file() and not mf.is_symlink(), "ARCHIVE_MANIFEST_MISSING")
    data = json.loads(mf.read_text())
    need(data.get("schema") == 1 and data.get("status") == "CAPTURED_NOT_RESTORED" and
         data.get("images") == {key:"sha256:"+v for key,v in EXPECTED.items()} and
         data.get("rollbackHub") == "sha256:"+ROLLBACK and
         isinstance(data.get("files"), list) and len(data["files"]) == 14,
         "PINNED_ORIGINAL_CAPTURE_SET_INVALID")
    entries = [e for e in data["files"] if isinstance(e, dict)
               and e.get("name") == IMAGE_ARCHIVE]
    need(len(entries) == 1, "IMAGE_CIPHERTEXT_ENTRY_INVALID")
    p = root / IMAGE_ARCHIVE
    need(p.is_file() and not p.is_symlink() and (p.stat().st_mode & 0o077) == 0,
         "IMAGE_CIPHERTEXT_INVALID")
    need(entries[0].get("bytes") == p.stat().st_size, "IMAGE_CIPHERTEXT_SIZE_CHANGED")
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda:f.read(1 << 20), b""):
            h.update(block)
    need(h.hexdigest() == entries[0].get("sha256"), "IMAGE_CIPHERTEXT_HASH_CHANGED")
    return p

def stream_proof(encrypted):
    p = subprocess.Popen(["gpg","--batch","--quiet","--decrypt",str(encrypted)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL)
    configs = None
    index_doc = None
    objects = {}
    scanned = 0
    try:
        with tarfile.open(fileobj=p.stdout,mode="r|") as tf:
            for member in tf:
                name = member.name.removeprefix("./")
                if name in ("manifest.json","index.json"):
                    need(member.isfile() and 0 < member.size <= 2*1024*1024,
                         "OCI_INDEX_OR_MANIFEST_SIZE_INVALID")
                    raw = tf.extractfile(member).read(member.size+1)
                    need(len(raw) == member.size, "OCI_INDEX_OR_MANIFEST_READ_INVALID")
                    doc = json.loads(raw)
                    if name == "manifest.json":
                        need(configs is None, "OCI_DUPLICATE_DOCKER_MANIFEST")
                        configs = config_paths(doc)
                    else:
                        need(index_doc is None, "OCI_DUPLICATE_INDEX")
                        index_doc = index_links(doc)
                        need(index_doc is not None, "OCI_INDEX_INVALID")
                    continue
                match = OCI_BLOB.fullmatch(name) or DOCKER_JSON.fullmatch(name)
                if not match or not member.isfile() or not (0 < member.size <= 2*1024*1024):
                    continue  # layer TARs/blobs may be huge
                need(scanned < 1000 and name not in objects,
                     "OCI_SMALL_BLOB_LIMIT_OR_DUPLICATE")
                stream=tf.extractfile(member)
                need(stream is not None, "OCI_BLOB_READ_INVALID")
                sha=hashlib.sha256()
                payload=bytearray()
                n=0
                for chunk in iter(lambda:stream.read(131072), b""):
                    n+=len(chunk)
                    need(n <= member.size, "OCI_BLOB_LENGTH_INVALID")
                    sha.update(chunk)
                    payload.extend(chunk)
                need(n == member.size, "OCI_BLOB_TRUNCATED")
                scanned+=1
                blob_id=match.group(1)
                # Do not trust SHA names unless content actually matches.
                good=sha.hexdigest() == blob_id
                conf=None
                idx=None
                if good:
                    try:
                        data=json.loads(payload)
                        conf=manifest_link(data)
                        idx=index_links(data)
                    except (ValueError, UnicodeDecodeError):
                        pass  # valid hashed image CONFIG need not be a JSON manifest
                objects[name]=(blob_id,good,conf,idx)
                del payload
        p.stdout.close()
        need(p.wait(timeout=90) == 0, "OCI_ARCHIVE_GPG_STREAM_INVALID")
    finally:
        if p.stdout and not p.stdout.closed:
            p.stdout.close()
        if p.poll() is None:
            p.kill()
        p.wait()

    need(configs is not None, "OCI_DOCKER_MANIFEST_ABSENT")
    # Map the digest of each verified blob to its linked configuration digest.
    blobs = {digest: (good, conf, idx) for digest,good,conf,idx in objects.values()}
    verified_configs = {d for d in configs if d in blobs and blobs[d][0]}
    manifests = {d: info[1] for d,info in blobs.items()
                 if info[0] and info[1] in verified_configs}
    indexes = {d: info[2] for d,info in blobs.items()
               if info[0] and info[2] is not None}
    manifest_to_config = {d:config for d,config in manifests.items()}
    # OCI index descriptors often directly refer to image manifest digests.
    index_to_configs = {
        d: {manifests.get(child) for child in children if manifests.get(child) is not None}
        for d,children in indexes.items()
    }
    matched_by_manifest = {pin:manifests[pin] for pin in PINS if pin in manifests}
    matched_by_index = {pin:index_to_configs[pin] for pin in PINS if pin in index_to_configs}
    ref_count = sum(1 for d in (index_doc or []) if d in manifests or d in indexes)
    print("R1_DOCKER_CONFIG_SHA_VALID=%d/5" % len(verified_configs))
    print("R1_OCI_SMALL_HASHED_BLOBS=%d" % len(blobs))
    print("R1_OCI_LINKED_IMAGE_MANIFESTS=%d" % len(manifests))
    print("R1_OCI_IMAGE_INDEX_OBJECTS=%d" % len(indexes))
    print("R1_OCI_INDEX_REFERENCES_RESOLVED=%d/%d" % (ref_count,len(index_doc or [])))
    print("R1_PINNED_IDS_AS_MANIFEST_DIGESTS=%d/5" % len(matched_by_manifest))
    print("R1_PINNED_IDS_AS_INDEX_DIGESTS=%d/5" % len(matched_by_index))
    print("R1_PINNED_MANIFEST_UNIQUE_CONFIGS=%d" % len(set(matched_by_manifest.values())))
    print("R1_PINNED_INDEX_UNIQUE_CONFIGS=%d" %
          len(set.union(set(), *matched_by_index.values())))
    print("R1_OCI_CONFIG_RELATIONS_FULLY_VERIFIED=" +
          ("YES" if len(configs) == len(verified_configs) == 5 else "NO"))
    print("R1_DATABASE_RESTORE=NOT_PERFORMED")
    print("R1_CUSTOMER_RELEASE=NO_GO")
    # No PASS signal for provenance unless all five pins match one of the
    # genuinely verified descriptor types and map to five distinct configs.
    by_manifest = len(matched_by_manifest) == 5 and len(set(matched_by_manifest.values())) == 5
    by_index = (len(matched_by_index) == 5
                and all(len(configs) == 1 for configs in matched_by_index.values())
                and len(set.union(set(), *matched_by_index.values())) == 5)
    need(len(verified_configs) == 5 and (by_manifest or by_index),
         "OCI_PIN_TO_CONFIG_PROVENANCE_NOT_PROVEN")
    print("R1_PINNED_OCI_ID_TO_CONFIG_PROVENANCE=PASS_OFFLINE_ONLY")

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--backup",type=Path,required=True)
    args=a.parse_args()
    print("R1_OCI_DIAGNOSTIC=NO_MUTATION",flush=True)
    stream_proof(prep(args.backup))

if __name__ == "__main__":
    try:
        main()
    except (Stop,OSError,ValueError,KeyError,tarfile.TarError,
            subprocess.TimeoutExpired) as e:
        print("STOP=" + str(e) if isinstance(e,Stop)
              else "STOP=OCI_PROVENANCE_DIAG_FAILED_REDACTED")
        print("R1_CUSTOMER_RELEASE=NO_GO")
        sys.exit(1)

#!/usr/bin/env python3
"""Generate SHA-pinned, Acer-only S2 PG image-cache proof from prior verified sources.

NO production access, decryption, container start, swap/network change or image import.
"""
import hashlib
import os
from pathlib import Path
import socket
import subprocess

ROOT = Path.home() / 'Downloads'
OLD = {
    'v79_s2_offline_oci_proof_v2.py': '71cbba066c56c070978d731dcb0c95c042a8c8ba4feefd83c7ef120d0b40ca62',
    'RUN_V79_S2_Guarded_Offline_OCI_v3.sh': '419896bd9971b3832b0d06ec67efc426f76a7884b169784a54b6d90e77ae9e09',
    'RUN_V79_S2_Reversible_Isolation_v3.sh': '0e9cbbb0aa4557fbe9b929c1fe988911cdf53762b54a1218c1e9030239d981b5',
}

def sha(raw):
    return hashlib.sha256(raw.encode()).hexdigest()

def replace_one(s, a, b):
    if s.count(a) != 1:
        raise RuntimeError('SOURCE_DRIFT')
    return s.replace(a, b, 1)

def read_verified(name, pin):
    p = ROOT / name
    if not p.is_file() or p.is_symlink() or p.stat().st_uid != os.getuid():
        raise RuntimeError('ORIGINAL_FILE_MISSING_OR_UNSAFE')
    text = p.read_text()
    if sha(text) != pin:
        raise RuntimeError('ORIGINAL_HASH_CHANGED')
    return text

CACHE_GATE = '''def cache_gate(pins, blobs):
    """Match exact S2 OCI Linux/amd64 config digests to local Podman PG images."""
    rootless = subprocess.run(['podman', '--remote=false', 'info', '--format',
                               '{{.Host.Security.Rootless}}'],
                              capture_output=True, text=True, timeout=35)
    need(rootless.returncode == 0 and rootless.stdout.strip() == 'true',
         'LOCAL_ROOTLESS_PODMAN_REQUIRED')

    def podman_json(argv):
        result = subprocess.run(['podman', '--remote=false'] + argv,
                                capture_output=True, text=True, timeout=35)
        need(result.returncode == 0, 'LOCAL_PODMAN_INVENTORY_UNAVAILABLE')
        return json.loads(result.stdout)

    imgs = podman_json(['images', '--no-trunc', '--format', 'json'])
    need(isinstance(imgs, list) and 0 < len(imgs) <= 200,
         'LOCAL_PODMAN_IMAGES_UNEXPECTED')
    cache = {}
    for row in imgs:
        need(isinstance(row, dict), 'LOCAL_IMAGE_RECORD_INVALID')
        ident = digest(row.get('Id') or row.get('ID'))
        need(ident is not None, 'LOCAL_IMAGE_ID_INVALID')
        info = podman_json(['image', 'inspect', 'sha256:' + ident])
        need(isinstance(info, list) and len(info) == 1 and
             digest(info[0].get('Id') or info[0].get('ID')) == ident,
             'LOCAL_IMAGE_INSPECT_UNEXPECTED')
        meta = info[0]
        env = (meta.get('Config') or {}).get('Env') or []
        need(isinstance(env, list), 'IMAGE_ENV_INVALID')
        cache[ident] = (str(meta.get('Os') or meta.get('OS') or '').lower(),
                        str(meta.get('Architecture') or '').lower(),
                        [v for v in env if isinstance(v, str)])
    verified = 0
    for role, major in [('tiquet-postgres', '16'), ('v79-hub-postgres', '17')]:
        resolved = resolve_image(pins[role], blobs)
        need(len(resolved) == 1, 'PG_OCI_CONFIG_AMBIGUOUS')
        config_id = next(iter(resolved))
        exists = cache.get(config_id)
        matched = (exists is not None and exists[0:2] == ('linux', 'amd64')
                   and exists[2].count('PG_MAJOR=' + major) == 1)
        print('CACHE_' + role.upper().replace('-', '_') + '=' +
              ('PASS_EXACT_IMAGE_CONFIG' if matched else 'STOP_NOT_EXACT'))
        verified += int(matched)
    print('S2_PG_CACHED_IMAGE_IDENTITY=' +
          ('PASS_2_OF_2' if verified == 2 else 'STOP_NOT_VERIFIED'))
    need(verified == 2, 'PG_IMAGE_CACHE_NOT_EXACT')

'''

def main():
    if socket.gethostname() != 'firelion-Aspire-A315-51' or os.getuid() == 0:
        raise RuntimeError('ACER_NONROOT_ONLY')
    os.umask(0o077)
    src = {name: read_verified(name, pin) for name,pin in OLD.items()}
    py = replace_one(src['v79_s2_offline_oci_proof_v2.py'],
        '\ndef synthetic_test():\n', '\n' + CACHE_GATE + 'def synthetic_test():\n')
    py = replace_one(py,
        '        ok = evaluate(pins, blobs, extras, counts)\n',
        '        ok = evaluate(pins, blobs, extras, counts)\n'
        '        if ok:\n            cache_gate(pins, blobs)\n')
    pyname = 'v79_s2_offline_oci_pg_cache_v3.py'
    inname = 'RUN_V79_S2_Guarded_Offline_OCI_v4.sh'
    outname = 'RUN_V79_S2_Reversible_Isolation_v4.sh'
    inner = src['RUN_V79_S2_Guarded_Offline_OCI_v3.sh']
    inner = replace_one(inner, 'v79_s2_offline_oci_proof_v2.py', pyname)
    inner = replace_one(inner, OLD['v79_s2_offline_oci_proof_v2.py'], sha(py))
    outer = src['RUN_V79_S2_Reversible_Isolation_v3.sh']
    outer = outer.replace('RUN_V79_S2_Guarded_Offline_OCI_v3.sh', inname)
    outer = outer.replace('v79_s2_offline_oci_proof_v2.py', pyname)
    outer = replace_one(outer, OLD['v79_s2_offline_oci_proof_v2.py'], sha(py))
    outer = replace_one(outer, OLD['RUN_V79_S2_Guarded_Offline_OCI_v3.sh'], sha(inner))
    outputs = {pyname:py, inname:inner, outname:outer}
    # Validate all destination hashes before writing any file.
    for name, text in outputs.items():
        dest = ROOT / name
        if dest.is_symlink() or (dest.exists() and
            (not dest.is_file() or sha(dest.read_text()) != sha(text))):
            raise RuntimeError('DESTINATION_CONFLICT')
    for name, text in outputs.items():
        dest = ROOT / name
        if not dest.exists():
            with dest.open('x') as f:
                f.write(text)
        print(name + '=SHA256_' + sha(text)[:16] + '_VERIFIED')
    for name in (inname, outname):
        if subprocess.run(['bash', '-n', str(ROOT/name)],
                          stdout=subprocess.DEVNULL).returncode:
            raise RuntimeError('SHELL_SYNTAX_FAIL')
    if subprocess.run(['python3', '-B', str(ROOT/pyname), '--self-test'],
                      stdout=subprocess.DEVNULL).returncode:
        raise RuntimeError('OCI_SELF_TEST_FAIL')
    print('S2_CACHE_GATE_PREPARATION=PASS')
    print('OFFLINE_RECOVERY_EXECUTION=NOT_STARTED')

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError) as err:
        print('SAFE_STOP=' + str(err))
        raise SystemExit(2)

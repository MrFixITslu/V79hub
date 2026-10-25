#!/usr/bin/env python3
"""Private durable release state. No Docker, SSH, deployment or approval API.

The caller supplies already verified models and pins the returned digest outside
this file. A checksum detects corruption; it is not owner authorization or a MAC.
Secrets may be present. Never print the payload or upload it to CI artifacts.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat

LIMIT = 16 * 1024 * 1024
SCHEMA = 'v79-private-release-context-v1'


class Refused(ValueError):
    pass


def encode(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=True, allow_nan=False).encode()
    except (ValueError, TypeError):
        raise Refused('CONTEXT_JSON_INVALID') from None


def contract():
    spec = importlib.util.spec_from_file_location('release_contract',
        Path(__file__).with_name('paired-image-release-contract.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(payload):
    c = contract()
    if not isinstance(payload, dict) or set(payload) != {'schema', 'apps'}:
        raise Refused('CONTEXT_SCOPE_INVALID')
    if (payload['schema'] != SCHEMA or not isinstance(payload['apps'], dict)
            or set(payload['apps']) != set(c.CURRENT)):
        raise Refused('CONTEXT_SCOPE_INVALID')
    for name, app in payload['apps'].items():
        if not isinstance(app, dict) or set(app) != {
                'before', 'candidate', 'rollback', 'interpolation', 'ordered_inputs'}:
            raise Refused('CONTEXT_APP_SCOPE_INVALID')
        try:
            c.verify_models(app['before'], app['candidate'], app['rollback'],
                            {name: c.CURRENT[name]})
        except (c.Refused, KeyError, TypeError):
            raise Refused('CONTEXT_MODEL_CONTRACT_FAILED') from None
        env = app['interpolation']
        if not isinstance(env, dict) or any(
                not isinstance(k, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', k)
                or not isinstance(v, str) or '\x00' in v for k, v in env.items()):
            raise Refused('CONTEXT_INTERPOLATION_INVALID')
        inputs = app['ordered_inputs']
        if not isinstance(inputs, list) or not inputs:
            raise Refused('CONTEXT_INPUTS_INVALID')
        seen = set()
        for item in inputs:
            if not isinstance(item, dict) or set(item) != {'path', 'content', 'sha256'}:
                raise Refused('CONTEXT_INPUTS_INVALID')
            p, content = item['path'], item['content']
            if (not isinstance(p, str) or not p.startswith('/') or '\x00' in p
                    or '..' in Path(p).parts or p in seen or not isinstance(content, str)
                    or hashlib.sha256(content.encode()).hexdigest() != item['sha256']):
                raise Refused('CONTEXT_INPUT_INTEGRITY_FAILED')
            seen.add(p)
    if len(encode(payload)) > LIMIT:
        raise Refused('CONTEXT_TOO_LARGE')


def private_directory(path):
    """Open a caller-provisioned 0700 directory without following any symlink."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise Refused('CONTEXT_DIRECTORY_INVALID')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                              dir_fd=fd)
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise Refused('CONTEXT_DIRECTORY_NOT_PRIVATE')
        return fd
    except BaseException:
        os.close(fd)
        raise


def filename(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}\.json', name):
        raise Refused('CONTEXT_FILENAME_INVALID')


def save(directory, name, payload):
    """Create once, flush file+directory, return digest only. Never overwrite."""
    filename(name)
    validate(payload)
    raw = encode(payload)
    directory_fd = private_directory(directory)
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory_fd)
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return hashlib.sha256(raw).hexdigest()


def load(directory, name, expected_sha256):
    """Requires an external trusted digest; never recovers prices from live apps."""
    filename(name)
    if not isinstance(expected_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
        raise Refused('CONTEXT_EXTERNAL_DIGEST_REQUIRED')
    directory_fd = private_directory(directory)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_size > LIMIT):
                raise Refused('CONTEXT_FILE_NOT_PRIVATE_REGULAR')
            raw = stream.read(LIMIT + 1)
            after = os.fstat(stream.fileno())
            fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns',
                      'st_mode', 'st_uid', 'st_nlink')
            if any(getattr(after, k) != getattr(info, k) for k in fields):
                raise Refused('CONTEXT_CHANGED_DURING_READ')
    finally:
        os.close(directory_fd)
    if len(raw) > LIMIT or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise Refused('CONTEXT_EXTERNAL_DIGEST_MISMATCH')
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        raise Refused('CONTEXT_JSON_INVALID') from None
    validate(payload)
    if encode(payload) != raw:
        raise Refused('CONTEXT_NONCANONICAL_JSON')
    return payload

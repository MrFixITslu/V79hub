"""Pure Academy inspection contract. No Docker, network, files or lifecycle actions.

Review candidate only: the existing startup/cleanup runner does not import this.
Input is supplied by the caller; output is a fixed code, never inspected values.
"""
import re

OWNER = 'v79.private-academy-isolated'
SYNTHETIC = {'PORT': '18081', 'NODE_ENV': 'production',
             'ACADEMY_STANDALONE_ADMIN_ENABLED': '0',
             'V79_PLATFORM_SHARED_SECRET': '',
             'ACADEMY_COURSE_PUBLISH_MODE': 'disabled'}
TMPFS = {'/app/data': '64m', '/tmp': '16m'}


def environment(entries):
    if not isinstance(entries, list):
        return None
    result = {}
    for item in entries:
        if not isinstance(item, str) or '=' not in item:
            return None
        key, value = item.split('=', 1)
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key) or key in result:
            return None
        result[key] = value
    return result


def temporary_storage(value, size):
    if not isinstance(value, str):
        return False
    parts = value.split(',')
    if len(parts) != 7 or len(set(parts)) != 7:
        return False
    return set(parts) == {'rw', 'nosuid', 'nodev', 'size=' + size,
                          'uid=1000', 'gid=1000', 'mode=0700'}


def _validate(row, image, token, public_image_env):
    """Validate only CREATED/RUNNING. Not authorization to remove/start a resource.

    public_image_env must be independently reviewed, pinned image defaults.
    Never derive that allowlist from the container being validated.
    """
    if not isinstance(row, dict) or not isinstance(public_image_env, dict):
        return 'INVALID_INPUT'
    if not isinstance(image, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        return 'INVALID_EXPECTED_IMAGE'
    if not isinstance(token, str) or not re.fullmatch(r'[0-9a-f]{14}', token):
        return 'INVALID_EXPECTED_OWNER'
    conf = row.get('Config')
    host = row.get('HostConfig')
    state = row.get('State')
    network = row.get('NetworkSettings')
    if not all(isinstance(x, dict) for x in (conf, host, state, network)):
        return 'INVALID_INPUT'
    labels = conf.get('Labels')
    if not isinstance(labels, dict):
        return 'INVALID_INPUT'
    if (row.get('Name') != '/v79-isolated-academy-' + token or
            labels.get(OWNER) != token or 'com.docker.compose.project' in labels):
        return 'OWNERSHIP_MISMATCH'
    if row.get('Image') != image:
        return 'IMAGE_MISMATCH'
    if state.get('Status') not in ('created', 'running'):
        return 'STATE_NOT_ACCEPTED'
    if (any(state.get(k) for k in ('Paused', 'Restarting', 'Dead', 'OOMKilled')) or
            state.get('Running') is not (state['Status'] == 'running')):
        return 'STATE_INCONSISTENT'
    if conf.get('User') != '1000:1000':
        return 'USER_MISMATCH'
    if not isinstance(network.get('Networks'), dict):
        return 'INVALID_INPUT'
    networks = set(network['Networks'])
    if host.get('NetworkMode') != 'none' or networks not in (set(), {'none'}):
        return 'NETWORK_MISMATCH'
    if host.get('PortBindings'):
        return 'PORTS_NOT_ACCEPTED'
    if (host.get('Privileged') or host.get('ReadonlyRootfs') is not True or
            host.get('Binds') or host.get('Mounts') or host.get('VolumesFrom') or
            host.get('Devices') or host.get('DeviceRequests') or host.get('CapAdd') or
            host.get('PidMode') or host.get('UTSMode') or host.get('IpcMode') not in ('private', '') or
            host.get('Sysctls') or host.get('Links') or host.get('ExtraHosts') or
            host.get('GroupAdd') or host.get('UsernsMode') or
            host.get('CgroupnsMode') not in ('private', '')):
        return 'HOST_ISOLATION_MISMATCH'
    if host.get('CapDrop') != ['ALL'] or host.get('SecurityOpt') not in (
            ['no-new-privileges:true'], ['no-new-privileges']):
        return 'PRIVILEGE_RESTRICTION_MISMATCH'
    if ((host.get('RestartPolicy') or {}).get('Name') != 'no' or
            host.get('Memory') != 512 * 1024**2 or host.get('MemorySwap') != 512 * 1024**2 or
            host.get('PidsLimit') != 64 or host.get('NanoCpus') != 750000000):
        return 'RESOURCE_LIMIT_MISMATCH'
    declared = host.get('Tmpfs')
    if not isinstance(declared, dict):
        return 'INVALID_INPUT'
    if set(declared) != set(TMPFS) or any(
            not temporary_storage(declared[path], size) for path, size in TMPFS.items()):
        return 'TMPFS_DECLARATION_MISMATCH'
    mounts = row.get('Mounts')
    if not isinstance(mounts, list) or any(not isinstance(m, dict) for m in mounts):
        return 'INVALID_INPUT'
    realized = (isinstance(mounts, list) and len(mounts) == 2 and
                {m.get('Destination') for m in mounts} == set(TMPFS) and
                all(m.get('Type') == 'tmpfs' and m.get('RW') is True and
                    not m.get('Source') for m in mounts))
    if not realized and not (state['Status'] == 'created' and mounts == []):
        return 'REALIZED_MOUNTS_MISMATCH'
    # Only reviewed noncredential image defaults are eligible for inheritance.
    for key, value in public_image_env.items():
        if (not isinstance(key, str) or not isinstance(value, str) or key in SYNTHETIC or
                re.search(r'SECRET|TOKEN|PASSWORD|API_KEY|DATABASE_URL|REDIS_URL', key, re.I)):
            return 'IMAGE_ENV_ALLOWLIST_UNSAFE'
    if environment(conf.get('Env')) != {**public_image_env, **SYNTHETIC}:
        return 'SYNTHETIC_ENV_MISMATCH'
    return 'PASS_CREATED' if state['Status'] == 'created' else 'PASS_RUNNING'


def validate(row, image, token, public_image_env):
    try:
        return _validate(row, image, token, public_image_env)
    except (TypeError, ValueError, AttributeError, KeyError):
        return 'INVALID_INPUT'


def realized_tmpfs(evidence):
    """Validate captured in-container mountinfo/stat evidence; no host operations."""
    try:
        info=evidence['mountinfo'];stats=evidence['stats']
        if not isinstance(info,str) or not isinstance(stats,dict):return None
        found={}
        for line in info.splitlines():
            fields=line.split();separator=fields.index('-')
            if len(fields)<separator+4:return None
            path=fields[4]
            if path not in TMPFS:continue
            if path in found:return None
            if fields[separator+1:separator+3]!=['tmpfs','tmpfs']:return None
            if not {'rw','nosuid','nodev'}<=set(fields[5].split(',')):return None
            options=fields[separator+3].split(',')
            sizes=[x[5:] for x in options if x.startswith('size=')]
            if len(sizes)!=1:return None
            match=re.fullmatch(r'(\d+)([kKmM]?)',sizes[0])
            if not match:return None
            size=int(match[1])*{'':1,'k':1024,'m':1024**2}[match[2].lower()]
            expected=64*1024**2 if path=='/app/data' else 16*1024**2
            if size!=expected:return None
            if stats.get(path)!={'uid':1000,'gid':1000,'mode':448,'directory':True}:return None
            found[path]={'Type':'tmpfs','Destination':path,'RW':True,'Source':''}
        if set(found)!=set(TMPFS):return None
        return list(found.values())
    except (TypeError,ValueError,KeyError,IndexError,AttributeError):return None

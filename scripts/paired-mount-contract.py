#!/usr/bin/env python3
"""Compare Docker storage semantics and every remaining HostConfig field.

Pure validation only. Recognized Binds/Mounts encodings may differ, but source,
access, propagation, creation/copy behavior and every supported option may not.
Unsupported options reject; no runtime mutation or release authorization exists.
"""
import copy
import posixpath


class Refused(ValueError):
    pass


PROPAGATIONS = {'private', 'rprivate', 'shared', 'rshared', 'slave', 'rslave'}
CONSISTENCIES = {'consistent', 'cached', 'delegated', 'default'}
RUNTIME_KEYS = {'Type', 'Name', 'Source', 'Destination', 'Driver', 'Mode', 'RW', 'Propagation'}
MOUNT_KEYS = {'Type', 'Source', 'Target', 'ReadOnly', 'Consistency', 'BindOptions', 'VolumeOptions'}
BIND_KEYS = {'Propagation', 'NonRecursive', 'CreateMountpoint', 'ReadOnlyNonRecursive', 'ReadOnlyForceRecursive'}
VOLUME_KEYS = {'NoCopy', 'Labels', 'Subpath', 'DriverConfig'}


def absolute(value):
    if not isinstance(value, str) or not value.startswith('/') or posixpath.normpath(value) != value:
        raise Refused('NONCANONICAL_MOUNT_PATH')
    if any(ord(char) < 32 for char in value) or ':' in value:
        raise Refused('UNSUPPORTED_MOUNT_PATH')
    return value


def consistency(value):
    if value in (None, '', 'default'):
        return 'consistent'
    if value not in CONSISTENCIES:
        raise Refused('UNSUPPORTED_MOUNT_CONSISTENCY')
    return value


def boolean(value):
    if not isinstance(value, bool):
        raise Refused('INVALID_MOUNT_BOOLEAN')
    return value


def canonical_host_storage(row):
    host = copy.deepcopy(row.get('HostConfig') or {})
    actual = {}
    for mount in row.get('Mounts') or []:
        if set(mount) - RUNTIME_KEYS or mount.get('Type') not in ('bind', 'volume'):
            raise Refused('UNSUPPORTED_RUNTIME_MOUNT_FIELDS')
        target = absolute(mount.get('Destination'))
        if target in actual:
            raise Refused('DUPLICATE_RUNTIME_MOUNT_TARGET')
        source = mount.get('Name') if mount['Type'] == 'volume' else absolute(mount.get('Source'))
        if not isinstance(source, str) or not source:
            raise Refused('MOUNT_SOURCE_IDENTITY_MISSING')
        mode = set(filter(None, mount.get('Mode', '').split(',')))
        if mode - ({'ro', 'rw', 'nocopy', 'z', 'Z'} | PROPAGATIONS | CONSISTENCIES):
            raise Refused('UNSUPPORTED_RUNTIME_MOUNT_MODE')
        actual[target] = {
            'type': mount['Type'], 'source': source,
            'resolved_source': absolute(mount.get('Source')),
            'driver': mount.get('Driver') or '',
            'read_only': not boolean(mount.get('RW')),
            'propagation': (mount.get('Propagation') or 'rprivate') if mount['Type'] == 'bind' else (mount.get('Propagation') or ''),
            'selinux': sorted(mode & {'z', 'Z'}),
        }
    declarations = {}

    def add(kind, source, target, read_only, options):
        if target not in actual or target in declarations:
            raise Refused('MOUNT_DECLARATION_TARGET_MISMATCH')
        runtime = actual[target]
        if kind != runtime['type'] or source != runtime['source'] or read_only != runtime['read_only']:
            raise Refused('MOUNT_DECLARATION_RUNTIME_MISMATCH')
        if kind == 'bind' and options['propagation'] != runtime['propagation']:
            raise Refused('BIND_PROPAGATION_RUNTIME_MISMATCH')
        if options.get('selinux', []) != runtime['selinux']:
            raise Refused('SELINUX_RUNTIME_MISMATCH')
        declarations[target] = {'runtime': runtime, 'options': options}

    binds = host.pop('Binds', None) or []
    typed = host.pop('Mounts', None) or []
    if not isinstance(binds, list) or not isinstance(typed, list):
        raise Refused('MOUNT_DECLARATIONS_INVALID')
    for bind in binds:
        if not isinstance(bind, str) or len(bind.split(':')) not in (2, 3):
            raise Refused('UNSUPPORTED_BIND_ENCODING')
        parts = bind.split(':')
        source, target = parts[:2]
        target = absolute(target)
        flags = parts[2].split(',') if len(parts) == 3 else []
        if len(flags) != len(set(flags)) or set(flags) - ({'ro', 'rw', 'nocopy', 'z', 'Z'} | PROPAGATIONS | CONSISTENCIES):
            raise Refused('UNSUPPORTED_BIND_MODE')
        flags = set(flags)
        if {'ro', 'rw'} <= flags or len(flags & PROPAGATIONS) > 1 or len(flags & CONSISTENCIES) > 1 or {'z', 'Z'} <= flags:
            raise Refused('CONTRADICTORY_BIND_MODE')
        if target not in actual:
            raise Refused('MOUNT_DECLARATION_TARGET_MISMATCH')
        kind = actual[target]['type']
        common = {'consistency': consistency(next(iter(flags & CONSISTENCIES), '')),
                  'selinux': sorted(flags & {'z', 'Z'})}
        if kind == 'bind':
            absolute(source)
            if 'nocopy' in flags:
                raise Refused('INVALID_BIND_NOCOPY')
            options = {**common, 'propagation': next(iter(flags & PROPAGATIONS), 'rprivate'),
                       'create_mountpoint': True, 'non_recursive': False,
                       'read_only_non_recursive': False, 'read_only_force_recursive': False}
        else:
            if flags & (PROPAGATIONS | {'z', 'Z'}):
                raise Refused('UNSUPPORTED_VOLUME_BIND_FLAGS')
            options = {**common, 'no_copy': 'nocopy' in flags, 'subpath': '',
                       'driver': actual[target]['driver'], 'driver_options': {}, 'labels': {}}
        add(kind, source, target, 'ro' in flags, options)
    for mount in typed:
        if not isinstance(mount, dict) or set(mount) - MOUNT_KEYS:
            raise Refused('UNSUPPORTED_TYPED_MOUNT_FIELDS')
        kind, source, target = mount.get('Type'), mount.get('Source'), absolute(mount.get('Target'))
        read_only = boolean(mount.get('ReadOnly', False))
        common = {'consistency': consistency(mount.get('Consistency')), 'selinux': []}
        if kind == 'bind':
            absolute(source)
            opts = mount.get('BindOptions') or {}
            if set(opts) - BIND_KEYS or mount.get('VolumeOptions'):
                raise Refused('UNSUPPORTED_TYPED_BIND_OPTIONS')
            propagation = opts.get('Propagation') or 'rprivate'
            if propagation not in PROPAGATIONS:
                raise Refused('UNSUPPORTED_BIND_PROPAGATION')
            options = {**common, 'propagation': propagation,
                       'create_mountpoint': boolean(opts.get('CreateMountpoint', False)),
                       'non_recursive': boolean(opts.get('NonRecursive', False)),
                       'read_only_non_recursive': boolean(opts.get('ReadOnlyNonRecursive', False)),
                       'read_only_force_recursive': boolean(opts.get('ReadOnlyForceRecursive', False))}
        elif kind == 'volume':
            opts = mount.get('VolumeOptions') or {}
            if set(opts) - VOLUME_KEYS or mount.get('BindOptions') or target not in actual:
                raise Refused('UNSUPPORTED_TYPED_VOLUME_OPTIONS')
            driver = opts.get('DriverConfig') or {}
            if set(driver) - {'Name', 'Options'}:
                raise Refused('UNSUPPORTED_VOLUME_DRIVER_FIELDS')
            options = {**common, 'no_copy': boolean(opts.get('NoCopy', False)),
                       'subpath': opts.get('Subpath') or '', 'labels': opts.get('Labels') or {},
                       'driver': driver.get('Name') or actual[target]['driver'],
                       'driver_options': driver.get('Options') or {}}
        else:
            raise Refused('UNSUPPORTED_TYPED_MOUNT_TYPE')
        add(kind, source, target, read_only, options)
    if set(declarations) != set(actual):
        raise Refused('UNACCOUNTED_RUNTIME_MOUNT')
    # Every field outside the two encoding alternatives stays in the comparison.
    return {'host_config': host, 'mount_contract': declarations}


def verify_host_storage(before, after):
    first, second = canonical_host_storage(before), canonical_host_storage(after)
    if first['host_config'] != second['host_config']:
        keys = sorted(key for key in set(first['host_config']) | set(second['host_config'])
                      if first['host_config'].get(key) != second['host_config'].get(key))
        # Docker field names only; no values or storage paths are returned.
        raise Refused('HOST_FIELDS_CHANGED:' + ','.join(keys))
    if first['mount_contract'] != second['mount_contract']:
        raise Refused('MOUNT_SOURCE_ACCESS_OR_OPTIONS_CHANGED')
    return {'host_and_storage_semantics_match': True, 'deployment_authorized': False}

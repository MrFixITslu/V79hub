#!/usr/bin/env python3
"""Pure image-only plan validation. No Docker, files, network or deployment.

The caller must supply fresh inspected identities and fully rendered models.
This contract is a preparation gate, never a production authorization.
"""
import copy
import hashlib
import json

CURRENT = {
    'v79-hub': 'sha256:d722f357206fec938eca691c92ddfe57ece62811f62124f6fbf760258b2b6940',
    'v79-tiquet-manager': 'sha256:18fc67f82ec3dc33a7b281da79d6ab8e6b17f2983f419833bd008101d5711fc3',
}
CANDIDATE = {
    'v79-hub': 'sha256:6cad753945278c6757de3947692c07e87e74d9337a29e08ca182967dee132b81',
    'v79-tiquet-manager': 'sha256:8e92b5d3a291151e8734b4128329bcfe44dbd2a99a91c46c3a0df5e241378f43',
}
REVISIONS = {
    'v79-hub': '48c3facacb049610862203535ffee54616573a81',
    'v79-tiquet-manager': 'f1c336bc4406b9c38c23df44a84609bf744512a6',
}


class Refused(ValueError):
    """Fixed safe diagnostics; never include raw model or secret values."""


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def verify_models(before, candidate, rollback, resolved_baseline):
    """Verify complete rendered models for one project containing either app.

    Both projects must be checked separately. Other services and all top-level
    fields must remain identical. Rollback image refs are immutable original IDs.
    No dollar decoding/reserialization happens here: preserve rendered values.
    """
    if not all(isinstance(v, dict) and isinstance(v.get('services'), dict)
               for v in (before, candidate, rollback)):
        raise Refused('RENDERED_MODELS_REQUIRED')
    selected = set(before['services']) & set(CURRENT)
    if not selected or set(resolved_baseline) != selected:
        raise Refused('BASELINE_RESOLUTION_SCOPE_INVALID')
    expected_candidate = copy.deepcopy(before)
    expected_rollback = copy.deepcopy(before)
    for service in selected:
        if resolved_baseline[service] != CURRENT[service]:
            raise Refused('CURRENT_IMAGE_CHANGED')
        if not isinstance(before['services'][service].get('image'), str):
            raise Refused('BASELINE_IMAGE_REFERENCE_MISSING')
        expected_candidate['services'][service]['image'] = CANDIDATE[service]
        expected_rollback['services'][service]['image'] = CURRENT[service]
    if candidate != expected_candidate:
        raise Refused('CANDIDATE_MUST_CHANGE_ONLY_APPROVED_IMAGES')
    if rollback != expected_rollback:
        raise Refused('ROLLBACK_MUST_RESTORE_COMPLETE_ORIGINAL_MODEL')
    return {
        'mode': 'PURE_PLAN_CONTRACT_ONLY',
        'services': sorted(selected),
        'candidate_only_image_delta': True,
        'rollback_complete_model_match': True,
        'baseline_model_sha256': fingerprint(before),
        'candidate_model_sha256': fingerprint(candidate),
        'rollback_model_sha256': fingerprint(rollback),
        'deployment_authorized': False,
    }


def envmap(values):
    if not isinstance(values, list) or any(not isinstance(v, str) or '=' not in v for v in values):
        raise Refused('IMAGE_ENVIRONMENT_INVALID')
    pairs = [v.split('=', 1) for v in values]
    if len({p[0] for p in pairs}) != len(pairs):
        raise Refused('DUPLICATE_IMAGE_ENVIRONMENT_KEY')
    return dict(pairs)


def verify_image_defaults(service_name, rendered_service, old_image, new_image):
    """Reject hidden process/default-env changes caused by image inheritance.

    Effective process comparison remains distinct from complete Docker runtime
    parity and Compose codec calibration; callers must establish those separately.
    """
    if service_name not in CURRENT:
        raise Refused('UNAPPROVED_SERVICE')
    if old_image.get('Id') != CURRENT[service_name] or new_image.get('Id') != CANDIDATE[service_name]:
        raise Refused('INSPECTED_IMAGE_IDENTITY_CHANGED')
    before, after = old_image.get('Config'), new_image.get('Config')
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise Refused('IMAGE_CONFIG_MISSING')
    if (after.get('Labels') or {}).get('org.opencontainers.image.revision') != REVISIONS[service_name]:
        raise Refused('CANDIDATE_SOURCE_LABEL_MISMATCH')
    # A null value in Compose requests image inheritance. An explicit empty list
    # is an override and must not accidentally be treated as null.
    inherited = {
        'command': 'Cmd', 'entrypoint': 'Entrypoint', 'user': 'User',
        'working_dir': 'WorkingDir', 'stop_signal': 'StopSignal',
    }
    for compose_key, config_key in inherited.items():
        if rendered_service.get(compose_key) is None and before.get(config_key) != after.get(config_key):
            raise Refused('INHERITED_IMAGE_PROCESS_CHANGED')
    for key in ('Volumes', 'ExposedPorts', 'Shell', 'OnBuild'):
        if before.get(key) != after.get(key):
            raise Refused('INHERITED_IMAGE_METADATA_CHANGED')
    # Partial healthcheck overrides still inherit the other image fields.
    if before.get('Healthcheck') != after.get('Healthcheck'):
        raise Refused('IMAGE_HEALTHCHECK_DEFAULT_CHANGED')
    configured = rendered_service.get('environment') or {}
    if not isinstance(configured, dict) or any(v is None for v in configured.values()):
        raise Refused('UNRESOLVED_COMPOSE_ENVIRONMENT')
    old_env = envmap(before.get('Env') or [])
    new_env = envmap(after.get('Env') or [])
    if {**old_env, **configured} != {**new_env, **configured}:
        raise Refused('INHERITED_IMAGE_ENVIRONMENT_CHANGED')
    return {'image_source_identity': True, 'inherited_process_and_environment_match': True,
            'deployment_authorized': False}

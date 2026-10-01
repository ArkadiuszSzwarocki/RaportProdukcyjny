"""Static regression tests for deployment/security findings from the audit."""

import re
from pathlib import Path
import yaml


ROOT = Path(__file__).resolve().parents[1]


def _text(relative_path):
    return (ROOT / relative_path).read_text(encoding='utf-8')


def test_trivy_action_is_immutable_and_gates_publish():
    workflow = _text('.github/workflows/deploy.yml')
    assert 'aquasecurity/trivy-action@master' not in workflow
    assert 'aquasecurity/trivy-action@915b19bbe73b92a6cf82a1bc12b087c9a19a5fe2' in workflow
    assert 'workflow_run:' in workflow
    assert "workflow_run.conclusion == 'success'" in workflow
    assert 'exit-code: "1"' in workflow
    assert 'needs: scan' in workflow


def test_all_external_github_actions_are_pinned_to_full_commit_sha():
    workflows_dir = ROOT / '.github' / 'workflows'
    uses_pattern = re.compile(r'^\s*-?\s*uses:\s*([^\s#]+)', re.MULTILINE)
    sha_pattern = re.compile(r'^[0-9a-f]{40}$')

    for workflow_path in workflows_dir.glob('*.yml'):
        workflow = workflow_path.read_text(encoding='utf-8')
        for action_ref in uses_pattern.findall(workflow):
            if action_ref.startswith('./'):
                continue
            assert '@' in action_ref, f'Missing immutable ref in {workflow_path.name}: {action_ref}'
            action_name, ref = action_ref.rsplit('@', 1)
            assert action_name, f'Invalid action reference in {workflow_path.name}: {action_ref}'
            assert sha_pattern.fullmatch(ref), (
                f'GitHub Action must be pinned to a 40-char commit SHA in '
                f'{workflow_path.name}: {action_ref}'
            )


def test_spellcheck_is_pinned_and_failure_gating():
    workflow = _text('.github/workflows/cspell.yml')
    assert 'npm install --no-save cspell@10.3.5 @cspell/dict-pl_pl@3.0.6' in workflow
    assert 'node-version: "22.18.0"' in workflow
    assert '@cspell/dict-uk-ua@4.0.6' in workflow
    assert 'node scripts/check_spelling.mjs' in workflow
    assert 'node --test tests/javascript/cspell_baseline.test.mjs' in workflow
    assert '|| true' not in workflow
    assert 'continue-on-error' not in workflow


def test_production_k8s_config_does_not_commit_secret_values():
    manifest = _text('k8s/00-namespace-config.yaml')
    assert 'kind: Secret' not in manifest
    assert 'CHANGE_THIS_TO_' not in manifest
    assert 'DB_PORT: "3306"' in manifest
    assert 'DB_SSL_DISABLED: "false"' in manifest
    assert 'SESSION_COOKIE_SECURE: "true"' in manifest
    assert 'TRUST_PROXY_HEADERS: "true"' in manifest


def test_k8s_web_service_is_internal_and_sa_cannot_read_secrets():
    manifest = _text('k8s/02-app.yaml')
    assert 'type: LoadBalancer' not in manifest
    assert 'type: ClusterIP' in manifest
    assert 'resources: ["configmaps", "secrets"]' not in manifest
    assert 'automountServiceAccountToken: false' in manifest
    assert 'key: PRINTER_BRIDGE_TOKEN' in manifest
    assert 'name: ENABLE_BACKGROUND_DAEMONS\n          value: "false"' in manifest
    deployment = next(doc for doc in yaml.safe_load_all(manifest) if doc['kind'] == 'Deployment')
    containers = deployment['spec']['template']['spec']['containers']
    web = next(container for container in containers if container['name'] == 'app')
    daemons = next(container for container in containers if container['name'] == 'daemons')
    assert daemons['command'] == ['python', 'scripts/run_daemons.py']
    assert daemons['image'] == web['image']
    assert daemons['volumeMounts'] == web['volumeMounts']
    assert 'name: ENABLE_BACKGROUND_DAEMONS\n          value: "true"' in manifest


def test_k8s_mysql_ingress_is_limited_to_application_pods():
    policy = _text('k8s/03-ingress.yaml')
    assert 'name: mysql-ingress-policy' in policy
    assert 'app: mysql' in policy
    assert 'raportprodukcyjny-daemons' in policy
    assert 'port: 3306' in policy


def test_compose_uses_mysql_internal_port_and_separate_root_password():
    compose = _text('docker-compose.yml')
    assert '127.0.0.1:${DB_HOST_PORT:-3307}:3306' in compose
    assert 'DB_PORT: 3306' in compose
    assert 'MYSQL_ROOT_PASSWORD: ${DB_ROOT_PASSWORD:' in compose
    assert 'MYSQL_ROOT_PASSWORD: ${DB_PASSWORD:' not in compose
    assert 'DB_SSL_DISABLED: ${DB_SSL_DISABLED:-false}' in compose
    assert 'daemons:' in compose
    assert 'command: ["python", "scripts/run_daemons.py"]' in compose
    assert 'ENABLE_BACKGROUND_DAEMONS: "false"' in compose
    assert 'ENABLE_BACKGROUND_DAEMONS: "true"' in compose
    assert "socket.create_connection(('127.0.0.1', 8082), 5)" in compose


def test_compose_requires_explicit_tested_application_image():
    compose = _text('docker-compose.yml')
    env_example = _text('.env.example')
    assert compose.count('${APP_IMAGE:?APP_IMAGE must reference the tested sha image}') == 2
    assert 'raportprodukcyjny:latest' not in compose
    assert 'APP_IMAGE=ghcr.io/arkadiuszszwarocki/raportprodukcyjny:sha-REPLACE_WITH_TESTED_COMMIT_SHA' in env_example


def test_docker_healthcheck_does_not_disable_tls_validation():
    dockerfile = _text('Dockerfile')
    assert 'verify=False' not in dockerfile
    assert '127.0.0.1:8082' in dockerfile


def test_production_dependencies_are_exactly_pinned():
    requirements = _text('requirements.txt').splitlines()
    for raw_line in requirements:
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        package_part = line.split(';', 1)[0].strip()
        assert '==' in package_part, f'Production dependency is not exactly pinned: {line}'
        assert '>=' not in package_part
        assert '<=' not in package_part


def test_runtime_artifacts_are_not_tracked_anymore():
    assert not (ROOT / '.machine_error_logs.json').exists()
    assert not (ROOT / '.machine_reject_logs.json').exists()
    assert not (ROOT / '0').exists()
    assert not (ROOT / 'db_compare_tmp.py').exists()
    assert not any(ROOT.glob('scratch_*.py'))
    assert not (ROOT / 'tools' / 'archive').exists()

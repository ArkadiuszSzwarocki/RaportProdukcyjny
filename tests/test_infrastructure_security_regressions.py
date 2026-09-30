"""Static regression tests for deployment/security findings from the audit."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(relative_path):
    return (ROOT / relative_path).read_text(encoding='utf-8')


def test_trivy_action_is_version_pinned():
    workflow = _text('.github/workflows/deploy.yml')
    assert 'aquasecurity/trivy-action@master' not in workflow
    assert 'aquasecurity/trivy-action@0.28.0' in workflow


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


def test_compose_uses_mysql_internal_port_and_separate_root_password():
    compose = _text('docker-compose.yml')
    assert '${DB_HOST_PORT:-3307}:3306' in compose
    assert 'DB_PORT: 3306' in compose
    assert 'MYSQL_ROOT_PASSWORD: ${DB_ROOT_PASSWORD:' in compose
    assert 'MYSQL_ROOT_PASSWORD: ${DB_PASSWORD:' not in compose
    assert 'DB_SSL_DISABLED: ${DB_SSL_DISABLED:-false}' in compose


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

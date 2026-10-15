"""The mutable tag must point to the same tested and scanned image."""
from pathlib import Path
import yaml


def test_latest_promotion_keeps_the_scan_gate_and_rejects_stale_releases():
    text = (Path(__file__).parents[1] / '.github/workflows/deploy.yml').read_text(encoding='utf-8')
    workflow = yaml.safe_load(text)
    assert workflow['concurrency'] == {'group': 'production-image-publication', 'cancel-in-progress': False}
    build = workflow['jobs']['build']
    assert build['needs'] == 'scan'
    assert "needs.scan.outputs.ready == 'true'" in build['if']
    steps = build['steps']
    scan = next(i for i, step in enumerate(steps) if step.get('name') == 'Gate publication on built image vulnerabilities')
    publish = next(i for i, step in enumerate(steps) if step.get('name') == 'Publish the scanned image and record its digest')
    promote = next(i for i, step in enumerate(steps) if step.get('name') == 'Update latest for Watchtower from the scanned image')
    assert scan < publish < promote
    assert steps[scan]['with']['exit-code'] == '1'
    assert steps[promote]['env']['IMAGE'] == steps[publish]['env']['IMAGE']
    script = steps[promote]['run']
    assert 'git/ref/heads/main' in script
    assert 'if [ "$current_main" != "$RELEASE_SHA" ]; then' in script
    assert script.index('exit 0') < script.index('docker tag "$IMAGE" "$LATEST_IMAGE"')
    assert 'docker push "$LATEST_IMAGE"' in script
    assert not steps[promote].get('continue-on-error')

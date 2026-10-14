from scripts.check_release_validations import publication_ready, REQUIRED

SHA = 'a' * 40


def runs():
    return [dict(id=i, name=name, head_sha=SHA, head_branch='main', event='push',
                 status='completed', conclusion='success') for i, name in enumerate(sorted(REQUIRED), 1)]


def test_all_three_validations_must_pass_on_exact_release_commit():
    assert publication_ready(runs(), SHA)
    assert not publication_ready(runs(), 'b' * 40)
    assert not publication_ready(runs()[:-1], SHA)


def test_failed_or_pending_python_tests_prevent_publication():
    for state, conclusion in [('completed', 'failure'), ('in_progress', None)]:
        data = runs()
        next(x for x in data if x['name'] == 'Python tests').update(status=state, conclusion=conclusion)
        assert not publication_ready(data, SHA)


def test_newer_failed_run_cannot_be_hidden_by_older_success():
    data = runs()
    data.append(dict(data[0], id=100, conclusion='failure'))
    assert not publication_ready(data, SHA)


def test_pull_request_and_other_branch_runs_do_not_authorize_publication():
    for change in [dict(event='pull_request'), dict(head_branch='develop')]:
        data = runs()
        data[0].update(change)
        assert not publication_ready(data, SHA)

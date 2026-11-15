import json

SUM_CODE = "a, b = map(int, input().split())\nprint(a + b)\n"


def _setup(client):
    problem_id = client.post("/problems", json={"title": "Add two", "prompt": "Add two numbers."}).json()["id"]
    client.post(f"/problems/{problem_id}/tests", json={"input_text": "2 3\n", "expected_output": "5\n"})
    client.post(
        f"/problems/{problem_id}/tests",
        json={"input_text": "10 20\n", "expected_output": "30\n", "is_hidden": True},
    )
    session_id = client.post(
        "/sessions",
        json={"problem_id": problem_id, "candidate_name": "Asha", "interviewer_name": "Ravi"},
    ).json()["id"]
    return problem_id, session_id


def test_public_test_view_hides_hidden_cases(client):
    problem_id, _ = _setup(client)
    tests = client.get(f"/problems/{problem_id}/tests").json()
    hidden = next(t for t in tests if t["is_hidden"])
    assert hidden["input_text"] is None
    assert hidden["expected_output"] is None


def test_visible_run_reports_per_test_detail(client):
    _, session_id = _setup(client)
    client.put(f"/sessions/{session_id}/snapshot", json={"code": SUM_CODE})
    run = client.post(f"/sessions/{session_id}/runs", json={"kind": "visible"}).json()
    assert run["status"] == "done"
    assert run["passed_count"] == 1
    assert run["total_count"] == 1
    details = json.loads(run["output"])
    assert details[0]["passed"] is True


def test_full_run_counts_hidden_without_leaking(client):
    _, session_id = _setup(client)
    run = client.post(f"/sessions/{session_id}/runs", json={"kind": "full", "code": SUM_CODE}).json()
    assert run["passed_count"] == 2
    assert run["total_count"] == 2
    assert run["output"] == ""


def test_wrong_code_fails_tests(client):
    _, session_id = _setup(client)
    run = client.post(f"/sessions/{session_id}/runs", json={"kind": "full", "code": "print(0)"}).json()
    assert run["passed_count"] == 0


def test_crashing_code_is_a_failed_test_not_a_500(client):
    _, session_id = _setup(client)
    run = client.post(f"/sessions/{session_id}/runs", json={"kind": "full", "code": "print(1/0)"}).json()
    assert run["status"] == "done"
    assert run["passed_count"] == 0


def test_scorecard_upsert(client):
    _, session_id = _setup(client)
    assert client.get(f"/sessions/{session_id}/scorecard").status_code == 404
    client.put(f"/sessions/{session_id}/scorecard", json={"correctness": 3, "communication": 4})
    updated = client.put(
        f"/sessions/{session_id}/scorecard",
        json={"correctness": 5, "communication": 4, "notes": "Clean solution"},
    ).json()
    assert updated["correctness"] == 5
    assert client.get(f"/sessions/{session_id}/scorecard").json()["notes"] == "Clean solution"


def test_copilot_is_disabled_without_api_key(client):
    _, session_id = _setup(client)
    assert client.post(f"/sessions/{session_id}/copilot").status_code == 503


def test_websocket_relays_code_to_other_clients(client):
    _, session_id = _setup(client)
    with client.websocket_connect(f"/ws/sessions/{session_id}") as a, \
            client.websocket_connect(f"/ws/sessions/{session_id}") as b:
        a.send_json({"type": "code", "code": "print(1)"})
        assert b.receive_json() == {"type": "code", "code": "print(1)"}


def test_latest_snapshot_is_returned_on_reload(client):
    _, session_id = _setup(client)
    assert client.get(f"/sessions/{session_id}/snapshot").json() == {"code": ""}
    client.put(f"/sessions/{session_id}/snapshot", json={"code": "print(1)"})
    client.put(f"/sessions/{session_id}/snapshot", json={"code": "print(2)"})
    assert client.get(f"/sessions/{session_id}/snapshot").json() == {"code": "print(2)"}


def test_binary_frames_are_relayed(client):
    _, session_id = _setup(client)
    with client.websocket_connect(f"/ws/sessions/{session_id}") as a, \
            client.websocket_connect(f"/ws/sessions/{session_id}") as b:
        a.send_bytes(b"\x00hello")
        assert b.receive_bytes() == b"\x00hello"


def test_sync_request_is_relayed_as_text(client):
    _, session_id = _setup(client)
    with client.websocket_connect(f"/ws/sessions/{session_id}") as a, \
            client.websocket_connect(f"/ws/sessions/{session_id}") as b:
        a.send_json({"type": "sync_request"})
        assert b.receive_json() == {"type": "sync_request"}


def test_summary_collects_session_results(client):
    _, session_id = _setup(client)
    client.put(f"/sessions/{session_id}/snapshot", json={"code": "print(1)"})
    client.post(f"/sessions/{session_id}/runs", json={"kind": "full", "code": "print(1)"})
    client.put(f"/sessions/{session_id}/scorecard", json={"correctness": 4, "communication": 3, "notes": "Good"})
    client.patch(f"/sessions/{session_id}", json={"status": "ended"})
    summary = client.get(f"/sessions/{session_id}/summary").json()
    assert summary["session"]["status"] == "ended"
    assert summary["problem"]["title"] == "Add two"
    assert summary["code"] == "print(1)"
    assert summary["run_count"] == 1
    assert summary["best_full_run"] == {"passed": 0, "total": 2}
    assert summary["scorecard"]["notes"] == "Good"


def test_summary_without_results_has_nulls(client):
    _, session_id = _setup(client)
    summary = client.get(f"/sessions/{session_id}/summary").json()
    assert summary["best_full_run"] is None
    assert summary["scorecard"] is None

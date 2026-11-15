def _make_problem(client):
    return client.post(
        "/problems",
        json={"title": "Reverse String", "prompt": "Reverse the input string."},
    ).json()["id"]


def _make_session(client, problem_id):
    return client.post(
        "/sessions",
        json={
            "problem_id": problem_id,
            "candidate_name": "Asha",
            "interviewer_name": "Ravi",
        },
    )


def test_create_session_defaults_to_scheduled(client):
    problem_id = _make_problem(client)
    created = _make_session(client, problem_id)
    assert created.status_code == 201
    assert created.json()["status"] == "scheduled"
    assert created.json()["started_at"] is None


def test_session_needs_existing_problem(client):
    assert _make_session(client, 999).status_code == 404


def test_going_live_sets_started_at(client):
    session_id = _make_session(client, _make_problem(client)).json()["id"]
    updated = client.patch(f"/sessions/{session_id}", json={"status": "live"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "live"
    assert updated.json()["started_at"] is not None


def test_ending_sets_ended_at(client):
    session_id = _make_session(client, _make_problem(client)).json()["id"]
    ended = client.patch(f"/sessions/{session_id}", json={"status": "ended"}).json()
    assert ended["status"] == "ended"
    assert ended["ended_at"] is not None


def test_invalid_status_is_rejected(client):
    session_id = _make_session(client, _make_problem(client)).json()["id"]
    assert client.patch(f"/sessions/{session_id}", json={"status": "paused"}).status_code == 422


def test_archived_problem_keeps_session_history(client):
    problem_id = _make_problem(client)
    session_id = _make_session(client, problem_id).json()["id"]
    assert client.delete(f"/problems/{problem_id}").status_code == 204
    assert client.get(f"/sessions/{session_id}/problem").status_code == 200

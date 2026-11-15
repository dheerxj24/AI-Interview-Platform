import pytest

from app.config import settings


def _new_session(client):
    problem_id = client.post("/problems", json={"title": "Add two", "prompt": "Add two numbers."}).json()["id"]
    return client.post(
        "/sessions",
        json={"problem_id": problem_id, "candidate_name": "Ravi", "interviewer_name": "Ashi"},
    ).json()


def test_candidate_token_cannot_read_summary(client):
    s = _new_session(client)
    res = client.get(f"/sessions/{s['id']}/summary", headers={"X-Session-Token": s["candidate_token"]})
    assert res.status_code == 403


def test_missing_token_is_rejected(client):
    s = _new_session(client)
    assert client.get(f"/sessions/{s['id']}/summary", headers={"X-Session-Token": ""}).status_code == 401


def test_token_from_another_session_is_rejected(client):
    first = _new_session(client)
    second = _new_session(client)
    res = client.get(f"/sessions/{second['id']}/summary", headers={"X-Session-Token": first["interviewer_token"]})
    assert res.status_code == 401


def test_candidate_can_code_and_run(client):
    s = _new_session(client)
    headers = {"X-Session-Token": s["candidate_token"]}
    assert client.put(f"/sessions/{s['id']}/snapshot", json={"code": "print(1)"}, headers=headers).status_code == 200
    assert client.post(f"/sessions/{s['id']}/runs", json={"kind": "visible"}, headers=headers).status_code == 201


def test_candidate_cannot_end_session(client):
    s = _new_session(client)
    res = client.patch(
        f"/sessions/{s['id']}", json={"status": "ended"}, headers={"X-Session-Token": s["candidate_token"]}
    )
    assert res.status_code == 403


def test_candidate_events_are_recorded_and_shown_in_summary(client):
    s = _new_session(client)
    res = client.post(
        f"/sessions/{s['id']}/events", json={"kind": "tab_hidden"}, headers={"X-Session-Token": s["candidate_token"]}
    )
    assert res.status_code == 201
    summary = client.get(f"/sessions/{s['id']}/summary").json()
    assert [e["kind"] for e in summary["events"]] == ["tab_hidden"]


def test_interviewer_cannot_post_candidate_events(client):
    s = _new_session(client)
    res = client.post(
        f"/sessions/{s['id']}/events", json={"kind": "paste"}, headers={"X-Session-Token": s["interviewer_token"]}
    )
    assert res.status_code == 403


def test_websocket_requires_a_valid_token(client):
    s = _new_session(client)
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/sessions/{s['id']}?token=wrong") as ws:
            ws.receive_text()


def test_candidate_can_read_the_problem(client):
    s = _new_session(client)
    res = client.get(f"/sessions/{s['id']}/problem", headers={"X-Session-Token": s["candidate_token"]})
    assert res.status_code == 200
    assert res.json()["title"] == "Add two"


def test_problem_requires_a_token(client):
    s = _new_session(client)
    assert client.get(f"/sessions/{s['id']}/problem", headers={"X-Session-Token": ""}).status_code == 401


def test_candidate_sees_scores_only_after_the_session_ends(client):
    s = _new_session(client)
    headers = {"X-Session-Token": s["candidate_token"]}
    client.put(f"/sessions/{s['id']}/scorecard", json={"correctness": 4, "communication": 3})
    assert client.get(f"/sessions/{s['id']}/feedback", headers=headers).json()["correctness"] is None
    client.patch(f"/sessions/{s['id']}", json={"status": "ended"})
    result = client.get(f"/sessions/{s['id']}/feedback", headers=headers).json()
    assert result == {"status": "ended", "correctness": 4, "communication": 3}


def test_problem_admin_routes_need_the_admin_token(client):
    res = client.post("/problems", json={"title": "T", "prompt": "p"}, headers={"X-Admin-Token": ""})
    assert res.status_code == 401


def test_session_list_needs_the_admin_token(client):
    assert client.get("/sessions", headers={"X-Admin-Token": ""}).status_code == 401
    assert client.get("/sessions").status_code == 200


def test_admin_token_opens_any_session_as_interviewer(client):
    s = _new_session(client)
    res = client.get(
        f"/sessions/{s['id']}/summary", headers={"X-Session-Token": "", "X-Admin-Token": "test-admin"}
    )
    assert res.status_code == 200


def test_admin_routes_report_503_when_unconfigured(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "")
    assert client.get("/sessions").status_code == 503

def _make_problem(client, **overrides):
    body = {"title": "Two Sum", "prompt": "Return indices of two numbers.", "difficulty": "easy"}
    body.update(overrides)
    return client.post("/problems", json=body)


def test_create_and_fetch_problem(client):
    created = _make_problem(client)
    assert created.status_code == 201
    problem_id = created.json()["id"]

    fetched = client.get(f"/problems/{problem_id}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Two Sum"
    assert fetched.json()["time_limit_s"] == 900


def test_missing_problem_returns_404(client):
    assert client.get("/problems/999").status_code == 404


def test_invalid_difficulty_is_rejected(client):
    assert _make_problem(client, difficulty="impossible").status_code == 422


def test_list_problems_paginates(client):
    for i in range(3):
        _make_problem(client, title=f"Problem {i}")
    page = client.get("/problems", params={"limit": 2, "offset": 0}).json()
    assert [p["title"] for p in page] == ["Problem 0", "Problem 1"]


def test_partial_update(client):
    problem_id = _make_problem(client).json()["id"]
    updated = client.patch(f"/problems/{problem_id}", json={"difficulty": "hard"})
    assert updated.status_code == 200
    assert updated.json()["difficulty"] == "hard"
    assert updated.json()["title"] == "Two Sum"


def test_delete_archives_problem(client):
    problem_id = _make_problem(client).json()["id"]
    assert client.delete(f"/problems/{problem_id}").status_code == 204
    assert problem_id not in [p["id"] for p in client.get("/problems").json()]

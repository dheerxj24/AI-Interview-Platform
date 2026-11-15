import json

import httpx
import pytest

from app import llm
from app.config import settings
from app.routers import activity, problems


def _session(client):
    problem_id = client.post("/problems", json={"title": "Upper", "prompt": "Uppercase the input."}).json()["id"]
    return client.post(
        "/sessions",
        json={"problem_id": problem_id, "candidate_name": "Asha", "interviewer_name": "Ravi"},
    ).json()["id"]


def test_copilot_retries_until_three_numbered_questions(client, monkeypatch):
    session_id = _session(client)
    client.put(f"/sessions/{session_id}/snapshot", json={"code": "print(input().upper())"})
    replies = iter(["Here are some thoughts about the code.", "1. Why upper?\n2. What if empty?\n3. Any tests?"])
    monkeypatch.setattr(activity, "llm_configured", lambda: True)
    monkeypatch.setattr(activity, "complete", lambda prompt, max_tokens=600: next(replies))

    response = client.post(f"/sessions/{session_id}/copilot")

    assert response.status_code == 200
    assert response.json()["suggestions"].splitlines() == ["1. Why upper?", "2. What if empty?", "3. Any tests?"]


def test_ai_scorecard_drafts_without_saving(client, monkeypatch):
    session_id = _session(client)
    client.put(f"/sessions/{session_id}/snapshot", json={"code": "print(input().upper())"})
    reply = json.dumps({"correctness": 4, "communication": 3, "notes": "Solid solution."})
    monkeypatch.setattr(activity, "llm_configured", lambda: True)
    monkeypatch.setattr(activity, "complete", lambda prompt, max_tokens=600: reply)

    response = client.post(f"/sessions/{session_id}/ai-scorecard")

    assert response.status_code == 200
    assert response.json() == {"correctness": 4, "communication": 3, "notes": "Solid solution."}
    assert client.get(f"/sessions/{session_id}/scorecard").status_code == 404


def test_ai_scorecard_rejects_out_of_range_scores(client, monkeypatch):
    session_id = _session(client)
    client.put(f"/sessions/{session_id}/snapshot", json={"code": "print(1)"})
    reply = json.dumps({"correctness": 9, "communication": 3, "notes": ""})
    monkeypatch.setattr(activity, "llm_configured", lambda: True)
    monkeypatch.setattr(activity, "complete", lambda prompt, max_tokens=600: reply)

    assert client.post(f"/sessions/{session_id}/ai-scorecard").status_code == 502


def _draft_text(code, inputs):
    fence = "```"
    lines = ["TITLE: Shout", "PROMPT:", "Uppercase each line.", "SOLUTION:", fence + "python", code, fence, "INPUTS:"]
    lines += [f"- {item}" for item in inputs]
    return "\n".join(lines)


def test_ai_problem_draft_uses_reference_output_as_expected(client, monkeypatch):
    reply = _draft_text("print(input().upper())", ["abc", "x", "hi there"])
    monkeypatch.setattr(problems, "llm_configured", lambda: True)
    monkeypatch.setattr(problems, "complete", lambda prompt, max_tokens=600: reply)

    response = client.post("/problems/ai-draft", json={"topic": "string basics", "difficulty": "easy"})

    assert response.status_code == 200
    tests = response.json()["tests"]
    assert [t["expected_output"] for t in tests] == ["ABC", "X", "HI THERE"]
    assert [t["is_hidden"] for t in tests] == [False, False, True]


def test_ai_problem_draft_retries_after_a_bad_reply(client, monkeypatch):
    replies = iter(["Sorry, I cannot help with that.", _draft_text("print(input().upper())", ["ab", "c"])])
    monkeypatch.setattr(problems, "llm_configured", lambda: True)
    monkeypatch.setattr(problems, "complete", lambda prompt, max_tokens=600: next(replies))

    response = client.post("/problems/ai-draft", json={"topic": "string basics"})

    assert response.status_code == 200
    assert response.json()["tests"][0]["expected_output"] == "AB"


def test_ai_problem_draft_reports_a_failing_reference(client, monkeypatch):
    reply = _draft_text("raise SystemExit(1)", ["a", "b"])
    monkeypatch.setattr(problems, "llm_configured", lambda: True)
    monkeypatch.setattr(problems, "complete", lambda prompt, max_tokens=600: reply)

    response = client.post("/problems/ai-draft", json={"topic": "anything"})

    assert response.status_code == 502
    assert "crashed on test 1" in response.json()["detail"]


def test_ai_problem_draft_reads_multiline_inputs(client, monkeypatch):
    reply = _draft_text("print(int(input()) + int(input()))", ["`1\\n2`"])
    monkeypatch.setattr(problems, "llm_configured", lambda: True)
    monkeypatch.setattr(problems, "complete", lambda prompt, max_tokens=600: reply)

    response = client.post("/problems/ai-draft", json={"topic": "addition"})

    assert response.status_code == 200
    test = response.json()["tests"][0]
    assert test["input_text"] == "1\n2"
    assert test["expected_output"] == "3"


def test_llm_timeout_gives_a_clear_message(monkeypatch):
    monkeypatch.setattr(settings, "ollama_url", "http://ollama.test")

    def slow(*args, **kwargs):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(llm.httpx, "post", slow)
    with pytest.raises(llm.LLMError, match="timed out"):
        llm.complete("hello")


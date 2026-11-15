from .executor import execute


def judge(code: str, tests: list, include_details: bool) -> dict:
    """Run code against each test. Details are returned only when include_details is True."""
    passed = 0
    runtime_ms = 0
    results = []

    for test in tests:
        outcome = execute(code, test.input_text)
        runtime_ms += outcome["runtime_ms"]
        ok = outcome["ok"] and outcome["stdout"].strip() == test.expected_output.strip()
        if ok:
            passed += 1
        if include_details:
            results.append({
                "test_id": test.id,
                "passed": ok,
                "input": test.input_text,
                "expected": test.expected_output,
                "stdout": outcome["stdout"],
                "stderr": outcome["stderr"],
            })

    return {"passed": passed, "total": len(tests), "runtime_ms": runtime_ms, "results": results}

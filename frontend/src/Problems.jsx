import { useEffect, useState } from "react";
import { api, hasAdminToken } from "./api.js";
import AdminLogin from "./AdminLogin.jsx";

const emptyProblem = { title: "", prompt: "", difficulty: "medium" };
const emptyTest = { input_text: "", expected_output: "", is_hidden: false };

export default function Problems() {
  const [problems, setProblems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [tests, setTests] = useState([]);
  const [problemForm, setProblemForm] = useState(emptyProblem);
  const [testForm, setTestForm] = useState(emptyTest);
  const [message, setMessage] = useState("");
  const [topic, setTopic] = useState("");
  const [draftDifficulty, setDraftDifficulty] = useState("easy");
  const [draft, setDraft] = useState(null);
  const [drafting, setDrafting] = useState(false);

  function loadProblems() {
    api.problems().then(setProblems).catch((e) => setMessage(e.message));
  }

  useEffect(loadProblems, []);

  useEffect(() => {
    if (!selected) return;
    api.problemTests(selected).then(setTests).catch((e) => setMessage(e.message));
  }, [selected]);

  async function deleteProblem(id) {
    if (!window.confirm("Delete this problem and all its tests? This cannot be undone.")) return;
    setMessage("");
    try {
      await api.deleteProblem(id);
      if (selected === id) setSelected(null);
      loadProblems();
      setMessage("Problem deleted");
    } catch (err) {
      setMessage(err.message);
    }
  }

  async function createProblem(event) {
    event.preventDefault();
    setMessage("");
    try {
      const created = await api.createProblem(problemForm);
      setProblemForm(emptyProblem);
      loadProblems();
      setSelected(created.id);
      setMessage(`Created "${created.title}"`);
    } catch (err) {
      setMessage(err.message);
    }
  }

  async function generateDraft(event) {
    event.preventDefault();
    setMessage("");
    setDrafting(true);
    try {
      setDraft(await api.aiProblemDraft({ topic, difficulty: draftDifficulty }));
    } catch (err) {
      setMessage(err.message);
    } finally {
      setDrafting(false);
    }
  }

  async function saveDraft() {
    setMessage("");
    try {
      const created = await api.createProblem({
        title: draft.title,
        prompt: draft.prompt,
        difficulty: draft.difficulty,
        time_limit_s: draft.time_limit_s,
      });
      for (const test of draft.tests) {
        await api.addTest(created.id, test);
      }
      setDraft(null);
      setTopic("");
      loadProblems();
      setSelected(created.id);
      setMessage(`Saved "${created.title}" with ${draft.tests.length} tests`);
    } catch (err) {
      setMessage(err.message);
    }
  }

  async function addTest(event) {
    event.preventDefault();
    setMessage("");
    try {
      await api.addTest(selected, testForm);
      setTestForm(emptyTest);
      setTests(await api.problemTests(selected));
    } catch (err) {
      setMessage(err.message);
    }
  }

  const visibleCount = tests.filter((t) => !t.is_hidden).length;
  const hiddenCount = tests.length - visibleCount;

  if (!hasAdminToken()) return <AdminLogin />;

  return (
    <section className="session">
      <h2>Problems and tests</h2>
      <p className="muted">
        <a href="?">Back to interviews</a>
      </p>
      {message && <p className="error">{message}</p>}

      <h3>Problems</h3>
      <ul className="runs">
        {problems.map((p) => (
          <li key={p.id}>
            <button className={selected === p.id ? "" : "secondary"} onClick={() => setSelected(p.id)}>
              {p.title} ({p.difficulty})
            </button>{" "}
            <button className="danger" onClick={() => deleteProblem(p.id)}>
              Delete
            </button>
          </li>
        ))}
      </ul>

      <h3>Generate with AI</h3>
      <form className="scorecard" onSubmit={generateDraft}>
        <label>
          Topic
          <input required value={topic} placeholder="e.g. string manipulation"
            onChange={(e) => setTopic(e.target.value)} />
        </label>
        <label>
          Difficulty
          <select value={draftDifficulty} onChange={(e) => setDraftDifficulty(e.target.value)}>
            <option value="easy">easy</option>
            <option value="medium">medium</option>
            <option value="hard">hard</option>
          </select>
        </label>
        <button type="submit" disabled={drafting}>{drafting ? "Generating..." : "Generate draft"}</button>
      </form>

      {draft && (
        <div>
          <h3>Draft: {draft.title}</h3>
          <p>{draft.prompt}</p>
          <h4>Tests</h4>
          <ul className="runs">
            {draft.tests.map((t, i) => (
              <li key={i}>
                {JSON.stringify(t.input_text)} → {JSON.stringify(t.expected_output)}
                {t.is_hidden ? " (hidden)" : ""}
              </li>
            ))}
          </ul>
          <h4>Reference solution (the expected outputs came from running this)</h4>
          <pre className="copilot">{draft.reference_solution}</pre>
          <button type="button" onClick={saveDraft}>Save as problem</button>{" "}
          <button type="button" className="secondary" onClick={() => setDraft(null)}>Discard</button>
        </div>
      )}

      <h3>New problem</h3>
      <form className="scorecard" onSubmit={createProblem}>
        <label>
          Title
          <input required value={problemForm.title}
            onChange={(e) => setProblemForm({ ...problemForm, title: e.target.value })} />
        </label>
        <label>
          Prompt
          <textarea required value={problemForm.prompt}
            onChange={(e) => setProblemForm({ ...problemForm, prompt: e.target.value })} />
        </label>
        <label>
          Difficulty
          <select value={problemForm.difficulty}
            onChange={(e) => setProblemForm({ ...problemForm, difficulty: e.target.value })}>
            <option value="easy">easy</option>
            <option value="medium">medium</option>
            <option value="hard">hard</option>
          </select>
        </label>
        <button type="submit">Create problem</button>
      </form>

      {selected && (
        <>
          <h3>Tests for this problem</h3>
          <p className="muted">
            {visibleCount} visible · {hiddenCount} hidden. Hidden test data is never shown here.
          </p>
          <ul className="runs">
            {tests.map((t) => (
              <li key={t.id}>
                {t.is_hidden
                  ? `Hidden test #${t.id}`
                  : `Visible test #${t.id}: input ${JSON.stringify(t.input_text)} → ${JSON.stringify(t.expected_output)}`}
              </li>
            ))}
          </ul>

          <h3>Add a test</h3>
          <form className="scorecard" onSubmit={addTest}>
            <label>
              Input (stdin)
              <textarea required value={testForm.input_text}
                onChange={(e) => setTestForm({ ...testForm, input_text: e.target.value })} />
            </label>
            <label>
              Expected output
              <textarea required value={testForm.expected_output}
                onChange={(e) => setTestForm({ ...testForm, expected_output: e.target.value })} />
            </label>
            <label>
              <span>
                <input type="checkbox" checked={testForm.is_hidden}
                  onChange={(e) => setTestForm({ ...testForm, is_hidden: e.target.checked })} /> Hidden from candidate
              </span>
            </label>
            <button type="submit">Add test</button>
          </form>
        </>
      )}
    </section>
  );
}

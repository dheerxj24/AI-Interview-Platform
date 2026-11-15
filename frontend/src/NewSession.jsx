import { useEffect, useState } from "react";
import { api, hasAdminToken, setAdminToken } from "./api.js";
import AdminLogin from "./AdminLogin.jsx";

export default function NewSession() {
  const [problems, setProblems] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [form, setForm] = useState({ problem_id: "", candidate_name: "", interviewer_name: "" });
  const [error, setError] = useState("");

  useEffect(() => {
    if (!hasAdminToken()) return;
    api.problems().then(setProblems).catch((e) => setError(e.message));
    api.listSessions().then(setSessions).catch((e) => setError(e.message));
  }, []);

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      const session = await api.createSession({ ...form, problem_id: Number(form.problem_id) });
      window.location.search = `?session=${session.id}&token=${session.interviewer_token}&candidate_token=${session.candidate_token}`;
    } catch (err) {
      setError(err.message);
    }
  }

  const update = (field) => (event) => setForm({ ...form, [field]: event.target.value });

  if (!hasAdminToken()) return <AdminLogin />;

  return (
    <div className="auth-frame">
      <section className="auth-left">
        <div className="auth-pill">Interview Platform</div>
        <div className="auth-form-box">
          <h2>New interview</h2>
          <p className="auth-sub">Pick a problem and add the two people in the room.</p>
          <form onSubmit={submit}>
            <label className="auth-field">
              <span>Problem</span>
              <select required value={form.problem_id} onChange={update("problem_id")}>
                <option value="">Choose a problem</option>
                {problems.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title} ({p.difficulty})
                  </option>
                ))}
              </select>
            </label>
            <label className="auth-field">
              <span>Candidate</span>
              <input required value={form.candidate_name} onChange={update("candidate_name")} />
            </label>
            <label className="auth-field">
              <span>Interviewer</span>
              <input required value={form.interviewer_name} onChange={update("interviewer_name")} />
            </label>
            <button type="submit" className="auth-submit">Create session</button>
          </form>
          {error && <p className="error">{error}</p>}
          <p className="auth-note">
            <a href="?problems=1">Manage problems and tests</a> ·{" "}
            <a
              href="#"
              onClick={(e) => {
                e.preventDefault();
                setAdminToken("");
                window.location.reload();
              }}
            >
              Forget admin token
            </a>
          </p>
        </div>
      </section>

      <section className="auth-right">
        <div className="auth-art auth-list">
          <h3 className="auth-list-title">Recent sessions</h3>
          {sessions.length === 0 && <p className="auth-sub">No sessions yet.</p>}
          <div className="auth-list-items">
          {sessions.slice(0, 6).map((s) => (
            <a
              key={s.id}
              className={`auth-session ${s.status}`}
              href={s.status === "ended" ? `?summary=${s.id}` : `?session=${s.id}`}
            >
              <strong>{s.candidate_name}</strong>
              <span>
                session #{s.id} · {s.status}
              </span>
            </a>
          ))}
          </div>
        </div>
      </section>
    </div>
  );
}

import { useEffect, useState } from "react";
import { api, getSessionToken } from "./api.js";

const EVENT_LABELS = { tab_hidden: "Tab hidden", window_blur: "Window lost focus", paste: "Paste" };

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : "—";
}

export default function Summary({ sessionId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.summary(sessionId).then(setData).catch((e) => setError(e.message));
  }, [sessionId]);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading summary...</p>;

  const { session, problem, code, run_count, best_full_run, scorecard, events = [] } = data;
  const counts = events.reduce((acc, e) => ({ ...acc, [e.kind]: (acc[e.kind] || 0) + 1 }), {});

  return (
    <section className="session">
      <p className="back-link"><a href="?">← Home</a></p>
      <h2>Interview summary</h2>
      <p className="muted">
        {session.candidate_name} with {session.interviewer_name} · {session.status}
      </p>

      <div className="grid">
        <div className="stat">
          <span className="muted">Problem</span>
          <strong>{problem.title}</strong>
          <span className="muted">{problem.difficulty}</span>
        </div>
        <div className="stat">
          <span className="muted">Started</span>
          <strong>{formatTime(session.started_at)}</strong>
        </div>
        <div className="stat">
          <span className="muted">Ended</span>
          <strong>{formatTime(session.ended_at)}</strong>
        </div>
        <div className="stat">
          <span className="muted">Runs</span>
          <strong>{run_count}</strong>
        </div>
        <div className="stat">
          <span className="muted">Best full result</span>
          <strong>
            {best_full_run ? `${best_full_run.passed}/${best_full_run.total} passed` : "No full run yet"}
          </strong>
        </div>
        <div className="stat">
          <span className="muted">Scores</span>
          <strong>
            {scorecard
              ? `Correctness ${scorecard.correctness}/5 · Communication ${scorecard.communication}/5`
              : "Not scored"}
          </strong>
        </div>
      </div>

      <h3>Integrity events</h3>
      {events.length === 0 ? (
        <p className="muted">No tab switches, focus loss, or pastes recorded.</p>
      ) : (
        <>
          <p className="muted">
            {Object.entries(counts).map(([kind, n]) => `${EVENT_LABELS[kind]}: ${n}`).join(" · ")}
          </p>
          <ul className="runs">
            {events.map((e, i) => (
              <li key={i}>
                <strong>{EVENT_LABELS[e.kind]}</strong> · {formatTime(e.at)}
                {e.detail && ` · ${e.detail}`}
              </li>
            ))}
          </ul>
        </>
      )}

      {scorecard?.notes && (
        <>
          <h3>Interviewer notes</h3>
          <p>{scorecard.notes}</p>
        </>
      )}

      <h3>Final code</h3>
      <pre className="copilot">{code || "No code saved."}</pre>

      <p>
        <a href={`?session=${sessionId}&token=${encodeURIComponent(getSessionToken())}`}>Back to session</a> · <a href="?">New interview</a>
      </p>
    </section>
  );
}

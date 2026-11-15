import { useEffect, useRef, useState } from "react";
import * as Y from "yjs";
import { Awareness, applyAwarenessUpdate, encodeAwarenessUpdate } from "y-protocols/awareness";
import { api, getAdminToken, getSessionToken, WS } from "./api.js";
import CodeEditor from "./CodeEditor.jsx";

// First byte of every binary frame says what the payload is.
const FRAME_DOC = 0;
const FRAME_AWARENESS = 1;

function parseDetails(output) {
  try {
    return JSON.parse(output || "[]");
  } catch {
    return [];
  }
}

function sendFrame(socket, kind, payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  const frame = new Uint8Array(payload.length + 1);
  frame[0] = kind;
  frame.set(payload, 1);
  socket.send(frame);
}

export default function Session({ sessionId, role = "interviewer" }) {
  const [session, setSession] = useState(null);
  const [problem, setProblem] = useState(null);
  const [feedback, setFeedback] = useState(null);
  const [shared, setShared] = useState(null);
  const [code, setCode] = useState("");
  const [runs, setRuns] = useState([]);
  const [connection, setConnection] = useState("connecting");
  const [peers, setPeers] = useState(0);
  const [copilotText, setCopilotText] = useState("");
  const [score, setScore] = useState({ correctness: 3, communication: 3, notes: "" });
  const [drafting, setDrafting] = useState(false);
  const [message, setMessage] = useState("");
  const saveTimer = useRef(null);
  const isInterviewer = role === "interviewer";
  const ended = session?.status === "ended";
  const candidateLocked = !isInterviewer && ended;
  const candidateToken = new URLSearchParams(window.location.search).get("candidate_token") || "";

  useEffect(() => {
    api
      .getSession(sessionId)
      .then((current) => {
        setSession(current);
        // Opening the interviewer view starts the session clock, once.
        if (role === "interviewer" && current.status === "scheduled") {
          api.updateSession(sessionId, { status: "live" }).then(setSession).catch(() => {});
        }
      })
      .catch((e) => setMessage(e.message));
    api.runs(sessionId).then(setRuns).catch(() => {});
    api.sessionProblem(sessionId).then(setProblem).catch(() => {});

    const doc = new Y.Doc();
    const ytext = doc.getText("code");
    const awareness = new Awareness(doc);
    awareness.setLocalStateField("user", { name: `Guest ${Math.floor(Math.random() * 90) + 10}` });
    const socket = new WebSocket(`${WS}/ws/sessions/${sessionId}?token=${encodeURIComponent(getSessionToken() || getAdminToken())}`);
    socket.binaryType = "arraybuffer";

    let gotRemoteDoc = false;

    // Local edits go to the other clients. Remote edits are applied with origin "remote" and not echoed back.
    doc.on("update", (update, origin) => {
      if (origin !== "remote") sendFrame(socket, FRAME_DOC, update);
    });
    awareness.on("update", ({ added, updated, removed }, origin) => {
      if (origin !== "remote") {
        sendFrame(socket, FRAME_AWARENESS, encodeAwarenessUpdate(awareness, [...added, ...updated, ...removed]));
      }
    });
    awareness.on("change", () => {
      const others = [...awareness.getStates().keys()].filter((id) => id !== doc.clientID);
      setPeers(others.length);
    });

    // Keep a plain copy for Run, and autosave local edits (not remote ones).
    ytext.observe((_event, transaction) => {
      setCode(ytext.toString());
      if (transaction.origin === "remote") return;
      clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => {
        api.saveSnapshot(sessionId, ytext.toString()).catch(() => {});
      }, 2000);
    });

    socket.onopen = () => {
      setConnection("live");
      socket.send(JSON.stringify({ type: "sync_request" }));
      sendFrame(socket, FRAME_AWARENESS, encodeAwarenessUpdate(awareness, [doc.clientID]));
      // If nobody answers, start from the last saved code instead of an empty editor.
      setTimeout(() => {
        // Restore the saved code whenever the editor is still empty, even if a connected peer sent an empty doc.
        if (ytext.length === 0) {
          api
            .latestSnapshot(sessionId)
            .then((snap) => {
              if (snap.code && ytext.length === 0) doc.transact(() => ytext.insert(0, snap.code));
            })
            .catch(() => {});
        }
      }, 800);
    };
    socket.onclose = () => setConnection("offline");
    socket.onmessage = (event) => {
      if (typeof event.data === "string") {
        const data = JSON.parse(event.data);
        if (data.type === "sync_request") sendFrame(socket, FRAME_DOC, Y.encodeStateAsUpdate(doc));
        return;
      }
      const bytes = new Uint8Array(event.data);
      const payload = bytes.slice(1);
      if (bytes[0] === FRAME_DOC) {
        gotRemoteDoc = true;
        Y.applyUpdate(doc, payload, "remote");
      } else if (bytes[0] === FRAME_AWARENESS) {
        applyAwarenessUpdate(awareness, payload, "remote");
      }
    };

    setShared({ ytext, awareness });
    return () => {
      clearTimeout(saveTimer.current);
      awareness.destroy();
      socket.close();
      doc.destroy();
    };
  }, [sessionId]);

  // Candidate view: wait for the interviewer to end the session, then show the released scores.
  useEffect(() => {
    if (role !== "candidate") return undefined;
    let timer;
    const check = async () => {
      try {
        const current = await api.getSession(sessionId);
        setSession(current);
        if (current.status === "ended") {
          const result = await api.feedback(sessionId);
          setFeedback(result);
          if (result.correctness != null) return;
        }
      } catch {
        // Keep polling; a transient failure should not stop the check.
      }
      timer = setTimeout(check, 3000);
    };
    check();
    return () => clearTimeout(timer);
  }, [sessionId, role]);

  // Record tab switches, focus loss, and pastes (lengths only, never the pasted text).
  useEffect(() => {
    if (role !== "candidate") return undefined;
    const post = (kind, detail = "") => api.recordEvent(sessionId, kind, detail).catch(() => {});
    const onVisibility = () => {
      if (document.hidden) post("tab_hidden");
    };
    const onBlur = () => post("window_blur");
    const onPaste = (event) => {
      const text = event.clipboardData?.getData("text") || "";
      post("paste", `${text.length} chars`);
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", onBlur);
    document.addEventListener("paste", onPaste);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("blur", onBlur);
      document.removeEventListener("paste", onPaste);
    };
  }, [sessionId, role]);

  // Poll while any run is still queued.
  useEffect(() => {
    if (!runs.some((r) => r.status === "queued")) return;
    const timer = setInterval(() => api.runs(sessionId).then(setRuns).catch(() => {}), 1000);
    return () => clearInterval(timer);
  }, [runs, sessionId]);

  async function startRun(kind) {
    setMessage("");
    try {
      const run = await api.startRun(sessionId, kind, code);
      setRuns((prev) => [...prev, run]);
    } catch (err) {
      setMessage(err.message);
    }
  }

  async function askCopilot() {
    setCopilotText("Thinking...");
    try {
      const result = await api.copilot(sessionId);
      setCopilotText(result.suggestions);
    } catch (err) {
      setCopilotText(err.message);
    }
  }

  async function draftScorecard() {
    setMessage("");
    setDrafting(true);
    try {
      const draft = await api.aiScorecard(sessionId);
      setScore({ correctness: draft.correctness, communication: draft.communication, notes: draft.notes });
      setMessage("AI draft filled in. Review it, then save.");
    } catch (err) {
      setMessage(err.message);
    } finally {
      setDrafting(false);
    }
  }

  async function saveScorecard(event) {
    event.preventDefault();
    try {
      await api.saveScorecard(sessionId, {
        correctness: Number(score.correctness),
        communication: Number(score.communication),
        notes: score.notes,
      });
      setMessage("Scorecard saved");
    } catch (err) {
      setMessage(err.message);
    }
  }

  async function endSession() {
    try {
      await api.updateSession(sessionId, { status: "ended" });
      window.location.search = `?summary=${sessionId}&token=${encodeURIComponent(getSessionToken())}`;
    } catch (err) {
      setMessage(err.message);
    }
  }

  return (
    <div className="session-frame">
    <section className="session session-main">
      <p className="back-link"><a href="?">← Home</a></p>
      <div className="session-head">
        <div>
          <h2>{session ? `${session.candidate_name} · session #${session.id}` : "Loading session..."}</h2>
          {session && <p className="muted">Interviewer: {session.interviewer_name}</p>}
          {isInterviewer && session && candidateToken && (
            <p className="muted">
              Candidate link: <code>{`${window.location.origin}/?session=${sessionId}&role=candidate&token=${candidateToken}`}</code>
            </p>
          )}
        </div>
        <div className="head-right">
          <span className="muted">
            {peers} other {peers === 1 ? "person" : "people"} here
          </span>
          <span className={`pill ${connection}`}>{connection}</span>
        </div>
      </div>

      {isInterviewer && ended && (
        <div className="ended-card">
          <h3>Interview ended</h3>
          <p>
            <a href={`?summary=${sessionId}&token=${encodeURIComponent(getSessionToken())}`}>View summary</a>
          </p>
        </div>
      )}

      {candidateLocked && (
        <div className="ended-card">
          <h3>Interview ended</h3>
          {feedback?.correctness != null ? (
            <p>
              Correctness {feedback.correctness}/5 · Communication {feedback.communication}/5
            </p>
          ) : (
            <p className="muted">Your scores will appear here once the interviewer records them.</p>
          )}
        </div>
      )}

      {problem && (
        <div className="problem">
          <h3>
            {problem.title} <span className="muted">· {problem.difficulty}</span>
          </h3>
          <pre className="problem-prompt">{problem.prompt}</pre>
        </div>
      )}

      {shared ? (
        <CodeEditor ytext={shared.ytext} awareness={shared.awareness} readOnly={ended} />
      ) : (
        <div className="code-editor muted">Connecting...</div>
      )}

      {!ended && (
      <div className="actions">
        <button onClick={() => startRun("visible")}>Run visible tests</button>
        <button onClick={() => startRun("full")}>Run all tests</button>
        {isInterviewer && (
          <>
            <button className="secondary" onClick={askCopilot}>Ask co-pilot</button>
            <button className="secondary" onClick={endSession}>End session</button>
          </>
        )}
      </div>
      )}
      {message && <p className="error">{message}</p>}

      </section>
      <aside className="session session-side">
      <h3>Runs</h3>
      {runs.length === 0 && <p className="muted">No runs yet.</p>}
      <ul className="runs">
        {runs.map((run) => (
          <li key={run.id}>
            <strong>{run.kind === "visible" ? "Visible" : "Full"}</strong> ·{" "}
            {run.status === "done"
              ? `${run.passed_count}/${run.total_count} passed · ${run.runtime_ms} ms`
              : run.status}
            {run.error && <span className="error"> {run.error}</span>}
            {run.kind === "visible" &&
              parseDetails(run.output).map((t) => (
                <div key={t.test_id} className={t.passed ? "ok" : "bad"}>
                  {t.passed ? "pass" : "fail"} · input {JSON.stringify(t.input)} · expected{" "}
                  {JSON.stringify(t.expected)} · got {JSON.stringify(t.stdout)}
                </div>
              ))}
          </li>
        ))}
      </ul>

      {isInterviewer && copilotText && (
        <>
          <h3>Co-pilot suggestions</h3>
          <pre className="copilot">{copilotText}</pre>
        </>
      )}

      {isInterviewer && (
      <>
      <h3>Scorecard</h3>
      <form className="scorecard" onSubmit={saveScorecard}>
        <label>
          Correctness (1–5)
          <input type="number" min="1" max="5" value={score.correctness}
            onChange={(e) => setScore({ ...score, correctness: e.target.value })} />
        </label>
        <label>
          Communication (1–5)
          <input type="number" min="1" max="5" value={score.communication}
            onChange={(e) => setScore({ ...score, communication: e.target.value })} />
        </label>
        <label>
          Notes
          <textarea value={score.notes} onChange={(e) => setScore({ ...score, notes: e.target.value })} />
        </label>
        <button type="button" className="secondary" disabled={drafting} onClick={draftScorecard}>{drafting ? "Drafting..." : "Draft with AI"}</button>
        <button type="submit">Save scorecard</button>
      </form>
      </>
      )}
      </aside>
    </div>
  );
}

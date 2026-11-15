import { useState } from "react";
import { setAdminToken } from "./api.js";

// Admin sign-in. The token is kept only in this browser tab's session storage.
export default function AdminLogin() {
  const [value, setValue] = useState("");
  const [show, setShow] = useState(false);

  function submit(event) {
    event.preventDefault();
    setAdminToken(value.trim());
    window.location.reload();
  }

  return (
    <div className="auth-frame">
      <section className="auth-left">
        <div className="auth-pill">Interview Platform</div>
        <div className="auth-form-box">
          <h2>Admin sign-in</h2>
          <p className="auth-sub">Enter your admin token to manage problems and interviews.</p>
          <form onSubmit={submit}>
            <label className="auth-field">
              <span>Admin token</span>
              <div className="auth-pillinput">
                <input
                  type={show ? "text" : "password"}
                  required
                  autoFocus
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                />
                <button type="button" className="auth-toggle" onClick={() => setShow(!show)}>
                  {show ? "hide" : "show"}
                </button>
              </div>
            </label>
            <button type="submit" className="auth-submit">Continue</button>
          </form>
          <p className="auth-note">The token is kept only in this browser tab.</p>
        </div>
      </section>

      <section className="auth-right">
        <div className="auth-art">
          <div className="auth-float auth-float-1">
            <strong>Live interview</strong>
            <span>Shared editor, 2 people</span>
          </div>
          <div className="auth-float auth-float-2">
            <strong>Scorecard saved</strong>
            <span>Correctness 4/5</span>
          </div>
          <div className="auth-float auth-float-3">
            <strong>Summary ready</strong>
            <span>Runs, events and notes</span>
          </div>
        </div>
      </section>
    </div>
  );
}

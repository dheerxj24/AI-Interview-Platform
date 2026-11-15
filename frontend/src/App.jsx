import { setSessionToken } from "./api.js";
import NewSession from "./NewSession.jsx";
import Problems from "./Problems.jsx";
import Session from "./Session.jsx";
import Summary from "./Summary.jsx";

export default function App() {
  const params = new URLSearchParams(window.location.search);
  const sessionId = params.get("session");
  const summaryId = params.get("summary");
  const role = params.get("role") === "candidate" ? "candidate" : "interviewer";
  setSessionToken(params.get("token") || "");

  let page;
  if (summaryId) page = <Summary sessionId={Number(summaryId)} />;
  else if (sessionId) page = <Session sessionId={Number(sessionId)} role={role} />;
  else if (params.has("problems")) page = <Problems />;
  else page = <NewSession />;

  return (
    <main className="shell">
      {(sessionId || summaryId || params.has("problems")) && (
        <header>
          <h1><a href="?">Interview Platform</a></h1>
        </header>
      )}
      {page}
    </main>
  );
}

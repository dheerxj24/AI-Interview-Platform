import { useEffect, useRef } from "react";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
import { defaultKeymap, indentWithTab } from "@codemirror/commands";
import { python } from "@codemirror/lang-python";
import { yCollab } from "y-codemirror.next";

// Code editor bound to a shared Y.Text. Remote edits and cursors update in place,
// so the cursor no longer jumps when someone else types.
export default function CodeEditor({ ytext, awareness, readOnly = false }) {
  const host = useRef(null);

  useEffect(() => {
    const view = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: "",
        extensions: [
          lineNumbers(),
          keymap.of([...defaultKeymap, indentWithTab]),
          python(),
          yCollab(ytext, awareness),
          EditorState.readOnly.of(readOnly),
        ],
      }),
    });
    return () => view.destroy();
  }, [ytext, awareness, readOnly]);

  return <div className="code-editor" ref={host} />;
}

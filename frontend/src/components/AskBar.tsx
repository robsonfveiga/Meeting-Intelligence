import { useEffect, useRef, useState } from "react";
import styles from "./AskBar.module.css";

interface Props {
  onAsk: (question: string) => void;
  busy: boolean;
  disabled: boolean;
}

/**
 * The question, set as the largest thing on the page.
 *
 * A textarea rather than an input, because the questions worth asking here run
 * long — "what did we decide about pricing, and was it revisited?" — and a single
 * line that scrolls sideways hides the thing the reader is composing.
 */
export function AskBar({ onAsk, busy, disabled }: Props) {
  const [value, setValue] = useState("");
  const field = useRef<HTMLTextAreaElement>(null);

  // "/" jumps here from anywhere, the way search does in tools people already know.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing =
        target?.tagName === "TEXTAREA" || target?.tagName === "INPUT";
      if (event.key === "/" && !typing) {
        event.preventDefault();
        field.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function submit() {
    if (!value.trim() || busy || disabled) return;
    onAsk(value);
  }

  return (
    <form
      className={styles.wrap}
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      {/*
        A label rather than a decorative eyebrow: it says the field is a field, and
        clicking it focuses the field, which a floating caption would not. It sits
        above the box rather than inside it, so the box reads as one surface.
      */}
      <label className={styles.eyebrow} htmlFor="question">
        Ask across the corpus
      </label>

      <div className={styles.ask}>
        <textarea
          id="question"
          ref={field}
          className={styles.field}
          value={value}
          rows={1}
          disabled={disabled}
          spellCheck={false}
          aria-label="Ask a question about the meetings"
          placeholder={
            disabled ? "Ingest a transcript first" : "What was decided?"
          }
          onChange={(event) => {
            setValue(event.target.value);
            const box = event.target;
            box.style.height = "auto";
            box.style.height = `${box.scrollHeight}px`;
          }}
          onKeyDown={(event) => {
            // Enter asks; Shift+Enter is a new line. The common action is the cheap one.
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />

        <div className={styles.controls}>
          <kbd className={styles.hint}>/</kbd>
          <button
            type="submit"
            className={styles.go}
            disabled={busy || disabled || !value.trim()}
          >
            {busy ? "Working" : "Ask"}
          </button>
        </div>
      </div>
    </form>
  );
}

import { useMemo, useState } from "react";
import { AnswerStream } from "./components/AnswerStream";
import { AskBar } from "./components/AskBar";
import { BuildTrace } from "./components/BuildTrace";
import { CorpusList } from "./components/CorpusList";
import { CorpusTimeline } from "./components/CorpusTimeline";
import { EvidencePanel } from "./components/EvidencePanel";
import { IngestPanel } from "./components/IngestPanel";
import { TheRecord } from "./components/TheRecord";
import { ThemeToggle } from "./components/ThemeToggle";
import { useAnswerStream } from "./hooks/useAnswerStream";
import { useFacts } from "./hooks/useFacts";
import { useMeetings } from "./hooks/useMeetings";
import { useTheme } from "./hooks/useTheme";
import { useTimeline } from "./hooks/useTimeline";
import styles from "./App.module.css";

type View = "ask" | "record" | "corpus";

const VIEWS: { id: View; label: string }[] = [
  { id: "ask", label: "Ask" },
  { id: "record", label: "The record" },
  // Named for what it holds rather than for one of the two things it does, now
  // that meetings can be removed here as well as added.
  { id: "corpus", label: "The corpus" },
];

/**
 * The timeline stays on screen in every view rather than belonging to one.
 *
 * It is the spine the whole product hangs off: in the answering view its marks
 * light up as evidence, in the record it is the shape of what was decided and
 * when, and after an ingest a new band simply appears. Hiding it per view would
 * turn the one thing that makes this application legible into a tab.
 */
export default function App() {
  const [view, setView] = useState<View>("ask");
  /**
   * One focused item, shared by three surfaces. Hovering a `[2]` in the prose,
   * its evidence card, or its mark on the timeline lights all three — because a
   * claim, the excerpt under it and the moment it was said are one thing, and the
   * interface should not make that a leap of faith.
   */
  const [focused, setFocused] = useState<string | null>(null);

  const { theme, toggle } = useTheme();
  const {
    meetings,
    loading,
    error,
    refresh: refreshMeetings,
    remove: removeMeeting,
  } = useMeetings();
  const { facts, refresh: refreshFacts } = useFacts();
  const answer = useAnswerStream();

  const citedChunkIds = useMemo(
    () =>
      new Map(
        answer.citations.map((citation) => [
          citation.chunk_id,
          citation.marker,
        ]),
      ),
    [answer.citations],
  );

  const bands = useTimeline(meetings, facts, answer.excerpts, citedChunkIds);

  const working =
    answer.status === "retrieving" || answer.status === "streaming";
  const chunkTotal = meetings.length ? facts.length : 0;

  return (
    <div className={styles.app}>
      <header className={styles.masthead}>
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true" />
          <h1 className={styles.wordmark}>Meeting Intelligence</h1>
        </div>

        <p className={styles.corpusStat}>
          {meetings.length} meetings · {chunkTotal} recorded facts
        </p>

        <nav className={styles.nav} aria-label="Views">
          {VIEWS.map((entry) => (
            <button
              key={entry.id}
              type="button"
              className={`${styles.tab} ${view === entry.id ? styles.current : ""}`}
              aria-current={view === entry.id}
              onClick={() => setView(entry.id)}
            >
              {entry.label}
            </button>
          ))}
          <ThemeToggle theme={theme} onToggle={toggle} />
        </nav>
      </header>

      {error && <p className={styles.offline}>{error}</p>}

      <section className={styles.hero}>
        <AskBar
          onAsk={(question) => {
            setView("ask");
            void answer.ask(question);
          }}
          busy={working}
          disabled={!meetings.length}
        />

        <CorpusTimeline
          bands={bands}
          focused={focused}
          onFocus={setFocused}
          dimmed={working}
          loading={loading}
        />
      </section>

      {view === "ask" && (
        <main key="ask" className={styles.main}>
          {answer.status === "idle" && (
            <div className={styles.invitation}>
              <p>
                Ask something that spans more than one meeting. The interesting
                questions here are the ones a single transcript cannot answer —{" "}
                <em>was that decision revisited?</em>,{" "}
                <em>did the thing Priya promised ever go out?</em>
              </p>
              <p className={styles.invitationNote}>
                Every claim comes back with the excerpt behind it, and the marks
                above show which moments it rests on.
              </p>
            </div>
          )}

          {answer.status === "retrieving" && (
            <p className={styles.retrieving}>
              Retrieved {answer.excerpts.length || "…"} excerpts. Reading them.
            </p>
          )}

          {answer.error && (
            <div className={styles.failure}>
              <h2>That did not work</h2>
              <p>{answer.error}</p>
            </div>
          )}

          {(answer.text || answer.refused) && (
            <div className={styles.result}>
              <div className={styles.answerColumn}>
                {answer.refused ? (
                  <div className={styles.refusal}>
                    <p className={styles.refusalText}>
                      Nothing in these transcripts answers that.
                    </p>
                    <p className={styles.refusalNote}>
                      Retrieval came back empty, so no model was called and
                      nothing was spent guessing. This is the system working,
                      not failing.
                    </p>
                  </div>
                ) : (
                  <AnswerStream
                    text={answer.text}
                    citations={answer.citations}
                    streaming={answer.status === "streaming"}
                    focused={focused}
                    onFocus={setFocused}
                  />
                )}
              </div>

              <EvidencePanel
                excerpts={answer.excerpts}
                citations={answer.citations}
                focused={focused}
                onFocus={setFocused}
              />

              {answer.trace && (
                <div className={styles.traceRow}>
                  <BuildTrace trace={answer.trace} />
                </div>
              )}
            </div>
          )}
        </main>
      )}

      {view === "record" && (
        <main key="record" className={styles.main}>
          <TheRecord facts={facts} focused={focused} onFocus={setFocused} />
        </main>
      )}

      {view === "corpus" && (
        <main key="corpus" className={styles.main}>
          <div className={styles.corpusView}>
            <IngestPanel
              onIngested={() => {
                void refreshMeetings();
                void refreshFacts();
              }}
            />

            <CorpusList
              meetings={meetings}
              onRemove={async (id) => {
                await removeMeeting(id);
                // The record and the timeline both read facts, and the deleted
                // meeting's facts went with it — so they are refetched rather
                // than left showing entries whose transcript no longer exists.
                refreshFacts();
              }}
            />
          </div>
        </main>
      )}

      <footer className={styles.footer}>
        <span>Answers are drawn only from ingested transcripts.</span>
        <span>
          Citations are verified; whether an excerpt supports its claim is not.
        </span>
      </footer>
    </div>
  );
}

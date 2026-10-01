import { useEffect, useRef, useState } from "react";
import { ChevronDown, MousePointer2, Search, Sparkles, X } from "lucide-react";
import { IconButton } from "../ui/Button";

type HelpTopic = { title: string; text: string; steps: string[] };

const TOPICS: HelpTopic[] = [
  {
    title: "Ask Nanvi",
    text: "Enter a question in the message box. Press Enter to send, or Shift+Enter to start a new line.",
    steps: ["Type your question in the message box.", "Press Enter to send it.", "Read Nanvi’s answer and sources."],
  },
  {
    title: "Attach a file",
    text: "Choose Attach File to add a PDF, DOCX, XLSX, CSV, TXT, or Markdown file to your question.",
    steps: ["Choose Attach File beside the message box.", "Select a supported document from your device.", "Add your question and send."],
  },
  {
    title: "Company file search",
    text: "Use the company file search control in the composer to turn document search on or off for a question.",
    steps: ["Turn company file search on in the composer.", "Type a question about company documents.", "Send it to get an answer grounded in files."],
  },
  {
    title: "Sources and answers",
    text: "When an answer includes sources, select a source to inspect the available document details. You can copy or retry an answer using its actions.",
    steps: ["Select a source listed under an answer.", "Review the document details that open.", "Use Copy or Retry from the answer actions."],
  },
  {
    title: "Conversation history",
    text: "Select a conversation under Recent to continue it. Choose New chat to begin a separate conversation.",
    steps: ["Open a conversation under Recent.", "Continue by sending your next message.", "Choose New chat to start a separate conversation."],
  },
  {
    title: "Reports and other tools",
    text: "Open More tools for the Knowledge, Email, Data, Reports, and department pages available to your account. Settings stays in the main navigation.",
    steps: ["Open More tools in the navigation.", "Choose a page available to your account.", "Use its search or actions to explore your data."],
  },
  {
    title: "Connections Hub",
    text: "Open Settings, then Connections Hub to see which services Nanvi can use, such as cloud storage, email, and databases. Active Connections shows linked services; Integrations Catalog lists available services. Depending on your role, you can connect, test, or manage a service and set its personal or organization scope.",
    steps: ["Open Settings, then Connections Hub.", "Review linked services or browse the catalog.", "Connect, test, or manage services allowed for your role."],
  },
];

type Props = { onClose: () => void };

export function HelpPanel({ onClose }: Props) {
  const [query, setQuery] = useState("");
  const [hoveredTopic, setHoveredTopic] = useState<string | null>(null);
  const [focusedTopic, setFocusedTopic] = useState<string | null>(null);
  const [pinnedTopic, setPinnedTopic] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const visibleTopics = TOPICS.filter((topic) => `${topic.title} ${topic.text}`.toLowerCase().includes(query.trim().toLowerCase()));
  const activeTopic = pinnedTopic ?? hoveredTopic ?? focusedTopic;

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    searchRef.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      opener?.focus();
    };
  }, []);

  const onKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      if (pinnedTopic) {
        setPinnedTopic(null);
        setHoveredTopic(null);
        setFocusedTopic(null);
        return;
      }
      closeRef.current();
      return;
    }
    if (event.key !== "Tab") return;
    const nodes = Array.from(panelRef.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])') ?? []);
    if (nodes.length === 0) { event.preventDefault(); return; }
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === panelRef.current)) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && active === last) { event.preventDefault(); first.focus(); }
  };

  return (
    <>
      <button type="button" tabIndex={-1} className="help-backdrop" aria-label="Close help" onClick={onClose} />
      <aside ref={panelRef} className="help-panel" role="dialog" aria-modal="true" aria-labelledby="help-title" tabIndex={-1} onKeyDown={onKeyDown}>
        <header className="help-panel-head">
          <h2 id="help-title">Nanvi help</h2>
          <IconButton icon={X} label="Close help" onClick={onClose} />
        </header>
        <label className="help-search">
          <Search size={17} aria-hidden="true" />
          <span className="sr-only">Search help</span>
          <input
            ref={searchRef}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search help"
          />
        </label>
        <div className="help-topic-list">
          {visibleTopics.map((topic) => {
            const topicId = topic.title.toLowerCase().replace(/[^a-z0-9]+/g, "-");
            const isOpen = activeTopic === topic.title;
            return (
              <section
                key={topic.title}
                className={`help-topic${isOpen ? " is-open" : ""}`}
                onMouseEnter={() => setHoveredTopic(topic.title)}
                onMouseLeave={() => setHoveredTopic((current) => current === topic.title ? null : current)}
                onFocus={() => setFocusedTopic(topic.title)}
                onBlur={(event) => {
                  if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                    setFocusedTopic((current) => current === topic.title ? null : current);
                  }
                }}
              >
                <button
                  type="button"
                  className="help-topic-trigger"
                  aria-expanded={isOpen}
                  aria-controls={isOpen ? `help-walkthrough-${topicId}` : undefined}
                  onClick={() => setPinnedTopic((current) => current === topic.title ? null : topic.title)}
                >
                  <span className="help-topic-copy">
                    <span className="help-topic-title" role="heading" aria-level={3}>{topic.title}</span>
                    <span className="help-topic-text">{topic.text}</span>
                  </span>
                  <ChevronDown className="help-topic-chevron" size={18} aria-hidden="true" />
                </button>
                {isOpen && (
                  <div id={`help-walkthrough-${topicId}`} className="help-walkthrough" aria-label={`${topic.title} animated walkthrough`}>
                    <div className="help-walkthrough-head">
                      <Sparkles size={15} aria-hidden="true" />
                      <span>Quick walkthrough</span>
                      <span className="help-walkthrough-hint"><MousePointer2 size={13} aria-hidden="true" /> Steps animate</span>
                    </div>
                    <ol className="help-walkthrough-steps">
                      {topic.steps.map((step, index) => (
                        <li key={step}>
                          <span className="help-step-number">{index + 1}</span>
                          <span>{step}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
              </section>
            );
          })}
          {visibleTopics.length === 0 && <p className="help-empty">No help topics match your search.</p>}
        </div>
      </aside>
    </>
  );
}

import { ArrowUp, Bot, RotateCcw, Sparkles } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { apiRequest } from '../../lib/api';
import type { IntelligenceAnswer } from '../../types';
import type { WorkspaceView } from '../../constants';

interface IntelligenceDockProps {
  view: WorkspaceView;
}

const CONTEXT: Record<WorkspaceView, { label: string; placeholder: string; suggestions: string[] }> = {
  overview: {
    label: 'Organization brief',
    placeholder: 'Ask about the organization',
    suggestions: ['Tell me about the organization', 'What needs attention today?', 'What should I focus on?'],
  },
  meetings: {
    label: 'Meeting context',
    placeholder: 'Ask about upcoming meetings',
    suggestions: ['Summarize the meeting cadence', 'What is the next decision forum?', 'What meetings need preparation?'],
  },
  actions: {
    label: 'Action context',
    placeholder: 'Ask about commitments and owners',
    suggestions: ['What needs attention today?', 'Summarize the action queue', 'What should I focus on?'],
  },
  people: {
    label: 'People context',
    placeholder: 'Ask about the organization and people',
    suggestions: ['Tell me about the organization', 'Summarize the people directory', 'What should I focus on?'],
  },
  crm: {
    label: 'Customer context',
    placeholder: 'Ask about customer health',
    suggestions: ['Summarize customer health', 'What needs attention today?', 'Tell me about the organization'],
  },
  projects: {
    label: 'Project context',
    placeholder: 'Ask about initiatives and delivery',
    suggestions: ['Summarize the active projects', 'What needs attention today?', 'What should I focus on?'],
  },
  tickets: {
    label: 'Service context',
    placeholder: 'Ask about active service issues',
    suggestions: ['Summarize active issues', 'What needs attention today?', 'What should I focus on?'],
  },
  departments: {
    label: 'Department context',
    placeholder: 'Ask about operating teams',
    suggestions: ['Summarize the departments', 'What needs attention today?', 'Tell me about the organization'],
  },
  reports: { label: 'Reports', placeholder: 'Ask RAPID', suggestions: [] },
  library: { label: 'Library', placeholder: 'Ask RAPID', suggestions: [] },
  search: { label: 'Search', placeholder: 'Ask RAPID', suggestions: [] },
  notifications: {
    label: 'Signal context',
    placeholder: 'Ask about operating signals',
    suggestions: ['What needs attention today?', 'Summarize the operating signals', 'What should I focus on?'],
  },
  settings: { label: 'Settings', placeholder: 'Ask RAPID', suggestions: [] },
};

export function IntelligenceDock({ view }: IntelligenceDockProps) {
  const context = CONTEXT[view];
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<IntelligenceAnswer | null>(null);
  const [pending, setPending] = useState(false);
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function focusQuestion(event: KeyboardEvent) {
      if (event.key !== '/' || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target;
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || target instanceof HTMLButtonElement || (target instanceof HTMLElement && target.isContentEditable)) return;
      event.preventDefault();
      inputRef.current?.focus();
    }

    window.addEventListener('keydown', focusQuestion);
    return () => window.removeEventListener('keydown', focusQuestion);
  }, []);

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const prompt = question.trim();
    if (!prompt || pending) return;
    setPending(true);
    setOpen(true);
    try {
      const response = await apiRequest<IntelligenceAnswer>('/intelligence/ask', {
        method: 'POST',
        body: JSON.stringify({ question: prompt, workspace_view: view }),
      });
      setAnswer(response);
    } catch (issue) {
      setAnswer({
        id: 'local-error', answer: issue instanceof Error ? issue.message : 'RAPID could not complete this request.',
        confidence: 0, warning: 'Try again after confirming your organization AI runtime.', departments: [],
        action: 'error', mode: 'scoped_evidence_fallback', evidence: [],
      });
    } finally {
      setPending(false);
    }
  }

  function reset() {
    setAnswer(null);
    setQuestion('');
    setOpen(false);
  }

  return (
    <section className={`intelligence-dock${open ? ' open' : ''}`} aria-label="RAPID intelligence">
      <form className="intelligence-prompt" onSubmit={ask}>
        <div className="intelligence-mark"><Sparkles size={15} aria-hidden="true" /></div>
        <input
          id="intelligence-question"
          ref={inputRef}
          value={question}
          onFocus={() => setOpen(true)}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={context.placeholder}
          aria-label="Ask RAPID"
          aria-keyshortcuts="/"
          maxLength={2000}
        />
        {open && (answer || question) ? <button className="icon-button intelligence-reset" type="button" onClick={reset} title="Clear intelligence response" aria-label="Clear intelligence response"><RotateCcw size={14} /></button> : null}
        <button className="intelligence-submit" type="submit" aria-label="Ask RAPID" disabled={!question.trim() || pending}>
          {pending ? <Bot size={15} className="intelligence-thinking" aria-hidden="true" /> : <ArrowUp size={15} aria-hidden="true" />}
        </button>
      </form>
      {!answer && !pending && !question && context.suggestions.length ? <div className="intelligence-suggestions" aria-label={`${context.label} suggestions`}>
        {context.suggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => {
          setQuestion(suggestion);
          requestAnimationFrame(() => inputRef.current?.focus());
        }}>{suggestion}</button>)}
      </div> : null}
      {open && (pending || answer) ? <div className="intelligence-result" aria-live="polite">
        {pending ? <p className="intelligence-pending"><Bot size={15} aria-hidden="true" /> Preparing a governed response</p> : null}
        {answer ? <>
          <div className="intelligence-response"><p>{answer.answer}</p><div className="intelligence-meta"><span>{answer.mode === 'workspace_brief' ? context.label : answer.mode === 'scoped_evidence_fallback' ? 'Approved records' : 'RAPID analysis'}</span>{answer.confidence ? <span>{Math.round(answer.confidence * 100)}% confidence</span> : null}{answer.departments.length ? <span>{answer.departments.join(', ').replaceAll('_', ' ')}</span> : null}</div></div>
          {answer.evidence.length ? <details className="intelligence-evidence"><summary>{answer.evidence.length} approved source{answer.evidence.length === 1 ? '' : 's'}</summary><ul>{answer.evidence.map((item, index) => <li key={`${item.title}-${index}`}><strong>{item.title}</strong><span>{item.excerpt}</span></li>)}</ul></details> : null}
          {answer.warning ? <p className="intelligence-warning">{answer.warning}</p> : null}
        </> : null}
      </div> : null}
    </section>
  );
}

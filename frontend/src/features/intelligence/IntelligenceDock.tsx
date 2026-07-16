import { ArrowUp, Sparkles } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { WorkspaceView } from '../../constants';

interface IntelligenceDockProps {
  view: WorkspaceView;
  onOpenChat: (prompt: string, context: WorkspaceView) => void;
}

const CONTEXT: Record<WorkspaceView, { placeholder: string; suggestions: string[] }> = {
  overview: { placeholder: 'Ask RAPID for a grounded startup update', suggestions: ['Give me the startup operating picture', 'What needs attention today?', 'What should I focus on?'] },
  meetings: { placeholder: 'Ask RAPID about meetings and decisions', suggestions: ['What meetings need preparation?', 'What decisions are pending?', 'Summarize the meeting cadence'] },
  actions: { placeholder: 'Ask RAPID about commitments and owners', suggestions: ['What needs attention today?', 'Which actions are overdue?', 'Who owns the highest-priority work?'] },
  people: { placeholder: 'Ask RAPID about people and capacity', suggestions: ['What should I know about team capacity?', 'Summarize the people directory', 'What needs attention today?'] },
  crm: { placeholder: 'Ask RAPID about customers and revenue', suggestions: ['Which customers need attention?', 'Summarize customer health', 'What is at risk this quarter?'] },
  projects: { placeholder: 'Ask RAPID about delivery and risk', suggestions: ['Which projects need attention?', 'Summarize delivery risk', 'What is blocking progress?'] },
  tickets: { placeholder: 'Ask RAPID about service issues', suggestions: ['Which issues are most urgent?', 'Summarize active issues', 'What is blocking resolution?'] },
  departments: { placeholder: 'Ask RAPID about a work area', suggestions: ['How are the work areas operating?', 'Which work area needs attention?', 'What should I focus on?'] },
  chat: { placeholder: 'Ask RAPID about your startup', suggestions: [] },
  reports: { placeholder: 'Ask RAPID about reporting', suggestions: [] },
  library: { placeholder: 'Ask RAPID about the knowledge library', suggestions: [] },
  search: { placeholder: 'Ask RAPID about connected records', suggestions: [] },
  notifications: { placeholder: 'Ask RAPID about operating signals', suggestions: ['What needs attention today?', 'Summarize the operating signals', 'What should I focus on?'] },
  settings: { placeholder: 'Ask RAPID about this workspace', suggestions: [] },
};

export function IntelligenceDock({ view, onOpenChat }: IntelligenceDockProps) {
  const context = CONTEXT[view];
  const [question, setQuestion] = useState('');
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

  function openConversation(prompt: string) {
    const normalized = prompt.trim();
    if (!normalized) return;
    onOpenChat(normalized, view);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    openConversation(question);
  }

  return (
    <section className="intelligence-dock" aria-label="Ask RAPID about this workspace area">
      <form className="intelligence-prompt" onSubmit={submit}>
        <div className="intelligence-mark"><Sparkles size={15} aria-hidden="true" /></div>
        <input id="intelligence-question" ref={inputRef} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={context.placeholder} aria-label="Ask RAPID" aria-keyshortcuts="/" maxLength={2000} />
        <button className="intelligence-submit" type="submit" aria-label="Open RAPID chat" disabled={!question.trim()}><ArrowUp size={15} aria-hidden="true" /></button>
      </form>
      {context.suggestions.length ? <div className="intelligence-suggestions" aria-label="Suggested questions">
        {context.suggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => openConversation(suggestion)}>{suggestion}</button>)}
      </div> : null}
    </section>
  );
}

import { ArrowUp, Bot, MessageSquareText, Plus, Sparkles, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DEPARTMENTS, isWorkspaceView, VIEW_META, type WorkspaceView } from '../../constants';
import { apiRequest, getProfile } from '../../lib/api';
import { capabilitiesFor, permittedDepartments as accessDepartments } from '../../lib/access';
import type { ChatMessage, ChatSession, IntelligenceAnswer, WorkspaceData } from '../../types';

interface RapidChatProps {
  data: WorkspaceData;
}

function displaySessionDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function assistantResponse(message: ChatMessage): IntelligenceAnswer | null {
  return message.metadata?.response ?? null;
}

export function RapidChat({ data }: RapidChatProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState('');
  const [department, setDepartment] = useState('');
  const [context, setContext] = useState<WorkspaceView>('overview');
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const processedPrompt = useRef('');
  const transcriptRef = useRef<HTMLDivElement>(null);

  const permittedDepartments = useMemo(() => {
    return accessDepartments(getProfile(), data.overview.departments.map((item) => item.key));
  }, [data.overview.departments]);
  const promptFromPage = searchParams.get('prompt')?.trim() ?? '';
  const contextFromPage = searchParams.get('context');
  const companyScope = capabilitiesFor(getProfile()).configureTenant;

  useEffect(() => {
    async function loadSessions() {
      setLoadingSessions(true);
      setError('');
      try {
        const response = await apiRequest<{ sessions: ChatSession[] }>('/chat-sessions');
        setSessions(response.sessions);
        if (!promptFromPage && response.sessions[0]) void selectSession(response.sessions[0].id);
      } catch (issue) {
        setError(issue instanceof Error ? issue.message : 'RAPID conversations could not load.');
      } finally {
        setLoadingSessions(false);
      }
    }
    void loadSessions();
  // Conversations are loaded once; page prompts are handled by the effect below.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!promptFromPage) return;
    const pageContext: WorkspaceView = isWorkspaceView(contextFromPage ?? undefined) ? contextFromPage as WorkspaceView : 'overview';
    const key = `${pageContext}:${promptFromPage}`;
    if (processedPrompt.current === key) return;
    processedPrompt.current = key;
    setContext(pageContext);
    void startNewConversation(promptFromPage, pageContext);
  // A page prompt is an explicit launch command. Do not rerun it after messages update.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [promptFromPage, contextFromPage]);

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, sending]);

  async function refreshSessions(preferredId?: string) {
    const response = await apiRequest<{ sessions: ChatSession[] }>('/chat-sessions');
    setSessions(response.sessions);
    if (preferredId) setSessionId(preferredId);
  }

  async function selectSession(id: string) {
    setLoadingMessages(true);
    setError('');
    try {
      const response = await apiRequest<{ messages: ChatMessage[] }>(`/chat-sessions/${id}/messages`);
      setSessionId(id);
      setMessages(response.messages);
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : 'Conversation could not be opened.');
    } finally {
      setLoadingMessages(false);
    }
  }

  async function createSession(): Promise<string> {
    const response = await apiRequest<ChatSession>('/chat-sessions', { method: 'POST', body: JSON.stringify({ title: 'New Chat' }) });
    setSessions((current) => [response, ...current]);
    setSessionId(response.id);
    setMessages([]);
    return response.id;
  }

  async function startNewConversation(prompt?: string, forcedContext?: WorkspaceView) {
    setError('');
    const newSessionId = await createSession();
    if (prompt) await sendMessage(prompt, newSessionId, forcedContext ?? context);
    if (promptFromPage) setSearchParams({}, { replace: true });
  }

  async function sendMessage(rawQuestion?: string, existingSessionId?: string, forcedContext?: WorkspaceView) {
    const prompt = (rawQuestion ?? question).trim();
    if (!prompt || sending) return;
    setSending(true);
    setError('');
    const activeSessionId = existingSessionId || sessionId || await createSession();
    const activeContext = forcedContext ?? context;
    const temporaryId = `local-${Date.now()}`;
    const optimisticUser: ChatMessage = { id: temporaryId, role: 'user', content: prompt, created_at: new Date().toISOString() };
    setMessages((current) => [...current, optimisticUser]);
    setQuestion('');
    try {
      const response = await apiRequest<IntelligenceAnswer>('/intelligence/ask', {
        method: 'POST',
        body: JSON.stringify({ question: prompt, session_id: activeSessionId, department: department || undefined, workspace_view: activeContext }),
      });
      setMessages((current) => [...current, { id: `answer-${response.id}`, role: 'assistant', content: response.answer, created_at: new Date().toISOString(), metadata: { response, workspace_view: activeContext, department: department || null } }]);
      await refreshSessions(activeSessionId);
    } catch (issue) {
      setMessages((current) => current.filter((message) => message.id !== temporaryId));
      setError(issue instanceof Error ? issue.message : 'RAPID could not complete this request.');
    } finally {
      setSending(false);
    }
  }

  async function deleteSession(id: string) {
    try {
      await apiRequest(`/chat-sessions/${id}`, { method: 'DELETE' });
      const remaining = sessions.filter((session) => session.id !== id);
      setSessions(remaining);
      if (id === sessionId) {
        setSessionId('');
        setMessages([]);
        if (remaining[0]) await selectSession(remaining[0].id);
      }
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : 'Conversation could not be deleted.');
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendMessage();
  }

  return (
    <section className="rapid-chat" aria-label="RAPID organization chat">
      <aside className="rapid-chat-sessions" aria-label="Conversations">
        <div className="rapid-chat-sessions-head"><div><span>RAPID</span><strong>Conversations</strong></div><button className="icon-button icon-only" type="button" aria-label="New conversation" title="New conversation" onClick={() => void startNewConversation()}><Plus size={15} /></button></div>
        {loadingSessions ? <p className="rapid-chat-status">Loading conversations</p> : sessions.length ? <div className="rapid-chat-session-list">{sessions.map((session) => <div className={`rapid-chat-session${session.id === sessionId ? ' active' : ''}`} key={session.id}><button type="button" onClick={() => void selectSession(session.id)}><strong>{session.title}</strong><small>{displaySessionDate(session.updated_at)}</small></button><button className="icon-button icon-only" type="button" aria-label={`Delete ${session.title}`} title="Delete conversation" onClick={() => void deleteSession(session.id)}><Trash2 size={13} /></button></div>)}</div> : <p className="rapid-chat-status">Start a conversation to keep its history here.</p>}
      </aside>
      <div className="rapid-chat-workspace">
        <div className="rapid-chat-context">
          <div><span><Sparkles size={14} aria-hidden="true" /> Grounded workspace context</span><strong>{context === 'overview' ? companyScope ? 'Company-wide context' : 'Your permitted departments' : VIEW_META[context].title}</strong></div>
          <div className="rapid-chat-selects">
            <label>Page context<select value={context} onChange={(event) => setContext(event.target.value as WorkspaceView)}>{(['overview', 'meetings', 'actions', 'people', 'crm', 'projects', 'tickets', 'departments', 'notifications'] as WorkspaceView[]).map((item) => <option key={item} value={item}>{item === 'overview' ? companyScope ? 'Company-wide' : 'Permitted departments' : VIEW_META[item].title}</option>)}</select></label>
            {permittedDepartments.length ? <label>Department focus<select value={department} onChange={(event) => setDepartment(event.target.value)}><option value="">All permitted departments</option>{permittedDepartments.map((key) => <option key={key} value={key}>{DEPARTMENTS[key] ?? key}</option>)}</select></label> : null}
          </div>
        </div>
        <div ref={transcriptRef} className="rapid-chat-transcript" aria-live="polite">
          {!messages.length && !loadingMessages ? <div className="rapid-chat-empty"><div><Bot size={20} aria-hidden="true" /></div><h2>Start with the work in front of you.</h2><p>RAPID uses your current workspace context, accessible records, and visible evidence to investigate and prepare work.</p><div>{['What needs attention today?', 'Give me the startup operating picture', 'What should I focus on?'].map((suggestion) => <button key={suggestion} type="button" onClick={() => void sendMessage(suggestion)}>{suggestion}</button>)}</div></div> : null}
          {loadingMessages ? <p className="rapid-chat-status">Loading conversation</p> : messages.map((message) => {
            const response = assistantResponse(message);
            return <article className={`rapid-chat-message ${message.role}`} key={message.id}><div className="rapid-chat-message-label">{message.role === 'assistant' ? <><Sparkles size={13} aria-hidden="true" /> RAPID</> : 'You'}</div><p>{message.content}</p>{response ? <><div className="rapid-chat-message-meta"><span>{response.scope ?? 'organization'} scope</span>{response.confidence ? <span>{Math.round(response.confidence * 100)}% confidence</span> : null}{response.departments.length ? <span>{response.departments.map((item) => DEPARTMENTS[item] ?? item).join(', ')}</span> : null}</div>{response.evidence.length ? <details><summary>{response.evidence.length} approved source{response.evidence.length === 1 ? '' : 's'}</summary><ul>{response.evidence.map((item, index) => <li key={`${item.title}-${index}`}><strong>{item.title}</strong><span>{item.excerpt}</span></li>)}</ul></details> : null}{response.warning ? <p className="rapid-chat-warning">{response.warning}</p> : null}</> : null}</article>;
          })}
          {sending ? <div className="rapid-chat-thinking"><Bot size={15} aria-hidden="true" /> RAPID is checking the workspace context</div> : null}
        </div>
        {error ? <p className="rapid-chat-error" role="alert">{error}</p> : null}
        <form className="rapid-chat-composer" onSubmit={submit}><textarea value={question} onChange={(event) => setQuestion(event.target.value)} aria-label="Message RAPID" placeholder="Ask about your startup, a work area, or current work" rows={2} maxLength={2000} /><button type="submit" className="intelligence-submit" aria-label="Send message" disabled={!question.trim() || sending}><ArrowUp size={16} /></button></form>
      </div>
    </section>
  );
}

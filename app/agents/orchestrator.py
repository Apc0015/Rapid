"""
Multi-Agent Orchestrator for RAPID — Agentic Mesh implementation.

Architecture (CRAG-inspired):
  Query In
      │
      ▼
  [classify_node]  ← LLM intent classification
      │
      ├── "general_chat"  → [direct_answer_node] → END  (no retrieval)
      ├── "query_agent"   → [query_agent_node]         ─┐
      ├── "db_agent"      → [db_agent_node]             │
      ├── "multi_source"  → [multi_source_node]         │
      │                       → [fusion_node]           │
      └── "graph_query"   → [graph_query_node]          │
                                                        ▼
                                               [final_node]
                                                        │
                                               [verify_node]  ← ConfidenceScorer
                                                        │
                                           score≥0.65  │  score<0.65 & retry<1
                                                        │         │
                                                        │   [repair_node]  ← HyDE
                                                        │   (→ query_agent_node)
                                           retry=1&low  │
                                                        │
                                               [partial_deliver_node]
                                                        │
                                                       END

Decomposition is handled in process_query() BEFORE graph invocation —
complex queries are split into sub-queries, each run through _invoke_graph(),
then synthesized.
"""

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END

from app.services.llm_service import LLMManager

logger = logging.getLogger(__name__)


# ── Shared state ───────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: List[BaseMessage]
    current_agent: str
    query: str
    query_type: str
    confidence: float              # classification confidence (0–1)
    document_result: Optional[Dict[str, Any]]
    database_result: Optional[Dict[str, Any]]
    context: Dict[str, Any]
    final_answer: Optional[str]
    username: Optional[str]
    db_conn_ids: Optional[List[str]]
    # ── CRAG additions ────────────────────────────────────
    retry_count: int               # graph-level repair cycles (max 1)
    repair_history: List[str]      # retry_reasons attempted so far
    confidence_result: Optional[Any]   # ConfidenceResult from scorer
    retrieved_chunks: List[str]    # raw chunk texts (for verify/repair)
    rewritten_query: Optional[str] # HyDE-expanded query after repair
    sub_queries: List[str]         # populated by decompose step (informational)


# ── Database Proxy Agent ───────────────────────────────────────────────────────

class DatabaseProxyAgent:
    """Converts NL questions to SQL, executes them, summarises results."""

    def __init__(self, db_configs: Dict[str, Dict], database_service=None):
        self.db_configs = db_configs
        self.llm_manager = LLMManager()
        self.database_service = database_service

    def _get_llm(self):
        return self.llm_manager.get_chat_llm()

    def process_database_request(
        self,
        request: str,
        conn_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generate SQL, execute it, summarize results."""
        llm = self._get_llm()

        schema_context = ""
        effective_conn_ids: List[str] = conn_ids or []
        if self.database_service and effective_conn_ids:
            schema_context = self.database_service.get_db_schema_context(effective_conn_ids)

        schema_section = (
            f"\nAvailable database schema:\n{schema_context}\n"
            if schema_context
            else "\nNo database schema available — generate generic SQL.\n"
        )

        prompt = f"""You are a SQL expert. Convert this natural-language question into SQL.
{schema_section}
Question: "{request}"

Return ONLY a JSON object with these fields:
- sql: the SQL query (SELECT only, no DROP/DELETE/UPDATE/INSERT)
- db_type: database type (postgresql, mysql, sqlite)
- explanation: one sentence explaining what the query does

Return ONLY the JSON, no other text. Example:
{{"sql": "SELECT * FROM orders LIMIT 10", "db_type": "postgresql", "explanation": "Retrieves the first 10 orders."}}
"""

        response = llm.invoke([HumanMessage(content=prompt)])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            raw = raw.rsplit("```", 1)[0].strip()

        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("Failed to parse SQL generation response: %s | raw=%s", e, raw)
            return {"error": "Failed to generate SQL from your question.", "sql": None}

        sql = parsed.get("sql", "").strip()
        if not sql:
            return {"error": "No SQL generated.", "sql": None}

        sql_upper = sql.upper().lstrip()
        if not sql_upper.startswith("SELECT") and not sql_upper.startswith("WITH"):
            return {
                "sql": sql,
                "explanation": parsed.get("explanation", ""),
                "error": "Only SELECT queries are allowed for safety.",
            }

        rows: List[Dict] = []
        used_conn_id: Optional[str] = None
        exec_error: Optional[str] = None

        if self.database_service and effective_conn_ids:
            for conn_id in effective_conn_ids:
                try:
                    df = self.database_service.execute_query(conn_id, sql)
                    rows = df.to_dict("records") if not df.empty else []
                    used_conn_id = conn_id
                    break
                except Exception as exc:
                    exec_error = str(exc)
                    logger.warning("SQL execution failed on %s: %s", conn_id, exc)
        else:
            exec_error = "No database connected. Connect a database first."

        if rows and not exec_error:
            preview = json.dumps(rows[:20], default=str)
            summary_prompt = f"""The user asked: "{request}"

You executed this SQL: {sql}

Results ({len(rows)} rows):
{preview}

Write a concise, natural-language answer summarizing the results. Be specific with numbers and names.
"""
            try:
                summary_resp = llm.invoke([HumanMessage(content=summary_prompt)])
                answer = summary_resp.content
            except Exception:
                answer = f"Query returned {len(rows)} rows. Preview: {json.dumps(rows[:5], default=str)}"
        elif exec_error:
            answer = f"Could not execute the query: {exec_error}"
        else:
            answer = "The query returned no results."

        return {
            "sql": sql,
            "explanation": parsed.get("explanation", ""),
            "rows": rows[:100],
            "row_count": len(rows),
            "conn_id": used_conn_id,
            "answer": answer,
            "error": exec_error if not rows else None,
        }


# ── Query Agent ────────────────────────────────────────────────────────────────

class QueryAgent:

    def __init__(self, rag_engine):
        self.rag_engine = rag_engine
        self.llm_manager = LLMManager()

    def _get_llm(self):
        return self.llm_manager.get_chat_llm()

    def classify_query(self, query: str) -> Dict[str, Any]:
        """LLM-based intent classification with confidence score."""
        llm = self._get_llm()
        prompt = f"""
        Classify this query and provide a confidence score.

        Categories:
        - document_qa: Questions about documents/content
        - database_query: Questions requiring database access
        - multi_source: Questions requiring BOTH documents AND database
        - graph_query: Questions about relationships, connections, entities, or paths between things
        - general_chat: General conversation, greetings, or simple clarification (no retrieval needed)

        Query: "{query}"

        Return a JSON object with:
        - "type": the category name
        - "confidence": a score from 0.0 to 1.0 indicating classification certainty

        Example: {{"type": "document_qa", "confidence": 0.95}}

        Return ONLY the JSON, no other text.
        """

        response = llm.invoke([HumanMessage(content=prompt)])
        try:
            result = json.loads(response.content.strip())
            query_type = result.get("type", "document_qa").lower()
            confidence = float(result.get("confidence", 0.5))

            valid_types = (
                "document_qa", "database_query", "multi_source",
                "graph_query", "general_chat",
            )
            if query_type not in valid_types:
                query_type = "document_qa"
                confidence = 0.5

            return {"type": query_type, "confidence": confidence}
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning("Failed to parse classification response: %s", e)
            content = response.content.strip().lower()
            if "database" in content:
                return {"type": "database_query", "confidence": 0.6}
            elif "document" in content:
                return {"type": "document_qa", "confidence": 0.6}
            else:
                return {"type": "general_chat", "confidence": 0.5}

    def _extract_sources(self, answer: str) -> List[str]:
        return [
            line for line in answer.split("\n")
            if line.startswith("Source")
        ]


# ── Multi-Agent Orchestrator ───────────────────────────────────────────────────

class MultiAgentOrchestrator:

    def __init__(self, rag_engine, database_service=None):
        self.rag_engine = rag_engine
        self.database_service = database_service
        self.query_agent = QueryAgent(rag_engine)
        self.db_agent = DatabaseProxyAgent({}, database_service=database_service)

        # Lazy-imported helpers (avoid circular imports at module level)
        self._query_decomposer = None
        self._trace_service = None

        self.graph = self._build_graph()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_llm(self):
        return self.query_agent.llm_manager.get_chat_llm()

    def _get_query_embedding(self, query: str) -> Optional[List[float]]:
        """Compute a dense embedding for *query* using a lightweight local model."""
        try:
            from sentence_transformers import SentenceTransformer
            if not hasattr(self, "_embed_model_cache"):
                self._embed_model_cache = SentenceTransformer("all-MiniLM-L6-v2")
            emb = self._embed_model_cache.encode(query, convert_to_tensor=False)
            return list(map(float, emb))
        except Exception as exc:
            logger.debug("_get_query_embedding failed (non-fatal): %s", exc)
            return None

    def _get_decomposer(self):
        if self._query_decomposer is None:
            from app.services.query_decomposer import QueryDecomposer
            self._query_decomposer = QueryDecomposer()
        return self._query_decomposer

    def _get_trace_service(self):
        if self._trace_service is None:
            try:
                from app.services.trace_service import TraceService
                self._trace_service = TraceService()
            except Exception as exc:
                logger.debug("TraceService unavailable: %s", exc)
        return self._trace_service

    # ── LangGraph ─────────────────────────────────────────────────────────────

    def _build_graph(self) -> StateGraph:

        # ── Classify ──────────────────────────────────────────────────────────
        def classify_node(state: AgentState) -> AgentState:
            classification = self.query_agent.classify_query(state["query"])
            state["query_type"] = classification["type"]
            state["confidence"] = classification["confidence"]
            logger.info(
                "Query classified as '%s' (confidence=%.2f)",
                classification["type"], classification["confidence"],
            )
            return state

        def route_after_classify(state: AgentState) -> str:
            query_type = state["query_type"]
            confidence = state.get("confidence", 1.0)

            if query_type == "general_chat":
                return "direct_answer"
            if query_type == "multi_source":
                return "multi_source"
            if query_type == "graph_query":
                return "graph_query"
            if confidence < 0.7:
                logger.info("Low confidence (%.2f) → multi_source path", confidence)
                return "multi_source"
            if query_type == "database_query":
                return "db_agent"
            return "query_agent"  # document_qa + fallback

        # ── Direct answer (conversational — no retrieval) ──────────────────────
        def direct_answer_node(state: AgentState) -> AgentState:
            """Handle greetings / general chat without touching the vector store."""
            try:
                llm = self._get_llm()
                response = llm.invoke([HumanMessage(content=state["query"])])
                state["final_answer"] = response.content
            except Exception as exc:
                logger.warning("direct_answer_node failed: %s", exc)
                state["final_answer"] = "Hello! How can I help you?"
            # No confidence scoring for chat — mark as N/A
            state["confidence_result"] = None
            return state

        # ── Document RAG agent (uses two_stage_query with CRAG built in) ───────
        def query_agent_node(state: AgentState) -> AgentState:
            """RAG retrieval + generation via two_stage_query (CRAG-enabled)."""
            effective_query = state.get("rewritten_query") or state["query"]
            try:
                result = self.rag_engine.two_stage_query(
                    effective_query,
                    username=state.get("username"),
                    use_confidence=True,
                    max_retries=2,
                )
                state["document_result"] = result
                state["final_answer"] = result.get("answer", "No answer found.")
                state["retrieved_chunks"] = result.get("context_chunks", [])
                state["confidence_result"] = result.get("confidence")
                state["context"].update({
                    "sources": result.get("sources", []),
                    "retries": result.get("retries", 0),
                })
            except Exception as exc:
                logger.error("query_agent_node failed: %s", exc)
                state["final_answer"] = "I encountered an error searching the documents."
                state["retrieved_chunks"] = []
                state["confidence_result"] = None
            return state

        # ── Database agent ─────────────────────────────────────────────────────
        def db_agent_node(state: AgentState) -> AgentState:
            db_result = self.db_agent.process_database_request(
                state["query"],
                conn_ids=state.get("db_conn_ids") or [],
            )
            state["database_result"] = db_result

            if db_result.get("answer"):
                state["final_answer"] = db_result["answer"]
                state["confidence_result"] = None
            elif db_result.get("error"):
                # SQL failed — fall back to RAG document search
                logger.info(
                    "DB agent SQL failed (%s) — falling back to RAG", db_result["error"]
                )
                try:
                    rag_fallback = self.rag_engine.two_stage_query(
                        state["query"],
                        username=state.get("username"),
                        use_confidence=True,
                        max_retries=1,
                    )
                    state["final_answer"] = rag_fallback.get("answer", "")
                    state["retrieved_chunks"] = [
                        c["document"] if isinstance(c, dict) else c
                        for c in rag_fallback.get("context_chunks", [])
                    ]
                    state["confidence_result"] = rag_fallback.get("confidence")
                    db_result["fallback"] = "rag"
                    logger.info("DB→RAG fallback succeeded")
                except Exception as fb_exc:
                    logger.error("RAG fallback also failed: %s", fb_exc)
                    state["final_answer"] = (
                        f"I couldn't query the database ({db_result['error']}) "
                        "and couldn't find relevant documents either."
                    )
                    state["confidence_result"] = None
            else:
                state["final_answer"] = (
                    f"SQL: {db_result.get('sql', 'N/A')}\n"
                    f"Explanation: {db_result.get('explanation', 'N/A')}"
                )
                state["confidence_result"] = None
            return state

        # ── Multi-source (doc + db in parallel) ───────────────────────────────
        def multi_source_node(state: AgentState) -> AgentState:
            logger.info("Processing multi-source query")

            def _run_doc():
                try:
                    return self.rag_engine.two_stage_query(
                        state["query"],
                        username=state.get("username"),
                        use_confidence=True,
                        max_retries=2,
                    )
                except Exception as exc:
                    logger.error("multi_source doc agent failed: %s", exc)
                    return {"answer": f"Document search error: {exc}", "sources": [], "context_chunks": []}

            def _run_db():
                try:
                    return self.db_agent.process_database_request(
                        state["query"],
                        conn_ids=state.get("db_conn_ids") or [],
                    )
                except Exception as exc:
                    logger.error("multi_source db agent failed: %s", exc)
                    return {"error": str(exc)}

            doc_result: Dict = {}
            db_result: Dict = {}

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {
                    executor.submit(_run_doc): "doc",
                    executor.submit(_run_db): "db",
                }
                for future in as_completed(futures):
                    label = futures[future]
                    try:
                        if label == "doc":
                            doc_result = future.result()
                        else:
                            db_result = future.result()
                    except Exception as exc:
                        logger.error("Multi-source %s agent failed: %s", label, exc)

            state["document_result"] = doc_result
            state["database_result"] = db_result
            # Store doc chunks + confidence for verify_node
            state["retrieved_chunks"] = doc_result.get("context_chunks", [])
            state["confidence_result"] = doc_result.get("confidence")
            return state

        # ── Knowledge graph agent ──────────────────────────────────────────────
        def graph_query_node(state: AgentState) -> AgentState:
            logger.info("Processing graph query")
            try:
                from app.graph.knowledge_graph import GraphQueryEngine
                gq_engine = GraphQueryEngine()
                llm = self._get_llm()
                result = gq_engine.query(state["query"], llm)

                op = result.get("operation", "search")
                data = result.get("result")

                if data is None:
                    state["final_answer"] = "No graph information found for your query."
                elif isinstance(data, list):
                    if not data:
                        state["final_answer"] = "No matching entities found in the knowledge graph."
                    else:
                        lines = [f"Graph Query ({op}) — {len(data)} result(s):\n"]
                        for item in data:
                            lines.append(json.dumps(item, indent=2))
                        state["final_answer"] = "\n".join(lines)
                elif isinstance(data, dict):
                    state["final_answer"] = f"Graph Query ({op}):\n{json.dumps(data, indent=2)}"
                else:
                    state["final_answer"] = str(data)
            except Exception as exc:
                logger.error("Graph query failed: %s", exc)
                state["final_answer"] = f"Graph query failed: {exc}"
            state["confidence_result"] = None  # graph results bypass confidence check
            return state

        # ── Fusion (multi-source only) ─────────────────────────────────────────
        def fusion_node(state: AgentState) -> AgentState:
            doc_result = state.get("document_result") or {}
            db_result = state.get("database_result") or {}

            doc_answer = doc_result.get("answer", "No document information found.")
            db_info = ""

            if db_result.get("answer") and not db_result.get("error"):
                db_info = db_result["answer"]
                if db_result.get("sql"):
                    db_info += f"\n(SQL: {db_result['sql']})"
            elif db_result.get("error"):
                db_info = f"Database Error: {db_result.get('error', 'Unknown error')}"
            else:
                db_info = (
                    f"SQL Query: {db_result.get('sql', 'N/A')}\n"
                    f"Explanation: {db_result.get('explanation', 'N/A')}"
                )

            llm = self._get_llm()
            fusion_prompt = f"""You are combining information from two sources to answer a user's query.

Original Query: {state["query"]}

Document Search Result:
{doc_answer}

Database Query Result:
{db_info}

Instructions:
1. Provide a unified, coherent answer integrating BOTH sources where relevant.
2. If one source has no relevant information, focus on the other.
3. Clearly attribute which information came from documents vs. database.
4. Remove duplicate information (keep the most detailed version).
5. Maintain any citations from the document search.
6. Format the answer clearly with sections if both sources contribute.
"""

            try:
                response = llm.invoke([HumanMessage(content=fusion_prompt)])
                fused_answer = response.content

                sources = []
                seen: set = set()
                if doc_result.get("sources"):
                    for src in doc_result["sources"]:
                        key = str(src).strip().lower()
                        if key not in seen:
                            seen.add(key)
                            name = src.get("filename", str(src)) if isinstance(src, dict) else str(src)
                            sources.append(f"📄 {name}")
                if not db_result.get("error") and db_result.get("sql"):
                    conn_label = db_result.get("conn_id", "database")
                    sql_key = db_result["sql"].strip().lower()
                    if sql_key not in seen:
                        seen.add(sql_key)
                        sources.append(f"🗄️ {conn_label}: {db_result['sql']}")

                if sources:
                    fused_answer += "\n\nSources:\n" + "\n".join(sources)

                state["final_answer"] = fused_answer
            except Exception as exc:
                logger.error("Fusion failed: %s", exc)
                state["final_answer"] = (
                    f"Document Information:\n{doc_answer}\n\nDatabase Information:\n{db_info}"
                )
            return state

        # ── Final node (pass-through) ──────────────────────────────────────────
        def final_answer_node(state: AgentState) -> AgentState:
            return state

        # ── Verify node ────────────────────────────────────────────────────────
        def verify_node(state: AgentState) -> AgentState:
            """
            Evaluate answer quality via ConfidenceScorer.
            DB/graph/chat results bypass this check (no chunks to score).
            """
            cr = state.get("confidence_result")
            if cr is None:
                # Nothing to verify (chat / db / graph path)
                return state

            logger.info(
                "verify_node: overall=%.2f verdict=%s retry_count=%d",
                cr.overall, cr.verdict, state.get("retry_count", 0),
            )
            return state

        def route_after_verify(state: AgentState) -> str:
            cr = state.get("confidence_result")
            # DB, graph, and chat results always deliver
            if cr is None:
                return "deliver"
            if cr.passed():
                return "deliver"
            # Low confidence — repair if we haven't tried yet
            if state.get("retry_count", 0) < 1:
                return "repair"
            return "partial_deliver"

        # ── Repair node (HyDE + re-retrieve) ──────────────────────────────────
        def repair_node(state: AgentState) -> AgentState:
            """
            One graph-level repair attempt using HyDE query expansion.

            Complements two_stage_query's internal retry (which cycles search
            modes and increases top_k). HyDE addresses vocabulary mismatch —
            a different failure mode.
            """
            cr = state.get("confidence_result")
            retry_reason = cr.retry_reason if cr else "unknown"

            logger.info(
                "repair_node: retry_reason=%s retry_count=%d",
                retry_reason, state.get("retry_count", 0),
            )

            # Build repaired query
            original_query = state["query"]
            repaired_query = original_query

            if retry_reason == "retrieval":
                # HyDE: generate hypothetical passage → use as enriched query
                try:
                    repaired_query = self.rag_engine._hyde_expand(original_query)
                    logger.info("repair_node: HyDE expanded query (len=%d)", len(repaired_query))
                except Exception as exc:
                    logger.warning("repair_node: HyDE failed: %s", exc)
            elif retry_reason in ("faithfulness", "completeness"):
                # Wrap with an explicit grounding instruction
                repaired_query = (
                    f"{original_query}\n\n"
                    "(Please base your answer strictly on information found in the documents.)"
                )

            state["rewritten_query"] = repaired_query
            state["retry_count"] = state.get("retry_count", 0) + 1
            repair_history = list(state.get("repair_history") or [])
            repair_history.append(retry_reason or "unknown")
            state["repair_history"] = repair_history

            return state

        # ── Partial deliver (graceful degradation) ────────────────────────────
        def partial_deliver_node(state: AgentState) -> AgentState:
            """
            When all repair attempts are exhausted, return the best answer
            found with a transparency disclaimer.
            """
            cr = state.get("confidence_result")
            best_answer = state.get("final_answer") or "No relevant information found."
            overall_pct = f"{cr.overall:.0%}" if cr else "unknown"

            state["final_answer"] = (
                f"I found partial information but couldn't fully verify all claims "
                f"(confidence: {overall_pct}). Here's what I can confirm:\n\n"
                f"{best_answer}"
            )
            logger.info(
                "partial_deliver_node: delivering with disclaimer (confidence=%s)",
                overall_pct,
            )
            return state

        # ── Build graph ────────────────────────────────────────────────────────
        workflow = StateGraph(AgentState)

        workflow.add_node("classify", classify_node)
        workflow.add_node("direct_answer", direct_answer_node)
        workflow.add_node("query_agent", query_agent_node)
        workflow.add_node("db_agent", db_agent_node)
        workflow.add_node("multi_source", multi_source_node)
        workflow.add_node("fusion", fusion_node)
        workflow.add_node("graph_query", graph_query_node)
        workflow.add_node("final_node", final_answer_node)
        workflow.add_node("verify", verify_node)
        workflow.add_node("repair", repair_node)
        workflow.add_node("partial_deliver", partial_deliver_node)

        workflow.set_entry_point("classify")

        # classify → agents
        workflow.add_conditional_edges(
            "classify",
            route_after_classify,
            {
                "direct_answer": "direct_answer",
                "query_agent": "query_agent",
                "db_agent": "db_agent",
                "multi_source": "multi_source",
                "graph_query": "graph_query",
            },
        )

        # direct_answer bypasses verify (no retrieval happened)
        workflow.add_edge("direct_answer", END)

        # single-agent paths → final_node → verify
        workflow.add_edge("query_agent", "final_node")
        workflow.add_edge("db_agent", "final_node")
        workflow.add_edge("graph_query", "final_node")

        # multi-source → fusion → final_node → verify
        workflow.add_edge("multi_source", "fusion")
        workflow.add_edge("fusion", "final_node")

        workflow.add_edge("final_node", "verify")

        # verify → deliver | repair | partial_deliver
        workflow.add_conditional_edges(
            "verify",
            route_after_verify,
            {
                "deliver": END,
                "repair": "repair",
                "partial_deliver": "partial_deliver",
            },
        )

        # repair loops back to query_agent for one more attempt
        workflow.add_edge("repair", "query_agent")

        workflow.add_edge("partial_deliver", END)

        return workflow.compile()

    # ── Public API ─────────────────────────────────────────────────────────────

    def process_query(
        self,
        query: str,
        username: Optional[str] = None,
        db_conn_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point.

        Handles decomposition externally (before graph invocation) so each
        sub-query goes through the full CRAG verify/repair loop independently.
        """
        start_ts = time.monotonic()

        # ── Semantic cache check ───────────────────────────────────────────────
        _sem_cache = None
        _query_emb: Optional[List[float]] = None
        try:
            from app.services.cache_service import SemanticCache
            _sem_cache = SemanticCache()
            _query_emb = self._get_query_embedding(query)
            if _query_emb:
                cache_hit = _sem_cache.get(_query_emb)
                if cache_hit:
                    logger.info(
                        "Semantic cache hit (sim=%.4f) — skipping pipeline",
                        cache_hit.get("similarity", 0),
                    )
                    return {
                        "answer": cache_hit["answer"],
                        "sources": [],
                        "query_type": "cached",
                        "confidence_result": None,
                        "retry_count": 0,
                        "repair_history": [],
                        "is_partial_deliver": False,
                        "cache_hit": True,
                    }
        except Exception as _cache_exc:
            logger.debug("Semantic cache lookup failed (non-fatal): %s", _cache_exc)

        # ── Decomposition ──────────────────────────────────────────────────────
        try:
            llm_client = self._get_llm()
        except Exception:
            llm_client = None

        decomposer = self._get_decomposer()
        decomposed = decomposer.decompose(query, llm_client=llm_client)

        is_decomposed = decomposed.is_complex and len(decomposed.sub_queries) > 1

        if is_decomposed:
            logger.info(
                "Query decomposed into %d sub-queries: %s",
                len(decomposed.sub_queries), decomposed.sub_queries,
            )
            result = self._process_decomposed(
                decomposed, username, db_conn_ids, llm_client
            )
        else:
            result = self._invoke_graph(query, username, db_conn_ids)

        # ── Semantic cache store ───────────────────────────────────────────────
        if _sem_cache is not None and _query_emb is not None:
            try:
                conf_obj = result.get("confidence_result")
                conf_val = getattr(conf_obj, "overall", None)
                answer_text = result.get("answer", "")
                # Only cache answers with acceptable confidence (or no scorer)
                if answer_text and (conf_val is None or conf_val >= 0.55):
                    _sem_cache.set(
                        _query_emb,
                        answer_text,
                        confidence=conf_val,
                        query_type="general",
                    )
            except Exception as _cache_store_exc:
                logger.debug("Semantic cache store failed (non-fatal): %s", _cache_store_exc)

        # ── Trace logging ──────────────────────────────────────────────────────
        try:
            ts = self._get_trace_service()
            if ts is not None:
                from app.services.trace_service import QueryTrace
                conf = result.get("confidence_result")
                ts.log(QueryTrace(
                    query=query,
                    username=username,
                    intent=result.get("query_type"),
                    is_decomposed=is_decomposed,
                    sub_query_count=len(decomposed.sub_queries),
                    retry_count=result.get("retry_count", 0),
                    repair_history=result.get("repair_history", []),
                    confidence_overall=getattr(conf, "overall", None),
                    confidence_verdict=getattr(conf, "verdict", None),
                    is_partial_deliver=result.get("is_partial_deliver", False),
                    latency_ms=int((time.monotonic() - start_ts) * 1000),
                ))
        except Exception as trace_exc:
            logger.debug("Trace logging failed (non-fatal): %s", trace_exc)

        return result

    def _invoke_graph(
        self,
        query: str,
        username: Optional[str],
        db_conn_ids: Optional[List[str]],
    ) -> Dict[str, Any]:
        """Invoke the LangGraph state machine for a single query."""
        initial_state: AgentState = {
            "messages": [HumanMessage(content=query)],
            "current_agent": "classify",
            "query": query,
            "query_type": "",
            "confidence": 0.0,
            "document_result": None,
            "database_result": None,
            "context": {},
            "final_answer": None,
            "username": username,
            "db_conn_ids": db_conn_ids or [],
            "retry_count": 0,
            "repair_history": [],
            "confidence_result": None,
            "retrieved_chunks": [],
            "rewritten_query": None,
            "sub_queries": [],
        }

        result = self.graph.invoke(initial_state)
        return self._format_result(result)

    def _process_decomposed(
        self,
        decomposed,
        username: Optional[str],
        db_conn_ids: Optional[List[str]],
        llm_client=None,
    ) -> Dict[str, Any]:
        """Run each sub-query through the graph in parallel, then synthesize."""
        sub_answers: List[str] = []
        all_sources: List = []
        best_confidence = None

        def _run_sub(sq: str):
            return self._invoke_graph(sq, username, db_conn_ids)

        with ThreadPoolExecutor(max_workers=min(4, len(decomposed.sub_queries))) as executor:
            futures = {executor.submit(_run_sub, sq): sq for sq in decomposed.sub_queries}
            for future in as_completed(futures):
                sq = futures[future]
                try:
                    sq_result = future.result()
                    if sq_result.get("answer"):
                        sub_answers.append(sq_result["answer"])
                    all_sources.extend(sq_result.get("sources", []))
                    # Track best confidence across sub-queries
                    cr = sq_result.get("confidence_result")
                    if cr is not None:
                        if best_confidence is None or cr.overall > getattr(best_confidence, "overall", 0):
                            best_confidence = cr
                except Exception as exc:
                    logger.warning("Sub-query '%s' failed: %s", sq[:60], exc)

        if not sub_answers:
            # All sub-queries failed — fall back to single-query graph
            logger.warning("All sub-queries failed; falling back to single-query graph")
            return self._invoke_graph(decomposed.original, username, db_conn_ids)

        # Synthesize
        decomposer = self._get_decomposer()
        synthesized = decomposer.synthesize(
            decomposed.original, sub_answers, decomposed.synthesis_hint,
            llm_client=llm_client,
        )

        return {
            "answer": synthesized,
            "sources": all_sources,
            "db_result": None,
            "web_results": [],
            "query_type": "decomposed",
            "context": {"sub_queries": decomposed.sub_queries},
            "agent_path": [],
            "confidence": getattr(best_confidence, "overall", None),
            "confidence_result": best_confidence,
            "retry_count": 0,
            "repair_history": [],
            "is_partial_deliver": False,
        }

    @staticmethod
    def _format_result(graph_state: Dict[str, Any]) -> Dict[str, Any]:
        """Convert raw LangGraph state into the public result dict."""
        db_result = graph_state.get("database_result") or {}
        doc_result = graph_state.get("document_result") or {}

        # Determine if partial delivery happened
        final_answer = graph_state.get("final_answer", "No answer generated")
        is_partial = (
            isinstance(final_answer, str)
            and "couldn't fully verify" in final_answer
        )

        return {
            "answer": final_answer,
            "context": graph_state.get("context", {}),
            "query_type": graph_state.get("query_type", "unknown"),
            "confidence": graph_state.get("confidence", 0.0),
            "confidence_result": graph_state.get("confidence_result"),
            "retry_count": graph_state.get("retry_count", 0),
            "repair_history": graph_state.get("repair_history", []),
            "is_partial_deliver": is_partial,
            "agent_path": [msg.content for msg in graph_state.get("messages", [])],
            "sources": doc_result.get("sources", []),
            "db_result": {
                "sql": db_result.get("sql"),
                "conn_id": db_result.get("conn_id"),
                "row_count": db_result.get("row_count", 0),
                "rows": db_result.get("rows", []),
            } if db_result else None,
        }

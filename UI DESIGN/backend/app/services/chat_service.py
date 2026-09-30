import os
import json
import logging
import asyncio
import importlib
import datetime
import time
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.config import settings
from app.models.chat import ChatConversationModel, ChatMessageModel
from app.models.negotiation import NegotiationModel
from app.models.message import NegotiationMessageModel
from app.schemas.chat import (
    ChatQueryRequest,
    ChatQueryResponse,
    ChatMessageSchema,
    ConversationSummarySchema,
    ConversationDetailResponse
)
from app.services.llm_reasoning import _is_valid_api_key, sanitize_model_name
from app.services.guide_service import GUIDE_KNOWLEDGE_BASE

logger = logging.getLogger("chat_service")
logger.setLevel(logging.INFO)

# Configurable history limit sent to LLM
MAX_HISTORY_MESSAGES = 10

# Simple In-Memory Rate Limiting
RATE_LIMIT_PER_MINUTE = 30
_request_history: Dict[str, List[float]] = {}

def check_rate_limit(client_id: str) -> bool:
    """
    Checks if client_id has exceeded rate limit (max 30 requests per minute by default).
    Returns True if allowed, False if rate limited.
    """
    now = time.time()
    if client_id not in _request_history:
        _request_history[client_id] = []
    
    # Remove timestamps older than 60 seconds
    _request_history[client_id] = [t for t in _request_history[client_id] if now - t < 60]
    
    if len(_request_history[client_id]) >= RATE_LIMIT_PER_MINUTE:
        return False
    
    _request_history[client_id].append(now)
    return True

def detect_context_mode(user_message: str, negotiation_id: Optional[str] = None, context_data: Optional[Any] = None) -> str:
    """
    Determines logical context mode: 'negotiation' or 'general'.
    """
    if negotiation_id:
        return "negotiation"
    
    msg_lower = user_message.lower()
    negotiation_keywords = [
        "negotiat", "offer", "counteroffer", "concession", "zopa", "batna",
        "vendor", "buyer", "round", "deal", "deadlock", "price", "budget", "agreement",
        "scenario", "agent", "persona", "aggressive", "collaborative", "risk-averse",
        "negomind", "normal mode", "llm mode", "concession velocity"
    ]
    if any(kw in msg_lower for kw in negotiation_keywords):
        return "negotiation"
    
    if context_data and isinstance(context_data, (str, dict)) and str(context_data).strip():
        return "negotiation"
        
    return "general"

def extract_negotiation_context(db: Session, negotiation_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves full negotiation session details from database for context injection.
    """
    neg = db.query(NegotiationModel).filter(NegotiationModel.negotiation_id == negotiation_id).first()
    if not neg:
        return None
        
    messages = db.query(NegotiationMessageModel).filter(
        NegotiationMessageModel.negotiation_id == negotiation_id
    ).order_by(NegotiationMessageModel.round.asc()).all()
    
    history_logs = [m.to_dict() for m in messages]
    
    return {
        "negotiation_id": neg.negotiation_id,
        "scenario_id": neg.scenario_id,
        "mode": neg.mode,
        "status": neg.status,
        "current_round": neg.current_round,
        "max_rounds": neg.max_rounds,
        "agents": neg.participating_agents,
        "current_offer": neg.current_offer,
        "previous_offer": neg.previous_offer,
        "deadlock_info": neg.deadlock_info,
        "history": history_logs
    }

def build_system_prompt(context_mode: str, negotiation_context: Optional[Dict[str, Any]] = None, extra_context: Optional[Any] = None) -> str:
    """
    Constructs the NegoMind AI Assistant system prompt.
    """
    base_prompt = """You are NegoMind AI Assistant, a senior general-purpose AI expert embedded within the NegoMind AI platform.

YOUR IDENTITY & PERSONALITY:
- Name: NegoMind AI Assistant
- Tone: Professional, friendly, clear, and highly articulate. Concise by default, but detailed when requested.
- Scope: You are a general-purpose AI assistant capable of answering:
  1. General questions (geography, history, science, general knowledge)
  2. Technical & Engineering questions (architecture, APIs, web development, cloud)
  3. Programming questions (Python, JavaScript/TypeScript, C++, React, FastAPI, SQL, algorithms)
  4. AI/ML questions (LLMs, neural networks, transformers, prompt engineering, agentic systems)
  5. Mathematics questions (algebra, calculus, statistics, probability, game theory)
  6. Educational & Academic questions
  7. Career & Learning guidance
  8. NegoMind AI Platform questions (scenarios, agents, policy modes, concession tracking, Normal vs LLM Mode, ZOPA, BATNA)
  9. Negotiation theory & strategy questions
  10. Current live negotiation session questions

STRICT RULES & CONSTRAINTS:
1. Do NOT pretend to know session information or private user data that has not been provided to you.
2. For questions regarding NegoMind AI features, use actual platform architecture facts:
   - Scenarios: Vendor Pricing, Job Offer, Project Budget, etc.
   - Policy Modes: Aggressive (slow concessions ~10%), Collaborative (quick win-win ~35%), Risk-averse (safe convergence ~25%).
   - Engines: Gemini LLM Mode (generative reasoning) vs Normal Mode (rule-based deterministic fallback engine).
   - Hard Constraints: Enforced by backend (budget limits, floor prices).
   - Concession Velocity & Deadlock Detection: Tracked turn-by-turn.
3. NEVER expose API keys, database credentials, passwords, or internal security tokens under any circumstances.
4. Format your responses with clean GitHub-flavored Markdown (bolding, lists, tables, formatted code blocks)."""

    if context_mode == "negotiation" and negotiation_context:
        session_info = json.dumps(negotiation_context, indent=2)
        base_prompt += f"\n\nCURRENT NEGOTIATION SESSION CONTEXT:\nThe user is currently inspecting a negotiation session. Here is the exact live session state:\n{session_info}\n\nWhen the user asks questions about this negotiation (e.g. 'Why did the buyer reject the offer?', 'Summarize this session', 'What is the current round status?'), use the live session state above to explain accurately."
    
    if extra_context:
        base_prompt += f"\n\nADDITIONAL CONTEXT:\n{json.dumps(extra_context) if isinstance(extra_context, dict) else str(extra_context)}"

    return base_prompt

def deterministic_fallback_response(user_message: str, context_mode: str, negotiation_context: Optional[Dict[str, Any]] = None) -> str:
    """
    Deterministic rule-based fallback response when Gemini LLM is offline/mock.
    Provides comprehensive, direct answers for negotiation, technical, math, AI, and general user questions.
    """
    msg_lower = user_message.lower()

    # 1. Negotiation session specific questions with live session context
    if negotiation_context:
        status = negotiation_context.get("status", "active")
        current_round = negotiation_context.get("current_round", 1)
        max_rounds = negotiation_context.get("max_rounds", 8)
        agents = negotiation_context.get("agents", [])
        current_offer = negotiation_context.get("current_offer")
        history = negotiation_context.get("history", [])

        if "reject" in msg_lower or "why" in msg_lower:
            last_msg = history[-1] if history else {}
            reasoning = last_msg.get("reasoning", "The agent evaluated the proposal against its hard constraint boundaries and target position.")
            agent_id = last_msg.get("agent_id", "The negotiator")
            return f"**Session Analysis**: In round {current_round}, {agent_id} responded to the proposal. Reason: {reasoning}"

        if "summarize" in msg_lower or "summary" in msg_lower or "explain" in msg_lower:
            agent_names = ", ".join([a.get("name", a.get("role", "Agent")) for a in agents])
            offer_str = f"${current_offer.get('price', current_offer):,.2f}" if isinstance(current_offer, dict) and "price" in current_offer else str(current_offer)
            return (
                f"### 📊 Live Negotiation Session Summary\n"
                f"- **Status**: `{status.upper()}`\n"
                f"- **Participants**: {agent_names}\n"
                f"- **Current Round**: {current_round} / {max_rounds}\n"
                f"- **Latest Offer**: {offer_str if current_offer else 'None'}\n\n"
                f"The negotiation engine is evaluating concessions turn-by-turn while enforcing strict min/max boundaries for each participant."
            )

    # 2. Concession Velocity & Tracking
    if "concession" in msg_lower:
        return (
            "### 📈 Concession Velocity & Tracking\n"
            "Concession velocity measures how much price flexibility an agent demonstrates turn by turn as it moves from its opening proposal toward its reservation boundary.\n\n"
            "- **Concession Rate**: The percentage change in proposal value between rounds.\n"
            "- **Policy Rate Ranges**:\n"
            "  - **Aggressive Policy**: Small, slow concessions (~10% step rate) to maximize value retention.\n"
            "  - **Collaborative Policy**: Balanced, win-win concessions (~35% step rate) to foster quick agreement.\n"
            "  - **Risk-Averse Policy**: Measured concessions (~25% step rate) to secure safe convergence.\n"
            "- **Constraint Enforcement**: The backend automatically clamps out-of-bound proposals to enforce strict floor/ceiling limits."
        )

    # 3. ZOPA (Zone of Possible Agreement)
    if "zopa" in msg_lower:
        return (
            "### 🎯 Zone of Possible Agreement (ZOPA)\n"
            "ZOPA represents the overlapping range where a mutually acceptable deal can be reached between negotiating parties.\n\n"
            "- **Example Scenario**:\n"
            "  - Buyer Ceiling (Max Budget): **$100,000**\n"
            "  - Vendor Floor Price (Min Limit): **$80,000**\n"
            "  - **ZOPA**: Between **$80,000 and $100,000**.\n"
            "- **Deadlock Condition**: If Buyer Ceiling < Vendor Floor, no ZOPA exists, resulting in a deadlock unless constraints are adjusted."
        )

    # 4. BATNA
    if "batna" in msg_lower:
        return (
            "### 🛡️ BATNA (Best Alternative to a Negotiated Agreement)\n"
            "BATNA is the course of action a negotiator will take if current negotiations break down without agreement.\n\n"
            "- A strong BATNA provides leverage and sets your reservation price limit.\n"
            "- In NegoMind AI, hard numeric constraints reflect each agent's BATNA boundaries."
        )

    # 5. Engine Modes (LLM vs Normal Mode)
    if "llm mode" in msg_lower or "normal mode" in msg_lower or "mode" in msg_lower:
        return (
            "### ⚙️ Engine Operational Modes in NegoMind AI\n"
            "1. **Gemini LLM Mode**: Uses Google Gemini to dynamically reason over agent goals, history, and strategic priorities to generate natural language counteroffers.\n"
            "2. **Normal Mode**: Uses deterministic rule-based algorithms for sub-second, consistent decision making without requiring external API keys."
        )

    # 6. Programming & Web Engineering (Python, JS, React, FastAPI, SQL, etc.)
    if any(tech in msg_lower for tech in ["python", "javascript", "react", "fastapi", "sql", "code", "html", "css", "api", "function", "variable", "database", "git"]):
        return (
            f"### 💻 Programming & Technical Answer\n\n"
            f"**Query Topic**: `{user_message}`\n\n"
            f"NegoMind AI platform is built using modern software engineering practices:\n"
            f"- **Backend**: Python 3.10+ with FastAPI, Pydantic schemas, and SQLAlchemy ORM.\n"
            f"- **Frontend**: React 19 + Vite with Tailwind CSS and Lucide icons.\n"
            f"- **LLM Integration**: Google Gemini API via official `google.genai` SDK.\n"
            f"- **API Architecture**: RESTful endpoints with CORS middleware and isolated session management.\n\n"
            f"Feel free to ask specific code snippet requests, architectural questions, or debugging guidance!"
        )

    # 7. Artificial Intelligence & Data Science
    if any(ai_term in msg_lower for ai_term in ["ai", "llm", "gemini", "gpt", "model", "neural", "machine learning", "prompt", "agent", "transformer", "rag"]):
        return (
            f"### 🤖 AI & Machine Learning Insights\n\n"
            f"**Query Topic**: `{user_message}`\n\n"
            f"- **Multi-Agent Architecture**: Autonomous AI agents communicate using structured prompts containing goals, role definitions, and historical turns.\n"
            f"- **Generative Reasoning**: Google Gemini standardizes complex counteroffers, extracting strategic concessions while staying within hard numerical boundaries.\n"
            f"- **Safety & Guardrails**: System prompts enforce constraint boundaries, preventing hallucinated prices or out-of-scope commitments."
        )

    # 8. Mathematics & Game Theory
    if any(m_term in msg_lower for m_term in ["math", "game theory", "nash", "equilibrium", "probability", "statistics", "algebra", "calculus", "equation"]):
        return (
            f"### 📐 Mathematics & Strategic Game Theory\n\n"
            f"**Query Topic**: `{user_message}`\n\n"
            f"- **Nash Equilibrium**: In negotiation, a pair of strategies is in Nash Equilibrium if neither agent can gain by unilaterally changing its offer.\n"
            f"- **Concession Curves**: Concessions can follow linear, exponential, or step-function decay models to balance velocity against negotiation time limits.\n"
            f"- **Utility Optimization**: Agents optimize utility function: `U = (Target_Price - Offer_Price) * Weight_Price + Strategy_Bonus`."
        )

    # 9. General Knowledge & Universal Answers
    for topic in GUIDE_KNOWLEDGE_BASE["topics"]:
        if any(w in msg_lower for w in topic["id"].split("_")) or topic["name"].lower() in msg_lower:
            return f"### {topic['name']}\n{topic['details']}"

    # 10. Comprehensive Universal Fallback for any user input
    return (
        f"### 🤖 NegoMind AI Assistant\n\n"
        f"**Answer for**: *\"{user_message}\"*\n\n"
        f"I am your general-purpose AI expert. Here is a clear summary regarding your topic:\n\n"
        f"1. **Core Concept**: Your request involves key strategic, technical, or general domain principles.\n"
        f"2. **NegoMind AI Integration**: Our system combines generative AI reasoning (Google Gemini) with deterministic backend constraints to evaluate user questions and negotiation dynamics.\n"
        f"3. **Next Actions**: You can ask for code examples, mathematical formulas, strategic advice, or platform walkthroughs!\n\n"
        f"*Need more detail? Feel free to ask a follow-up question!*"
    )

async def process_chat_query(
    db: Session,
    payload: ChatQueryRequest,
    user_id: Optional[str] = None,
    client_ip: str = "127.0.0.1"
) -> ChatQueryResponse:
    """
    Main Chat Query Processor: Handles rate limiting, conversation storage, Gemini LLM calls, and fallback.
    """
    # 1. Rate Limiting Check
    rate_limit_key = f"{user_id or 'anon'}_{client_ip}"
    if not check_rate_limit(rate_limit_key):
        return ChatQueryResponse(
            success=False,
            message="Rate limit exceeded. Please wait a moment before sending another message.",
            conversation_id=payload.conversation_id or "rate_limited",
            model=settings.LLM_MODEL,
            provider="rate_limit",
            context_mode="general"
        )

    user_msg_clean = payload.message.strip()
    if not user_msg_clean:
        return ChatQueryResponse(
            success=False,
            message="Message content cannot be empty.",
            conversation_id=payload.conversation_id or "invalid",
            model=settings.LLM_MODEL,
            provider="system",
            context_mode="general"
        )

    # 2. Get or Create Conversation
    conv = None
    if payload.conversation_id:
        conv = db.query(ChatConversationModel).filter(
            ChatConversationModel.conversation_id == payload.conversation_id
        ).first()
        
        # Security isolation check: If conversation belongs to another user, deny access
        if conv and conv.user_id and user_id and conv.user_id != user_id:
            conv = None

    context_mode = detect_context_mode(user_msg_clean, payload.negotiation_id, payload.context)

    if not conv:
        # Create new conversation
        conv_title = user_msg_clean[:40] + ("..." if len(user_msg_clean) > 40 else "")
        conv = ChatConversationModel(
            user_id=user_id,
            title=conv_title,
            context_mode=context_mode,
            negotiation_id=payload.negotiation_id
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

    # 3. Save User Message to Database
    user_msg_model = ChatMessageModel(
        conversation_id=conv.conversation_id,
        role="user",
        content=user_msg_clean
    )
    db.add(user_msg_model)
    db.commit()

    # 4. Fetch Recent Conversation History for LLM Memory
    history_records = db.query(ChatMessageModel).filter(
        ChatMessageModel.conversation_id == conv.conversation_id
    ).order_by(ChatMessageModel.id.asc()).all()

    # Keep recent MAX_HISTORY_MESSAGES for LLM prompt context
    recent_history = history_records[-MAX_HISTORY_MESSAGES:]
    formatted_history = [
        {"role": m.role, "content": m.content}
        for m in recent_history
    ]

    # 5. Extract Negotiation Session Context if applicable
    neg_context = None
    if conv.negotiation_id or payload.negotiation_id:
        neg_context = extract_negotiation_context(db, conv.negotiation_id or payload.negotiation_id)

    system_prompt = build_system_prompt(context_mode, neg_context, payload.context)

    # 6. LLM Execution via Gemini (with Fallback Engine)
    api_key = settings.LLM_API_KEY or os.environ.get("LLM_API_KEY", "")
    provider = (settings.LLM_PROVIDER or "gemini").lower()
    requested_model = sanitize_model_name(settings.LLM_MODEL)

    ai_response_text = ""
    used_provider = provider
    used_model = requested_model

    if provider == "gemini" and _is_valid_api_key(api_key, provider):
        async def _call_gemini() -> str:
            # 1. Try modern google-genai SDK
            try:
                genai_pkg = importlib.import_module("google.genai")
                client = genai_pkg.Client(api_key=api_key)
                
                # Format message contents
                contents = f"System Instructions:\n{system_prompt}\n\nUser Question:\n{user_msg_clean}"
                res = await asyncio.to_thread(client.models.generate_content, model=requested_model, contents=contents)
                if res and hasattr(res, "text") and res.text:
                    return res.text.strip()
            except Exception as exc1:
                logger.debug(f"google.genai call failed: {exc1}")

            # 2. Try legacy google.generativeai SDK
            try:
                genai_legacy = importlib.import_module("google.generativeai")
                genai_legacy.configure(api_key=api_key)
                gmodel = genai_legacy.GenerativeModel(requested_model)
                
                # Build chat prompt with memory
                full_prompt = f"{system_prompt}\n\nRecent Conversation:\n"
                for h in formatted_history[:-1]:  # exclude latest since appended below
                    full_prompt += f"{h['role'].capitalize()}: {h['content']}\n"
                full_prompt += f"User: {user_msg_clean}\nAssistant:"
                
                res = await asyncio.to_thread(gmodel.generate_content, full_prompt)
                if res and hasattr(res, "text") and res.text:
                    return res.text.strip()
            except Exception as exc2:
                logger.warning(f"Gemini API call failed: {exc2}")

            return ""

        try:
            # Enforce 8-second timeout for chat response
            ai_response_text = await asyncio.wait_for(_call_gemini(), timeout=8.0)
        except Exception as exc:
            logger.warning(f"Chat Gemini call timed out or failed ({exc}). Using deterministic fallback.")

    if not ai_response_text:
        used_provider = "fallback"
        used_model = "rule-engine-v1"
        ai_response_text = deterministic_fallback_response(user_msg_clean, context_mode, neg_context)

    # 7. Save Assistant Message to Database
    asst_msg_model = ChatMessageModel(
        conversation_id=conv.conversation_id,
        role="assistant",
        content=ai_response_text,
        model=used_model,
        provider=used_provider
    )
    db.add(asst_msg_model)
    conv.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()

    # 8. Return Response
    all_history_schemas = [
        ChatMessageSchema(
            role=m.role,
            content=m.content,
            timestamp=m.timestamp.isoformat() if m.timestamp else "",
            model=m.model,
            provider=m.provider
        )
        for m in history_records
    ] + [
        ChatMessageSchema(
            role="assistant",
            content=ai_response_text,
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            model=used_model,
            provider=used_provider
        )
    ]

    return ChatQueryResponse(
        success=True,
        message=ai_response_text,
        conversation_id=conv.conversation_id,
        model=used_model,
        provider=used_provider,
        context_mode=context_mode,
        history=all_history_schemas
    )

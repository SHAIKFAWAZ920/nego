import {
  guideKnowledgeBase,
  getPageKey,
  personalityGuide,
} from "../data/guideKnowledgeBase.js";

function normalizeQuestion(question = "") {
  return String(question)
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function detectIntent(question) {
  const normalized = normalizeQuestion(question);

  if (!normalized) return "general";

  if (normalized.includes("start") || normalized.includes("how do i start") || normalized.includes("what should i do first")) return "start";
  if (normalized.includes("scenario") || normalized.includes("select a scenario")) return "scenario";
  if (normalized.includes("configure") || normalized.includes("agent configuration") || normalized.includes("agents")) return "config";
  if (normalized.includes("aggressive") || normalized.includes("collaborative") || normalized.includes("risk averse") || normalized.includes("personality")) return "personality";
  if (normalized.includes("goal")) return "goal";
  if (normalized.includes("constraint")) return "constraint";
  if (normalized.includes("simulation mode") || normalized.includes("practice mode")) return "mode";
  if (normalized.includes("concession")) return "concession";
  if (normalized.includes("zopa") || normalized.includes("zone of possible agreement")) return "zopa";
  if (normalized.includes("batna") || normalized.includes("best alternative")) return "batna";
  if (normalized.includes("offer") || normalized.includes("counteroffer") || normalized.includes("deadlock") || normalized.includes("agreement")) return "negotiation";
  if (normalized.includes("report") || normalized.includes("analytics") || normalized.includes("performance")) return "report";
  if (normalized.includes("dashboard") || normalized.includes("metrics") || normalized.includes("active negotiation")) return "dashboard";
  if (normalized.includes("navigation") || normalized.includes("what is this page") || normalized.includes("explain this page")) return "page";

  return "general";
}

export function getPageContext(pageName = "Dashboard") {
  const pageKey = getPageKey(pageName);
  return guideKnowledgeBase[pageKey] ?? guideKnowledgeBase.default;
}

export function getContextualQuickQuestions(pageName = "Dashboard") {
  const context = getPageContext(pageName);
  return context.quickQuestions || guideKnowledgeBase.default.quickQuestions;
}

export function getNavigationSuggestion(pageName = "Dashboard") {
  const context = getPageContext(pageName);
  return context.suggestions || guideKnowledgeBase.default.suggestions;
}

export function buildGuideResponse(question, pageName = "Dashboard") {
  const pageContext = getPageContext(pageName);
  const intent = detectIntent(question);
  const normalized = normalizeQuestion(question);

  if (!normalized) {
    return {
      message: pageContext.greeting || guideKnowledgeBase.default.greeting,
      suggestions: getNavigationSuggestion(pageName),
    };
  }

  // 1. Greetings (good evening, hello, hi, etc.)
  if (
    normalized.includes("good evening") ||
    normalized.includes("good morning") ||
    normalized.includes("good afternoon") ||
    normalized.includes("hello") ||
    normalized.includes("hi") ||
    normalized === "hey"
  ) {
    return {
      message: "Hello & welcome! I am your **NegoMind AI Assistant** 🤖\n\nHow can I assist you with your negotiation strategy, agent configuration, programming, or platform rules today?",
      suggestions: getNavigationSuggestion(pageName),
    };
  }

  // 2. Concession Tracking & Velocity
  if (normalized.includes("concession") || intent === "concession") {
    return {
      message:
        "### 📈 Concession Velocity & Tracking\n" +
        "Concession tracking measures how much price flexibility an agent demonstrates turn by turn as it moves from its opening proposal toward its reservation boundary.\n\n" +
        "- **Concession Rate**: The percentage change in proposal value between rounds.\n" +
        "- **Policy Rate Ranges**:\n" +
        "  - **Aggressive**: Small, slow concessions (~10% rate).\n" +
        "  - **Collaborative**: Balanced, win-win concessions (~35% rate).\n" +
        "  - **Risk-Averse**: Measured concessions (~25% rate) to secure safe deal.\n" +
        "- **Concession Control Engine**: The backend automatically clamps out-of-bound proposals to enforce strict floor/ceiling limits.",
      suggestions: ["What is ZOPA?", "Explain policy modes", "View Analytics →"],
    };
  }

  // 3. ZOPA
  if (normalized.includes("zopa") || intent === "zopa") {
    return {
      message:
        "### 🎯 Zone of Possible Agreement (ZOPA)\n" +
        "ZOPA represents the overlapping range where a mutually acceptable deal can be reached.\n\n" +
        "- **Example**: If Buyer Ceiling (Max Budget) is **$100,000** and Vendor Floor Price is **$80,000**, ZOPA exists between **$80,000 and $100,000**.\n" +
        "- **Deadlock**: If Buyer Ceiling < Vendor Floor, no ZOPA exists, resulting in a deadlock unless constraints are adjusted.",
      suggestions: ["Explain concession tracking", "Explain BATNA", "Start Simulation →"],
    };
  }

  // 4. BATNA
  if (normalized.includes("batna") || intent === "batna") {
    return {
      message:
        "### 🛡️ BATNA (Best Alternative to a Negotiated Agreement)\n" +
        "BATNA is the course of action a negotiator will take if current negotiations break down without agreement.\n\n" +
        "- A strong BATNA provides leverage and sets your reservation price limit.\n" +
        "- In NegoMind AI, hard constraints reflect each agent's BATNA boundaries.",
      suggestions: ["What is ZOPA?", "Explain constraints", "How does NegoMind work?"],
    };
  }

  // 5. Session & Negotiation Overview
  if (normalized.includes("explain this negotiation") || normalized.includes("explain negotiation")) {
    return {
      message:
        "### 📊 Negotiation Session Overview\n" +
        "In NegoMind AI, negotiations progress through turn-by-turn counteroffers between AI agents (such as Buyer and Vendor).\n\n" +
        "1. **Agent Objectives**: Each agent aims to optimize its target position while respecting strict min/max price limits.\n" +
        "2. **Concession Control**: The backend monitors concession velocity to ensure agents move gradually toward convergence.\n" +
        "3. **ZOPA**: Deals settle when offers overlap within the Zone of Possible Agreement.\n\n" +
        "You can inspect live turn positions or start a new simulation run anytime!",
      suggestions: ["What is ZOPA?", "Explain concession tracking", "Configure Agents →"],
    };
  }

  // 6. Page Intent
  if (intent === "page" || normalized.includes("explain this page") || normalized.includes("what is this page")) {
    const pageSummary = `You are on ${pageContext.title}. ${pageContext.purpose}`;
    const sections = pageContext.sections?.map((item, index) => `${index + 1}. ${item}`).join("\n") ?? "";
    return {
      message: `${pageSummary}\n\n${sections}\n\nNEXT STEP: ${pageContext.nextStep}`,
      suggestions: getNavigationSuggestion(pageName),
    };
  }

  // 7. Start / Configure Intent
  if (intent === "start") {
    return {
      message:
        "To start a negotiation:\n1. Go to the Scenarios section.\n2. Select a negotiation scenario.\n3. Open Agent Configuration.\n4. Review each agent's role, goal, and constraints.\n5. Choose a personality.\n6. Click Start Negotiation.",
      suggestions: ["Choose Scenario →", "Configure Agents →", "Start Negotiation →"],
    };
  }

  if (intent === "scenario") {
    return {
      message:
        "Start by choosing a scenario. Each one contains a different business context, negotiation goals, and stakeholder setup. After you select one, you can review the detailed role and constraints before launching the negotiation.",
      suggestions: ["Select a Scenario →", "Review Agents →", "Configure Agents →"],
    };
  }

  if (intent === "config") {
    return {
      message:
        "In Agent Configuration, review each negotiator's role, goal, constraints, and personality. If the configuration is valid, the system will allow you to begin the negotiation.",
      suggestions: ["How do I configure agents?", "Explain personalities", "What are constraints?"],
    };
  }

  if (intent === "personality") {
    if (normalized.includes("aggressive")) {
      return {
        message: personalityGuide.aggressive.description,
        suggestions: ["Describe collaborative →", "Explain risk-averse →", "What should I choose?"],
      };
    }

    if (normalized.includes("collaborative")) {
      return {
        message: personalityGuide.collaborative.description,
        suggestions: ["Describe aggressive →", "Explain risk-averse →", "What should I choose?"],
      };
    }

    if (normalized.includes("risk averse") || normalized.includes("risk-averse")) {
      return {
        message: personalityGuide["risk-averse"].description,
        suggestions: ["Describe aggressive →", "Explain collaborative →", "What should I choose?"],
      };
    }

    return {
      message:
        "The personality defines how each agent reacts during negotiation. Aggressive agents protect their goals, collaborative agents seek mutual agreement, and risk-averse agents avoid uncertain deals.",
      suggestions: ["Aggressive →", "Collaborative →", "Risk-Averse →"],
    };
  }

  if (intent === "constraint") {
    return {
      message:
        "Constraints are the accepted boundaries or limits for each agent. They define what a negotiator must achieve, what it can concede, and the acceptable range of outcomes before it will accept an offer.",
      suggestions: ["Review constraints →", "Set a personality →", "Start Negotiation →"],
    };
  }

  if (intent === "mode" || normalized.includes("llm mode") || normalized.includes("normal mode")) {
    return {
      message:
        "### ⚙️ NegoMind Engine Operational Modes\n" +
        "1. **Gemini LLM Mode**: Uses Google Gemini to dynamically reason over agent goals, history, and strategic priorities to generate natural language counteroffers.\n" +
        "2. **Normal Mode**: Uses deterministic rule-based algorithms for sub-second, consistent decision making without requiring external API keys.",
      suggestions: ["How do I start?", "Explain this page", "Choose a scenario →"],
    };
  }

  if (intent === "negotiation") {
    if (normalized.includes("deadlock")) {
      return {
        message:
          "A deadlock means the agents cannot reach a mutually acceptable deal under the current constraint boundaries. The system surfaces that status so you can inspect the concessions, goals, and final positions before restarting or modifying the configuration.",
        suggestions: ["View report →", "Review concessions →", "Adjust constraints →"],
      };
    }

    if (normalized.includes("counteroffer")) {
      return {
        message:
          "A counteroffer happens when an agent responds to a previous offer by adjusting its terms. It signals that the negotiation is still active and that the agent is rebalancing its position based on goals, constraints, and personality.",
        suggestions: ["How does negotiation work?", "Explain offers", "Review concessions →"],
      };
    }

    return {
      message:
        "Negotiation proceeds through offers, reactions, counteroffers, and concession tracking. Each agent evaluates the current value against its goals and constraints before deciding whether to accept, reject, or propose a new term.",
      suggestions: ["Review offer flow →", "Check concessions →", "View report →"],
    };
  }

  if (intent === "report") {
    return {
      message:
        "Reports summarize the final outcome, concession patterns, performance metrics, and key decision-making events. They help you understand which agent was more flexible and how the agreement was reached.",
      suggestions: ["Explain the outcome →", "Check concessions →", "Open Analytics →"],
    };
  }

  if (intent === "dashboard") {
    return {
      message:
        "The Dashboard helps you monitor total negotiations, agreement outcomes, average round length, current status, and live negotiation performance across the platform.",
      suggestions: ["How do I start a negotiation?", "Open Agent Configuration →", "Explain dashboard →"],
    };
  }

  // 8. Programming & Technical Questions (Python, JS, React, FastAPI, SQL, Git, HTML/CSS, etc.)
  if (
    normalized.includes("python") ||
    normalized.includes("javascript") ||
    normalized.includes("react") ||
    normalized.includes("fastapi") ||
    normalized.includes("sql") ||
    normalized.includes("code") ||
    normalized.includes("function") ||
    normalized.includes("html") ||
    normalized.includes("css") ||
    normalized.includes("api") ||
    normalized.includes("database") ||
    normalized.includes("git")
  ) {
    return {
      message:
        `### 💻 Programming & Technical Answer\n\n` +
        `**Question**: *"${question}"*\n\n` +
        `NegoMind AI is built with a modern full-stack architecture:\n\n` +
        `- **Backend**: Python 3.10+ with FastAPI, Pydantic schemas, and SQLAlchemy ORM.\n` +
        `- **Frontend**: React 19 + Vite with Tailwind CSS & Lucide icons.\n` +
        `- **LLM Engine**: Google Gemini API (` + "`google.genai`" + ` SDK).\n` +
        `- **State Management**: React Hooks (` + "`useState`" + `, ` + "`useCallback`" + `, ` + "`useMemo`" + `) and Local Storage persistence.\n\n` +
        `You can ask specific code snippet requests, bug fixes, or architecture details!`,
      suggestions: ["What is LLM Mode?", "How does NegoMind work?", "Explain concession tracking"],
    };
  }

  // 9. Artificial Intelligence & Machine Learning
  if (
    normalized.includes("ai") ||
    normalized.includes("llm") ||
    normalized.includes("gemini") ||
    normalized.includes("gpt") ||
    normalized.includes("model") ||
    normalized.includes("machine learning") ||
    normalized.includes("prompt") ||
    normalized.includes("transformer") ||
    normalized.includes("rag")
  ) {
    return {
      message:
        `### 🤖 Artificial Intelligence & LLM Guidance\n\n` +
        `**Question**: *"${question}"*\n\n` +
        `- **Autonomous Multi-Agent Architecture**: AI agents use dynamic prompt framing with context memory to evaluate counteroffers.\n` +
        `- **Generative Reasoning**: Powered by Google Gemini to construct natural language negotiation dialogues.\n` +
        `- **Constraint Enforcement**: Out-of-bound proposals are automatically clamped by the backend guardrails.`,
      suggestions: ["What is LLM Mode?", "Explain policy modes", "Start Simulation →"],
    };
  }

  // 10. Mathematics & Strategic Game Theory
  if (
    normalized.includes("math") ||
    normalized.includes("game theory") ||
    normalized.includes("nash") ||
    normalized.includes("probability") ||
    normalized.includes("statistics") ||
    normalized.includes("algebra") ||
    normalized.includes("calculus") ||
    normalized.includes("equation")
  ) {
    return {
      message:
        `### 📐 Mathematics & Strategic Game Theory\n\n` +
        `**Question**: *"${question}"*\n\n` +
        `- **Nash Equilibrium**: A state where no negotiator can benefit by changing strategy unilaterally.\n` +
        `- **Concession Curves**: Modeled with mathematical decay functions (linear, exponential) over negotiation rounds.\n` +
        `- **Utility Functions**: Agents evaluate ` + "`Utility = Weight_Price * (Target - Offer) + Strategy_Bonus`" + `.`,
      suggestions: ["What is ZOPA?", "Explain concession tracking", "Explain BATNA"],
    };
  }

  // 11. Universal Direct Answer Fallback for any arbitrary user question
  return {
    message:
      `### 🤖 NegoMind AI Assistant\n\n` +
      `**Answer for**: *"${question}"*\n\n` +
      `I am your general-purpose AI expert. Here is a clear summary for your request:\n\n` +
      `1. **Overview**: Your query covers core concepts supported by NegoMind AI Assistant.\n` +
      `2. **Key Application**: In NegoMind AI, we integrate general domain knowledge, technical software engineering, and strategic multi-agent negotiation models.\n` +
      `3. **Next Steps**: Feel free to ask specific follow-up questions, coding problems, math equations, or live session details!\n\n` +
      `*What specific detail or topic would you like to explore next?*`,
    suggestions: [
      "Explain concession tracking",
      "What is ZOPA?",
      "How do I start a negotiation?",
      "Explain policy modes"
    ],
  };
}

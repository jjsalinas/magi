/* =========================================================
   MAGI CLIENT
   Backend is authoritative.
   The frontend NEVER recomputes the final decision.
   ========================================================= */

const form = document.getElementById("form");
const input = document.getElementById("question");
const submit = document.getElementById("submit");

const members = ["melchior", "balthasar", "casper"];

const memberIds = {
  MELCHIOR: "melchior",
  "MELCHIOR-01": "melchior",

  BALTHASAR: "balthasar",
  "BALTHASAR-02": "balthasar",

  CASPER: "casper",
  "CASPER-03": "casper",
};

/* =========================================================
   DOM HELPERS
   ========================================================= */

function el(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  const element = el(id);

  if (element) {
    element.textContent = value ?? "";
  }
}

/* =========================================================
   DECISION NORMALIZATION
   ========================================================= */

function normalizeDecision(value) {
  if (value === null || value === undefined) {
    return null;
  }

  const decision = String(value).trim().toUpperCase();

  switch (decision) {
    case "YES":
      return "YES";

    case "NO":
      return "NO";

    case "UNRESOLVED":
      return "UNRESOLVED";

    default:
      return null;
  }
}

/*
 * IMPORTANT:
 *
 * This function ONLY reads the backend's final decision.
 *
 * It does NOT:
 *   - count votes
 *   - infer YES/NO
 *   - inspect answer_polarity
 *   - inspect question wording
 *
 * The backend is the MAGI.
 */

function getBackendDecision(data) {
  const decision = normalizeDecision(data?.decision);

  if (decision) {
    return decision;
  }

  return "UNRESOLVED";
}

/* =========================================================
   QUESTION TYPE
   ========================================================= */

function normalizeQuestionType(value) {
  if (!value) {
    return "GENERAL";
  }

  return String(value).trim().toUpperCase();
}

function isBinaryQuestion(data) {
  const type = normalizeQuestionType(data?.question_type);

  return (
    type === "BINARY" || type === "YES_NO" || type === "AFFIRMATIVE_NEGATIVE"
  );
}

/* =========================================================
   SYSTEM STATUS SIGN
   ========================================================= */

function setSystemSign(status) {
  const sign = el("system-sign");
  const value = el("system-sign-value");

  if (!sign || !value) {
    return;
  }

  sign.classList.remove("yes", "no", "thinking", "unresolved", "complete");

  const normalized = String(status || "").toUpperCase();

  value.textContent = normalized;

  switch (normalized) {
    case "YES":
    case "AFFIRMATIVE":
      sign.classList.add("yes");
      break;

    case "NO":
    case "NEGATIVE":
      sign.classList.add("no");
      break;

    case "THINKING...":
    case "DELIBERATING...":
    case "REVIEW":
      sign.classList.add("thinking");
      break;

    case "UNRESOLVED":
    case "MAJORITY":
      sign.classList.add("unresolved");
      break;

    case "COMPLETE":
      sign.classList.add("complete");
      break;
  }
}

/* =========================================================
   DECISION VISUALS
   ========================================================= */

function colorDecision(element, decision) {
  if (!element) {
    return;
  }

  element.style.color = "";
  element.style.textShadow = "";

  switch (decision) {
    case "YES":
      element.style.color = "var(--green)";
      element.style.textShadow = "0 0 20px var(--green)";
      break;

    case "NO":
      element.style.color = "var(--red)";
      element.style.textShadow = "0 0 20px var(--red)";
      break;

    case "UNRESOLVED":
    default:
      element.style.color = "var(--yellow)";
      element.style.textShadow = "0 0 20px var(--yellow)";
      break;
  }
}

/* =========================================================
   RESET MEMBER
   ========================================================= */

function resetMember(id) {
  const node = el(id);

  if (!node) {
    return;
  }

  node.classList.remove("thinking", "voted", "yes", "no", "unresolved");

  setText(`${id}-status`, "STANDBY");
  setText(`${id}-reason`, "Awaiting proposition.");
  setText(`${id}-confidence`, "");
}

/* =========================================================
   MEMBER THINKING
   ========================================================= */

function setThinking(id) {
  const node = el(id);

  if (!node) {
    return;
  }

  node.classList.remove("yes", "no", "unresolved");
  node.classList.add("thinking");

  setText(`${id}-status`, "THINKING...");
}

/* =========================================================
   MEMBER DECISION CLASS
   ========================================================= */

function applyDecisionClass(node, decision) {
  if (!node) {
    return;
  }

  node.classList.remove("yes", "no", "unresolved");

  if (decision === "YES") {
    node.classList.add("yes");
  } else if (decision === "NO") {
    node.classList.add("no");
  } else {
    node.classList.add("unresolved");
  }
}

/* =========================================================
   SHOW MEMBER RESULT
   ========================================================= */

function showResult(result) {
  if (!result || !result.member) {
    return;
  }

  const memberName = String(result.member).trim().toUpperCase();
  const id = memberIds[memberName];
  const node = el(id);

  if (!id || !node) {
    console.warn("Unknown MAGI member:", result.member);
    return;
  }

  const decision = normalizeDecision(result.decision);

  node.classList.remove("thinking", "voted");
  node.classList.add("voted");

  applyDecisionClass(node, decision);

  /*
   * A member's decision comes directly from the backend.
   */

  setText(`${id}-status`, decision || "REVIEW");

  setText(`${id}-reason`, result.reason || "No reasoning supplied.");

  if (
    typeof result.confidence === "number" &&
    Number.isFinite(result.confidence)
  ) {
    const confidence = Math.max(0, Math.min(1, result.confidence));

    setText(`${id}-confidence`, `CONFIDENCE: ${Math.round(confidence * 100)}%`);
  } else {
    setText(`${id}-confidence`, "");
  }
}

/* =========================================================
   ROUND / STATE DISPLAY
   ========================================================= */

function getState(data) {
  return data?.state || {};
}

function getRound(data) {
  const state = getState(data);

  const round = Number(state.round);

  if (Number.isFinite(round) && round > 0) {
    return round;
  }

  return null;
}

function getMaxRounds(data) {
  const state = getState(data);

  const maxRounds = Number(state.max_rounds);

  if (Number.isFinite(maxRounds) && maxRounds > 0) {
    return maxRounds;
  }

  return 5;
}

function getPhase(data) {
  const state = getState(data);

  return String(state.phase || "").toUpperCase();
}

/* =========================================================
   CONSENSUS DESCRIPTION
   ========================================================= */

function buildConsensusLabel(data) {
  const decision = getBackendDecision(data);
  const state = getState(data);

  const yes = Number(data?.votes?.yes ?? 0);
  const no = Number(data?.votes?.no ?? 0);

  const unanimous =
    state.unanimous === true ||
    (yes === 3 && no === 0) ||
    (no === 3 && yes === 0);

  const final =
    state.final === true ||
    getPhase(data) === "CONSENSUS_REACHED" ||
    getPhase(data) === "MAJORITY_FINAL";

  if (decision === "YES") {
    if (unanimous) {
      return "3 / 3 CONSENSUS";
    }

    if (final) {
      return `${yes} YES / ${no} NO — MAJORITY`;
    }

    return `${yes} YES / ${no} NO`;
  }

  if (decision === "NO") {
    if (unanimous) {
      return "3 / 3 CONSENSUS";
    }

    if (final) {
      return `${no} NO / ${yes} YES — MAJORITY`;
    }

    return `${yes} YES / ${no} NO`;
  }

  return `${yes} YES / ${no} NO — UNRESOLVED`;
}

/* =========================================================
   STATE SIGN
   ========================================================= */

function showFinalSystemState(data) {
  const decision = getBackendDecision(data);
  const state = getState(data);
  const phase = getPhase(data);

  /*
   * FINAL DECISION ALWAYS WINS.
   *
   * This is the critical fix.
   *
   * We do NOT use:
   *   answer_polarity
   *   vote counts
   *   question wording
   *   previous UI state
   *
   * to determine the visual state.
   */

  if (decision === "YES") {
    setSystemSign("YES");
    return;
  }

  if (decision === "NO") {
    setSystemSign("NO");
    return;
  }

  if (decision === "UNRESOLVED") {
    setSystemSign("UNRESOLVED");
    return;
  }

  /*
   * Defensive fallback.
   */

  if (state.final === true || phase === "CONSENSUS_REACHED") {
    setSystemSign("COMPLETE");
  } else {
    setSystemSign("REVIEW");
  }
}

/* =========================================================
   MAGI CONCLUSION
   ========================================================= */

function showConclusion(data) {
  const conclusion = el("case-decision");

  if (!conclusion) {
    return;
  }

  /*
   * NEVER derive this from member votes.
   *
   * data.decision is authoritative.
   */

  const decision = getBackendDecision(data);

  conclusion.textContent = decision;

  colorDecision(conclusion, decision);

  setText("case-votes", buildConsensusLabel(data));
}

/* =========================================================
   DELIBERATION SUMMARY
   ========================================================= */

function showDeliberationState(data) {
  const state = getState(data);

  const round = getRound(data);
  const maxRounds = getMaxRounds(data);
  const phase = getPhase(data);

  /*
   * These elements are optional.
   * This lets the JS work with both the old and upgraded HTML.
   */

  const sessionElement = el("session-id");

  if (sessionElement) {
    sessionElement.textContent = state.session_id || "---";
  }

  const phaseElement = el("phase");

  if (phaseElement) {
    phaseElement.textContent = phase || "UNKNOWN";
  }

  const roundElement = el("round");

  if (roundElement) {
    roundElement.textContent =
      round !== null ? `${round} / ${maxRounds}` : `0 / ${maxRounds}`;
  }
}

/* =========================================================
   FULL RESULT
   ========================================================= */

function renderResult(data) {
  /*
   * 1. Render individual MAGI opinions.
   */

  if (Array.isArray(data.members)) {
    data.members.forEach(showResult);
  }

  /*
   * 2. Render the backend's authoritative conclusion.
   */

  showConclusion(data);

  /*
   * 3. Render deliberation state.
   */

  showDeliberationState(data);

  /*
   * 4. Update system visual.
   */

  showFinalSystemState(data);
}

/* =========================================================
   ERROR STATE
   ========================================================= */

function showError(error) {
  console.error(error);

  members.forEach((id) => {
    const node = el(id);

    if (node) {
      node.classList.remove("thinking", "voted", "yes", "no");

      node.classList.add("unresolved");
    }

    setText(`${id}-status`, "ERROR");
    setText(`${id}-reason`, "MAGI communication failure.");
    setText(`${id}-confidence`, "");
  });

  const conclusion = el("case-decision");

  if (conclusion) {
    conclusion.textContent = "SYSTEM ERROR";
    conclusion.style.color = "var(--red)";
    conclusion.style.textShadow = "0 0 20px var(--red)";
  }

  setText("case-votes", error?.message || "Unknown system error.");

  setSystemSign("NO");
}

/* =========================================================
   SUBMIT
   ========================================================= */

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const question = input.value.trim();

  if (!question) {
    return;
  }

  submit.disabled = true;
  submit.textContent = "DELIBERATING...";

  /*
   * Reset members.
   */

  members.forEach(resetMember);
  members.forEach(setThinking);

  /*
   * System enters deliberation.
   */

  setSystemSign("DELIBERATING...");

  /*
   * Question display.
   */

  setText("case-question", question);

  const conclusion = el("case-decision");

  if (conclusion) {
    conclusion.textContent = "DELIBERATING...";
    conclusion.style.color = "";
    conclusion.style.textShadow = "";
  }

  setText("case-votes", "MAGI DELIBERATION IN PROGRESS");

  try {
    const response = await fetch("/api/decide", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        question,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();

    if (data.error) {
      throw new Error(data.error);
    }

    console.log("MAGI RESULT:", data);

    /*
     * IMPORTANT:
     *
     * We deliberately do NOT calculate:
     *
     *   yes > no
     *   no > yes
     *
     * here.
     *
     * The backend has already performed the deliberation
     * and determined the final decision.
     */

    renderResult(data);
  } catch (error) {
    showError(error);
  } finally {
    submit.disabled = false;
    submit.textContent = "INITIATE";
  }
});

/* =========================================================
   INITIAL STATE
   ========================================================= */

setSystemSign("STANDBY");

members.forEach(resetMember);

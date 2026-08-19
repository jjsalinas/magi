/* =========================================================
   MAGI CLIENT
   =========================================================
   Flow:

   1. User submits a question.
   2. POST /api/decide starts a MAGI session.
   3. Backend immediately returns session_id.
   4. Frontend begins polling GET /api/decide/{session_id}.
   5. Every poll updates:
      - MAGI member states
      - confidence brick backgrounds
      - round / phase
      - deliberation accordion
      - final decision
   6. Polling stops when the backend reports a final state.
   ========================================================= */

const form = document.getElementById("form");
const input = document.getElementById("question");
const submit = document.getElementById("submit");

const members = ["melchior", "balthasar", "casper"];

/*
 * How often we ask the backend for the current session.
 *
 * 10000ms gives the UI a fairly responsive feeling without
 * hammering the local LLM server.
 */
const POLL_INTERVAL = 10000;

let pollTimer = null;
let activeSessionId = null;

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

/* =========================================================
   BACKEND DECISION
   ========================================================= */

function getBackendDecision(data) {
  const decision = normalizeDecision(data?.decision);

  if (decision) {
    return decision;
  }

  return "UNRESOLVED";
}

/* =========================================================
   STATE HELPERS
   ========================================================= */

function getState(data) {
  return data?.state || {};
}

function getPhase(data) {
  const state = getState(data);

  return String(state.phase || "").toUpperCase();
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

/* =========================================================
   SESSION FINISHED?
   ========================================================= */

function isSessionFinished(data) {
  const state = getState(data);
  const phase = getPhase(data);
  const decision = normalizeDecision(data?.decision);

  /*
   * These are the phases currently emitted by the backend.
   */

  const finalPhases = [
    "CONSENSUS_REACHED",
    "FINAL_MAJORITY",
    "FORCED_FINAL_MAJORITY",
    "COMPLETE",
    "COMPLETED",
  ];

  if (finalPhases.includes(phase)) {
    return true;
  }

  /*
   * Some backend versions may expose an explicit final flag.
   */

  if (state.final === true || state.complete === true) {
    return true;
  }

  /*
   * A valid YES/NO decision combined with the maximum round
   * is also treated as final.
   */

  const round = getRound(data);
  const maxRounds = getMaxRounds(data);

  if (
    decision &&
    decision !== "UNRESOLVED" &&
    round !== null &&
    round >= maxRounds
  ) {
    return true;
  }

  return false;
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

  sign.classList.remove(
    "yes",
    "no",
    "thinking",
    "unresolved",
    "complete",
    "error",
  );

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

    case "ERROR":
      sign.classList.add("error");
      break;
  }
}

/* =========================================================
   DECISION COLORS
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

  /*
   * Remove any previously generated confidence bricks.
   */

  const bricks = node.querySelector(".confidence-bricks");

  if (bricks) {
    bricks.innerHTML = "";
  }

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
   CONFIDENCE BRICKS
   =========================================================
   Visualizes confidence as a brick wall.

   Example:

   25%

   [][][][]
   [][][][]

   75%

   [][][][]
   [][][][]
   [][][][]
   [][][]

   The bricks grow upward from the bottom.

   Green = YES confidence
   Red   = NO confidence

   We deliberately cap the visual at 70%.

   This means:
     70% confidence = completely filled
     35% confidence = half filled
     10% confidence = small amount
   ========================================================= */

function renderConfidenceBricks(node, decision, confidence) {
  if (!node) {
    return;
  }

  let container = node.querySelector(".confidence-bricks");

  if (!container) {
    container = document.createElement("div");
    container.className = "confidence-bricks";
    node.appendChild(container);
  }

  container.innerHTML = "";

  if (typeof confidence !== "number" || !Number.isFinite(confidence)) {
    return;
  }

  /*
   * Confidence is 0..1.
   *
   * Visual saturation stops at 70%.
   */

  const normalized = Math.max(0, Math.min(1, confidence));

  const fill = Math.min(normalized / 0.7, 1);

  /*
   * Number of brick rows and columns.
   *
   * CSS controls the actual dimensions.
   */

  const columns = 7;
  const rows = 8;
  const total = columns * rows;

  const brickCount = Math.round(fill * total);

  /*
   * Only YES and NO get confidence bricks.
   */

  if (decision !== "YES" && decision !== "NO") {
    return;
  }

  for (let index = 0; index < total; index++) {
    const brick = document.createElement("span");

    brick.className = "confidence-brick";

    if (decision === "YES") {
      brick.classList.add("brick-yes");
    } else {
      brick.classList.add("brick-no");
    }

    /*
     * Fill bottom-up.
     */

    const rowFromBottom = Math.floor(index / columns);

    const column = index % columns;

    /*
     * Alternate rows to produce an actual brick-wall
     * pattern instead of a simple grid.
     */

    const offset = rowFromBottom % 2 === 0 ? 0 : 0.5;

    /*
     * Convert the brick position into a fill index.
     *
     * This isn't used for geometry; it makes the visual
     * progression deterministic.
     */

    const visualIndex = rowFromBottom * columns + column;

    if (visualIndex < brickCount) {
      brick.classList.add("active");
    }

    /*
     * Slightly offset every second row.
     */

    brick.style.setProperty("--brick-offset", `${offset}em`);

    container.appendChild(brick);
  }
}

/* =========================================================
   MEMBER ID NORMALIZATION
   ========================================================= */

function normalizeMemberId(value) {
  if (!value) {
    return null;
  }

  const normalized = String(value)
    .trim()
    .toLowerCase();

  /*
   * Backend may return:
   *
   *   MELCHIOR
   *   MELCHIOR-01
   *   MELCHIOR_01
   *   melchior
   *
   * The DOM uses only:
   *
   *   melchior
   *   balthasar
   *   casper
   */

  if (normalized.startsWith("melchior")) {
    return "melchior";
  }

  if (normalized.startsWith("balthasar")) {
    return "balthasar";
  }

  if (normalized.startsWith("casper")) {
    return "casper";
  }

  return null;
}


/* =========================================================
   SHOW MEMBER RESULT
   ========================================================= */

function showResult(result) {
  if (!result || !result.member) {
    return;
  }

  const id = normalizeMemberId(result.member);
  const node = id ? el(id) : null;

  if (!node) {
    console.warn("Unknown MAGI member:", result.member);
    return;
  }

  const decision = normalizeDecision(result.decision);

  /*
   * IMPORTANT:
   *
   * Remove the temporary thinking state.
   */

  node.classList.remove(
    "thinking",
    "voted",
    "yes",
    "no",
    "unresolved",
  );

  /*
   * Mark the member as having completed its response.
   */

  node.classList.add("voted");

  /*
   * Apply the backend's actual decision.
   */

  applyDecisionClass(node, decision);

  setText(
    `${id}-status`,
    decision || "REVIEW",
  );

  setText(
    `${id}-reason`,
    result.reason || "No reasoning supplied.",
  );

  if (
    typeof result.confidence === "number" &&
    Number.isFinite(result.confidence)
  ) {
    const confidence = Math.max(
      0,
      Math.min(1, result.confidence),
    );

    setText(
      `${id}-confidence`,
      `CONFIDENCE: ${Math.round(confidence * 100)}%`,
    );
  } else {
    setText(`${id}-confidence`, "");
  }
}

/* =========================================================
   RENDER ALL MEMBERS
   ========================================================= */

function renderMembers(data) {
  if (!Array.isArray(data?.members)) {
    return;
  }

  data.members.forEach(showResult);
}

/* =========================================================
   ROUND / SESSION DISPLAY
   ========================================================= */

function showDeliberationState(data) {
  const state = getState(data);

  const sessionElement = el("session-id");

  if (sessionElement) {
    sessionElement.textContent = state.session_id || data.session_id || "---";
  }

  /*
   * Current HTML uses session-phase.
   *
   * Support "phase" too in case an upgraded HTML uses it.
   */

  const phase = getPhase(data) || "UNKNOWN";

  const phaseElement = el("session-phase") || el("phase");

  if (phaseElement) {
    phaseElement.textContent = phase;
  }

  const round = getRound(data);
  const maxRounds = getMaxRounds(data);

  const roundElement = el("session-round") || el("round");

  if (roundElement) {
    roundElement.textContent =
      round !== null ? `${round} / ${maxRounds}` : `0 / ${maxRounds}`;
  }
}

/* =========================================================
   CONSENSUS LABEL
   ========================================================= */

function buildConsensusLabel(data) {
  const decision = getBackendDecision(data);

  const yes = Number(data?.votes?.yes ?? 0);

  const no = Number(data?.votes?.no ?? 0);

  const state = getState(data);
  const phase = getPhase(data);

  const unanimous =
    state.unanimous === true ||
    (yes === 3 && no === 0) ||
    (no === 3 && yes === 0);

  const final =
    state.final === true ||
    phase === "CONSENSUS_REACHED" ||
    phase === "FINAL_MAJORITY" ||
    phase === "FORCED_FINAL_MAJORITY";

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
   FINAL SYSTEM STATE
   ========================================================= */

function showFinalSystemState(data) {
  const decision = getBackendDecision(data);

  if (decision === "YES") {
    setSystemSign("YES");
    return;
  }

  if (decision === "NO") {
    setSystemSign("NO");
    return;
  }

  if (isSessionFinished(data)) {
    setSystemSign("UNRESOLVED");
    return;
  }

  setSystemSign("DELIBERATING...");
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
   * During polling, the backend may not yet have a final
   * decision. Do not display a fake YES/NO.
   */

  const rawDecision = normalizeDecision(data?.decision);

  const finished = isSessionFinished(data);

  if (!finished && (!rawDecision || rawDecision === "UNRESOLVED")) {
    conclusion.textContent = "DELIBERATING...";

    conclusion.style.color = "";
    conclusion.style.textShadow = "";

    setText("case-votes", "MAGI DELIBERATION IN PROGRESS");

    return;
  }

  const decision = getBackendDecision(data);

  conclusion.textContent = decision;

  colorDecision(conclusion, decision);

  setText("case-votes", buildConsensusLabel(data));
}

/* =========================================================
   DELIBERATION ACCORDION
   =========================================================
   This function supports the accordion if the updated
   index.html contains:

       <details id="deliberation-panel">
           <summary>...</summary>
           <div id="deliberation-content"></div>
       </details>

   It also supports slightly different IDs.
   ========================================================= */

function renderDeliberation(data) {
  const content = el("deliberation-content") || el("magi-deliberation-content");

  if (!content) {
    return;
  }

  const rounds = Array.isArray(data?.rounds) ? data.rounds : [];

  content.innerHTML = "";

  if (rounds.length === 0) {
    const empty = document.createElement("div");

    empty.className = "deliberation-empty";

    empty.textContent = "NO DELIBERATION DATA RECEIVED.";

    content.appendChild(empty);

    return;
  }

  rounds.forEach((round) => {
    const entry = document.createElement("div");

    entry.className = "deliberation-entry";

    const label = document.createElement("div");

    label.className = "deliberation-entry-label";

    label.textContent =
      `ROUND ${round.round ?? "?"} — ` +
      `${round.yes ?? 0} YES / ` +
      `${round.no ?? 0} NO`;

    entry.appendChild(label);

    const memberResults = Array.isArray(round.members) ? round.members : [];

    memberResults.forEach((member) => {
      const memberBlock = document.createElement("div");

      memberBlock.className = "deliberation-member";

      const memberLabel = document.createElement("div");

      memberLabel.className = "deliberation-member-label";

      memberLabel.textContent =
        `${member.member || "UNKNOWN"} ` +
        `— ${member.decision || "?"} ` +
        `(${Math.round(Number(member.confidence || 0) * 100)}%)`;

      const reason = document.createElement("div");

      reason.className = "deliberation-entry-body";

      reason.textContent = member.reason || "No reasoning supplied.";

      memberBlock.appendChild(memberLabel);

      memberBlock.appendChild(reason);

      entry.appendChild(memberBlock);
    });

    content.appendChild(entry);
  });
}

/* =========================================================
   FULL RESULT SNAPSHOT
   ========================================================= */

function renderResult(data) {
  renderMembers(data);

  showConclusion(data);

  showDeliberationState(data);

  renderDeliberation(data);

  showFinalSystemState(data);
}

/* =========================================================
   POLLING
   ========================================================= */

function stopPolling() {
  if (pollTimer !== null) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

/*
 * Poll recursively with setTimeout rather than setInterval.
 *
 * This prevents overlapping requests if the backend happens
 * to take longer than POLL_INTERVAL to answer.
 */

async function pollSession(sessionId) {
  if (!sessionId) {
    return;
  }

  if (sessionId !== activeSessionId) {
    return;
  }

  try {
    const response = await fetch(
      `/api/decide/${encodeURIComponent(sessionId)}`,
      {
        method: "GET",
        headers: {
          Accept: "application/json",
        },
        cache: "no-store",
      },
    );

    if (!response.ok) {
      throw new Error(`Polling HTTP ${response.status}`);
    }

    const data = await response.json();

    if (data.error) {
      throw new Error(data.error);
    }

    /*
     * Every snapshot updates the UI.
     *
     * This is what makes the confidence bricks appear
     * to grow as the backend advances through rounds.
     */

    renderResult(data);

    /*
     * Stop when MAGI is finished.
     */

    if (isSessionFinished(data)) {
      stopPolling();

      activeSessionId = null;

      submit.disabled = false;
      submit.textContent = "INITIATE";

      return;
    }

    /*
     * Continue polling.
     */

    pollTimer = setTimeout(() => pollSession(sessionId), POLL_INTERVAL);
  } catch (error) {
    /*
     * Don't immediately destroy the whole UI on a transient
     * polling failure.
     *
     * Try again unless this session has been superseded.
     */

    console.error("MAGI polling error:", error);

    if (sessionId !== activeSessionId) {
      return;
    }

    pollTimer = setTimeout(() => pollSession(sessionId), POLL_INTERVAL);
  }
}

/* =========================================================
   ERROR STATE
   ========================================================= */

function showError(error) {
  console.error(error);

  stopPolling();

  activeSessionId = null;

  members.forEach((id) => {
    const node = el(id);

    if (node) {
      node.classList.remove("thinking", "voted", "yes", "no");

      node.classList.add("unresolved");

      const bricks = node.querySelector(".confidence-bricks");

      if (bricks) {
        bricks.innerHTML = "";
      }
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

  setSystemSign("ERROR");

  submit.disabled = false;
  submit.textContent = "INITIATE";
}

/* =========================================================
   START SESSION
   ========================================================= */

async function startSession(question) {
  /*
   * Kill any previous polling session.
   */

  stopPolling();

  activeSessionId = null;

  /*
   * POST ONCE.
   */

  const response = await fetch("/api/decide", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
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

  /*
   * The POST must return the session ID.
   *
   * Support both:
   *
   *   data.session_id
   *
   * and:
   *
   *   data.state.session_id
   */

  const sessionId = data.session_id || data.state?.session_id;

  if (!sessionId) {
    throw new Error("MAGI session started, but no session_id was returned.");
  }

  activeSessionId = sessionId;

  /*
   * Render the initial POST response immediately.
   */

  renderResult(data);

  /*
   * If the backend somehow completed the entire session
   * before returning the POST response, don't poll.
   */

  if (isSessionFinished(data)) {
    activeSessionId = null;

    submit.disabled = false;
    submit.textContent = "INITIATE";

    return;
  }

  /*
   * Begin polling.
   */

  pollSession(sessionId);
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
  submit.textContent = "INITIALIZING...";

  /*
   * Reset previous session.
   */

  stopPolling();
  activeSessionId = null;

  members.forEach(resetMember);
  members.forEach(setThinking);

  /*
   * System enters deliberation.
   */

  setSystemSign("DELIBERATING...");

  /*
   * Show question immediately.
   */

  setText("case-question", question);

  /*
   * Reset conclusion.
   */

  const conclusion = el("case-decision");

  if (conclusion) {
    conclusion.textContent = "DELIBERATING...";

    conclusion.style.color = "";
    conclusion.style.textShadow = "";
  }

  setText("case-votes", "INITIALIZING MAGI SESSION...");

  try {
    await startSession(question);
  } catch (error) {
    showError(error);
  }
});

/* =========================================================
   INITIAL STATE
   ========================================================= */

setSystemSign("STANDBY");

members.forEach(resetMember);

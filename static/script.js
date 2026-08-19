/* =========================================================
   MAGI CLIENT
   ========================================================= */

const form = document.getElementById("form");
const input = document.getElementById("question");
const submit = document.getElementById("submit");

const members = ["melchior", "balthasar", "casper"];

/* =========================================================
   SYSTEM STATUS SIGN
   ========================================================= */

function setSystemSign(status) {
  const sign = document.getElementById("system-sign");
  const value = document.getElementById("system-sign-value");

  sign.classList.remove("yes", "no", "thinking");

  const normalized = String(status).toUpperCase();

  value.textContent = normalized;

  if (normalized === "YES") {
    sign.classList.add("yes");
  } else if (normalized === "NO") {
    sign.classList.add("no");
  } else if (normalized === "THINKING..." || normalized === "DELIBERATING...") {
    sign.classList.add("thinking");
  }
}

/* =========================================================
   RESET MEMBER
   ========================================================= */

function resetMember(id) {
  const node = document.getElementById(id);

  node.classList.remove("thinking", "voted");

  document.getElementById(id + "-status").textContent = "STANDBY";

  document.getElementById(id + "-reason").textContent = "Awaiting proposition.";

  document.getElementById(id + "-confidence").textContent = "";
}

/* =========================================================
   THINKING STATE
   ========================================================= */

function setThinking(id) {
  const node = document.getElementById(id);

  node.classList.add("thinking");

  document.getElementById(id + "-status").textContent = "THINKING...";
}

/* =========================================================
   NORMALIZE DECISION
   ========================================================= */

function normalizeDecision(value) {
  if (!value) {
    return null;
  }

  const decision = String(value).trim().toUpperCase();

  if (decision === "YES" || decision === "NO") {
    return decision;
  }

  return null;
}

/* =========================================================
   SHOW MEMBER RESULT
   ========================================================= */

function showResult(result) {
  const id = result.member.toLowerCase();

  const node = document.getElementById(id);

  const decision = normalizeDecision(result.decision);

  node.classList.remove("thinking");

  node.classList.add("voted");

  document.getElementById(id + "-status").textContent = decision || "INVALID";

  document.getElementById(id + "-reason").textContent = result.reason || "";

  if (typeof result.confidence === "number") {
    document.getElementById(id + "-confidence").textContent =
      "CONFIDENCE: " + Math.round(result.confidence * 100) + "%";
  } else {
    document.getElementById(id + "-confidence").textContent = "";
  }
}

/* =========================================================
   RESULT COLOR
   ========================================================= */

function colorDecision(element, decision) {
  element.style.color = "";
  element.style.textShadow = "";

  if (decision === "YES") {
    element.style.color = "var(--green)";
    element.style.textShadow = "0 0 20px var(--green)";
  } else if (decision === "NO") {
    element.style.color = "var(--red)";
    element.style.textShadow = "0 0 20px var(--red)";
  } else {
    element.style.color = "var(--yellow)";
    element.style.textShadow = "0 0 20px var(--yellow)";
  }
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

  /* -----------------------------------------------
       RESET
       ----------------------------------------------- */

  members.forEach(resetMember);

  members.forEach(setThinking);

  /*
   * Status placard:
   * green = YES
   * red   = NO
   * orange = processing
   */

  setSystemSign("THINKING...");

  /* -----------------------------------------------
       QUESTION
       ----------------------------------------------- */

  document.getElementById("case-question").textContent = question;

  document.getElementById("case-decision").textContent = "DELIBERATING...";

  document.getElementById("case-decision").style.color = "";

  document.getElementById("case-decision").style.textShadow = "";

  document.getElementById("case-votes").textContent = "";

  /* -----------------------------------------------
       API
       ----------------------------------------------- */

  try {
    const response = await fetch("/api/decide", {
      method: "POST",

      headers: {
        "Content-Type": "application/json",
      },

      body: JSON.stringify({ question }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();

    if (data.error) {
      throw new Error(data.error);
    }

    /* -------------------------------------------
           MEMBER RESULTS
           ------------------------------------------- */

    data.members.forEach(showResult);

    /* -------------------------------------------
           COUNT ACTUAL MEMBER VOTES
           ------------------------------------------- */

    const normalizedMembers = data.members.map((member) => ({
      ...member,

      decision: normalizeDecision(member.decision),
    }));

    const yes = normalizedMembers.filter(
      (member) => member.decision === "YES",
    ).length;

    const no = normalizedMembers.filter(
      (member) => member.decision === "NO",
    ).length;

    /* -------------------------------------------
           MAGI CONSENSUS
           ------------------------------------------- */

    let finalDecision;

    if (yes > no) {
      finalDecision = "YES";
    } else if (no > yes) {
      finalDecision = "NO";
    } else {
      finalDecision = "UNRESOLVED";
    }

    /* -------------------------------------------
           FINAL CONCLUSION
           ------------------------------------------- */

    const conclusion = document.getElementById("case-decision");

    conclusion.textContent = finalDecision;

    colorDecision(conclusion, finalDecision);

    document.getElementById("case-votes").textContent = `${yes} YES / ${no} NO`;

    /*
     * Update the Evangelion-style status sign.
     */

    setSystemSign(finalDecision);

    /* -------------------------------------------
           BACKEND CONSISTENCY CHECK
           ------------------------------------------- */

    if (data.decision && normalizeDecision(data.decision) !== finalDecision) {
      console.warn(
        "MAGI backend consensus differs from member votes:",
        data.decision,
        finalDecision,
      );
    }
  } catch (error) {
    console.error(error);

    const conclusion = document.getElementById("case-decision");

    conclusion.textContent = "SYSTEM ERROR";

    conclusion.style.color = "var(--red)";

    conclusion.style.textShadow = "0 0 20px var(--red)";

    document.getElementById("case-votes").textContent = error.message;

    /*
     * System failure gets the red sign too.
     */

    setSystemSign("NO");
  } finally {
    submit.disabled = false;

    submit.textContent = "INITIATE";
  }
});

/* =========================================================
   INITIAL STATE
   ========================================================= */

setSystemSign("STANDBY");

const LOCAL_KEYS = {
  reviewState: "lineDrill.reviewState.v1",
  reviewHistory: "lineDrill.reviewHistory.v1",
};
const REVIEW_LIMIT = 200;
const HEALTH_CHECK_INTERVAL_MS = 5000;

const state = {
  dialogues: [],
  todayItems: [],
  reviewQueue: [],
  practiceIndex: 0,
  showKo: false,
  todayRepeat: false,
  todayPlaying: false,
  practiceRepeat: false,
  selectedReviewId: null,
  deferredPrompt: null,
  useBackend: true,
  speechToken: 0,
  audioPlayer: null,
  audioObjectUrl: null,
  audioFetchController: null,
  backendBootId: null,
  backendHealthTimer: null,
  backendHealthInFlight: false,
};

const el = {
  tabs: Array.from(document.querySelectorAll(".tab")),
  panels: {
    today: document.getElementById("todayPanel"),
    practice: document.getElementById("practicePanel"),
    review: document.getElementById("reviewPanel"),
  },
  totalDialogues: document.getElementById("totalDialogues"),
  dueToday: document.getElementById("dueToday"),
  reviewedToday: document.getElementById("reviewedToday"),
  todayList: document.getElementById("todayList"),
  playTodayBtn: document.getElementById("playTodayBtn"),
  todayRepeatBtn: document.getElementById("todayRepeatBtn"),
  shuffleToday: document.getElementById("shuffleToday"),
  dialogMeta: document.getElementById("dialogMeta"),
  patternChips: document.getElementById("patternChips"),
  turnList: document.getElementById("turnList"),
  playBtn: document.getElementById("playBtn"),
  practiceRepeatBtn: document.getElementById("practiceRepeatBtn"),
  toggleKoBtn: document.getElementById("toggleKoBtn"),
  clozeBtn: document.getElementById("clozeBtn"),
  clozeBox: document.getElementById("clozeBox"),
  prevBtn: document.getElementById("prevBtn"),
  nextBtn: document.getElementById("nextBtn"),
  pagerText: document.getElementById("pagerText"),
  reviewList: document.getElementById("reviewList"),
  refreshReview: document.getElementById("refreshReview"),
  recallInput: document.getElementById("recallInput"),
  scoreRow: document.getElementById("scoreRow"),
  installBtn: document.getElementById("installBtn"),
  modeBadge: document.getElementById("modeBadge"),
};

function formatLocalIso(dateObj) {
  const year = dateObj.getFullYear();
  const month = String(dateObj.getMonth() + 1).padStart(2, "0");
  const day = String(dateObj.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function todayIso() {
  return formatLocalIso(new Date());
}

function parseIso(dateText) {
  const [year, month, day] = dateText.split("-").map((v) => Number(v));
  return new Date(year, month - 1, day);
}

function addDays(baseIso, days) {
  const date = parseIso(baseIso);
  date.setDate(date.getDate() + days);
  return formatLocalIso(date);
}

function readLocalJson(key, fallbackValue) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) {
      return fallbackValue;
    }
    return JSON.parse(raw);
  } catch {
    return fallbackValue;
  }
}

function writeLocalJson(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function ensureLocalReviewState() {
  const today = todayIso();
  const map = readLocalJson(LOCAL_KEYS.reviewState, {});
  let changed = false;

  for (const dialogue of state.dialogues) {
    if (!map[dialogue.id]) {
      map[dialogue.id] = {
        due_date: today,
        interval_days: 1,
        repetitions: 0,
        easiness: 2.5,
        last_score: 0,
      };
      changed = true;
    }
  }

  if (changed) {
    writeLocalJson(LOCAL_KEYS.reviewState, map);
  }

  return map;
}

function applySrs(review, score) {
  const next = {
    due_date: review.due_date || todayIso(),
    interval_days: review.interval_days || 1,
    repetitions: review.repetitions || 0,
    easiness: review.easiness || 2.5,
    last_score: review.last_score || 0,
  };

  if (score < 3) {
    next.repetitions = 0;
    next.interval_days = 1;
  } else {
    if (next.repetitions === 0) {
      next.interval_days = 1;
    } else if (next.repetitions === 1) {
      next.interval_days = 3;
    } else {
      next.interval_days = Math.max(1, Math.round(next.interval_days * next.easiness));
    }
    next.repetitions += 1;
  }

  const qualityGap = 5 - score;
  next.easiness = Math.max(
    1.3,
    next.easiness + (0.1 - qualityGap * (0.08 + qualityGap * 0.02)),
  );
  next.last_score = score;
  next.due_date = addDays(todayIso(), next.interval_days);

  return next;
}

function appendLocalHistory(dialogueId, score) {
  const today = todayIso();
  const history = readLocalJson(LOCAL_KEYS.reviewHistory, []);
  history.push({
    dialogue_id: dialogueId,
    score,
    local_day: today,
    attempt_at: new Date().toISOString(),
  });
  if (history.length > 3000) {
    history.splice(0, history.length - 3000);
  }
  writeLocalJson(LOCAL_KEYS.reviewHistory, history);
}

function removeLocalHistoryAttempt(dialogueId) {
  const today = todayIso();
  const history = readLocalJson(LOCAL_KEYS.reviewHistory, []);
  for (let i = history.length - 1; i >= 0; i -= 1) {
    const row = history[i];
    if (row.dialogue_id === dialogueId && getHistoryLocalDay(row) === today) {
      history.splice(i, 1);
      break;
    }
  }
  writeLocalJson(LOCAL_KEYS.reviewHistory, history);
}

function getHistoryLocalDay(row) {
  if (row.local_day) {
    return row.local_day;
  }
  if (row.attempt_at) {
    const parsed = new Date(row.attempt_at);
    if (!Number.isNaN(parsed.getTime())) {
      return formatLocalIso(parsed);
    }
    if (typeof row.attempt_at === "string" && row.attempt_at.length >= 10) {
      return row.attempt_at.slice(0, 10);
    }
  }
  return "";
}

function localStats() {
  const today = todayIso();
  const reviewMap = ensureLocalReviewState();
  const dueToday = state.dialogues.filter((dialogue) => {
    const review = reviewMap[dialogue.id];
    return review && review.due_date <= today;
  }).length;
  const reviewedToday = Math.max(0, state.dialogues.length - dueToday);

  return {
    total_dialogues: state.dialogues.length,
    due_today: dueToday,
    reviewed_today: reviewedToday,
  };
}

function localReviewQueue(limit, dueOnly = false) {
  const today = todayIso();
  const reviewMap = ensureLocalReviewState();

  let items = state.dialogues
    .map((dialogue) => ({
      dialogue,
      ...reviewMap[dialogue.id],
    }));

  if (dueOnly) {
    items = items.filter((item) => item.due_date <= today);
  }

  return items
    .sort((a, b) => {
      if (a.due_date === b.due_date) {
        return a.dialogue.set_no - b.dialogue.set_no;
      }
      return a.due_date.localeCompare(b.due_date);
    })
    .slice(0, limit);
}

async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const res = await fetch(path, { ...options, signal: controller.signal });
    if (!res.ok) {
      throw new Error(`${res.status} ${res.statusText}`);
    }
    return await res.json();
  } finally {
    clearTimeout(timeout);
  }
}

function setPlaybackState(value) {
  if (!("mediaSession" in navigator)) {
    return;
  }
  try {
    navigator.mediaSession.playbackState = value;
  } catch {
    // Playback state is optional.
  }
}

function releaseAudioObjectUrl() {
  if (state.audioObjectUrl) {
    URL.revokeObjectURL(state.audioObjectUrl);
    state.audioObjectUrl = null;
  }
}

async function prepareAudioBlobUrl(url, token) {
  if (token !== state.speechToken) {
    return null;
  }
  if (state.audioFetchController) {
    state.audioFetchController.abort();
    state.audioFetchController = null;
  }
  const controller = new AbortController();
  state.audioFetchController = controller;
  try {
    const res = await fetch(url, { signal: controller.signal, cache: "no-store" });
    if (!res.ok) {
      return null;
    }
    const blob = await res.blob();
    if (token !== state.speechToken) {
      return null;
    }
    releaseAudioObjectUrl();
    const objectUrl = URL.createObjectURL(blob);
    state.audioObjectUrl = objectUrl;
    return objectUrl;
  } catch {
    return null;
  } finally {
    if (state.audioFetchController === controller) {
      state.audioFetchController = null;
    }
  }
}

function ensureAudioPlayer() {
  if (state.audioPlayer) {
    return state.audioPlayer;
  }
  const player = new Audio();
  player.preload = "auto";
  player.setAttribute("playsinline", "true");
  state.audioPlayer = player;
  return player;
}

function setMediaSessionTitle(title) {
  if (!("mediaSession" in navigator)) {
    return;
  }
  try {
    navigator.mediaSession.metadata = new MediaMetadata({
      title,
      artist: "English Line Drill",
    });
  } catch {
    // Media metadata is optional.
  }
}

async function playDialogueAudio(dialogue, token, loop = false) {
  const player = ensureAudioPlayer();
  const url = `/api/audio/dialogue/${encodeURIComponent(dialogue.id)}.wav`;
  const source = await prepareAudioBlobUrl(url, token);
  if (!source) {
    return false;
  }
  player.pause();
  player.currentTime = 0;
  player.loop = loop;
  player.src = source;
  setMediaSessionTitle(`${dialogue.set_no}. ${dialogue.title}`);

  try {
    await player.play();
    setPlaybackState("playing");
  } catch {
    setPlaybackState("none");
    return false;
  }

  if (loop) {
    return true;
  }

  return await new Promise((resolve) => {
    let settled = false;
    const finish = (ok) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      setPlaybackState("none");
      resolve(ok);
    };
    const onEnded = () => finish(token === state.speechToken);
    const onError = () => finish(false);
    const onPause = () => {
      if (token !== state.speechToken) {
        finish(false);
      }
    };
    const cleanup = () => {
      player.removeEventListener("ended", onEnded);
      player.removeEventListener("error", onError);
      player.removeEventListener("pause", onPause);
    };

    player.addEventListener("ended", onEnded);
    player.addEventListener("error", onError);
    player.addEventListener("pause", onPause);
  });
}

async function playPlaylistAudio(dialogueIds, token, loop = false) {
  if (!dialogueIds.length) {
    return false;
  }
  const player = ensureAudioPlayer();
  const idsParam = encodeURIComponent(dialogueIds.join(","));
  const url = `/api/audio/playlist.wav?ids=${idsParam}`;
  const source = await prepareAudioBlobUrl(url, token);
  if (!source) {
    return false;
  }
  player.pause();
  player.currentTime = 0;
  player.loop = loop;
  player.src = source;
  setMediaSessionTitle("Today's 5 Lines");

  try {
    await player.play();
    setPlaybackState("playing");
  } catch {
    setPlaybackState("none");
    return false;
  }

  if (loop) {
    return true;
  }

  return await new Promise((resolve) => {
    let settled = false;
    const finish = (ok) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      setPlaybackState("none");
      resolve(ok);
    };
    const onEnded = () => finish(token === state.speechToken);
    const onError = () => finish(false);
    const onPause = () => {
      if (token !== state.speechToken) {
        finish(false);
      }
    };
    const cleanup = () => {
      player.removeEventListener("ended", onEnded);
      player.removeEventListener("error", onError);
      player.removeEventListener("pause", onPause);
    };

    player.addEventListener("ended", onEnded);
    player.addEventListener("error", onError);
    player.addEventListener("pause", onPause);
  });
}

function stopSpeech() {
  state.speechToken += 1;
  state.todayPlaying = false;
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
  if (state.audioFetchController) {
    state.audioFetchController.abort();
    state.audioFetchController = null;
  }
  if (state.audioPlayer) {
    state.audioPlayer.pause();
    state.audioPlayer.currentTime = 0;
    state.audioPlayer.loop = false;
    state.audioPlayer.removeAttribute("src");
  }
  releaseAudioObjectUrl();
  setPlaybackState("none");
  updatePlayButtons();
}

function stopForBackendRestart() {
  stopSpeech();
  state.todayRepeat = false;
  state.practiceRepeat = false;
  updateRepeatButtons();
}

function clearBackendHealthMonitor() {
  if (!state.backendHealthTimer) {
    return;
  }
  clearInterval(state.backendHealthTimer);
  state.backendHealthTimer = null;
}

async function checkBackendBootId() {
  if (!state.useBackend) {
    return;
  }
  if (state.backendHealthInFlight) {
    return;
  }
  state.backendHealthInFlight = true;

  try {
    const health = await api("/api/health");
    const nextBootId = health?.server_boot_id || null;
    if (state.backendBootId && nextBootId && state.backendBootId !== nextBootId) {
      stopForBackendRestart();
    }
    state.backendBootId = nextBootId;
  } catch {
    const isAudioPlaying = Boolean(state.audioPlayer && !state.audioPlayer.paused);
    if (state.todayPlaying || isAudioPlaying) {
      stopForBackendRestart();
    }
  } finally {
    state.backendHealthInFlight = false;
  }
}

function startBackendHealthMonitor() {
  clearBackendHealthMonitor();
  if (!state.useBackend) {
    return;
  }
  state.backendHealthTimer = window.setInterval(() => {
    checkBackendBootId().catch(() => {});
  }, HEALTH_CHECK_INTERVAL_MS);
}

function setTab(name) {
  stopSpeech();
  for (const tab of el.tabs) {
    tab.classList.toggle("active", tab.dataset.tab === name);
  }
  for (const [panelName, panel] of Object.entries(el.panels)) {
    panel.classList.toggle("active", panelName === name);
  }
}

function updateRepeatButtons() {
  el.todayRepeatBtn.textContent = state.todayRepeat ? "Repeat On" : "Repeat Off";
  el.practiceRepeatBtn.textContent = state.practiceRepeat ? "Repeat On" : "Repeat Off";
  el.todayRepeatBtn.classList.toggle("active-toggle", state.todayRepeat);
  el.practiceRepeatBtn.classList.toggle("active-toggle", state.practiceRepeat);
}

function updatePlayButtons() {
  if (!el.playTodayBtn) {
    return;
  }
  el.playTodayBtn.textContent = state.todayPlaying ? "Stop 5" : "Play 5";
  el.playTodayBtn.classList.toggle("active-toggle", state.todayPlaying);
}

async function speakText(text, token) {
  if (token !== state.speechToken) {
    return;
  }
  await new Promise((resolve) => {
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "en-US";
    utter.rate = 0.94;
    utter.onend = () => resolve();
    utter.onerror = () => resolve();
    window.speechSynthesis.speak(utter);
  });
}

async function speakDialogue(dialogue, token) {
  for (const turn of dialogue.turns) {
    if (token !== state.speechToken) {
      break;
    }
    await speakText(turn.en, token);
  }
}

async function playDialogueBestEffort(dialogue, token) {
  if (state.useBackend) {
    const audioOk = await playDialogueAudio(dialogue, token);
    if (token !== state.speechToken) {
      return;
    }
    if (audioOk) {
      return;
    }
  }
  await speakDialogue(dialogue, token);
}

async function playTodayBatch() {
  if (!state.todayItems.length) {
    return;
  }
  stopSpeech();
  state.todayPlaying = true;
  updatePlayButtons();
  const token = state.speechToken;
  let keepPlaying = false;

  try {
    if (state.useBackend) {
      const ids = state.todayItems.map((item) => item.id);
      const audioOk = await playPlaylistAudio(ids, token, state.todayRepeat);
      if (token !== state.speechToken) {
        return;
      }
      if (audioOk) {
        keepPlaying = state.todayRepeat;
        return;
      }
    }

    do {
      for (const dialogue of state.todayItems) {
        if (token !== state.speechToken) {
          return;
        }
        await playDialogueBestEffort(dialogue, token);
      }
    } while (token === state.speechToken && state.todayRepeat);
  } finally {
    if (token === state.speechToken && !keepPlaying) {
      state.todayPlaying = false;
      updatePlayButtons();
    }
  }
}

function renderModeBadge() {
  if (state.useBackend) {
    el.modeBadge.textContent = "Online Sync Mode";
    el.modeBadge.style.background = "#e8f4ea";
    el.modeBadge.style.borderColor = "#9db8a6";
    el.modeBadge.style.color = "#2d473d";
  } else {
    el.modeBadge.textContent = "Offline Phone Mode";
    el.modeBadge.style.background = "#fbe7cb";
    el.modeBadge.style.borderColor = "#dfc39f";
    el.modeBadge.style.color = "#5d3c22";
  }
}

function shuffleArray(input) {
  const arr = [...input];
  for (let i = arr.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

function getPracticeItems() {
  if (state.todayItems.length) {
    return state.todayItems;
  }
  return state.dialogues.slice(0, 5);
}

function getCurrentPracticeDialogue() {
  const items = getPracticeItems();
  if (!items.length) {
    return null;
  }
  state.practiceIndex = ((state.practiceIndex % items.length) + items.length) % items.length;
  return items[state.practiceIndex];
}

function pickToday() {
  state.todayItems = shuffleArray(state.dialogues).slice(0, 5);
  state.practiceIndex = 0;
  renderToday();
  renderPractice();
}

function renderToday() {
  el.todayList.innerHTML = "";
  if (!state.todayItems.length) {
    const empty = document.createElement("li");
    empty.className = "tile";
    empty.textContent = "No dialogues loaded.";
    el.todayList.appendChild(empty);
    return;
  }
  for (const d of state.todayItems) {
    const li = document.createElement("li");
    li.className = "tile";
    li.innerHTML = `<strong>${d.set_no}. ${d.title}</strong><p>${d.level} | ${d.scene}</p>`;
    li.addEventListener("click", () => {
      const index = state.todayItems.findIndex((item) => item.id === d.id);
      if (index >= 0) {
        stopSpeech();
        state.practiceIndex = index;
        setTab("practice");
        renderPractice();
      }
    });
    el.todayList.appendChild(li);
  }
}

function renderPractice() {
  const items = getPracticeItems();
  const total = items.length;
  if (!total) {
    el.dialogMeta.textContent = "No dialogue data";
    el.turnList.innerHTML = "";
    el.patternChips.innerHTML = "";
    el.pagerText.textContent = "0 / 0";
    return;
  }

  state.practiceIndex = ((state.practiceIndex % total) + total) % total;
  const current = items[state.practiceIndex];
  el.dialogMeta.textContent = `${current.set_no}. ${current.title} | ${current.level} | ${current.scene}`;
  el.pagerText.textContent = `${state.practiceIndex + 1} / ${total}`;
  el.patternChips.innerHTML = "";
  el.turnList.innerHTML = "";
  el.clozeBox.hidden = true;
  el.clozeBox.innerHTML = "";

  for (const pattern of current.key_patterns) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = pattern;
    el.patternChips.appendChild(chip);
  }

  for (const turn of current.turns) {
    const li = document.createElement("li");
    li.innerHTML = `<strong>${turn.speaker}:</strong> ${turn.en}`;
    if (state.showKo) {
      const ko = document.createElement("span");
      ko.className = "turn-ko";
      ko.textContent = `KO: ${turn.ko}`;
      li.appendChild(ko);
    }
    el.turnList.appendChild(li);
  }
}

function buildCloze(sentence) {
  const words = sentence.split(" ");
  const candidate = words
    .map((word, idx) => ({ word, idx }))
    .filter((item) => item.word.replace(/[^a-zA-Z]/g, "").length >= 4)
    .sort((a, b) => b.word.length - a.word.length)[0];

  if (!candidate) {
    return {
      hasBlank: false,
      maskedSentence: sentence,
      hint: "Repeat it 3 times out loud.",
      answer: "",
      originalWord: "",
    };
  }

  const cleanedAnswer = candidate.word.replace(/[^a-zA-Z]/g, "");
  const answer = cleanedAnswer.toLowerCase();
  words[candidate.idx] = "_".repeat(candidate.word.length);

  return {
    hasBlank: true,
    maskedSentence: words.join(" "),
    hint: answer ? `${answer[0]}...` : "Think about context.",
    answer,
    originalWord: candidate.word,
  };
}

function normalizeClozeText(text) {
  return (text || "").toLowerCase().replace(/[^a-z]/g, "");
}

function renderCloze(sentence) {
  const cloze = buildCloze(sentence);
  el.clozeBox.hidden = false;

  if (!cloze.hasBlank) {
    el.clozeBox.textContent = `${cloze.maskedSentence}\nHint: ${cloze.hint}`;
    return;
  }

  el.clozeBox.innerHTML = `
    <p class="cloze-line">${cloze.maskedSentence}</p>
    <p class="muted small">Hint: ${cloze.hint}</p>
    <div class="cloze-input-row">
      <input id="clozeInput" class="cloze-input" type="text" inputmode="text" autocapitalize="off" autocomplete="off" placeholder="Type missing word" />
      <button id="clozeCheckBtn" class="ghost-btn" type="button">Check</button>
      <button id="clozeRevealBtn" class="ghost-btn" type="button">Reveal</button>
    </div>
    <p id="clozeFeedback" class="cloze-feedback muted small"></p>
  `;

  const input = el.clozeBox.querySelector("#clozeInput");
  const checkBtn = el.clozeBox.querySelector("#clozeCheckBtn");
  const revealBtn = el.clozeBox.querySelector("#clozeRevealBtn");
  const feedback = el.clozeBox.querySelector("#clozeFeedback");

  function checkAnswer() {
    const typed = normalizeClozeText(input.value);
    if (!typed) {
      feedback.textContent = "Type your answer first.";
      return;
    }
    if (typed === cloze.answer) {
      feedback.textContent = "Correct!";
      feedback.style.color = "#1c6b3d";
    } else {
      feedback.textContent = "Not yet. Try once more.";
      feedback.style.color = "#8a4f1a";
    }
  }

  checkBtn.addEventListener("click", checkAnswer);
  revealBtn.addEventListener("click", () => {
    feedback.textContent = `Answer: ${cloze.originalWord}`;
    feedback.style.color = "#2d473d";
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      checkAnswer();
    }
  });

  input.focus();
}

function renderReview() {
  el.reviewList.innerHTML = "";
  const today = todayIso();
  if (!state.reviewQueue.length) {
    const li = document.createElement("li");
    li.className = "tile";
    li.innerHTML = "<strong>Queue empty</strong><p>No review due now.</p>";
    el.reviewList.appendChild(li);
    state.selectedReviewId = null;
    return;
  }

  if (!state.selectedReviewId) {
    state.selectedReviewId = state.reviewQueue[0].dialogue.id;
  }

  for (const item of state.reviewQueue) {
    const activeClass = item.dialogue.id === state.selectedReviewId ? " active" : "";
    const isDone = item.due_date > today;
    const statusLabel = isDone ? "Done" : "Due";
    const statusClass = isDone ? "status-done" : "status-due";
    const li = document.createElement("li");
    li.className = `tile${activeClass}`;
    li.innerHTML = `
      <div class="tile-head">
        <strong>${item.dialogue.set_no}. ${item.dialogue.title}</strong>
        <span class="status-chip ${statusClass}">${statusLabel}</span>
      </div>
      <p>Due: ${item.due_date} | Rep: ${item.repetitions} | Int: ${item.interval_days}d</p>
    `;
    li.addEventListener("click", () => {
      state.selectedReviewId = item.dialogue.id;
      renderReview();
    });
    el.reviewList.appendChild(li);
  }
}

function renderStats(stats) {
  el.totalDialogues.textContent = stats.total_dialogues ?? 0;
  el.dueToday.textContent = stats.due_today ?? 0;
  el.reviewedToday.textContent = stats.reviewed_today ?? 0;
}

async function refreshStatsAndQueue() {
  if (state.useBackend) {
    const [stats, queue] = await Promise.all([
      api("/api/stats"),
      api(`/api/review/next?limit=${REVIEW_LIMIT}&due_only=false`),
    ]);
    state.reviewQueue = queue;
    if (!state.reviewQueue.some((x) => x.dialogue.id === state.selectedReviewId)) {
      state.selectedReviewId = state.reviewQueue[0]?.dialogue.id ?? null;
    }
    renderStats(stats);
    renderReview();
    return;
  }

  state.reviewQueue = localReviewQueue(REVIEW_LIMIT, false);
  if (!state.reviewQueue.some((x) => x.dialogue.id === state.selectedReviewId)) {
    state.selectedReviewId = state.reviewQueue[0]?.dialogue.id ?? null;
  }
  renderStats(localStats());
  renderReview();
}

async function submitScore(score) {
  const dialogueId = state.selectedReviewId;
  if (!dialogueId) {
    return;
  }

  if (state.useBackend) {
    const payload = {
      dialogue_id: dialogueId,
      recalled_sentence: el.recallInput.value.trim(),
      score,
    };
    await api("/api/review/attempt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } else {
    const reviewMap = ensureLocalReviewState();
    const current = reviewMap[dialogueId] || {
      due_date: todayIso(),
      interval_days: 1,
      repetitions: 0,
      easiness: 2.5,
      last_score: 0,
    };
    reviewMap[dialogueId] = applySrs(current, score);
    writeLocalJson(LOCAL_KEYS.reviewState, reviewMap);
    appendLocalHistory(dialogueId, score);
  }

  el.recallInput.value = "";
  await refreshStatsAndQueue();
}

async function resetSelectedReview() {
  const dialogueId = state.selectedReviewId;
  if (!dialogueId) {
    return;
  }

  if (state.useBackend) {
    await api("/api/review/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dialogue_id: dialogueId }),
    });
  } else {
    const reviewMap = ensureLocalReviewState();
    reviewMap[dialogueId] = {
      due_date: todayIso(),
      interval_days: 1,
      repetitions: 0,
      easiness: 2.5,
      last_score: 0,
    };
    writeLocalJson(LOCAL_KEYS.reviewState, reviewMap);
    removeLocalHistoryAttempt(dialogueId);
  }

  await refreshStatsAndQueue();
}

function setupScores() {
  el.scoreRow.innerHTML = "";
  const resetBtn = document.createElement("button");
  resetBtn.className = "score-btn ghost-btn";
  resetBtn.textContent = "R";
  resetBtn.title = "Reset selected review";
  resetBtn.addEventListener("click", () => {
    resetSelectedReview().catch((error) => {
      alert(`Failed to reset: ${error.message}`);
    });
  });
  el.scoreRow.appendChild(resetBtn);

  for (let i = 0; i <= 5; i += 1) {
    const btn = document.createElement("button");
    btn.className = "score-btn";
    btn.textContent = String(i);
    btn.addEventListener("click", () => {
      submitScore(i).catch((error) => {
        alert(`Failed to submit score: ${error.message}`);
      });
    });
    el.scoreRow.appendChild(btn);
  }
}

async function playDialogue() {
  const dialogue = getCurrentPracticeDialogue();
  if (!dialogue) {
    return;
  }
  stopSpeech();
  const token = state.speechToken;

  if (state.useBackend && state.practiceRepeat) {
    const audioLoopOk = await playDialogueAudio(dialogue, token, true);
    if (audioLoopOk) {
      return;
    }
  }

  do {
    await playDialogueBestEffort(dialogue, token);
  } while (token === state.speechToken && state.practiceRepeat);
}

function setupInstallPrompt() {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    state.deferredPrompt = event;
    el.installBtn.hidden = false;
  });

  el.installBtn.addEventListener("click", async () => {
    if (!state.deferredPrompt) {
      return;
    }
    state.deferredPrompt.prompt();
    await state.deferredPrompt.userChoice;
    state.deferredPrompt = null;
    el.installBtn.hidden = true;
  });
}

function setupMediaSessionControls() {
  if (!("mediaSession" in navigator)) {
    return;
  }
  try {
    navigator.mediaSession.setActionHandler("play", async () => {
      if (state.audioPlayer && state.audioPlayer.src) {
        try {
          await state.audioPlayer.play();
          setPlaybackState("playing");
        } catch {
          // ignore resume errors
        }
      }
    });
    navigator.mediaSession.setActionHandler("pause", () => stopSpeech());
    navigator.mediaSession.setActionHandler("stop", () => stopSpeech());
  } catch {
    // Action handlers are best-effort.
  }
}

async function loadOnlineData() {
  const health = await api("/api/health");
  const [dialogues, stats, queue] = await Promise.all([
    api("/api/dialogues?limit=100"),
    api("/api/stats"),
    api(`/api/review/next?limit=${REVIEW_LIMIT}&due_only=false`),
  ]);
  state.useBackend = true;
  state.backendBootId = health?.server_boot_id || null;
  state.dialogues = dialogues;
  state.reviewQueue = queue;
  state.selectedReviewId = queue[0]?.dialogue.id ?? null;
  renderStats(stats);
}

async function loadOfflineData() {
  const seedRes = await fetch("/static/dialogues_seed.json");
  if (!seedRes.ok) {
    throw new Error("Offline seed file missing.");
  }
  const seed = await seedRes.json();
  state.useBackend = false;
  state.backendBootId = null;
  state.dialogues = seed.dialogues || [];
  ensureLocalReviewState();
  state.reviewQueue = localReviewQueue(REVIEW_LIMIT, false);
  state.selectedReviewId = state.reviewQueue[0]?.dialogue.id ?? null;
  renderStats(localStats());
}

async function init() {
  setupScores();
  try {
    await loadOnlineData();
  } catch {
    await loadOfflineData();
  }

  state.practiceIndex = 0;
  state.showKo = false;
  state.todayRepeat = false;
  state.todayPlaying = false;
  state.practiceRepeat = false;
  renderModeBadge();
  updatePlayButtons();
  updateRepeatButtons();
  pickToday();
  renderPractice();
  renderReview();
  startBackendHealthMonitor();
}

for (const tab of el.tabs) {
  tab.addEventListener("click", () => setTab(tab.dataset.tab));
}

el.shuffleToday.addEventListener("click", pickToday);
el.playTodayBtn.addEventListener("click", () => {
  if (state.todayPlaying) {
    stopSpeech();
    return;
  }
  playTodayBatch().catch((error) => alert(`TTS error: ${error.message}`));
});
el.todayRepeatBtn.addEventListener("click", () => {
  state.todayRepeat = !state.todayRepeat;
  if (state.todayRepeat) {
    state.practiceRepeat = false;
  } else {
    stopSpeech();
  }
  updateRepeatButtons();
  if (state.todayRepeat) {
    playTodayBatch().catch((error) => alert(`TTS error: ${error.message}`));
  }
});
el.prevBtn.addEventListener("click", () => {
  const items = getPracticeItems();
  if (!items.length) {
    return;
  }
  stopSpeech();
  state.practiceIndex = (state.practiceIndex - 1 + items.length) % items.length;
  renderPractice();
});
el.nextBtn.addEventListener("click", () => {
  const items = getPracticeItems();
  if (!items.length) {
    return;
  }
  stopSpeech();
  state.practiceIndex = (state.practiceIndex + 1) % items.length;
  renderPractice();
});
el.toggleKoBtn.addEventListener("click", () => {
  state.showKo = !state.showKo;
  el.toggleKoBtn.textContent = state.showKo ? "Hide KO" : "Show KO";
  renderPractice();
});
el.playBtn.addEventListener("click", () => {
  playDialogue().catch((error) => alert(`TTS error: ${error.message}`));
});
el.practiceRepeatBtn.addEventListener("click", () => {
  state.practiceRepeat = !state.practiceRepeat;
  if (state.practiceRepeat) {
    state.todayRepeat = false;
  } else {
    stopSpeech();
  }
  updateRepeatButtons();
  if (state.practiceRepeat) {
    playDialogue().catch((error) => alert(`TTS error: ${error.message}`));
  }
});
el.clozeBtn.addEventListener("click", () => {
  const dialogue = getCurrentPracticeDialogue();
  if (!dialogue) {
    return;
  }
  const source = dialogue.turns[Math.floor(Math.random() * dialogue.turns.length)].en;
  renderCloze(source);
});
el.refreshReview.addEventListener("click", () => {
  refreshStatsAndQueue().catch((error) => alert(`Refresh failed: ${error.message}`));
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/static/sw.js").catch(() => {});
  });
}

document.addEventListener("visibilitychange", () => {
  if (document.hidden || !state.useBackend) {
    return;
  }
  checkBackendBootId().catch(() => {});
});

window.addEventListener("beforeunload", () => {
  clearBackendHealthMonitor();
  stopSpeech();
});

setupInstallPrompt();
setupMediaSessionControls();
init().catch((error) => {
  alert(`Failed to load app data: ${error.message}`);
});

const chatLog = document.getElementById("chatLog");
const commandInput = document.getElementById("commandInput");
const executeBtn = document.getElementById("executeBtn");
const statusPill = document.getElementById("statusPill");
const statusText = document.getElementById("statusText");
const alarmBanner = document.getElementById("alarmBanner");

let busy = false;
let _consecutiveFailures = 0;
let _lastKnownBackendOk = true;

const STATUS_CLASS = {
  "未连接": "idle",
  "已就绪": "ready",
  "分析中": "planning",
  "执行中": "executing",
  "错误": "error",
  "报警": "error",
};

function setStatus(status) {
  statusText.textContent = status;
  statusPill.className = "status-pill " + (STATUS_CLASS[status] || "idle");
}

function setBusy(nextBusy) {
  busy = nextBusy;
  executeBtn.disabled = nextBusy;
  commandInput.disabled = nextBusy;
  /* 脚本模式控件也受 busy 保护 */
  document.getElementById("scriptAddBtn").disabled = nextBusy;
  document.getElementById("scriptInput").disabled = nextBusy;
  document.getElementById("scriptMicBtn").disabled = nextBusy;
  document.getElementById("addPointBtn").disabled = nextBusy;
  document.getElementById("saveProgramBtn").disabled = nextBusy;
  document.getElementById("exportLuaBtn").disabled = nextBusy;
  document.getElementById("runProgramBtn").disabled = nextBusy;
  document.getElementById("newProgramBtn").disabled = nextBusy;
  document.getElementById("importProgramBtn").disabled = nextBusy;
  document.getElementById("programSelect").disabled = nextBusy;
  document.getElementById("programName").disabled = nextBusy;
}

function scrollToBottom() {
  chatLog.scrollTop = chatLog.scrollHeight;
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function botParagraphHtml(text, extraClass = "") {
  const cls = extraClass ? ` class="${extraClass}"` : "";
  const body = escapeHtml(text).split("\n").join("<br>");
  return `<p${cls}>${body}</p>`;
}

function appendRow(role, bubbleHtml) {
  const isUser = role === "user";
  const row = document.createElement("div");
  row.className = `msg-row ${isUser ? "msg-user" : "msg-bot"}`;
  const avatar = `<div class="avatar ${isUser ? "avatar-user" : "avatar-bot"}" aria-hidden="true">${isUser ? "我" : "AI"}</div>`;
  const bubble = `<div class="bubble">${bubbleHtml}</div>`;
  row.innerHTML = isUser ? `${bubble}${avatar}` : `${avatar}${bubble}`;
  chatLog.appendChild(row);
  scrollToBottom();
  return row;
}

function appendUser(text) {
  appendRow("user", `<p>${escapeHtml(text)}</p>`);
}

let _thinkingRow = null; // track the bot bubble that currently has a spinner

function appendBot(content, { isError = false, isSuccess = false, thinking = false } = {}) {
  // Remove spinner from previous thinking message
  if (_thinkingRow) {
    const s = _thinkingRow.querySelector('.spinner');
    if (s) s.remove();
    _thinkingRow = null;
  }

  let html;
  if (isSuccess) {
    html = `<p><span class="success-prefix">✓ 执行成功！</span> ${escapeHtml(content)}</p>`;
  } else {
    html = botParagraphHtml(content, isError ? "error-text" : "");
  }

  const bubbleHtml = thinking ? html + '<span class="spinner"></span>' : html;
  const row = appendRow("bot", bubbleHtml);

  if (thinking) {
    _thinkingRow = row;
  }
}

async function requestJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("服務版本過舊，請在終端 Ctrl+C 停止後重新運行 web_app.py，再 Ctrl+F5 刷新頁面");
  }
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.error || "請求失敗");
  }
  return data;
}

async function refreshStatus() {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    const response = await fetch("/api/status", { signal: controller.signal });
    clearTimeout(timer);
    const data = await response.json();
    _consecutiveFailures = 0;
    _lastKnownBackendOk = true;
    if (data.ok && !busy) {
      if (data.alarm) {
        setStatus("报警");
        alarmBanner.style.display = "flex";
      } else {
        setStatus(data.connected ? "已就绪" : "未连接");
        alarmBanner.style.display = "none";
      }
    }
  } catch (_) {
    // 靜默處理：偶爾超時不影響實際使用，狀態等下次輪詢自動恢復
  }
}

async function sendAndExecute() {
  const text = commandInput.value.trim();
  if (!text || busy) return;

  setBusy(true);
  appendUser(text);
  commandInput.value = "";
  commandInput.style.height = "auto";

  try {
    // 階段一：理解中（帶旋轉指示器）
    setStatus("分析中");
    appendBot("正在理解您的需求，請稍候", { thinking: true });

    const planData = await requestJson("/api/plan", { text });
    const skill = planData.validated_plan?.skill || planData.plan?.skill;

    // 階段二：已理解，展示動作摘要
    appendBot(planData.message);

    // 階段三：執行 / 讀取（帶旋轉指示器）
    setStatus("執行中");
    const executingMsg =
      skill === "read_pose" ? "正在讀取當前位姿" : "正在控制機器人運動";
    appendBot(executingMsg, { thinking: true });

    const result = await requestJson("/api/run-once", { text, plan: planData.plan });

    // 完成：讀位姿展示座標，運動類展示執行成功
    const doneMsg = result.message || (skill === "read_pose" ? "位姿讀取完成" : "動作已完成");
    appendBot(doneMsg, { isSuccess: skill !== "read_pose" });
    setStatus("已就緒");
  } catch (error) {
    appendBot(error.message || "無法執行該動作，請換一種說法", { isError: true });
    setStatus("錯誤");
  } finally {
    setBusy(false);
  }
}

executeBtn.addEventListener("click", sendAndExecute);

commandInput.addEventListener("input", () => {
  commandInput.style.height = "auto";
  commandInput.style.height = `${Math.min(commandInput.scrollHeight, 120)}px`;
});

commandInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendAndExecute();
  }
});

refreshStatus();
setInterval(refreshStatus, 5000);

/* ── Clear Alarm ── */
const _clearAlarmHandler = async () => {
  if (busy) return;
  setBusy(true);
  try {
    const res = await fetch("/api/clear-alarm", { method: "POST" });
    const data = await res.json();
    if (data.ok) {
      appendBot("報警已清除", { isSuccess: true });
      alarmBanner.style.display = "none";
      setStatus("已就緒");
    } else {
      appendBot(data.error || "清除報警失敗", { isError: true });
    }
  } catch (e) {
    appendBot("清除報警失敗: 無法連接後端", { isError: true });
  } finally {
    setBusy(false);
  }
};
document.getElementById("clearAlarmBtn").addEventListener("click", _clearAlarmHandler);
const bannerBtn = document.getElementById("clearAlarmBannerBtn");
if (bannerBtn) bannerBtn.addEventListener("click", _clearAlarmHandler);

/* ── Speech Recognition ── */
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const micBtn = document.getElementById("micBtn");
let isListening = false;

if (!SpeechRecognition) {
  micBtn.style.display = "none";
} else {
  micBtn.addEventListener("click", toggleSpeech);
}

function toggleSpeech() {
  if (isListening) {
    stopListening();
    return;
  }
  startListening();
}

function startListening() {
  if (busy) return;
  const recognition = new SpeechRecognition();
  recognition.lang = "zh-CN";
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  isListening = true;
  micBtn.classList.add("listening");
  micBtn.title = "點擊停止錄音";

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    commandInput.value = transcript;
    commandInput.style.height = "auto";
    commandInput.style.height = `${Math.min(commandInput.scrollHeight, 120)}px`;
    commandInput.focus();
  };

  recognition.onerror = (event) => {
    if (event.error === "not-allowed") {
      appendBot("麥克風權限被拒絕，請在瀏覽器設置中允許麥克風訪問", { isError: true });
    } else if (event.error === "no-speech") {
      // silent, just reset
    } else {
      console.warn("語音識別錯誤:", event.error);
    }
    stopListening();
  };

  recognition.onend = () => {
    stopListening();
  };

  try {
    recognition.start();
  } catch (e) {
    stopListening();
  }

  // Store recognition instance for manual stop
  micBtn._recognition = recognition;
}

function stopListening() {
  isListening = false;
  micBtn.classList.remove("listening");
  micBtn.title = "語音輸入";
  if (micBtn._recognition) {
    try { micBtn._recognition.stop(); } catch (_) {}
    micBtn._recognition = null;
  }
}

// Also stop listening when busy state changes via setBusy
const _origSetBusy = setBusy;
setBusy = function (nextBusy) {
  _origSetBusy(nextBusy);
  if (nextBusy && isListening) {
    stopListening();
  }
  micBtn.disabled = nextBusy;
};

/* ══════════════ 页面导航（主页 / 子页面） ══════════════ */

const homeViewEl = document.getElementById("homeView");
const appShellEl = document.getElementById("appShell");
const pageNameEl = document.getElementById("pageName");
const views = {
  chat: document.getElementById("chatView"),
  script: document.getElementById("scriptView"),
};
const VIEW_TITLES = { chat: "对话控制", script: "脚本编程" };

function switchToView(view) {
  if (!view || !views[view]) return;
  homeViewEl.classList.add("fade-out");
  appShellEl.style.display = "flex";
  appShellEl.classList.add("fade-in");

  setTimeout(() => {
    homeViewEl.style.display = "none";
    homeViewEl.classList.remove("fade-out");
  }, 350);

  Object.entries(views).forEach(([key, el]) => {
    el.style.display = key === view ? "flex" : "none";
  });
  pageNameEl.textContent = VIEW_TITLES[view] || "";
  if (view === "script") loadProgramList();
}

function goHome() {
  appShellEl.classList.add("fade-out");
  homeViewEl.style.display = "flex";
  homeViewEl.classList.add("fade-in");

  setTimeout(() => {
    appShellEl.style.display = "none";
    appShellEl.classList.remove("fade-out");
    homeViewEl.classList.remove("fade-in");
  }, 300);
}

/* Card click handlers */
document.querySelectorAll(".home-card").forEach((card) => {
  card.addEventListener("click", () => {
    const view = card.dataset.view;
    if (view) switchToView(view);
  });
});

/* Home button (logo) click */
document.getElementById("homeBtn").addEventListener("click", goHome);

/* ── 簡易提示 toast ── */
function toast(message, type = "info") {
  let box = document.getElementById("toastBox");
  if (!box) {
    box = document.createElement("div");
    box.id = "toastBox";
    box.style.cssText =
      "position:fixed;left:50%;bottom:90px;transform:translateX(-50%);z-index:9999;display:flex;flex-direction:column;gap:8px;align-items:center;pointer-events:none";
    document.body.appendChild(box);
  }
  const el = document.createElement("div");
  const color = type === "error" ? "#e57373" : type === "success" ? "#4caf50" : "#333";
  el.style.cssText =
    `pointer-events:auto;background:#fff;color:${color};border:1px solid ${color};border-radius:10px;padding:10px 16px;font-size:0.88rem;box-shadow:0 4px 16px rgba(0,0,0,0.12);max-width:80vw`;
  el.textContent = message;
  box.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

/* ── 腳本程序狀態 ── */
const program = { name: "", points: [], instructions: [] };

const instructionList = document.getElementById("instructionList");
const pointList = document.getElementById("pointList");
const instrEmptyHint = document.getElementById("instrEmptyHint");
const pointEmptyHint = document.getElementById("pointEmptyHint");
const programSelect = document.getElementById("programSelect");
const programNameInput = document.getElementById("programName");
const scriptInput = document.getElementById("scriptInput");

function nextPointId() {
  let max = 0;
  for (const p of program.points) {
    const m = /^P(\d+)$/.exec(p.id);
    if (m) max = Math.max(max, Number(m[1]));
  }
  return "P" + (max + 1);
}

function stripCondPrefix(text) {
  return text.replace(/^當 DI\d+ 為 (ON|OFF) 時，/, "").replace(/^当 DI\d+ 为 (ON|OFF) 时，/, "");
}

function applyCondText(inst) {
  const base = stripCondPrefix(inst.text || "");
  inst.text = inst.condition
    ? `當 DI${inst.condition.di} 為 ${inst.condition.state} 時，${base}`
    : base;
}

function renderInstructions() {
  instructionList.innerHTML = "";
  instrEmptyHint.classList.toggle("hidden", program.instructions.length > 0);
  program.instructions.forEach((inst, idx) => {
    const li = document.createElement("li");
    li.className = "instruction-item" + (inst.condition ? " has-condition" : "");
    li.innerHTML =
      `<span class="instr-index">${idx + 1}</span>` +
      `<span class="instr-text">${escapeHtml(inst.text || inst.skill)}</span>` +
      `<span class="instr-actions">` +
      `<button class="icon-btn" data-act="up" title="上移">↑</button>` +
      `<button class="icon-btn" data-act="down" title="下移">↓</button>` +
      `<button class="icon-btn" data-act="cond" title="編輯條件">⚙</button>` +
      `<button class="icon-btn danger" data-act="del" title="刪除">✕</button>` +
      `</span>`;
    li.querySelectorAll(".icon-btn").forEach((b) => {
      b.addEventListener("click", () => instructionAction(idx, b.dataset.act));
    });
    instructionList.appendChild(li);
  });
}

function instructionAction(idx, act) {
  if (act === "del") {
    program.instructions.splice(idx, 1);
  } else if (act === "up" && idx > 0) {
    [program.instructions[idx - 1], program.instructions[idx]] = [program.instructions[idx], program.instructions[idx - 1]];
  } else if (act === "down" && idx < program.instructions.length - 1) {
    [program.instructions[idx + 1], program.instructions[idx]] = [program.instructions[idx], program.instructions[idx + 1]];
  } else if (act === "cond") {
    const inst = program.instructions[idx];
    const cur = inst.condition ? String(inst.condition.di) : "";
    const di = prompt("輸入 DI 編號（留空表示無條件）", cur);
    if (di === null) return;
    if (di.trim() === "") {
      inst.condition = null;
    } else {
      const st = prompt("狀態 ON / OFF", inst.condition ? inst.condition.state : "ON");
      if (st === null) return;
      inst.condition = { di: Number(di), state: String(st).trim().toUpperCase() === "OFF" ? "OFF" : "ON" };
    }
    applyCondText(inst);
  }
  renderInstructions();
}

function renderPoints() {
  pointList.innerHTML = "";
  pointEmptyHint.classList.toggle("hidden", program.points.length > 0);
  program.points.forEach((p, idx) => {
    const li = document.createElement("li");
    li.className = "point-item";
    const coords = p.pose.map((v) => Number(v).toFixed(1)).join(", ");
    li.innerHTML =
      `<div class="point-row"><span class="point-id">${escapeHtml(p.id)}</span>` +
      `<span class="point-actions">` +
      `<button class="tool-btn small" data-act="update">修改</button>` +
      `<button class="tool-btn small" data-act="del">刪除</button>` +
      `</span></div>` +
      `<div class="point-coords">${coords}</div>`;
    li.querySelector('[data-act="update"]').addEventListener("click", () => updatePoint(idx));
    li.querySelector('[data-act="del"]').addEventListener("click", () => {
      program.points.splice(idx, 1);
      renderPoints();
    });
    pointList.appendChild(li);
  });
}

async function capturePose() {
  const res = await fetch("/api/capture-pose", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "讀取位置失敗");
  return data.pose;
}

document.getElementById("addPointBtn").addEventListener("click", async () => {
  try {
    setStatus("執行中");
    const pose = await capturePose();
    program.points.push({ id: nextPointId(), pose });
    renderPoints();
    setStatus("已就緒");
    toast("已添加 " + program.points[program.points.length - 1].id, "success");
  } catch (e) {
    setStatus("錯誤");
    toast(e.message, "error");
  }
});

async function updatePoint(idx) {
  try {
    setStatus("執行中");
    const pose = await capturePose();
    program.points[idx].pose = pose;
    renderPoints();
    setStatus("已就緒");
    toast("已更新 " + program.points[idx].id, "success");
  } catch (e) {
    setStatus("錯誤");
    toast(e.message, "error");
  }
}

/* ── 解析並插入指令 ── */
async function addScriptInstruction() {
  const text = scriptInput.value.trim();
  if (!text) return;
  try {
    const data = await requestJson("/api/script/plan", { text });
    (data.instructions || []).forEach((inst) => program.instructions.push(inst));
    scriptInput.value = "";
    scriptInput.style.height = "auto";
    renderInstructions();
  } catch (e) {
    toast(e.message || "無法識別該指令", "error");
  }
}

document.getElementById("scriptAddBtn").addEventListener("click", addScriptInstruction);
scriptInput.addEventListener("input", () => {
  scriptInput.style.height = "auto";
  scriptInput.style.height = `${Math.min(scriptInput.scrollHeight, 120)}px`;
});
scriptInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    addScriptInstruction();
  }
});

/* ── 程序 CRUD ── */
async function loadProgramList() {
  try {
    const res = await fetch("/api/programs");
    const data = await res.json();
    if (!data.ok) return;
    const current = programSelect.value;
    programSelect.innerHTML = '<option value="">— 選擇程序 —</option>';
    data.programs.forEach((name) => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      programSelect.appendChild(opt);
    });
    programSelect.value = current;
  } catch (_) {}
}

programSelect.addEventListener("change", async () => {
  const name = programSelect.value;
  if (!name) return;
  try {
    const res = await fetch(`/api/programs/${encodeURIComponent(name)}`);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "讀取失敗");
    loadProgramInto(data.program);
    toast("已載入程序：" + name, "success");
  } catch (e) {
    toast(e.message, "error");
  }
});

function loadProgramInto(p) {
  program.name = p.name || "";
  program.points = Array.isArray(p.points) ? p.points : [];
  program.instructions = Array.isArray(p.instructions) ? p.instructions : [];
  programNameInput.value = program.name;
  renderInstructions();
  renderPoints();
}

document.getElementById("newProgramBtn").addEventListener("click", () => {
  if (program.instructions.length || program.points.length) {
    if (!confirm("新建將清空當前編輯內容，確定嗎？")) return;
  }
  program.name = "";
  program.points = [];
  program.instructions = [];
  programNameInput.value = "";
  programSelect.value = "";
  renderInstructions();
  renderPoints();
});

document.getElementById("saveProgramBtn").addEventListener("click", () => saveProgram(false));

async function saveProgram(overwrite) {
  const name = programNameInput.value.trim();
  if (!name) {
    toast("請先輸入程序名稱", "error");
    return;
  }
  program.name = name;
  try {
    const res = await fetch(`/api/programs/${encodeURIComponent(name)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ points: program.points, instructions: program.instructions, overwrite }),
    });
    const data = await res.json();
    if (res.status === 409 && data.exists) {
      if (confirm(`程序「${name}」已存在，覆蓋保存？`)) saveProgram(true);
      return;
    }
    if (!res.ok || !data.ok) throw new Error(data.error || "保存失敗");
    toast("已保存：" + name, "success");
    loadProgramList();
    programSelect.value = name;
  } catch (e) {
    toast(e.message, "error");
  }
}

/* ── 導入（本地 JSON） ── */
const importFile = document.getElementById("importFile");
document.getElementById("importProgramBtn").addEventListener("click", () => importFile.click());
importFile.addEventListener("change", () => {
  const file = importFile.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const p = JSON.parse(reader.result);
      loadProgramInto(p);
      toast("已導入程序", "success");
    } catch (_) {
      toast("文件格式無效", "error");
    }
    importFile.value = "";
  };
  reader.readAsText(file, "utf-8");
});

/* ── 導出 Lua ── */
document.getElementById("exportLuaBtn").addEventListener("click", async () => {
  if (!program.instructions.length) {
    toast("程序為空，無可導出內容", "error");
    return;
  }
  try {
    const data = await requestJson("/api/export-lua", { program });
    const blob = new Blob([data.lua], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${program.name || "program"}.lua`;
    a.click();
    URL.revokeObjectURL(url);
    toast("已導出 Lua 文件", "success");
  } catch (e) {
    toast(e.message, "error");
  }
});

/* ── 運行程序 ── */
const runProgramBtn = document.getElementById("runProgramBtn");
runProgramBtn.addEventListener("click", async () => {
  if (busy) return;
  if (!program.instructions.length) {
    toast("程序為空，無法運行", "error");
    return;
  }
  setBusy(true);
  runProgramBtn.disabled = true;
  setStatus("執行中");
  try {
    const data = await requestJson("/api/run-program", { program });
    setStatus("已就緒");
    toast(data.message || "程序執行完成", "success");
  } catch (e) {
    setStatus("錯誤");
    toast(e.message || "執行失敗", "error");
  } finally {
    setBusy(false);
    runProgramBtn.disabled = false;
  }
});

/* ── 腳本模式語音輸入 ── */
const scriptMicBtn = document.getElementById("scriptMicBtn");
let scriptListening = false;

if (!SpeechRecognition) {
  scriptMicBtn.style.display = "none";
} else {
  scriptMicBtn.addEventListener("click", () => {
    if (scriptListening) {
      if (scriptMicBtn._recognition) {
        try { scriptMicBtn._recognition.stop(); } catch (_) {}
      }
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = "zh-CN";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    scriptListening = true;
    scriptMicBtn.classList.add("listening");
    recognition.onresult = (event) => {
      scriptInput.value = event.results[0][0].transcript;
      scriptInput.style.height = "auto";
      scriptInput.style.height = `${Math.min(scriptInput.scrollHeight, 120)}px`;
      scriptInput.focus();
    };
    recognition.onerror = (event) => {
      if (event.error === "not-allowed") toast("麥克風權限被拒絕", "error");
    };
    recognition.onend = () => {
      scriptListening = false;
      scriptMicBtn.classList.remove("listening");
      scriptMicBtn._recognition = null;
    };
    try { recognition.start(); } catch (_) { scriptListening = false; scriptMicBtn.classList.remove("listening"); }
    scriptMicBtn._recognition = recognition;
  });
}

/* ── Restart ── */
document.getElementById("restartBtn").addEventListener("click", async () => {
  if (busy) return;
  if (!confirm("確定要重啓服務嗎？會話將短暫中斷。")) return;
  try {
    setBusy(true);
    await fetch("/api/restart", { method: "POST" });
    appendBot("服務正在重啓，頁面將自動恢復...", { thinking: true });
    // 等待後端重啓後刷新頁面
    setTimeout(() => {
      window.location.reload();
    }, 3000);
  } catch (_) {
    // 重啓時 fetch 可能斷開，直接刷新頁面重連
    setTimeout(() => window.location.reload(), 1500);
  }
});

/* ═══════════════════════════════════════════════
   粒子系统（Canvas）
   ═══════════════════════════════════════════════ */

(function initParticles() {
  const canvas = document.getElementById("particleCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let w, h;
  const particles = [];
  const COUNT = 160;
  const CONNECT_DIST = 200;
  let mouseX = -9999, mouseY = -9999;

  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  }
  window.addEventListener("resize", resize);
  resize();

  for (let i = 0; i < COUNT; i++) {
    particles.push({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.4,
      vy: (Math.random() - 0.5) * 0.4,
      r: Math.random() * 7 + 3,
      alpha: Math.random() * 0.4 + 0.4,
    });
  }

  function animate() {
    ctx.clearRect(0, 0, w, h);

    for (const p of particles) {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0) p.x = w;
      if (p.x > w) p.x = 0;
      if (p.y < 0) p.y = h;
      if (p.y > h) p.y = 0;

      // 鼠标排斥效果
      const dx = p.x - mouseX;
      const dy = p.y - mouseY;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 100) {
        p.x += dx * 0.02;
        p.y += dy * 0.02;
      }

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(0, 180, 216, ${p.alpha})`;
      ctx.fill();
    }

    // 粒子连线
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < CONNECT_DIST) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(0, 180, 216, ${0.12 * (1 - dist / CONNECT_DIST)})`;
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }
      }
    }

    requestAnimationFrame(animate);
  }

  canvas.addEventListener("mousemove", (e) => {
    mouseX = e.clientX;
    mouseY = e.clientY;
  });
  canvas.addEventListener("mouseleave", () => {
    mouseX = -9999;
    mouseY = -9999;
  });

  animate();
})();

/* ═══════════════════════════════════════════════
   标题打字机效果
   ═══════════════════════════════════════════════ */

(function typewriter() {
  const titleEl = document.getElementById("mainTitle");
  const subtitleEl = document.getElementById("subtitle");
  if (!titleEl || !subtitleEl) return;

  const titleText = "COBOT AI 智能协作系统";
  const subtitleText = "领志科技 · 智造未来";
  let charIndex = 0;

  titleEl.textContent = "";
  subtitleEl.textContent = "";
  subtitleEl.style.visibility = "hidden";

  function typeTitle() {
    if (charIndex < titleText.length) {
      titleEl.textContent += titleText[charIndex];
      charIndex++;
      setTimeout(typeTitle, 60 + Math.random() * 40);
    } else {
      subtitleEl.style.visibility = "visible";
      charIndex = 0;
      typeSubtitle();
    }
  }

  function typeSubtitle() {
    if (charIndex < subtitleText.length) {
      subtitleEl.textContent += subtitleText[charIndex];
      charIndex++;
      setTimeout(typeSubtitle, 80 + Math.random() * 30);
    }
  }

  setTimeout(typeTitle, 400);
})();

/* ═══════════════════════════════════════════════
   点动控制（Jog）
   ═══════════════════════════════════════════════ */
(function initJog() {
  const jogToggleBtn = document.getElementById("jogToggleBtn");
  const jogOverlay = document.getElementById("jogOverlay");
  const jogCloseBtn = document.getElementById("jogCloseBtn");
  const jogStopAllBtn = document.getElementById("jogStopAllBtn");
  const jogSpeed = document.getElementById("jogSpeed");
  const jogSpeedVal = document.getElementById("jogSpeedVal");
  const modeTabs = document.querySelectorAll(".jog-mode-tab");
  const jogCartesian = document.getElementById("jogCartesian");
  const jogJoint = document.getElementById("jogJoint");
  const jogBtns = document.querySelectorAll(".jog-btn[data-axis]");
  let _jogActive = false;

  if (!jogToggleBtn || !jogOverlay) return;

  // 打开/关闭面板
  jogToggleBtn.addEventListener("click", () => {
    jogOverlay.style.display = "block";
  });

  jogCloseBtn.addEventListener("click", closeJog);
  jogOverlay.addEventListener("click", (e) => {
    if (e.target === jogOverlay) closeJog();
  });

  function closeJog() {
    jogOverlay.style.display = "none";
    stopAllJog();
  }

  // 模式切换
  modeTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      modeTabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      const mode = tab.dataset.mode;
      jogCartesian.style.display = mode === "cartesian" ? "" : "none";
      jogJoint.style.display = mode === "joint" ? "" : "none";
      // 切换模式时停止当前点动
      stopAllJog();
    });
  });

  // 速度滑块
  jogSpeed.addEventListener("input", () => {
    jogSpeedVal.textContent = jogSpeed.value;
  });

  // 点动按钮事件
  jogBtns.forEach((btn) => {
    const axisId = btn.dataset.axis;

    const startJog = async () => {
      if (_jogActive) return;
      _jogActive = true;
      btn.classList.add("active");
      try {
        await fetch("/api/jog/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ axis_id: axisId }),
        });
      } catch (_) {
        _jogActive = false;
        btn.classList.remove("active");
      }
    };

    const stopJog = async () => {
      if (!_jogActive) return;
      _jogActive = false;
      btn.classList.remove("active");
      try {
        await fetch("/api/jog/stop", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        });
      } catch (_) {}
    };

    btn.addEventListener("mousedown", startJog);
    btn.addEventListener("mouseup", stopJog);
    btn.addEventListener("mouseleave", stopJog);
    btn.addEventListener("touchstart", (e) => {
      e.preventDefault();
      startJog();
    });
    btn.addEventListener("touchend", (e) => {
      e.preventDefault();
      stopJog();
    });
    btn.addEventListener("touchcancel", (e) => {
      e.preventDefault();
      stopJog();
    });
  });

  // 紧急停止
  jogStopAllBtn.addEventListener("click", stopAllJog);

  function stopAllJog() {
    if (!_jogActive) return;
    _jogActive = false;
    document.querySelectorAll(".jog-btn.active").forEach((b) => b.classList.remove("active"));
    fetch("/api/jog/stop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    }).catch(() => {});
  }

  // 页面关闭/离开时自动停止
  window.addEventListener("beforeunload", () => {
    navigator.sendBeacon("/api/jog/stop", "{}");
  });
})();

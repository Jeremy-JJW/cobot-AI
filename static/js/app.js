const chatLog = document.getElementById("chatLog");
const commandInput = document.getElementById("commandInput");
const executeBtn = document.getElementById("executeBtn");
const statusPill = document.getElementById("statusPill");
const statusText = document.getElementById("statusText");
const alarmBanner = document.getElementById("alarmBanner");

let busy = false;

const STATUS_CLASS = {
  "未連接": "idle",
  "已就緒": "ready",
  "分析中": "planning",
  "執行中": "executing",
  "錯誤": "error",
  "報警": "error",
};

function setStatus(status) {
  statusText.textContent = status;
  statusPill.className = "status-pill " + (STATUS_CLASS[status] || "idle");
}

function setBusy(nextBusy) {
  busy = nextBusy;
  executeBtn.disabled = nextBusy;
  commandInput.disabled = nextBusy;
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
    html = `<p><span class="success-prefix">✓ 執行成功！</span> ${escapeHtml(content)}</p>`;
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
    window._lastKnownBackendOk = true;
    if (data.ok && !busy) {
      if (data.alarm) {
        setStatus("報警");
        alarmBanner.style.display = "flex";
      } else {
        setStatus(data.connected ? "已就緒" : "未連接");
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
document.getElementById("clearAlarmBtn").addEventListener("click", async () => {
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
});

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
  recognition.lang = "zh-TW";
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

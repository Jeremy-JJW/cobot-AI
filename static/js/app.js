const chatLog = document.getElementById("chatLog");
const commandInput = document.getElementById("commandInput");
const executeBtn = document.getElementById("executeBtn");
const statusPill = document.getElementById("statusPill");
const statusText = document.getElementById("statusText");
const alarmBanner = document.getElementById("alarmBanner");

let busy = false;

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
    throw new Error("服务版本过旧，请在终端 Ctrl+C 停止后重新运行 web_app.py，再 Ctrl+F5 刷新页面");
  }
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.error || "请求失败");
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
        setStatus("报警");
        alarmBanner.style.display = "flex";
      } else {
        setStatus(data.connected ? "已就绪" : "未连接");
        alarmBanner.style.display = "none";
      }
    }
  } catch (_) {
    // 静默处理：偶尔超时不影响实际使用，状态等下次轮询自动恢复
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
    // 阶段一：理解中（带旋转指示器）
    setStatus("分析中");
    appendBot("正在理解您的需求，请稍候", { thinking: true });

    const planData = await requestJson("/api/plan", { text });
    const skill = planData.validated_plan?.skill || planData.plan?.skill;

    // 阶段二：已理解，展示动作摘要
    appendBot(planData.message);

    // 阶段三：执行 / 读取（带旋转指示器）
    setStatus("执行中");
    const executingMsg =
      skill === "read_pose" ? "正在读取当前位姿" : "正在控制机器人运动";
    appendBot(executingMsg, { thinking: true });

    const result = await requestJson("/api/run-once", { text, plan: planData.plan });

    // 完成：读位姿展示坐标，运动类展示执行成功
    const doneMsg = result.message || (skill === "read_pose" ? "位姿读取完成" : "动作已完成");
    appendBot(doneMsg, { isSuccess: skill !== "read_pose" });
    setStatus("已就绪");
  } catch (error) {
    appendBot(error.message || "无法执行该动作，请换一种说法", { isError: true });
    setStatus("错误");
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
      appendBot("报警已清除", { isSuccess: true });
      alarmBanner.style.display = "none";
      setStatus("已就绪");
    } else {
      appendBot(data.error || "清除报警失败", { isError: true });
    }
  } catch (e) {
    appendBot("清除报警失败: 无法连接后端", { isError: true });
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
  recognition.lang = "zh-CN";
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  isListening = true;
  micBtn.classList.add("listening");
  micBtn.title = "点击停止录音";

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    commandInput.value = transcript;
    commandInput.style.height = "auto";
    commandInput.style.height = `${Math.min(commandInput.scrollHeight, 120)}px`;
    commandInput.focus();
  };

  recognition.onerror = (event) => {
    if (event.error === "not-allowed") {
      appendBot("麦克风权限被拒绝，请在浏览器设置中允许麦克风访问", { isError: true });
    } else if (event.error === "no-speech") {
      // silent, just reset
    } else {
      console.warn("语音识别错误:", event.error);
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
  micBtn.title = "语音输入";
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
  if (!confirm("确定要重启服务吗？会话将短暂中断。")) return;
  try {
    setBusy(true);
    await fetch("/api/restart", { method: "POST" });
    appendBot("服务正在重启，页面将自动恢复...", { thinking: true });
    // 等待后端重启后刷新页面
    setTimeout(() => {
      window.location.reload();
    }, 3000);
  } catch (_) {
    // 重启时 fetch 可能断开，直接刷新页面重连
    setTimeout(() => window.location.reload(), 1500);
  }
});

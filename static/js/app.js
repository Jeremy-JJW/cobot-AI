const chatLog = document.getElementById("chatLog");
const commandInput = document.getElementById("commandInput");
const executeBtn = document.getElementById("executeBtn");
const statusPill = document.getElementById("statusPill");
const statusText = document.getElementById("statusText");

let busy = false;

const STATUS_CLASS = {
  "未连接": "idle",
  "已就绪": "ready",
  "分析中": "planning",
  "执行中": "executing",
  "错误": "error",
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

let _backendDown = false;
let _consecutiveFailures = 0;

async function refreshStatus() {
  try {
    const response = await fetch("/api/status");
    const data = await response.json();
    _consecutiveFailures = 0;
    if (_backendDown) {
      _backendDown = false;
      appendBot("后端服务已恢复连接");
    }
    if (data.ok && !busy) {
      setStatus(data.connected ? "已就绪" : "未连接");
    }
  } catch (_) {
    _consecutiveFailures++;
    // 连续 2 次（约 10 秒）连不上再提示，避免误报
    if (_consecutiveFailures >= 2 && !_backendDown) {
      _backendDown = true;
      setStatus("未连接");
      appendBot(
        "无法连接到后端服务，请确认已启动 web_app.py\n" +
        "启动命令：.venv\\Scripts\\python web_app.py",
        { isError: true }
      );
    }
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

    // 阶段二：已理解，展示动作摘要
    appendBot(planData.message);

    // 阶段三：执行中（带旋转指示器）
    setStatus("执行中");
    appendBot("正在控制机器人运动", { thinking: true });

    const result = await requestJson("/api/run-once", { text, plan: planData.plan });

    // 完成
    appendBot(result.message || "动作已完成", { isSuccess: true });
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

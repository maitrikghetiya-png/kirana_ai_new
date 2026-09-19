// KiranaAI Frontend Client
document.addEventListener("DOMContentLoaded", () => {

  const API_BASE = "https://6plsoyd4sk.execute-api.ap-south-1.amazonaws.com";
  const chatForm = document.getElementById("chat-form");
  const userInput = document.getElementById("user-input");
  const chatMessages = document.getElementById("chat-messages");
  const sendBtn = document.getElementById("send-btn");
  const resetBtn = document.getElementById("reset-btn");
  const stepCards = document.querySelectorAll(".step-card");
  const navTotalAmount = document.getElementById("nav-total-amount");
  const ledgerTotalAmount = document.getElementById("ledger-total-amount");
  const ledgerCustomerCount = document.getElementById("ledger-customer-count");
  const mobileKhataBal = document.getElementById("mobile-khata-bal");
  const customersList = document.getElementById("customers-list");
  const mobileLedgerBtn = document.getElementById("mobile-ledger-btn");
  const ledgerPane = document.getElementById("ledger-pane");
  const autoReminderBtn = document.getElementById("auto-reminder-btn");
  const micBtn = document.getElementById("mic-btn");

  // ── Voice Input (Web Speech API) ──────────────────────────────────────────
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let isListening = false;

  if (!SpeechRecognition) {
    // Browser doesn't support speech — hide the mic button gracefully
    if (micBtn) micBtn.style.display = "none";
  } else {
    recognition = new SpeechRecognition();
    recognition.lang = "hi-IN";          // Hindi/Hinglish primary
    recognition.interimResults = true;   // Show live partial transcript
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      isListening = true;
      micBtn.classList.add("listening");
      userInput.placeholder = "🎤 Bol raha hai... (bolo Hinglish mein)";
    };

    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map(r => r[0].transcript)
        .join("");
      userInput.value = transcript;
      // If the result is final, auto-submit
      if (event.results[event.results.length - 1].isFinal) {
        recognition.stop();
      }
    };

    recognition.onend = () => {
      isListening = false;
      micBtn.classList.remove("listening");
      userInput.placeholder = "Jaise: Ramesh liya 500 doodh ya Kaun paisa dena hai...";
      // Auto-send if there's a transcribed value
      const val = userInput.value.trim();
      if (val) {
        sendMessage(val);
        userInput.value = "";
      }
    };

    recognition.onerror = (event) => {
      isListening = false;
      micBtn.classList.remove("listening");
      userInput.placeholder = "Jaise: Ramesh liya 500 doodh ya Kaun paisa dena hai...";
      if (event.error !== "aborted") {
        appendBotMessage(`🎤 Voice error: ${event.error}. Please type your message instead.`, null);
      }
    };

    micBtn.addEventListener("click", () => {
      if (isListening) {
        recognition.abort();
      } else {
        userInput.value = "";
        recognition.start();
      }
    });
  }
  // ─────────────────────────────────────────────────────────────────────────

  let currentStep = 1;

  // Initial load
  loadDues();

  // Autonomous EventBridge Reminder Trigger button
  if (autoReminderBtn) {
    autoReminderBtn.addEventListener("click", async () => {
      autoReminderBtn.disabled = true;
      autoReminderBtn.style.opacity = "0.6";
      try {
        const resp = await fetch(`${API_BASE}/api/reminders/trigger`, { method: "POST" });
        const data = await resp.json();
        appendAutonomousMessage(data);

        if (data.ledger) {
          renderLedger(data.ledger.customers, data.ledger.total_outstanding);
        } else {
          loadDues();
        }
      } catch (err) {
        appendBotMessage("Error running autonomous reminder: " + err.message, null);
      } finally {
        autoReminderBtn.disabled = false;
        autoReminderBtn.style.opacity = "1";
      }
    });
  }

  // Handle Demo Flow Stepper card clicks
  stepCards.forEach(card => {
    card.addEventListener("click", () => {
      const step = parseInt(card.getAttribute("data-step"));
      const query = card.getAttribute("data-query");
      if (query) {
        currentStep = step;
        setActiveStep(step);
        sendMessage(query, step);
      }
    });
  });

  // Mobile ledger view toggle
  if (mobileLedgerBtn && ledgerPane) {
    mobileLedgerBtn.addEventListener("click", () => {
      ledgerPane.scrollIntoView({ behavior: "smooth" });
    });
  }

  // Handle chat form submit
  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const query = userInput.value.trim();
    if (query) {
      sendMessage(query);
    }
  });

  // Reset Demo button
  resetBtn.addEventListener("click", async () => {
    if (!confirm("Reset all customer udhaar records to fresh state?")) return;
    try {
      await fetch(`${API_BASE}/api/reset`, { method: "POST" });
      currentStep = 1;
      setActiveStep(1);
      stepCards.forEach(c => c.classList.remove("completed"));
      appendBotMessage("🔄 Khata reset! Sabhi udhaar records saaf ho gaye. Step 1 'Add Credit' dabakar shuru karein.", null);
      loadDues();
    } catch (err) {
      console.error("Reset error:", err);
    }
  });

  async function sendMessage(text, fromStep = null) {
    appendUserMessage(text);
    userInput.value = "";
    userInput.disabled = true;
    sendBtn.disabled = true;

    const thinkingId = appendThinkingMessage();

    try {
      const resp = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text })
      });
      const data = await resp.json();
      removeThinkingMessage(thinkingId);

      appendBotMessage(data.response, data.tool_called);

      // Advance guided demo stepper
      if (fromStep !== null) {
        markStepCompleted(fromStep);
        if (fromStep < 4) {
          currentStep = fromStep + 1;
          setActiveStep(currentStep);
        }
      }

      // Sync ledger data
      if (data.ledger) {
        renderLedger(data.ledger.customers, data.ledger.total_outstanding);
      } else {
        loadDues();
      }
    } catch (err) {
      removeThinkingMessage(thinkingId);
      appendBotMessage("Error connecting to KiranaAI agent: " + err.message, null);
    } finally {
      userInput.disabled = false;
      sendBtn.disabled = false;
      userInput.focus();
    }
  }

  function setActiveStep(stepNum) {
    stepCards.forEach(card => {
      const step = parseInt(card.getAttribute("data-step"));
      if (step === stepNum) {
        card.classList.add("active");
      } else {
        card.classList.remove("active");
      }
    });
  }

  function markStepCompleted(stepNum) {
    const card = document.getElementById(`step-${stepNum}`);
    if (card) {
      card.classList.add("completed");
    }
  }

  async function loadDues() {
    try {
      const res = await fetch(`${API_BASE}/api/dues`);
      const data = await res.json();
      renderLedger(data.customers, data.total_outstanding);
    } catch (err) {
      console.error("Failed to load dues:", err);
    }
  }

  function renderLedger(customers, total) {
    const totalFormatted = `₹${(total || 0).toLocaleString("en-IN")}`;
    if (navTotalAmount) navTotalAmount.textContent = totalFormatted;
    if (ledgerTotalAmount) ledgerTotalAmount.textContent = totalFormatted;
    if (mobileKhataBal) mobileKhataBal.textContent = totalFormatted;

    const pendingCount = (customers || []).filter(c => (c.balance || 0) > 0).length;
    if (ledgerCustomerCount) {
      ledgerCustomerCount.textContent = `${pendingCount} customer${pendingCount === 1 ? '' : 's'} with pending dues`;
    }

    if (!customers || customers.length === 0) {
      customersList.innerHTML = `
        <div class="empty-ledger-state">
          <div class="empty-icon">📝</div>
          <p>Khata bilkul saaf hai!</p>
          <small>Step 1 dabakar "Ramesh liya 500 doodh" test karein.</small>
        </div>
      `;
      return;
    }

    customersList.innerHTML = "";
    customers.forEach(c => {
      const item = document.createElement("div");
      item.className = "customer-item";
      const initial = c.customer_name ? c.customer_name[0].toUpperCase() : "C";
      const isCleared = (c.balance || 0) <= 0;
      const balDisplay = isCleared ? "₹0 (Cleared)" : `₹${c.balance.toLocaleString("en-IN")}`;
      const phoneDisplay = c.phone ? `📞 +91 ${c.phone}` : "+ Add Phone";
      const waBtn = (!isCleared && c.whatsapp_url) ? `
        <a href="${c.whatsapp_url}" target="_blank" class="btn-whatsapp-sm" title="Send WhatsApp Reminder">
          💬 WhatsApp
        </a>
      ` : "";

      item.innerHTML = `
        <div class="cust-details">
          <div class="cust-initial">${initial}</div>
          <div>
            <span class="cust-title">${escapeHtml(c.customer_name)}</span>
            <div class="cust-phone-sub">
              <button class="btn-edit-phone" data-name="${escapeHtml(c.customer_name)}" data-phone="${escapeHtml(c.phone || '')}">
                ${phoneDisplay}
              </button>
            </div>
          </div>
        </div>
        <div class="cust-actions-group">
          <div class="cust-balance-badge ${isCleared ? 'cleared' : ''}">${balDisplay}</div>
          ${waBtn}
        </div>
      `;
      customersList.appendChild(item);
    });

    // Handle Edit Phone button clicks
    document.querySelectorAll(".btn-edit-phone").forEach(btn => {
      btn.addEventListener("click", async () => {
        const name = btn.getAttribute("data-name");
        const currentPhone = btn.getAttribute("data-phone") || "";
        const input = prompt(`Enter WhatsApp mobile number for ${name} (10 digits):`, currentPhone);
        if (input !== null && input.trim() !== "") {
          try {
            await fetch(`${API_BASE}/api/customer/phone`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ customer_name: name, phone: input.trim() })
            });
            loadDues();
          } catch (err) {
            alert("Could not update phone: " + err.message);
          }
        }
      });
    });
  }

  function appendUserMessage(text) {
    const row = document.createElement("div");
    row.className = "message-row user";
    row.innerHTML = `
      <div class="message-bubble">
        <div>${escapeHtml(text)}</div>
      </div>
    `;
    chatMessages.appendChild(row);
    scrollToBottom();
  }

  function appendBotMessage(text, toolName) {
    const row = document.createElement("div");
    row.className = "message-row bot";

    let toolBadgeHtml = "";
    if (toolName) {
      toolBadgeHtml = `<div class="tool-execution-pill">⚡ Tool executed: <code>${escapeHtml(toolName)}</code></div>`;
    }

    let bodyHtml = escapeHtml(text).replace(/\n/g, "<br>");
    
    // Extract WhatsApp URL if present
    const waMatch = text.match(/(https:\/\/(?:wa\.me|api\.whatsapp\.com)[^\s"']+)/);
    let waActionBtn = "";
    if (waMatch) {
      const waUrl = waMatch[1];
      waActionBtn = `
        <div>
          <a href="${waUrl}" target="_blank" class="btn-whatsapp-action">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12.031 6.172c-3.181 0-5.767 2.586-5.768 5.766-.001 1.298.38 2.27 1.019 3.287l-.711 2.598 2.664-.699c.983.54 1.777.817 2.796.817 3.182 0 5.768-2.587 5.769-5.768.001-3.18-2.585-5.767-5.769-5.767zm7.57 5.766c-.001 4.173-3.398 7.57-7.57 7.57-1.309 0-2.548-.342-3.633-.941l-4.041 1.06 1.079-3.94c-.663-1.127-1.025-2.427-1.025-3.749.001-4.174 3.399-7.571 7.57-7.571 4.172.001 7.57 3.398 7.57 7.571z"/>
            </svg>
            <span>📱 Send via WhatsApp (व्हाट्सएप पर भेजें)</span>
          </a>
        </div>
      `;
    }

    if (toolName === "send_reminder" || text.includes("Reminder for")) {
      bodyHtml = `<div class="reminder-box">${bodyHtml}${waActionBtn}</div>`;
    }

    row.innerHTML = `
      <div class="message-avatar">🏪</div>
      <div class="message-bubble">
        <div class="bubble-author">KiranaAI Munim</div>
        ${toolBadgeHtml}
        <div>${bodyHtml}</div>
      </div>
    `;
    chatMessages.appendChild(row);
    scrollToBottom();
  }

  function appendAutonomousMessage(data) {
    const row = document.createElement("div");
    row.className = "message-row bot";
    let bodyHtml = escapeHtml(data.reminder_output || "").replace(/\n/g, "<br>");
    const count = data.pending_count || 0;
    const countText = count > 0 ? `${count} customer(s) reminded` : "All settled";

    let waButtonsHtml = "";
    if (data.reminders && data.reminders.length > 0) {
      waButtonsHtml = `<div style="margin-top: 10px; display: flex; flex-wrap: wrap; gap: 8px;">`;
      data.reminders.forEach(r => {
        waButtonsHtml += `
          <a href="${r.whatsapp_url}" target="_blank" class="btn-whatsapp-action">
            <span>💬 Send WhatsApp to ${escapeHtml(r.customer_name)} (₹${r.balance})</span>
          </a>
        `;
      });
      waButtonsHtml += `</div>`;
    }

    row.innerHTML = `
      <div class="message-avatar">⏰</div>
      <div class="message-bubble">
        <div class="bubble-author">Autonomous Scheduler (EventBridge Engine)</div>
        <div class="tool-execution-pill">⚡ Tool executed: <code>send_reminder</code></div>
        <div class="autonomous-card">
          <div class="autonomous-card-head">
            <span>Scan: DynamoDB Ledger • ${countText}</span>
            <span class="autonomous-card-source">${escapeHtml(data.trigger_source || 'eventbridge.scheduler')}</span>
          </div>
          <div>${bodyHtml}</div>
          ${waButtonsHtml}
        </div>
      </div>
    `;
    chatMessages.appendChild(row);
    scrollToBottom();
  }

  function appendThinkingMessage() {
    const id = "think-" + Date.now();
    const row = document.createElement("div");
    row.id = id;
    row.className = "message-row bot";
    row.innerHTML = `
      <div class="message-avatar">🏪</div>
      <div class="message-bubble" style="color: var(--slate-500); font-style: italic;">
        KiranaAI hisaab jod raha hai...
      </div>
    `;
    chatMessages.appendChild(row);
    scrollToBottom();
    return id;
  }

  function removeThinkingMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
});

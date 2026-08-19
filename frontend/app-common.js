/* Funções compartilhadas entre admin.html e minhas-provas.html.
   Depende de elementos com estes IDs existirem na página:
   #report-modal, #report-title, #report-body, #report-close-btn */

async function api(path, options = {}) {
  const res = await fetch(path, { credentials: "include", ...options });
  let data = null;
  try { data = await res.json(); } catch (e) { /* sem corpo */ }
  return { ok: res.ok, status: res.status, data };
}

function showMsg(elId, kind, text, list) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.className = `msg show ${kind}`;
  let html = text;
  if (list && list.length) {
    html += "<ul>" + list.map(x => `<li>${x}</li>`).join("") + "</ul>";
  }
  el.innerHTML = html;
}

function pctClass(correct, total) {
  if (total === 0) return "";
  return (correct / total) * 100 >= 60 ? "good" : "bad";
}

async function copyShareLink(token, btnEl) {
  const url = `${location.origin}/simulado-interativo.html?token=${token}`;
  try {
    await navigator.clipboard.writeText(url);
    const original = btnEl.textContent;
    btnEl.textContent = t("copied");
    setTimeout(() => { btnEl.textContent = original; }, 1500);
  } catch (err) {
    prompt(t("copy_link_prompt"), url);
  }
}

async function openReport(examId, title) {
  const titleEl = document.getElementById("report-title");
  const bodyEl = document.getElementById("report-body");
  const modalEl = document.getElementById("report-modal");
  if (!titleEl || !bodyEl || !modalEl) return;

  titleEl.textContent = `${t("report_title")} — ${title}`;
  bodyEl.innerHTML = `<p>${t("loading")}</p>`;
  modalEl.classList.add("show");

  const res = await api(`/api/exams/${examId}/reports`);
  if (!res.ok || !res.data || !res.data.results || res.data.results.length === 0) {
    bodyEl.innerHTML = `<p>${t("report_no_attempts")}</p>`;
    return;
  }

  const categoryMap = new Map();
  res.data.results.forEach(r => r.by_category.forEach(c => categoryMap.set(c.category_id, c.category_name)));
  const categories = [...categoryMap.entries()];

  const header = `<tr><th>${t("th_person")}</th><th>${t("th_overall_score")}</th>${categories.map(([, name]) => `<th>${name}</th>`).join("")}<th>${t("th_when")}</th><th>${t("th_detail")}</th></tr>`;

  const rows = res.data.results.map(r => {
    const overallCls = pctClass(r.score, r.total);
    const catCells = categories.map(([cid]) => {
      const c = r.by_category.find(x => x.category_id === cid);
      if (!c) return "<td>—</td>";
      return `<td class="cell-pct ${pctClass(c.correct, c.total)}">${c.correct}/${c.total}</td>`;
    }).join("");
    const when = new Date(r.submitted_at).toLocaleDateString(dateLocale());
    const passTag = r.passed === true ? " ✓" : r.passed === false ? " ✗" : "";
    const lateTag = r.late ? ` (${t("late_tag")})` : "";
    return `<tr>
      <td>${r.user.name || r.user.email}</td>
      <td class="cell-pct ${overallCls}">${r.score}/${r.total}${passTag}${lateTag}</td>
      ${catCells}
      <td>${when}</td>
      <td class="actions"><button class="btn-secondary" data-attempt-id="${r.attempt_id}">${t("view_questions")}</button></td>
    </tr>`;
  }).join("");

  bodyEl.innerHTML = `<div class="table-scroll"><table><thead>${header}</thead><tbody>${rows}</tbody></table></div>`;
  bodyEl.querySelectorAll("button[data-attempt-id]").forEach(btn => {
    btn.addEventListener("click", () => openAttemptDetail(examId, btn.dataset.attemptId));
  });
}

/* Monta o texto plano de um relatório de tentativa — pensado pra colar
   direto numa IA e pedir um plano de estudo em cima do que foi errado. */
function attemptDetailToText(data) {
  const lines = [t("attempt_result_line", { score: data.score, total: data.total }), ""];
  data.questions.forEach((q, i) => {
    const correctOpt = q.options.find(o => o.is_correct);
    const chosenOpt = q.chosen_option_id !== null ? q.options.find(o => o.id === q.chosen_option_id) : null;
    const status = q.is_correct ? t("status_correct_caps") : (chosenOpt ? t("status_wrong_caps") : t("status_unanswered_caps"));
    lines.push(t("attempt_question_line", { n: i + 1, category: q.category_name, status }));
    lines.push(t("attempt_question_prefix", { text: q.question_text }));
    if (!q.is_correct && chosenOpt) {
      lines.push(t("attempt_your_answer", { label: chosenOpt.label, text: chosenOpt.option_text }));
    }
    if (correctOpt) lines.push(t("attempt_correct_answer", { label: correctOpt.label, text: correctOpt.option_text }));
    if (q.explanation) lines.push(t("attempt_explanation_line", { text: q.explanation }));
    lines.push("");
  });
  return lines.join("\n");
}

/* Mostra só a alternativa certa e, se errou, também a que foi escolhida —
   sem listar as outras alternativas, que não importam pro estudo. */
function renderAttemptDetailHTML(data) {
  return data.questions.map((q, i) => {
    const correctOpt = q.options.find(o => o.is_correct);
    const chosenOpt = q.chosen_option_id !== null ? q.options.find(o => o.id === q.chosen_option_id) : null;
    const statusText = q.is_correct ? t("status_correct") : (chosenOpt ? t("status_wrong") : t("status_unanswered"));

    let answerHtml = "";
    if (!q.is_correct && chosenOpt) {
      answerHtml += `<div class="opt-line is-chosen-wrong">${t("attempt_your_answer", { label: chosenOpt.label, text: chosenOpt.option_text })}</div>`;
    } else if (!q.is_correct && !chosenOpt) {
      answerHtml += `<div class="opt-line" style="font-style:italic;">${t("status_unanswered_plain")}</div>`;
    }
    if (correctOpt) {
      answerHtml += `<div class="opt-line is-correct">${t("attempt_correct_answer", { label: correctOpt.label, text: correctOpt.option_text })}</div>`;
    }

    return `
    <div class="detail-q">
      <div class="qnum">
        <span class="mark ${q.is_correct ? "right" : "wrong"}">${statusText}</span>
        <span style="text-transform:uppercase; font-size:.68rem; letter-spacing:.08em; color:var(--ink-soft);">
          ${t("question_label", { n: i + 1, category: q.category_name })}
        </span>
      </div>
      <div class="qtext">${q.question_text}</div>
      ${answerHtml}
      ${q.explanation ? `<div class="explain">${t("attempt_explanation_line", { text: q.explanation })}</div>` : ""}
    </div>`;
  }).join("");
}

let lastAttemptDetail = null;

async function openAttemptDetail(examId, attemptId) {
  const titleEl = document.getElementById("attempt-detail-title");
  const bodyEl = document.getElementById("attempt-detail-body");
  const modalEl = document.getElementById("attempt-detail-modal");
  if (!titleEl || !bodyEl || !modalEl) return;

  lastAttemptDetail = null;
  bodyEl.innerHTML = `<p>${t("loading")}</p>`;
  modalEl.classList.add("show");

  const res = await api(`/api/exams/${examId}/attempts/${attemptId}/detail`);
  if (!res.ok || !res.data) {
    bodyEl.innerHTML = `<p>${t("attempt_detail_load_failed")}</p>`;
    return;
  }

  lastAttemptDetail = res.data;
  titleEl.textContent = t("attempt_detail_title_with_score", { score: res.data.score, total: res.data.total });
  bodyEl.innerHTML = renderAttemptDetailHTML(res.data);
}

async function copyAttemptDetail(btnEl) {
  if (!lastAttemptDetail) return;
  const text = attemptDetailToText(lastAttemptDetail);
  try {
    await navigator.clipboard.writeText(text);
    const original = btnEl.textContent;
    btnEl.textContent = t("copied");
    setTimeout(() => { btnEl.textContent = original; }, 1500);
  } catch (err) {
    prompt(t("copy_report_prompt"), text);
  }
}

function initAttemptDetailModal() {
  const closeBtn = document.getElementById("attempt-detail-close-btn");
  const copyBtn = document.getElementById("attempt-detail-copy-btn");
  const overlay = document.getElementById("attempt-detail-modal");
  if (closeBtn) closeBtn.addEventListener("click", () => overlay.classList.remove("show"));
  if (copyBtn) copyBtn.addEventListener("click", () => copyAttemptDetail(copyBtn));
  if (overlay) overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.classList.remove("show"); });
}

function initReportModal() {
  const closeBtn = document.getElementById("report-close-btn");
  const overlay = document.getElementById("report-modal");
  if (closeBtn) closeBtn.addEventListener("click", () => overlay.classList.remove("show"));
}

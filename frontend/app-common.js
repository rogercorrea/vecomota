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
    btnEl.textContent = "Copiado!";
    setTimeout(() => { btnEl.textContent = original; }, 1500);
  } catch (err) {
    prompt("Copie o link:", url);
  }
}

async function openReport(examId, title) {
  const titleEl = document.getElementById("report-title");
  const bodyEl = document.getElementById("report-body");
  const modalEl = document.getElementById("report-modal");
  if (!titleEl || !bodyEl || !modalEl) return;

  titleEl.textContent = `Relatório — ${title}`;
  bodyEl.innerHTML = "<p>Carregando...</p>";
  modalEl.classList.add("show");

  const res = await api(`/api/exams/${examId}/reports`);
  if (!res.ok || !res.data || !res.data.results || res.data.results.length === 0) {
    bodyEl.innerHTML = "<p>Ainda não há tentativas finalizadas nessa prova.</p>";
    return;
  }

  const categoryMap = new Map();
  res.data.results.forEach(r => r.by_category.forEach(c => categoryMap.set(c.category_id, c.category_name)));
  const categories = [...categoryMap.entries()];

  const header = `<tr><th>Pessoa</th><th>Nota geral</th>${categories.map(([, name]) => `<th>${name}</th>`).join("")}<th>Quando</th></tr>`;

  const rows = res.data.results.map(r => {
    const overallCls = pctClass(r.score, r.total);
    const catCells = categories.map(([cid]) => {
      const c = r.by_category.find(x => x.category_id === cid);
      if (!c) return "<td>—</td>";
      return `<td class="cell-pct ${pctClass(c.correct, c.total)}">${c.correct}/${c.total}</td>`;
    }).join("");
    const when = new Date(r.submitted_at).toLocaleString("pt-BR");
    const passTag = r.passed === true ? " ✓" : r.passed === false ? " ✗" : "";
    const lateTag = r.late ? " (atrasado)" : "";
    return `<tr>
      <td>${r.user.name || r.user.email}</td>
      <td class="cell-pct ${overallCls}">${r.score}/${r.total}${passTag}${lateTag}</td>
      ${catCells}
      <td>${when}</td>
    </tr>`;
  }).join("");

  bodyEl.innerHTML = `<table><thead>${header}</thead><tbody>${rows}</tbody></table>`;
}

function initReportModal() {
  const closeBtn = document.getElementById("report-close-btn");
  const overlay = document.getElementById("report-modal");
  if (closeBtn) closeBtn.addEventListener("click", () => overlay.classList.remove("show"));
}

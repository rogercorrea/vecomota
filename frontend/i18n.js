/* i18n compartilhado entre admin.html, minhas-provas.html e simulado-interativo.html.
   Depende de `api()` (definido em app-common.js ou inline na própria página).

   Uso:
   - Texto estático: <span data-i18n="chave"></span>
   - Atributos: <input data-i18n-placeholder="chave"> (ou data-i18n-title, data-i18n-aria-label)
   - Texto dinâmico em JS: t("chave", {n: 3})
   - Seletor de idioma: <select id="locale-select"></select> (i18n.js popula e escuta sozinho)

   Prioridade pra decidir o locale inicial: escolha manual salva neste navegador
   (localStorage) > preferência salva na conta (users.locale) > idioma do
   navegador > pt-BR como último fallback. */

const SUPPORTED_LOCALES = ["pt-BR", "en", "es"];
const LOCALE_STORAGE_KEY = "vecomota_locale";
const LOCALE_LABELS = { "pt-BR": "🇧🇷 Português", "en": "🇺🇸 English (US)", "es": "🇪🇸 Español" };
/* BCP47 completo, só pra formatação de data/hora (toLocaleDateString etc.) —
   os códigos de locale da conta continuam sendo os curtos (pt-BR/en/es). */
const DATE_LOCALE_MAP = { "pt-BR": "pt-BR", "en": "en-US", "es": "es-ES" };

function dateLocale() {
  return DATE_LOCALE_MAP[currentLocale] || "pt-BR";
}

let currentLocale = null;
let strings = {};
const i18nReadyListeners = [];

function guessBrowserLocale() {
  const langs = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language];
  for (const raw of langs) {
    if (!raw) continue;
    const lower = raw.toLowerCase();
    if (lower.startsWith("pt")) return "pt-BR";
    if (lower.startsWith("es")) return "es";
    if (lower.startsWith("en")) return "en";
  }
  return "pt-BR";
}

function interpolate(template, vars) {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, key) => (key in vars ? vars[key] : match));
}

function t(key, vars) {
  const template = strings[key];
  if (template === undefined) return key;
  return interpolate(template, vars);
}

function applyI18nToDom(root) {
  const scope = root || document;
  scope.querySelectorAll("[data-i18n]").forEach(el => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  scope.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
    el.placeholder = t(el.getAttribute("data-i18n-placeholder"));
  });
  scope.querySelectorAll("[data-i18n-title]").forEach(el => {
    el.title = t(el.getAttribute("data-i18n-title"));
  });
  scope.querySelectorAll("[data-i18n-aria-label]").forEach(el => {
    el.setAttribute("aria-label", t(el.getAttribute("data-i18n-aria-label")));
  });
  scope.querySelectorAll("[data-i18n-alt]").forEach(el => {
    el.alt = t(el.getAttribute("data-i18n-alt"));
  });
  scope.querySelectorAll("[data-i18n-html]").forEach(el => {
    el.innerHTML = t(el.getAttribute("data-i18n-html"));
  });
  document.documentElement.lang = currentLocale;
}

function renderLocaleSelect() {
  const sel = document.getElementById("locale-select");
  if (!sel) return;
  sel.innerHTML = SUPPORTED_LOCALES.map(loc =>
    `<option value="${loc}" ${loc === currentLocale ? "selected" : ""}>${LOCALE_LABELS[loc]}</option>`
  ).join("");
}

async function loadStrings(locale) {
  const res = await fetch(`i18n/strings.${locale}.json`);
  if (!res.ok) throw new Error(`i18n: não consegui carregar strings.${locale}.json`);
  return res.json();
}

async function setLocale(locale, opts = {}) {
  if (!SUPPORTED_LOCALES.includes(locale)) locale = "pt-BR";
  strings = await loadStrings(locale);
  currentLocale = locale;
  localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  applyI18nToDom(document);
  renderLocaleSelect();
  if (opts.syncAccount && typeof api === "function") {
    api("/api/me/locale", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ locale }),
    }).catch(() => { /* offline ou não logado — a escolha local já foi salva */ });
  }
  i18nReadyListeners.forEach(fn => fn(locale));
}

function onI18nReady(fn) {
  i18nReadyListeners.push(fn);
  if (currentLocale) fn(currentLocale);
}

/* Chame depois de resolver o login (ex: dentro de checkAuth), passando o
   `locale` salvo na conta (ou null/undefined se não logado). Só troca de
   idioma automaticamente se a pessoa nunca escolheu manualmente NESTE
   navegador — escolha manual sempre tem prioridade. */
function syncLocaleWithAccount(accountLocale) {
  if (!accountLocale) return;
  const manuallyChosen = localStorage.getItem(LOCALE_STORAGE_KEY);
  if (manuallyChosen) return;
  if (accountLocale !== currentLocale) setLocale(accountLocale);
}

async function initI18n() {
  const saved = localStorage.getItem(LOCALE_STORAGE_KEY);
  const initial = saved && SUPPORTED_LOCALES.includes(saved) ? saved : guessBrowserLocale();
  await setLocale(initial);

  const sel = document.getElementById("locale-select");
  if (sel) {
    sel.addEventListener("change", () => setLocale(sel.value, { syncAccount: true }));
  }
}

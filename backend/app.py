import os
import json
from datetime import datetime, timedelta, timezone

from sanic import Sanic, response
from sanic.response import json as json_response

import auth as auth_lib
from db import get_pool, close_pool
from import_schema import validate_import, slugify

app = Sanic("Vecomota")
# Serve os arquivos estáticos do frontend (admin.html, simulado-interativo.html, i18n/...)
app.static("/", "/app/frontend")

SESSION_COOKIE = "session"
SUPPORTED_LOCALES = ("pt-BR", "en", "es")
# Guarda temporária dos "state" do OAuth. Em produção com mais de um
# processo/worker, troque por Redis ou pela própria tabela do Postgres.
STATE_STORE: set[str] = set()


def _normalize_locale(raw: str | None) -> str:
    """Mapeia o locale devolvido pelo Google (ex: 'pt-BR', 'en-US', 'es-AR')
    para um dos idiomas de interface que a plataforma realmente suporta."""
    if not raw:
        return "pt-BR"
    raw = raw.lower()
    if raw.startswith("pt"):
        return "pt-BR"
    if raw.startswith("es"):
        return "es"
    if raw.startswith("en"):
        return "en"
    return "pt-BR"


def _admin_emails() -> set[str]:
    """E-mails que viram admin automaticamente ao logar (lista no .env)."""
    raw = os.environ.get("ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _current_user_id(request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return auth_lib.decode_session_jwt(token)


def require_auth(handler):
    async def wrapper(request, *args, **kwargs):
        user_id = _current_user_id(request)
        if not user_id:
            return json_response({"error": "not_authenticated"}, status=401)
        return await handler(request, *args, user_id=user_id, **kwargs)
    return wrapper


async def _is_admin(conn, user_id: str) -> bool:
    row = await conn.fetchrow("SELECT is_admin FROM users WHERE id = $1", user_id)
    return bool(row and row["is_admin"])


def require_admin(handler):
    async def wrapper(request, *args, **kwargs):
        user_id = _current_user_id(request)
        if not user_id:
            return json_response({"error": "not_authenticated"}, status=401)
        pool = await get_pool()
        async with pool.acquire() as conn:
            if not await _is_admin(conn, user_id):
                return json_response({"error": "admin_required"}, status=403)
        return await handler(request, *args, user_id=user_id, **kwargs)
    return wrapper


async def _require_exam_access(conn, exam_id: int, user_id: str, allow_taker: bool = False):
    """
    Confere se user_id pode gerenciar (dono ou admin) uma prova. Se
    allow_taker=True, também libera quem já tentou a prova (usado em
    relatório de UMA tentativa, onde o próprio candidato pode ver o
    resultado dele, mas não o de outras pessoas).
    Retorna (exam_row, is_owner_or_admin: bool) ou (None, False) se não achou.
    """
    exam = await conn.fetchrow("SELECT * FROM exams WHERE id = $1", exam_id)
    if not exam:
        return None, False
    is_owner = str(exam["created_by"]) == user_id
    is_admin_user = await _is_admin(conn, user_id)
    return exam, (is_owner or is_admin_user)


def _summarize_integrity(raw: dict) -> dict:
    """
    Só organiza os sinais brutos enviados pelo cliente (contagens de troca de
    aba, tentativas de copiar/colar, mouse fora da área etc.) e classifica um
    nível de atenção ILUSTRATIVO — isto é material para revisão humana, NUNCA
    usado para reprovar ou marcar alguém automaticamente. Os limiares abaixo
    são só um ponto de partida; ajuste como fizer sentido pro seu contexto.
    """
    tab_switches = int(raw.get("tab_switches", 0) or 0)
    mouse_leaves = int(raw.get("mouse_leaves", 0) or 0)
    paste_attempts = int(raw.get("paste_attempts", 0) or 0)
    copy_attempts = int(raw.get("copy_attempts", 0) or 0)

    if tab_switches >= 5 or paste_attempts >= 1:
        level = "high"
    elif tab_switches >= 2 or copy_attempts >= 3 or mouse_leaves >= 3:
        level = "medium"
    elif tab_switches >= 1 or copy_attempts >= 1 or mouse_leaves >= 1:
        level = "low"
    else:
        level = "none"

    return {
        "tab_switches": tab_switches,
        "mouse_leaves": mouse_leaves,
        "paste_attempts": paste_attempts,
        "copy_attempts": copy_attempts,
        "attention_level": level,
        "note": "Indicador informativo, não penaliza a nota automaticamente.",
    }


async def _get_or_create_category(conn, exam_id: int, name: str) -> int:
    """Categorias pertencem à prova. Reaproveita se já existe (por slug),
    cria se for a primeira vez que esse nome aparece nessa prova."""
    slug = slugify(name)
    row = await conn.fetchrow(
        "SELECT id FROM categories WHERE exam_id = $1 AND slug = $2", exam_id, slug
    )
    if row:
        return row["id"]
    row = await conn.fetchrow(
        "INSERT INTO categories (exam_id, slug, name) VALUES ($1,$2,$3) RETURNING id",
        exam_id, slug, name.strip(),
    )
    return row["id"]


async def _insert_exams(conn, exams: list[dict], creator_user_id: str, force_is_public: bool | None) -> list[int]:
    """
    Núcleo de criação de provas, compartilhado entre a importação de admin
    (catálogo público oficial) e a criação por qualquer usuário (provas
    privadas, acessadas por link). force_is_public, quando não é None,
    ignora o "is_public" do JSON — é como garantimos que uma prova criada
    por um usuário comum nasce privada mesmo que o JSON diga o contrário.
    """
    existing_types = {r["slug"]: r["id"] for r in await conn.fetch("SELECT id, slug FROM exam_types")}
    unknown = sorted({e["exam_type"] for e in exams if e["exam_type"] not in existing_types})
    if unknown:
        raise ValueError(
            "Tipo(s) de prova inexistente(s): " + ", ".join(unknown) +
            " — peça a um admin para criar em /api/admin/exam-types, ou use 'outro'."
        )

    created_ids = []
    for exam in exams:
        is_public = exam.get("is_public", False) if force_is_public is None else force_is_public

        exam_row = await conn.fetchrow(
            """
            INSERT INTO exams
              (exam_type_id, title, description, language, passing_score_percent,
               time_limit_minutes, anti_cheat_enabled, copy_protection_enabled,
               is_public, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            RETURNING id, share_token
            """,
            existing_types[exam["exam_type"]], exam["title"], exam.get("description"), exam["language"],
            exam.get("passing_score_percent"), exam.get("time_limit_minutes"),
            exam.get("anti_cheat_enabled", False), exam.get("copy_protection_enabled", False),
            is_public, creator_user_id,
        )
        exam_id = exam_row["id"]
        created_ids.append(exam_id)

        for position, q in enumerate(exam["questions"], start=1):
            category_id = await _get_or_create_category(conn, exam_id, q["category"])
            question_row = await conn.fetchrow(
                """
                INSERT INTO questions (exam_id, category_id, position, question_text, explanation)
                VALUES ($1,$2,$3,$4,$5) RETURNING id
                """,
                exam_id, category_id, position, q["question_text"], q.get("explanation"),
            )
            question_id = question_row["id"]
            for opt in q["options"]:
                await conn.execute(
                    "INSERT INTO options (question_id, label, option_text, is_correct) VALUES ($1,$2,$3,$4)",
                    question_id, opt["label"], opt["text"], bool(opt.get("correct", False)),
                )

    return created_ids


async def _serialize_exam(conn, exam) -> dict:
    """Monta o payload de uma prova com questões/alternativas (sem revelar a
    correta) e categoria de cada questão."""
    questions = await conn.fetch(
        """
        SELECT q.id, q.position, q.question_text, c.id AS category_id, c.name AS category_name
        FROM questions q JOIN categories c ON c.id = q.category_id
        WHERE q.exam_id = $1 ORDER BY q.position
        """,
        exam["id"],
    )
    question_ids = [q["id"] for q in questions]
    options = await conn.fetch(
        "SELECT id, question_id, label, option_text FROM options "
        "WHERE question_id = ANY($1::int[]) ORDER BY question_id, label",
        question_ids,
    )
    opts_by_question: dict[int, list] = {}
    for o in options:
        opts_by_question.setdefault(o["question_id"], []).append(
            {"id": o["id"], "label": o["label"], "option_text": o["option_text"]}
        )

    return {
        "id": exam["id"],
        "title": exam["title"],
        "description": exam["description"],
        "language": exam["language"],
        "passing_score_percent": exam["passing_score_percent"],
        "time_limit_minutes": exam["time_limit_minutes"],
        "anti_cheat_enabled": exam["anti_cheat_enabled"],
        "copy_protection_enabled": exam["copy_protection_enabled"],
        "questions": [
            {
                "id": q["id"],
                "position": q["position"],
                "question_text": q["question_text"],
                "category": {"id": q["category_id"], "name": q["category_name"]},
                "options": opts_by_question.get(q["id"], []),
            }
            for q in questions
        ],
    }


@app.after_server_stop
async def _shutdown(app, loop):
    await close_pool()


# ---------- Autenticação ----------

@app.get("/api/auth/google/login")
async def google_login(request):
    state = auth_lib.new_state_token()
    STATE_STORE.add(state)
    return response.redirect(auth_lib.build_google_auth_url(state))


@app.get("/api/auth/google/callback")
async def google_callback(request):
    code = request.args.get("code")
    state = request.args.get("state")
    if not code or state not in STATE_STORE:
        return json_response({"error": "invalid_state"}, status=400)
    STATE_STORE.discard(state)

    userinfo = await auth_lib.exchange_code_for_userinfo(code)
    google_locale = _normalize_locale(userinfo.get("locale"))
    is_admin = userinfo.get("email", "").lower() in _admin_emails()

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (google_sub, email, name, avatar_url, locale, is_admin)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (google_sub) DO UPDATE
              SET email = EXCLUDED.email,
                  name = EXCLUDED.name,
                  avatar_url = EXCLUDED.avatar_url,
                  is_admin = EXCLUDED.is_admin
              -- locale NÃO é sobrescrito de propósito (ver _normalize_locale acima);
              -- is_admin É recalculado a cada login a partir do ADMIN_EMAILS do .env.
            RETURNING id
            """,
            userinfo["sub"], userinfo["email"], userinfo.get("name"), userinfo.get("picture"),
            google_locale, is_admin,
        )

    token = auth_lib.issue_session_jwt(str(row["id"]))
    res = response.redirect(os.environ.get("FRONTEND_URL", "/"))
    res.cookies[SESSION_COOKIE] = token
    res.cookies[SESSION_COOKIE]["httponly"] = True
    res.cookies[SESSION_COOKIE]["samesite"] = "Lax"
    res.cookies[SESSION_COOKIE]["max-age"] = auth_lib.JWT_TTL_SECONDS
    return res


@app.get("/api/auth/logout")
async def logout(request):
    res = response.redirect(os.environ.get("FRONTEND_URL", "/"))
    del res.cookies[SESSION_COOKIE]
    return res


@app.get("/api/me")
@require_auth
async def me(request, user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, name, avatar_url, locale, is_admin FROM users WHERE id = $1", user_id
        )
    return json_response(dict(row))


@app.patch("/api/me/locale")
@require_auth
async def update_locale(request, user_id):
    """Troca o idioma da interface (independe do idioma das provas)."""
    payload = request.json or {}
    locale = payload.get("locale")
    if locale not in SUPPORTED_LOCALES:
        return json_response({"error": "unsupported_locale", "supported": SUPPORTED_LOCALES}, status=400)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET locale = $1 WHERE id = $2", locale, user_id)
    return json_response({"locale": locale})


# ---------- Catálogo público ----------

@app.get("/api/exam-types")
async def list_exam_types(request):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, slug, name FROM exam_types ORDER BY name")
    return json_response([dict(r) for r in rows])


@app.get("/api/exams")
async def list_exams(request):
    """Só o catálogo PÚBLICO (is_public = true). Provas privadas aparecem em
    /api/my/exams (pro dono) ou via /api/exams/shared/<token> (pra quem tem o link)."""
    type_slug = request.args.get("type")
    language = request.args.get("language")
    pool = await get_pool()
    conditions, params = [], []
    if type_slug:
        params.append(type_slug)
        conditions.append(f"et.slug = ${len(params)}")
    if language:
        params.append(language)
        conditions.append(f"e.language = ${len(params)}")
    where_extra = (" AND " + " AND ".join(conditions)) if conditions else ""
    query = f"""
        SELECT e.id, e.title, e.description, e.language, et.slug AS exam_type
        FROM exams e JOIN exam_types et ON et.id = e.exam_type_id
        WHERE e.is_public = true {where_extra}
        ORDER BY e.created_at DESC
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return json_response([dict(r) for r in rows])


@app.get("/api/exams/<exam_id:int>")
async def get_exam(request, exam_id):
    """Pública se is_public=true; senão, só o dono ou um admin (login opcional)."""
    user_id = _current_user_id(request)
    pool = await get_pool()
    async with pool.acquire() as conn:
        exam = await conn.fetchrow("SELECT * FROM exams WHERE id = $1", exam_id)
        if not exam:
            return json_response({"error": "not_found"}, status=404)
        if not exam["is_public"]:
            allowed = user_id is not None and (
                str(exam["created_by"]) == user_id or await _is_admin(conn, user_id)
            )
            if not allowed:
                return json_response({"error": "not_found"}, status=404)  # esconde a existência
        data = await _serialize_exam(conn, exam)
    return json_response(data)


@app.get("/api/exams/shared/<token:str>")
@require_auth
async def get_exam_by_share_token(request, token, user_id):
    """Acesso via link de compartilhamento — funciona pra provas privadas,
    independentemente de is_public. Precisa estar logado (a resposta vai
    virar uma tentativa vinculada a esse usuário)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        exam = await conn.fetchrow("SELECT * FROM exams WHERE share_token = $1", token)
        if not exam:
            return json_response({"error": "not_found"}, status=404)
        data = await _serialize_exam(conn, exam)
    return json_response(data)


# ---------- Minhas provas (qualquer usuário logado cria e compartilha) ----------

@app.post("/api/my/exams/import")
@require_auth
async def create_my_exam(request, user_id):
    """Qualquer usuário logado pode criar sua(s) própria(s) prova(s) nesse
    mesmo formato JSON padrão. Nasce sempre privada (só acessível via link) —
    is_public do JSON é ignorado aqui de propósito."""
    payload = request.json
    if payload is None:
        return json_response({"error": "corpo da requisição precisa ser JSON"}, status=400)

    exams, errors = validate_import(payload)
    if errors:
        return json_response({"error": "validation_failed", "details": errors}, status=422)

    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                created_ids = await _insert_exams(conn, exams, user_id, force_is_public=False)
    except ValueError as e:
        return json_response({"error": "unknown_exam_type", "details": [str(e)]}, status=422)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, share_token FROM exams WHERE id = ANY($1::int[])", created_ids
        )
    return json_response({
        "created_exams": [
            {"id": r["id"], "share_url": f"/api/exams/shared/{r['share_token']}"} for r in rows
        ],
        "count": len(created_ids),
    })


@app.get("/api/my/exams")
@require_auth
async def list_my_exams(request, user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT e.id, e.title, e.language, e.is_public, e.share_token,
                   e.passing_score_percent, e.time_limit_minutes, e.created_at,
                   COUNT(DISTINCT q.id) AS question_count,
                   COUNT(DISTINCT a.id) FILTER (WHERE a.submitted_at IS NOT NULL) AS attempt_count
            FROM exams e
            LEFT JOIN questions q ON q.exam_id = e.id
            LEFT JOIN attempts a ON a.exam_id = e.id
            WHERE e.created_by = $1
            GROUP BY e.id
            ORDER BY e.created_at DESC
            """,
            user_id,
        )
    return json_response([
        {
            "id": r["id"], "title": r["title"], "language": r["language"], "is_public": r["is_public"],
            "share_url": f"/api/exams/shared/{r['share_token']}",
            "passing_score_percent": r["passing_score_percent"], "time_limit_minutes": r["time_limit_minutes"],
            "question_count": r["question_count"], "attempt_count": r["attempt_count"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ])


@app.patch("/api/exams/<exam_id:int>")
@require_auth
async def update_exam(request, exam_id, user_id):
    """Dono ou admin. Hoje só alterna visibilidade pública — suficiente pra
    "esconder" uma prova com erro sem apagar o histórico de quem já respondeu."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        exam, allowed = await _require_exam_access(conn, exam_id, user_id)
        if not exam:
            return json_response({"error": "not_found"}, status=404)
        if not allowed:
            return json_response({"error": "forbidden"}, status=403)

        payload = request.json or {}
        if "is_public" not in payload:
            return json_response({"error": "informe is_public (true/false)"}, status=400)
        row = await conn.fetchrow(
            "UPDATE exams SET is_public = $1 WHERE id = $2 RETURNING id, is_public",
            bool(payload["is_public"]), exam_id,
        )
    return json_response(dict(row))


@app.delete("/api/exams/<exam_id:int>")
@require_auth
async def delete_exam(request, exam_id, user_id):
    """Dono ou admin. Apaga a prova e, em cascata, questões, categorias,
    alternativas e TODAS as tentativas já registradas nela."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        exam, allowed = await _require_exam_access(conn, exam_id, user_id)
        if not exam:
            return json_response({"error": "not_found"}, status=404)
        if not allowed:
            return json_response({"error": "forbidden"}, status=403)
        await conn.execute("DELETE FROM exams WHERE id = $1", exam_id)
    return json_response({"deleted": True})


# ---------- Tentativas (iniciar → finalizar) ----------

@app.post("/api/exams/<exam_id:int>/attempts/start")
@require_auth
async def start_attempt(request, exam_id, user_id):
    """Abre uma tentativa e registra o horário de início — necessário pra
    aplicar o limite de tempo (se houver) e pra dar um attempt_id estável
    desde já, usado depois pra finalizar e pra registrar a auditoria."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        exam = await conn.fetchrow(
            "SELECT id, time_limit_minutes FROM exams WHERE id = $1", exam_id
        )
        if not exam:
            return json_response({"error": "not_found"}, status=404)

        row = await conn.fetchrow(
            "INSERT INTO attempts (exam_id, user_id) VALUES ($1, $2) RETURNING id, started_at",
            exam_id, user_id,
        )

    deadline_at = None
    if exam["time_limit_minutes"] is not None:
        deadline_at = (row["started_at"] + timedelta(minutes=exam["time_limit_minutes"])).isoformat()

    return json_response({
        "attempt_id": row["id"],
        "started_at": row["started_at"].isoformat(),
        "time_limit_minutes": exam["time_limit_minutes"],
        "deadline_at": deadline_at,  # null quando a prova é sem limite de tempo
    })


@app.post("/api/exams/<exam_id:int>/attempts/<attempt_id:int>/submit")
@require_auth
async def submit_attempt(request, exam_id, attempt_id, user_id):
    """
    Corpo esperado:
    {
      "answers": {"<question_id>": <option_id>, ...},
      "integrity": {"tab_switches":0,"mouse_leaves":0,"paste_attempts":0,"copy_attempts":0}  // opcional
    }
    Finaliza uma tentativa aberta em /attempts/start.
    """
    payload = request.json or {}
    answers = payload.get("answers", {})
    integrity_raw = payload.get("integrity", {})

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            attempt = await conn.fetchrow(
                "SELECT id, started_at, submitted_at FROM attempts "
                "WHERE id = $1 AND exam_id = $2 AND user_id = $3",
                attempt_id, exam_id, user_id,
            )
            if not attempt:
                return json_response({"error": "attempt_not_found"}, status=404)
            if attempt["submitted_at"] is not None:
                return json_response({"error": "attempt_already_submitted"}, status=409)

            exam = await conn.fetchrow(
                "SELECT passing_score_percent, time_limit_minutes FROM exams WHERE id = $1", exam_id
            )
            questions = await conn.fetch(
                "SELECT id, explanation FROM questions WHERE exam_id = $1 ORDER BY position",
                exam_id,
            )
            question_ids = [q["id"] for q in questions]

            correct_options = await conn.fetch(
                "SELECT id, question_id FROM options "
                "WHERE question_id = ANY($1::int[]) AND is_correct = true",
                question_ids,
            )
            correct_by_question = {r["question_id"]: r["id"] for r in correct_options}

            score = 0
            details = []
            for q in questions:
                qid = q["id"]
                chosen_raw = answers.get(str(qid))
                chosen = int(chosen_raw) if chosen_raw is not None else None
                correct_option_id = correct_by_question.get(qid)
                is_correct = chosen is not None and chosen == correct_option_id
                if is_correct:
                    score += 1
                details.append({
                    "question_id": qid,
                    "chosen_option_id": chosen,
                    "correct_option_id": correct_option_id,
                    "is_correct": is_correct,
                    "explanation": q["explanation"],
                })

            total = len(question_ids)
            passing_percent = exam["passing_score_percent"]
            passed = None
            if passing_percent is not None and total > 0:
                passed = (score / total) * 100 >= passing_percent

            now = datetime.now(timezone.utc)
            late = False
            if exam["time_limit_minutes"] is not None:
                elapsed_minutes = (now - attempt["started_at"]).total_seconds() / 60
                late = elapsed_minutes > exam["time_limit_minutes"]

            integrity_summary = _summarize_integrity(integrity_raw)

            await conn.execute(
                "UPDATE attempts SET score=$1, total=$2, passed=$3, late=$4, "
                "integrity_flags=$5::jsonb, submitted_at=$6 WHERE id=$7",
                score, total, passed, late, json.dumps(integrity_summary), now, attempt_id,
            )

            for d in details:
                await conn.execute(
                    "INSERT INTO attempt_answers (attempt_id, question_id, option_id, is_correct) "
                    "VALUES ($1,$2,$3,$4)",
                    attempt_id, d["question_id"], d["chosen_option_id"], d["is_correct"],
                )

    return json_response({
        "attempt_id": attempt_id,
        "score": score,
        "total": total,
        "passing_score_percent": passing_percent,
        "passed": passed,
        "late": late,
        "integrity": integrity_summary,
        "submitted_at": now.isoformat(),
        "details": details,
    })


@app.get("/api/exams/<exam_id:int>/history")
@require_auth
async def exam_history(request, exam_id, user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, score, total, passed, late, integrity_flags, submitted_at FROM attempts "
            "WHERE exam_id = $1 AND user_id = $2 AND submitted_at IS NOT NULL ORDER BY submitted_at",
            exam_id, user_id,
        )
    return json_response([
        {"id": r["id"], "score": r["score"], "total": r["total"], "passed": r["passed"], "late": r["late"],
         "integrity": json.loads(r["integrity_flags"]) if r["integrity_flags"] else {},
         "submitted_at": r["submitted_at"].isoformat()}
        for r in rows
    ])


@app.get("/api/me/stats")
@require_auth
async def my_stats(request, user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT et.slug AS exam_type, et.name,
                   COUNT(a.id) AS attempts,
                   ROUND(AVG(a.score::numeric / NULLIF(a.total, 0)) * 100, 1) AS avg_percent
            FROM attempts a
            JOIN exams e ON e.id = a.exam_id
            JOIN exam_types et ON et.id = e.exam_type_id
            WHERE a.user_id = $1 AND a.submitted_at IS NOT NULL
            GROUP BY et.slug, et.name
            ORDER BY et.name
            """,
            user_id,
        )
    return json_response([dict(r) for r in rows])


# ---------- Auditoria de integridade ----------

@app.post("/api/attempts/<attempt_id:int>/audit")
@require_auth
async def submit_audit_log(request, attempt_id, user_id):
    """
    Registra o log detalhado de eventos (com horário de cada ocorrência),
    enviado pelo cliente quando a prova é finalizada. Fica separado da
    correção (caminho crítico) — mesmo que o envio da auditoria falhe ou
    demore, a nota da pessoa já está salva.

    Corpo esperado: {"events": [{"type": "mouse_leave", "occurred_at": "...", "meta": {}}, ...]}
    """
    payload = request.json or {}
    events = payload.get("events", [])
    if not isinstance(events, list) or len(events) == 0:
        return json_response({"inserted": 0})

    pool = await get_pool()
    async with pool.acquire() as conn:
        attempt = await conn.fetchrow(
            "SELECT id FROM attempts WHERE id = $1 AND user_id = $2", attempt_id, user_id
        )
        if not attempt:
            return json_response({"error": "attempt_not_found"}, status=404)

        rows = [
            (attempt_id, ev.get("type"), ev.get("occurred_at"), json.dumps(ev.get("meta", {})))
            for ev in events if ev.get("type") and ev.get("occurred_at")
        ]
        if rows:
            await conn.executemany(
                "INSERT INTO attempt_audit_events (attempt_id, event_type, occurred_at, meta) "
                "VALUES ($1,$2,$3,$4::jsonb)",
                rows,
            )
    return json_response({"inserted": len(rows)})


@app.get("/api/exams/<exam_id:int>/attempts/<attempt_id:int>/audit")
@require_auth
async def view_audit_log(request, exam_id, attempt_id, user_id):
    """Dono da prova ou admin revisam os sinais registrados numa tentativa —
    usada pra decidir caso a caso, nunca automaticamente, se algo merece
    desclassificação."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        exam, allowed = await _require_exam_access(conn, exam_id, user_id)
        if not exam:
            return json_response({"error": "not_found"}, status=404)
        if not allowed:
            return json_response({"error": "forbidden"}, status=403)

        attempt = await conn.fetchrow(
            """
            SELECT a.id, a.score, a.total, a.passed, a.late, a.started_at, a.submitted_at,
                   a.integrity_flags, u.email, u.name
            FROM attempts a JOIN users u ON u.id = a.user_id
            WHERE a.id = $1 AND a.exam_id = $2
            """,
            attempt_id, exam_id,
        )
        if not attempt:
            return json_response({"error": "not_found"}, status=404)
        events = await conn.fetch(
            "SELECT event_type, occurred_at, meta FROM attempt_audit_events "
            "WHERE attempt_id = $1 ORDER BY occurred_at",
            attempt_id,
        )
    return json_response({
        "attempt": {
            **{k: attempt[k] for k in ("id", "score", "total", "passed", "late", "email", "name")},
            "started_at": attempt["started_at"].isoformat(),
            "submitted_at": attempt["submitted_at"].isoformat() if attempt["submitted_at"] else None,
            "integrity_summary": json.loads(attempt["integrity_flags"]) if attempt["integrity_flags"] else {},
        },
        "events": [
            {"type": e["event_type"], "occurred_at": e["occurred_at"].isoformat(), "meta": json.loads(e["meta"])}
            for e in events
        ],
    })


# ---------- Relatórios por categoria ----------

@app.get("/api/exams/<exam_id:int>/reports")
@require_auth
async def exam_report(request, exam_id, user_id):
    """Dono da prova (ou admin): desempenho de CADA pessoa que respondeu,
    separado por categoria de questão. Considera todas as tentativas
    finalizadas (uma pessoa que tentou mais de uma vez aparece mais de uma vez —
    o consumidor da API decide se quer só a última)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        exam, allowed = await _require_exam_access(conn, exam_id, user_id)
        if not exam:
            return json_response({"error": "not_found"}, status=404)
        if not allowed:
            return json_response({"error": "forbidden"}, status=403)

        rows = await conn.fetch(
            """
            SELECT a.id AS attempt_id, a.user_id, u.name, u.email, a.score, a.total,
                   a.passed, a.late, a.submitted_at,
                   c.id AS category_id, c.name AS category_name,
                   COUNT(aa.id) AS category_total,
                   SUM(CASE WHEN aa.is_correct THEN 1 ELSE 0 END) AS category_correct
            FROM attempts a
            JOIN users u ON u.id = a.user_id
            JOIN attempt_answers aa ON aa.attempt_id = a.id
            JOIN questions q ON q.id = aa.question_id
            JOIN categories c ON c.id = q.category_id
            WHERE a.exam_id = $1 AND a.submitted_at IS NOT NULL
            GROUP BY a.id, a.user_id, u.name, u.email, a.score, a.total, a.passed, a.late,
                     a.submitted_at, c.id, c.name
            ORDER BY a.submitted_at, c.name
            """,
            exam_id,
        )

    attempts: dict[int, dict] = {}
    for r in rows:
        aid = r["attempt_id"]
        if aid not in attempts:
            attempts[aid] = {
                "attempt_id": aid,
                "user": {"id": str(r["user_id"]), "name": r["name"], "email": r["email"]},
                "score": r["score"], "total": r["total"], "passed": r["passed"], "late": r["late"],
                "submitted_at": r["submitted_at"].isoformat(),
                "by_category": [],
            }
        attempts[aid]["by_category"].append({
            "category_id": r["category_id"], "category_name": r["category_name"],
            "correct": r["category_correct"], "total": r["category_total"],
        })

    return json_response({"exam_id": exam_id, "results": list(attempts.values())})


@app.get("/api/exams/<exam_id:int>/attempts/<attempt_id:int>/report")
@require_auth
async def attempt_report(request, exam_id, attempt_id, user_id):
    """Relatório de UMA tentativa por categoria — acessível pelo próprio
    candidato (o resultado dele), pelo dono da prova ou por um admin."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        attempt = await conn.fetchrow(
            "SELECT id, user_id, score, total, passed, late, submitted_at FROM attempts "
            "WHERE id = $1 AND exam_id = $2",
            attempt_id, exam_id,
        )
        if not attempt:
            return json_response({"error": "not_found"}, status=404)

        is_self = str(attempt["user_id"]) == user_id
        if not is_self:
            _, allowed = await _require_exam_access(conn, exam_id, user_id)
            if not allowed:
                return json_response({"error": "forbidden"}, status=403)

        rows = await conn.fetch(
            """
            SELECT c.id AS category_id, c.name AS category_name,
                   COUNT(aa.id) AS category_total,
                   SUM(CASE WHEN aa.is_correct THEN 1 ELSE 0 END) AS category_correct
            FROM attempt_answers aa
            JOIN questions q ON q.id = aa.question_id
            JOIN categories c ON c.id = q.category_id
            WHERE aa.attempt_id = $1
            GROUP BY c.id, c.name
            ORDER BY c.name
            """,
            attempt_id,
        )

    return json_response({
        "attempt_id": attempt_id,
        "score": attempt["score"], "total": attempt["total"],
        "passed": attempt["passed"], "late": attempt["late"],
        "submitted_at": attempt["submitted_at"].isoformat() if attempt["submitted_at"] else None,
        "by_category": [
            {"category_id": r["category_id"], "category_name": r["category_name"],
             "correct": r["category_correct"], "total": r["category_total"]}
            for r in rows
        ],
    })


# ---------- Admin: catálogo oficial, tipos e supervisão geral ----------

@app.get("/api/admin/exam-types")
@require_admin
async def admin_list_exam_types(request, user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, slug, name FROM exam_types ORDER BY name")
    return json_response([dict(r) for r in rows])


@app.post("/api/admin/exam-types")
@require_admin
async def admin_create_exam_type(request, user_id):
    payload = request.json or {}
    slug, name = payload.get("slug"), payload.get("name")
    if not slug or not name:
        return json_response({"error": "slug e name são obrigatórios"}, status=400)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO exam_types (slug, name) VALUES ($1, $2) "
            "ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name RETURNING id, slug, name",
            slug, name,
        )
    return json_response(dict(row))


@app.get("/api/admin/exams")
@require_admin
async def admin_list_exams(request, user_id):
    """
    Visão geral de TODAS as provas do sistema, inclusive privadas de outros
    usuários — é um papel de supervisão, não só de curadoria de catálogo.
    Se isso não for desejável (privacidade de provas de terceiros), restrinja
    esse endpoint pra só mostrar as próprias + as públicas.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT e.id, e.title, e.language, e.is_public, e.passing_score_percent,
                   e.time_limit_minutes, e.anti_cheat_enabled, e.copy_protection_enabled,
                   e.created_at, e.share_token, et.slug AS exam_type, et.name AS exam_type_name,
                   u.email AS owner_email, u.name AS owner_name,
                   COUNT(q.id) AS question_count
            FROM exams e
            JOIN exam_types et ON et.id = e.exam_type_id
            JOIN users u ON u.id = e.created_by
            LEFT JOIN questions q ON q.exam_id = e.id
            GROUP BY e.id, et.slug, et.name, u.email, u.name
            ORDER BY e.created_at DESC
            """
        )
    return json_response([
        {**dict(r), "created_at": r["created_at"].isoformat()} for r in rows
    ])


@app.post("/api/admin/exams/import")
@require_admin
async def admin_import_exams(request, user_id):
    """Importação em lote pro catálogo oficial — aqui, is_public do JSON É
    respeitado (permite publicar no catálogo geral). Tudo roda em uma
    transação: se qualquer prova do lote falhar a validação, nada é gravado."""
    payload = request.json
    if payload is None:
        return json_response({"error": "corpo da requisição precisa ser JSON"}, status=400)

    exams, errors = validate_import(payload)
    if errors:
        return json_response({"error": "validation_failed", "details": errors}, status=422)

    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                created_ids = await _insert_exams(conn, exams, user_id, force_is_public=None)
    except ValueError as e:
        return json_response({"error": "unknown_exam_type", "details": [str(e)]}, status=422)

    return json_response({"created_exam_ids": created_ids, "count": len(created_ids)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, dev=os.environ.get("SANIC_DEV", "false") == "true")

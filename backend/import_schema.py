"""
Formato JSON padrão para criar/importar provas.

Categorias pertencem à PROVA (não a um tipo genérico): cada prova define seu
próprio vocabulário de categorias a partir do campo "category" de cada
questão — "Windows"/"Segurança" numa prova de TI, "Matemática"/"Inglês" numa
prova estilo ENEM. Toda questão precisa ter uma categoria; a categoria é
criada automaticamente na prova na primeira vez que aparece (reaproveitada
se o mesmo nome já existir nessa prova).

{
  "exams": [
    {
      "exam_type": "ti",                  // slug existente em exam_types (rótulo amplo, catálogo)
      "title": "Simulado de TI — Fundamentos",
      "description": "...",                // opcional
      "language": "pt-BR",                 // idioma do CONTEÚDO (não é a interface)
      "passing_score_percent": 60,         // opcional, null/ausente = sem nota mínima
      "time_limit_minutes": 90,            // opcional, null/ausente = sem limite de tempo (infinito)
      "anti_cheat_enabled": true,          // opcional, default false
      "copy_protection_enabled": true,     // opcional, default false
      "questions": [
        {
          "category": "Windows",           // OBRIGATÓRIA — vira uma categoria dessa prova
          "question_text": "...",
          "explanation": "...",            // opcional, mostrado após a correção
          "options": [
            {"label": "A", "text": "...", "correct": false},
            {"label": "B", "text": "...", "correct": true},
            {"label": "C", "text": "...", "correct": false},
            {"label": "D", "text": "...", "correct": false}
          ]
        },
        {
          "category": "Segurança",
          "question_text": "...",
          "options": [ ... ]
        }
      ]
    }
  ]
}

Também aceita um único objeto de prova no nível raiz (sem o array "exams"),
por conveniência ao importar/criar uma prova de cada vez.

Observações sobre dono e visibilidade (não fazem parte do JSON, são
decididas por QUEM está chamando a API, não pelo conteúdo importado):
- Toda prova criada fica vinculada (created_by) a quem a criou.
- Quando um usuário comum cria a prova (não-admin), ela nasce privada
  (is_public = false) e acessível só por quem tiver o link de
  compartilhamento (share_token) — is_public no JSON é ignorado nesse caso.
- Quando um admin importa pela tela de admin, is_public do JSON é respeitado
  (permite publicar no catálogo geral).
"""

import re
import unicodedata

VALID_LANGUAGE_PATTERN_HINT = "use códigos como 'pt-BR', 'en', 'es'"


def slugify(text: str) -> str:
    """Normaliza um nome de categoria pra um slug estável (sem acento, minúsculo,
    espaços viram '_'), usado pra deduplicar categorias com o mesmo nome."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text or "categoria"


def normalize_import_payload(payload: dict) -> list[dict]:
    """Aceita tanto {"exams": [...]} quanto um único objeto de prova solto."""
    if "exams" in payload:
        return payload["exams"]
    return [payload]


def validate_exam(exam: dict, index: int) -> list[str]:
    """Retorna uma lista de erros (vazia = válido). index é só pra mensagens legíveis."""
    errors = []
    prefix = f"exams[{index}]"

    def require_str(field):
        val = exam.get(field)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{prefix}.{field}: obrigatório e precisa ser texto não vazio.")

    require_str("exam_type")
    require_str("title")
    require_str("language")

    passing = exam.get("passing_score_percent")
    if passing is not None and (not isinstance(passing, int) or not (0 <= passing <= 100)):
        errors.append(f"{prefix}.passing_score_percent: precisa ser um inteiro entre 0 e 100, ou omitido.")

    time_limit = exam.get("time_limit_minutes")
    if time_limit is not None and (not isinstance(time_limit, int) or time_limit <= 0):
        errors.append(f"{prefix}.time_limit_minutes: precisa ser um inteiro positivo, ou omitido/null para sem limite.")

    questions = exam.get("questions")
    if not isinstance(questions, list) or len(questions) == 0:
        errors.append(f"{prefix}.questions: precisa ser uma lista com pelo menos 1 questão.")
        return errors  # sem questões, não dá pra validar o resto

    for qi, q in enumerate(questions):
        qprefix = f"{prefix}.questions[{qi}]"

        if not isinstance(q.get("category"), str) or not q["category"].strip():
            errors.append(f"{qprefix}.category: obrigatória — toda questão precisa de uma categoria.")

        if not isinstance(q.get("question_text"), str) or not q["question_text"].strip():
            errors.append(f"{qprefix}.question_text: obrigatório.")

        options = q.get("options")
        if not isinstance(options, list) or not (2 <= len(options) <= 8):
            errors.append(f"{qprefix}.options: precisa ser uma lista com 2 a 8 alternativas.")
            continue

        correct_count = 0
        seen_labels = set()
        for oi, opt in enumerate(options):
            oprefix = f"{qprefix}.options[{oi}]"
            if not isinstance(opt.get("label"), str) or not opt["label"].strip():
                errors.append(f"{oprefix}.label: obrigatório (ex: 'A').")
            elif opt["label"] in seen_labels:
                errors.append(f"{oprefix}.label: rótulo '{opt['label']}' duplicado nesta questão.")
            else:
                seen_labels.add(opt["label"])
            if not isinstance(opt.get("text"), str) or not opt["text"].strip():
                errors.append(f"{oprefix}.text: obrigatório.")
            if opt.get("correct") is True:
                correct_count += 1

        if correct_count != 1:
            errors.append(
                f"{qprefix}.options: precisa ter exatamente 1 alternativa com \"correct\": true "
                f"(encontrado: {correct_count})."
            )

    return errors


def validate_import(payload: dict) -> tuple[list[dict], list[str]]:
    """Retorna (lista_de_provas_normalizada, lista_de_erros)."""
    try:
        exams = normalize_import_payload(payload)
    except Exception:
        return [], ["Formato inválido: esperado um objeto com \"exams\": [...] ou uma prova única."]

    if not isinstance(exams, list) or len(exams) == 0:
        return [], ["\"exams\" precisa ser uma lista com pelo menos 1 prova."]

    all_errors = []
    for i, exam in enumerate(exams):
        all_errors.extend(validate_exam(exam, i))

    return exams, all_errors

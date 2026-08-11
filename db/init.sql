-- Schema inicial: usuários, tipos de prova, provas, questões, opções, tentativas

CREATE EXTENSION IF NOT EXISTS "pgcrypto"; -- para gen_random_uuid()

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  google_sub TEXT UNIQUE NOT NULL,
  email TEXT UNIQUE NOT NULL,
  name TEXT,
  avatar_url TEXT,
  locale TEXT NOT NULL DEFAULT 'pt-BR', -- idioma preferido da INTERFACE (pt-BR, en, es)
  is_admin BOOLEAN NOT NULL DEFAULT false, -- pode importar/gerenciar provas na tela de admin
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Tipos de prova: seriado, enem, concurso, inglês... fácil de crescer.
-- Serve só como um rótulo amplo pro catálogo público — a classificação de
-- verdade das questões é por categoria (ver abaixo), que pertence à prova.
CREATE TABLE exam_types (
  id SERIAL PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL
);

CREATE TABLE exams (
  id SERIAL PRIMARY KEY,
  exam_type_id INT NOT NULL REFERENCES exam_types(id),
  title TEXT NOT NULL,
  description TEXT,
  language TEXT NOT NULL DEFAULT 'pt-BR', -- idioma do CONTEÚDO da prova (pt-BR, en, es) — independe da interface
  passing_score_percent INT CHECK (passing_score_percent BETWEEN 0 AND 100), -- NULL = sem nota mínima definida
  time_limit_minutes INT CHECK (time_limit_minutes IS NULL OR time_limit_minutes > 0), -- NULL = sem limite (infinito)
  anti_cheat_enabled BOOLEAN NOT NULL DEFAULT false,   -- registra sinais (troca de aba, colar), não reprova sozinho
  copy_protection_enabled BOOLEAN NOT NULL DEFAULT false, -- dificulta copiar o enunciado (não é DRM real)
  created_by UUID NOT NULL REFERENCES users(id), -- dono da prova: só ele (e admins) editam/veem relatórios
  share_token UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE, -- link secreto de acesso, independe de is_public
  is_public BOOLEAN NOT NULL DEFAULT false, -- true = aparece no catálogo público; false = só via share_token/dono/admin
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Categorias pertencem à PROVA (não a um tipo genérico): cada prova define o
-- próprio vocabulário — "Windows"/"Segurança" numa prova de TI, "Matemática"/
-- "Inglês" numa prova estilo ENEM. Toda questão é obrigatoriamente vinculada
-- a uma categoria (ver questions.category_id abaixo).
CREATE TABLE categories (
  id SERIAL PRIMARY KEY,
  exam_id INT NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  slug TEXT NOT NULL,
  name TEXT NOT NULL,
  UNIQUE (exam_id, slug)
);

CREATE TABLE questions (
  id SERIAL PRIMARY KEY,
  exam_id INT NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  category_id INT NOT NULL REFERENCES categories(id), -- obrigatória; RESTRICT: não dá pra apagar categoria em uso
  position INT NOT NULL,
  question_text TEXT NOT NULL,
  explanation TEXT
);

CREATE TABLE options (
  id SERIAL PRIMARY KEY,
  question_id INT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  label CHAR(1) NOT NULL,
  option_text TEXT NOT NULL,
  is_correct BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE attempts (
  id SERIAL PRIMARY KEY,
  exam_id INT NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  submitted_at TIMESTAMPTZ, -- NULL enquanto a prova está em andamento (ou foi abandonada)
  score INT,                -- preenchido só na finalização
  total INT,
  passed BOOLEAN,           -- NULL se a prova não tem nota mínima configurada
  late BOOLEAN NOT NULL DEFAULT false, -- true se finalizou depois do time_limit_minutes
  integrity_flags JSONB NOT NULL DEFAULT '{}'::jsonb -- resumo agregado, só informativo
);

CREATE TABLE attempt_audit_events (
  id SERIAL PRIMARY KEY,
  attempt_id INT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,       -- ex: 'mouse_leave', 'tab_switch', 'copy_attempt', 'paste_attempt'
  occurred_at TIMESTAMPTZ NOT NULL,
  meta JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE attempt_answers (
  id SERIAL PRIMARY KEY,
  attempt_id INT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
  question_id INT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  option_id INT REFERENCES options(id),
  is_correct BOOLEAN NOT NULL
);

CREATE INDEX idx_questions_exam ON questions(exam_id);
CREATE INDEX idx_questions_category ON questions(category_id);
CREATE INDEX idx_categories_exam ON categories(exam_id);
CREATE INDEX idx_options_question ON options(question_id);
CREATE INDEX idx_attempts_user_exam ON attempts(user_id, exam_id);
CREATE INDEX idx_exams_language ON exams(language);
CREATE INDEX idx_exams_created_by ON exams(created_by);
CREATE INDEX idx_audit_events_attempt ON attempt_audit_events(attempt_id);

INSERT INTO exam_types (slug, name) VALUES
  ('seriado_ufmg', 'Seriado UFMG'),
  ('enem', 'ENEM'),
  ('concurso', 'Concursos Públicos'),
  ('ingles', 'Inglês'),
  ('ti', 'TI'),
  ('outro', 'Outro')
ON CONFLICT DO NOTHING;

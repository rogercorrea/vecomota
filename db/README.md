# Sobre o antigo `seed_example.sql`

Esse arquivo existiu numa versão anterior do schema, quando `exams.created_by`
era opcional. Agora toda prova precisa de um dono real (`created_by NOT NULL`),
e usuários só existem depois do primeiro login com Google — ou seja, não dá
mais pra popular uma prova de exemplo durante a inicialização do Postgres
(`docker-entrypoint-initdb.d` roda antes de qualquer login acontecer).

**Como carregar o conteúdo de exemplo agora:**

1. Suba o projeto (`docker compose up --build`) e faça login em
   `http://localhost:8000/admin.html` (seu e-mail precisa estar em
   `ADMIN_EMAILS` no `.env`).
2. Use o botão "Carregar exemplo" — ele busca `example_import.json` — e
   clique em "Importar".

Isso cria a prova já vinculada à sua conta, com `is_public = true` (catálogo
oficial, porque foi importada via admin).

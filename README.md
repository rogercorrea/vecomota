# Vecomota — plataforma de simulados (Docker + Sanic + Postgres + Login Google)

Modelo: **qualquer usuário logado cria sua própria prova** (dono = quem criou) e
compartilha um link secreto com quem for responder. Um papel de **admin**
separado cuida do catálogo público oficial (Seriado UFMG, ENEM etc.) e tem
visão geral do sistema. Categorias (ex: "Windows"/"Segurança" numa prova de TI,
"Matemática"/"Inglês" numa prova estilo ENEM) pertencem à **prova**, não a um
tipo genérico — cada prova define seu próprio vocabulário, e toda questão é
obrigatoriamente vinculada a uma categoria.

## O que já funciona

- Login com Google (OAuth 2.0), sessão via cookie httpOnly com JWT.
- Qualquer usuário cria provas (`POST /api/my/exams/import`) e lista as suas
  (`GET /api/my/exams`, com o link de compartilhamento pronto).
- Acesso via link secreto (`GET /api/exams/shared/<token>`), independente de a
  prova estar no catálogo público.
- Toda questão pertence a uma categoria da própria prova (criada automaticamente
  na importação — sem precisar cadastrar categoria à parte antes).
- Correção no servidor com nota mínima opcional, limite de tempo opcional
  (com sinalização de atraso), monitoramento de foco e proteção de cópia opcionais.
- Auditoria de integridade separada da correção (`POST /api/attempts/<id>/audit`).
- **Relatórios por categoria**: `GET /api/exams/<id>/reports` mostra o desempenho
  de cada pessoa que respondeu, separado por categoria — é o que o dono da prova
  usa pra ver onde o grupo (ou uma pessoa) está mais fraco.
- Painel de admin (`admin.html`) para o catálogo oficial: importar em lote,
  criar tipos de prova, publicar/ocultar, ver relatório, copiar link.

## O que **não** está pronto (próximos passos, se fizer sentido pra vocês)

- **Tela para usuário comum criar prova.** Hoje a criação por qualquer usuário
  existe só via API (`POST /api/my/exams/import`) — não tem uma UI própria
  ainda (o `admin.html` é só para quem tem `is_admin`). Se o uso real vai ser
  "qualquer pessoa cria e compartilha", vale construir essa tela.
- **Frontend integrado.** O HTML interativo de prova (`simulado-interativo.html`)
  ainda roda com dados fixos e `window.storage` local, não chamando essa API de
  verdade (iniciar/finalizar tentativa, enviar auditoria). Os recursos (tempo,
  aviso de mouse, nota mínima) já estão implementados nele, só falta plugar nas
  chamadas reais.
- **Hospedagem.** Este projeto roda localmente com Docker, mas o ambiente onde eu gero
  código (aqui no chat) não mantém servidores no ar — o container se encerra ao final da
  conversa. Para ficar acessível de verdade (ex: da rua, do celular dela), vocês vão
  precisar rodar este `docker compose up` em algum lugar que fique ligado: um VPS
  (Hetzner, DigitalOcean, Contabo — a partir de uns R$25/mês) ou uma plataforma que
  aceita `docker-compose` (Railway, Render, Fly.io).

## Como rodar localmente

1. **Criar credenciais do Google OAuth:**
   - Acesse [Google Cloud Console](https://console.cloud.google.com/) → *APIs e Serviços* → *Credenciais*.
   - Crie um *ID do cliente OAuth* do tipo *Aplicativo da Web*.
   - Em "URIs de redirecionamento autorizados", adicione: `http://localhost:8000/api/auth/google/callback`.
   - Copie o Client ID e o Client Secret.

2. **Configurar variáveis de ambiente:**
   ```bash
   cp .env.example .env
   # edite .env e preencha GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET e JWT_SECRET
   ```

3. **Subir os containers:**
   ```bash
   docker compose up --build
   ```
   Na primeira subida, o Postgres roda automaticamente `db/init.sql` (schema —
   já vem com os tipos de prova básicos, mas nenhuma prova: toda prova precisa
   de um dono real, que só existe depois do primeiro login).

4. **Fazer login e criar/importar sua primeira prova:**
   ```bash
   # login (abre no navegador, não em curl, por causa do redirect do Google)
   open http://localhost:8000/api/auth/google/login

   # se seu e-mail estiver em ADMIN_EMAILS, a tela de admin já importa por você:
   open http://localhost:8000/admin.html
   # (botão "Carregar exemplo" carrega db/example_import.json)
   ```
   Qualquer usuário (admin ou não) também pode criar a própria prova direto pela
   API — ver seção "Minhas provas" abaixo.

## Idiomas (interface × conteúdo)

São dois eixos independentes, tratados separadamente de propósito:

- **Idioma da interface** (`users.locale`, um de `pt-BR` / `en` / `es`): preferência
  de navegação da pessoa. Vem do perfil do Google no primeiro login (campo `locale`
  do Google, normalizado) e pode ser trocado a qualquer momento em
  `PATCH /api/me/locale`, sem depender do idioma de nenhuma prova específica.
- **Idioma do conteúdo** (`exams.language`): propriedade da prova em si. Um simulado
  de Inglês tem texto em inglês por natureza, mesmo que o usuário navegue com a
  interface em português — por isso `GET /api/exams?language=en` filtra por esse
  campo, separado do `?type=`.

O backend não traduz nada — ele só devolve dados e códigos de erro (`not_authenticated`,
`unsupported_locale` etc.). Toda a tradução da interface fica no frontend, lendo os
dicionários em `frontend/i18n/strings.<locale>.json` (já com pt-BR, en e es prontos
com as strings usadas no simulado interativo). Quando integrarmos aquele HTML à API,
essa é a base que ele vai consumir.



```
vecomota/
├── docker-compose.yml
├── .env.example
├── db/
│   ├── init.sql              # schema
│   ├── README.md             # nota sobre o antigo seed_example.sql
│   └── example_import.json   # exemplo do formato JSON padrão (2 provas, categorias diferentes)
├── frontend/
│   ├── i18n/                     # dicionários de interface (pt-BR, en, es)
│   ├── admin.html                # tela de admin (importação, catálogo, relatórios)
│   ├── simulado-interativo.html  # tela de prova pro estudante
│   └── example_import.json       # cópia usada pelo botão "Carregar exemplo" do admin
└── backend/
    ├── Dockerfile
    ├── requirements.txt
    ├── app.py              # rotas Sanic
    ├── auth.py             # OAuth Google + sessão JWT
    ├── db.py               # pool de conexão asyncpg
    └── import_schema.py    # validação do formato JSON padrão + slugify de categoria
```

## Dono, compartilhamento e categorias

- **Toda prova tem um dono** (`exams.created_by`) — quem criou. Só o dono (e
  admins) pode editar visibilidade, apagar, ou ver relatórios/auditoria da prova.
- **Link de compartilhamento**: toda prova nasce com um `share_token` (UUID)
  aleatório. `GET /api/exams/shared/<token>` dá acesso às questões independente
  de a prova estar no catálogo público (`is_public`) — é assim que o dono
  compartilha com quem quiser, sem precisar publicar pra todo mundo ver.
- **`POST /api/my/exams/import`** — qualquer usuário logado cria sua própria
  prova (mesmo formato JSON do admin). Nasce sempre privada
  (`is_public = false`, ignorando o que vier no JSON) — só existe pra quem tem
  o link. **`GET /api/my/exams`** lista as suas, já com a URL do link pronta.
- **Categorias pertencem à prova**, não a um tipo genérico — cada prova define
  seu próprio vocabulário a partir do campo `"category"` de cada questão no
  JSON (ex: "Windows"/"Segurança" numa prova de TI, "Matemática"/"Inglês" numa
  prova estilo ENEM). A categoria é criada automaticamente na primeira vez que
  aparece nessa prova (reaproveitada se o nome já existir ali). Toda questão
  **precisa** ter uma categoria — não tem mais opção de deixar em branco.
- **Relatórios**: `GET /api/exams/<id>/reports` (dono/admin) devolve, para cada
  tentativa finalizada, a nota geral e o desempenho por categoria — a base pra
  responder "essa turma está fraca em quê?". `GET /api/exams/<id>/attempts/<attempt_id>/report`
  é o mesmo recorte, mas de uma tentativa só (o próprio candidato também pode
  ver o seu).

## Tipos de prova (`exam_types`) — catálogo, não classificação

`exam_types` (Seriado UFMG, ENEM, Concursos, Inglês, TI, Outro) é só um rótulo
amplo usado no catálogo público e nas estatísticas gerais (`/api/me/stats`) —
não tem relação com as categorias de dentro da prova. Só admins criam tipos
novos (`POST /api/admin/exam-types`); ao criar sua própria prova, escolha um
tipo existente (ou use `"outro"`).

## Nota mínima, monitoramento de foco e proteção de cópia

Três campos novos em `exams`, todos opcionais por prova:

- **`passing_score_percent`** — nota mínima em %. Se `NULL`, a prova não tem
  reprovação, só nota. `attempts.passed` é calculado na correção.
- **`anti_cheat_enabled`** — quando ligado, o frontend registra trocas de aba
  (`visibilitychange`) e tentativas de copiar/colar durante a prova, e envia
  esses números junto com as respostas. **Isso é só um indicador para revisão
  humana** — o backend nunca reprova ou penaliza a nota com base nisso, e a
  pessoa que está fazendo a prova vê um aviso claro de que o monitoramento
  está ativo (nada de rastreamento oculto) e também vê o próprio resultado
  dos indicadores depois de corrigir. Os limiares em `_summarize_integrity()`
  (função em `backend/app.py`) são só um ponto de partida — ajuste ou remova
  como fizer sentido.
- **`copy_protection_enabled`** — dificulta cópia casual do enunciado
  (desabilita seleção de texto, clique direito e `Ctrl+C`/`Ctrl+U`/`Ctrl+P`).
  **Isso não é proteção real contra cópia** — captura de tela, "ver código-fonte"
  em alguns navegadores e fotografar a tela continuam funcionando. Trate como
  fricção para desestimular cópia rápida, não como garantia técnica.
- **"Mouse saiu da área"** — na primeira vez que o cursor sai da janela durante
  a prova (evento `mouseleave`), a pessoa vê um aviso explícito de que isso fica
  registrado e que comportamento suspeito repetido pode levar à desclassificação
  **na revisão**. Ocorrências seguintes só incrementam o contador, sem repetir o
  aviso — pra não virar um pop-up irritante a cada vez que ela troca de janela
  sem querer.

O simulado interativo (`simulado-interativo.html`) já implementa os quatro
recursos localmente, com os valores de exemplo em `EXAM_CONFIG` no início do
`<script>` — dá pra ligar/desligar cada um ali pra testar o comportamento.

## Ciclo de vida da tentativa: iniciar → responder → finalizar → auditar

A tentativa (`attempts`) nasce em `POST /api/exams/<id>/attempts/start`
(guarda `started_at`) e só fica completa em
`POST /api/exams/<id>/attempts/<attempt_id>/submit` (calcula nota, aprovação e
se passou do tempo). Isso existe por dois motivos:

1. **Limite de tempo** (`exams.time_limit_minutes`, `NULL` = prova infinita):
   só dá pra saber se alguém estourou o tempo se o sistema souber quando a
   tentativa começou. Na finalização, `late: true` é calculado comparando
   `submitted_at - started_at` com o limite — de novo, é um sinalizador, a
   prova continua sendo corrigida e a nota registrada normalmente.
2. **Auditoria detalhada**: `POST /api/attempts/<attempt_id>/audit` recebe o
   log de eventos com horário (`mouse_leave`, `tab_switch`, `copy_attempt`...)
   depois que a prova termina. Fica separado da correção de propósito — o
   caminho crítico (salvar a nota) não depende do envio da auditoria, que pode
   falhar ou demorar sem prejudicar o resultado. O dono da prova (ou um admin)
   revisa esse log em `GET /api/exams/<exam_id>/attempts/<attempt_id>/audit`.

Tentativas nunca finalizadas (`submitted_at IS NULL` — a pessoa fechou a aba
no meio, por exemplo) não entram no histórico nem nas estatísticas.

## Tela de admin e importação de conteúdo

- **Quem tem acesso:** e-mails listados em `ADMIN_EMAILS` no `.env` (separados por
  vírgula) recebem `is_admin = true` automaticamente ao logar com Google. Tirar um
  e-mail da lista revoga o acesso no próximo login dessa pessoa. Isso dá acesso ao
  catálogo oficial e à supervisão geral — **não** é pré-requisito pra criar prova
  própria (isso qualquer usuário logado faz via `/api/my/exams/import`).
- **Onde fica:** depois de rodar `docker compose up`, acesse
  `http://localhost:8000/admin.html`. De lá dá pra colar/subir um JSON, criar novos
  tipos de prova, publicar/ocultar/excluir provas, copiar o link de compartilhamento
  e abrir o relatório por categoria de qualquer prova do sistema.
- **Formato JSON padrão:** documentado com comentários no topo de
  `backend/import_schema.py`, com exemplo em `db/example_import.json` (o botão
  "Carregar exemplo" na tela de admin usa esse arquivo — traz uma prova de
  Inglês e uma de TI, cada uma com suas próprias categorias). Resumo:

  ```json
  {
    "exams": [
      {
        "exam_type": "ti",
        "title": "Simulado de TI — Fundamentos",
        "language": "pt-BR",
        "questions": [
          {
            "category": "Windows",
            "question_text": "...",
            "explanation": "...",
            "options": [
              { "label": "A", "text": "...", "correct": false },
              { "label": "B", "text": "...", "correct": true }
            ]
          },
          {
            "category": "Segurança",
            "question_text": "...",
            "options": [ "..." ]
          }
        ]
      }
    ]
  }
  ```

  `"category"` é obrigatória em toda questão e é criada automaticamente na
  prova (não precisa cadastrar categoria antes) — ver seção "Dono,
  compartilhamento e categorias" acima.
- **Validação:** a importação roda em uma transação — se qualquer prova do lote
  tiver um erro (campo faltando, categoria ausente, questão sem alternativa
  marcada como correta, duas alternativas corretas, tipo de prova inexistente...),
  nada é gravado, e a resposta lista todos os erros encontrados de uma vez.
- **Admin importando vs. usuário comum criando:** os dois usam o mesmo formato
  JSON e a mesma lógica de inserção por baixo, mas `POST /api/admin/exams/import`
  respeita o `is_public` do JSON (catálogo oficial), enquanto
  `POST /api/my/exams/import` sempre força `is_public = false` (prova privada,
  só acessível pelo link) — não importa o que o JSON diga.

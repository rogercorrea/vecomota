<p align="center">
  <img src="frontend/assets/logo.png" alt="Vecomota — Vê como tá." width="260">
</p>

<h1 align="center">Vecomota</h1>
<p align="center"><b>Vê como tá.</b> Descubra como está o conhecimento — o seu ou de quem você acompanha.</p>

<p align="center">
  <img alt="License: AGPL-3.0" src="https://img.shields.io/badge/license-AGPL--3.0-blue.svg">
  <img alt="Backend" src="https://img.shields.io/badge/backend-Python%20%2F%20Sanic-2bb3a3.svg">
  <img alt="Database" src="https://img.shields.io/badge/database-PostgreSQL-1a2456.svg">
  <img alt="Deploy" src="https://img.shields.io/badge/deploy-Docker%20%7C%20Railway-f2685f.svg">
</p>

---

**Vecomota** é uma plataforma de simulados com correção automática, login com Google,
categorias por prova e relatórios de desempenho — o suficiente pra transformar um
monte de PDF de gabarito em provas cronometradas, corrigidas na hora, com histórico
e relatório de onde a pessoa está mais fraca.

Nasceu de uma necessidade bem concreta: acompanhar de perto os simulados da minha
filha pro Seriado UFMG, sem depender de planilha e PDF impresso. Virou uma
plataforma completa — e agora está aberta pra quem quiser usar, adaptar ou
aprender com o código.

## ✨ O que ela faz

- 🔐 **Login com Google** — qualquer conta cria e gerencia suas próprias provas.
- 📝 **Qualquer pessoa cria uma prova** colando um JSON (ou subindo um arquivo) —
  não precisa ser admin. Nasce privada, com um link secreto pra compartilhar.
- ⏱️ **Correção automática**, com nota mínima opcional, tempo de prova opcional
  (com sinalização de quem estourou o prazo) e categorias que pertencem à prova
  (não a um tipo genérico fixo).
- 📊 **Relatório de desempenho por categoria** — pra quem aplicou a prova ver onde
  o grupo (ou uma pessoa) está mais fraco.
- ✅❌ **Detalhe questão a questão** de cada tentativa — o que acertou, o que errou,
  a explicação de cada uma — com um botão **"Copiar"** que gera um resumo em texto
  puro pronto pra colar numa IA e pedir um plano de estudo em cima do que errou.
- ⏳ **Cooldown de 24h** pra refazer a mesma prova — sem decorar resposta de um dia
  pro outro.
- 🕵️ **Monitoramento de foco e proteção de cópia opcionais** — indicadores pra
  revisão humana, nunca reprovação automática nem rastreamento oculto.
- 🌎 **Interface em pt-BR, en-US ou es**, com seletor de idioma (bandeiras) em
  toda tela — idioma da interface e idioma do conteúdo da prova são eixos
  independentes.
- 🛠️ **Painel de admin** pra curar um catálogo público oficial, separado das provas
  privadas de cada usuário.

## 🚀 Comece em 2 minutos

```bash
git clone https://github.com/rogercorrea/vecomota.git
cd vecomota
cp .env.example .env   # preencha GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET e JWT_SECRET
docker compose up --build
```

Depois é só logar em `http://localhost:8000/api/auth/google/login` e criar sua
primeira prova em `minhas-provas.html`. Passo a passo completo (incluindo como
gerar as credenciais do Google) na seção [Como rodar localmente](#como-rodar-localmente).

## 📚 Índice

- [Como rodar localmente](#como-rodar-localmente)
- [Deploy na Railway](#deploy-na-railway)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Como abrir/compartilhar uma prova](#como-abrircompartilhar-uma-prova)
- [Dono, compartilhamento e categorias](#dono-compartilhamento-e-categorias)
- [Tipos de prova (exam_types)](#tipos-de-prova-exam_types)
- [Nota mínima, monitoramento de foco e proteção de cópia](#nota-mínima-monitoramento-de-foco-e-proteção-de-cópia)
- [Ciclo de vida da tentativa](#ciclo-de-vida-da-tentativa)
- [Tela de admin e importação de conteúdo](#tela-de-admin-e-importação-de-conteúdo)
- [Idiomas (interface × conteúdo)](#idiomas-interface--conteúdo)
- [Próximos passos](#próximos-passos)
- [Licença](#licença)

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

## Deploy na Railway

A Railway **não roda `docker-compose.yml`** — cada serviço é configurado
separadamente. O `railway.toml` na raiz do repositório já resolve a parte do
build (aponta pro `backend/Dockerfile`, buildado a partir da raiz pra
conseguir empacotar o `frontend/` junto). Falta configurar o resto pelo painel:

1. **Criar o projeto** apontando pro repositório do GitHub (Railway detecta o
   `railway.toml` sozinho — não precisa mexer em "Root Directory" nem em
   "Dockerfile Path" manualmente).

2. **Adicionar um Postgres:** no projeto, `+ New` → `Database` → `PostgreSQL`.
   Isso cria um serviço separado com seu próprio `DATABASE_URL`.

3. **Configurar as variáveis** do serviço do backend (aba *Variables*):
   ```
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   JWT_SECRET=<gere uma string aleatória longa>
   GOOGLE_CLIENT_ID=...
   GOOGLE_CLIENT_SECRET=...
   GOOGLE_REDIRECT_URI=https://<seu-dominio-da-railway>/api/auth/google/callback
   FRONTEND_URL=https://<seu-dominio-da-railway>
   ADMIN_EMAILS=seu@email.com
   ```
   `${{Postgres.DATABASE_URL}}` é a sintaxe da Railway pra referenciar a variável
   de outro serviço do mesmo projeto — não precisa copiar o valor manualmente.
   Não defina `PORT`: a Railway injeta essa variável sozinha, e o app já lê
   `os.environ["PORT"]` (com fallback pra 8000 se não existir).

4. **Gerar um domínio público:** *Settings* → *Networking* → *Generate Domain*
   (é o que resolve o "Unexposed service" que você viu). Depois de gerado,
   volte no passo 3 e troque `<seu-dominio-da-railway>` pelo domínio real nas
   duas variáveis que dependem dele.

5. **Atualizar o Google Cloud Console:** adicione
   `https://<seu-dominio-da-railway>/api/auth/google/callback` nas URIs de
   redirecionamento autorizadas (o `localhost` continua lá também, pra
   desenvolvimento local).

6. **Aplicar o schema no Postgres da Railway** (ela não roda o
   `docker-entrypoint-initdb.d` como o Postgres local — isso é só um mecanismo
   da imagem oficial rodando localmente). Pegue o `DATABASE_URL` na aba
   *Variables* do serviço Postgres e rode, da sua máquina:
   ```bash
   # Debian: sudo apt install postgresql-client (se ainda não tiver o psql)
   psql "postgresql://usuario:senha@host:porta/banco" -f db/init.sql
   ```

7. **Fazer o deploy** (a Railway já deve ter feito automaticamente após o
   push — se não, *Deployments* → *Redeploy*). Depois, acesse
   `https://<seu-dominio>/admin.html`, faça login com um e-mail que esteja em
   `ADMIN_EMAILS`, e importe o exemplo pra testar o fluxo completo.

## Estrutura do repositório

```
vecomota/
├── docker-compose.yml
├── railway.toml               # config de build pra Railway (aponta pro backend/Dockerfile)
├── .env.example
├── db/
│   ├── init.sql              # schema
│   ├── README.md             # nota sobre o antigo seed_example.sql
│   └── example_import.json   # exemplo do formato JSON padrão (2 provas, categorias diferentes)
├── frontend/
│   ├── assets/logo.png            # identidade visual
│   ├── i18n/                      # dicionários de interface (pt-BR, en, es — 142 chaves)
│   ├── i18n.js                    # módulo de i18n compartilhado pelas 3 telas
│   ├── app-common.js              # funções JS compartilhadas (admin.html + minhas-provas.html)
│   ├── admin.html                 # tela de admin (importação, catálogo, relatórios)
│   ├── minhas-provas.html         # autoatendimento: qualquer usuário cria/gerencia suas provas
│   ├── simulado-interativo.html   # tela de prova pro estudante, ligada à API real
│   └── example_import.json        # cópia usada pelo botão "Carregar exemplo"
└── backend/
    ├── Dockerfile
    ├── requirements.txt
    ├── app.py              # rotas Sanic
    ├── auth.py             # OAuth Google + sessão JWT
    ├── db.py               # pool de conexão asyncpg
    └── import_schema.py    # validação do formato JSON padrão + slugify de categoria
```

## Como abrir/compartilhar uma prova

- **Quem cria** vai em `minhas-provas.html`, cola o JSON, cria a prova. A tela
  já mostra o link: `.../simulado-interativo.html?token=<share_token>`.
- **Quem responde** abre esse link, faz login (se ainda não estiver), vê uma
  tela inicial com o histórico dela nessa prova, clica em "Começar" — só aí o
  cronômetro (se houver) começa a contar.
- Também dá pra abrir uma prova pública do catálogo direto pelo id:
  `.../simulado-interativo.html?exam=<id>`.

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
  ver o seu). `GET /api/exams/<id>/attempts/<attempt_id>/detail` vai mais fundo:
  questão a questão, o que foi respondido, o que era certo e a explicação — a
  base do botão "Detalhes"/"Copiar" usado pra montar um plano de estudo.

## Tipos de prova (exam_types)

Catálogo, não classificação: `exam_types` (Seriado UFMG, ENEM, Concursos, Inglês, TI, Outro) é só um rótulo
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
- **Cooldown de 24h**: depois de uma tentativa finalizada, a mesma prova só
  pode ser refeita 24h depois (`RETRY_COOLDOWN_HOURS` em `backend/app.py`) —
  aplicado tanto no backend (`POST /attempts/start` responde 429) quanto no
  frontend (botão desabilitado com contagem regressiva).

O simulado interativo (`simulado-interativo.html`) já implementa esses
recursos localmente, com os valores de exemplo em `EXAM_CONFIG` no início do
`<script>` — dá pra ligar/desligar cada um ali pra testar o comportamento.

## Ciclo de vida da tentativa

Iniciar → responder → finalizar → auditar. A tentativa (`attempts`) nasce em `POST /api/exams/<id>/attempts/start`
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
`unsupported_locale` etc.). Toda a tradução da interface fica no frontend.

### Como funciona o i18n do frontend

`frontend/i18n.js` é o módulo compartilhado pelas 3 telas (`admin.html`,
`minhas-provas.html`, `simulado-interativo.html`), lido a partir dos dicionários
completos em `frontend/i18n/strings.<locale>.json` (pt-BR, en, es — 142 chaves,
cobrindo desde texto estático até mensagens de erro e templates com variável).

- **Prioridade pra decidir o idioma inicial**: escolha manual salva neste
  navegador (`localStorage`) → preferência salva na conta (`users.locale`) →
  idioma do navegador (`navigator.languages`) → `pt-BR` como último fallback.
- **Texto estático** vira `<span data-i18n="chave">`, `data-i18n-placeholder`,
  `data-i18n-title`, `data-i18n-alt` ou `data-i18n-html` (esse último quando o
  texto tem markup embutido, tipo um `<code>` dentro da frase) — `i18n.js`
  aplica tudo sozinho ao carregar e a cada troca de idioma.
- **Texto gerado em JS** (tabelas, mensagens de erro, templates com contagem/
  nota/data) usa `t("chave", {var: valor})`, com interpolação de `{var}` no
  template.
- **Seletor de idioma**: qualquer página só precisa ter um
  `<select id="locale-select" autocomplete="off">` vazio — `i18n.js` popula as
  opções (com bandeira) e escuta a troca sozinho. O `autocomplete="off"` não é
  cosmético: sem ele, o Chrome tenta "restaurar" o valor do select depois de um
  reload e dispara um `change` sozinho, revertendo o idioma escolhido.
- **Conteúdo dinâmico e troca de idioma**: `data-i18n` só cobre o que já está
  no HTML — uma tabela ou um card desenhado via JS só pega a tradução no
  momento em que é desenhado. Por isso cada tela registra um callback via
  `onI18nReady(fn)` (disparado a cada troca de idioma, não só no carregamento)
  que redesenha o que precisa: `checkAuth()` de novo em `admin.html`/
  `minhas-provas.html` (refaz o user-box e a tabela de provas), e em
  `simulado-interativo.html` a tela inicial é redesenhada inteira, mas a prova
  em andamento só tem o texto do rótulo de cada questão atualizado — sem
  recriar o formulário, pra não perder as alternativas já marcadas.

## Próximos passos

O que ainda não está pronto, mas faria sentido implementar:

- **Planos (Gratuito/Profissional/Escola).** Foi desenhado (limite de provas
  ativas por plano, organizações tipo "escola" com múltiplos professores
  compartilhando visibilidade) mas ainda não entrou no código.
- **Múltiplos workers/réplicas.** O `STATE_STORE` do OAuth (`backend/app.py`)
  e o cooldown de 24h assumem um único processo/réplica. Rodando mais de um
  worker, isso precisa migrar pra Redis (ou pra uma tabela do Postgres).

Contribuições são bem-vindas — abra uma issue ou mande um PR.

## Licença

Distribuído sob a licença **[AGPL-3.0](LICENSE)**. Em resumo: pode usar, estudar,
modificar e redistribuir livremente — inclusive rodando sua própria instância —
desde que o código-fonte (com as suas modificações, se houver) continue
disponível para quem usa o serviço, e mantendo os créditos originais.

# RDV — Relatório de Despesas de Viagem

Aplicação Streamlit para envio, análise e exportação dos RDVs de motoristas e ajudantes de motorista. Cada colaborador usa seu próprio acesso e as telas de gestão permanecem protegidas por credenciais administrativas.

## Recursos

- formulário mobile-first gerado a partir do período ativo e do colaborador autenticado;
- acesso individual com senha temporária aleatória armazenada somente como hash;
- redefinição administrativa de senha, exibida uma única vez;
- aprovação em duas etapas, pelo analista e pelo gestor;
- folha concluída com linhas para assinaturas físicas do colaborador, analista e gestor;
- folha disponível para visualização e download em PDF e PNG;
- exclusão administrativa da folha para liberar um novo preenchimento;
- criação e ativação automáticas dos períodos de 13 dias, com um dia de intervalo, a partir de 28/09/2026;
- seletor temporário de perfil no painel para alternar entre analista e gestor durante os testes;
- modelos distintos para motorista e ajudante;
- total da quinzena formado somente por diária e ticket, com hotel e adiantamento mantidos como informações separadas em `Decimal`;
- correção do mesmo protocolo quando um RDV é rejeitado;
- painel com filtros, visualização da folha em PDF, aprovação, rejeição e indicadores;
- cadastro e desativação de colaboradores;
- criação, ativação e encerramento de períodos;
- PDF A4 paisagem baseado no formulário da empresa;
- exportação individual em PDF, Excel e CSV, além de Excel por filtro/período;
- SQLite local e PostgreSQL em produção.

## Estrutura

```text
.
├── app.py
├── assets/logo_jr.png
├── auth.py
├── database.py
├── exports.py
├── models.py
├── services.py
├── ui.py
├── utils.py
├── pages/
│   ├── formulario.py
│   ├── admin_login.py
│   ├── admin_dashboard.py
│   ├── admin_colaboradores.py
│   └── admin_periodos.py
├── tests/
├── requirements.txt
├── requirements-dev.txt
└── .env.example
```

## Instalação local

Requer Python 3.11 ou superior.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Gere um hash bcrypt para a senha administrativa:

```powershell
python -c "import bcrypt; print(bcrypt.hashpw(b'SUA_SENHA', bcrypt.gensalt()).decode())"
```

Edite `.env` e informe os usuários e hashes de senha do analista e do gestor. A senha em texto puro não é armazenada. Para instalações antigas, `ADMIN_PASSWORD_HASH` funciona temporariamente para os usuários `analista` e `gestor`, além do login administrativo anterior.

Execute:

```powershell
streamlit run app.py
```

As tabelas e o arquivo `data/rdv.db` são criados automaticamente no primeiro acesso. Entre em `/acesso` com uma conta administrativa e cadastre os colaboradores. O usuário e a senha temporária são mostrados no momento do cadastro; a senha original não pode ser recuperada depois.

## PostgreSQL

Crie um banco e defina a URL no `.env` ou no gerenciador de segredos da hospedagem:

```dotenv
DATABASE_URL=postgresql://usuario:senha@host:5432/rdv
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=$2b$12$hash_bcrypt_completo
ANALYST_USERNAME=analista
ANALYST_PASSWORD_HASH=$2b$12$hash_bcrypt_do_analista
MANAGER_USERNAME=gestor
MANAGER_PASSWORD_HASH=$2b$12$hash_bcrypt_do_gestor
```

A aplicação seleciona o driver psycopg 3 automaticamente para URLs iniciadas em `postgresql://`. Em produção, mantenha `.env` fora do versionamento e prefira secrets da plataforma.

## Testes e verificação

```powershell
pip install -r requirements-dev.txt
pytest -q
ruff check .
```

Os testes de serviço usam um SQLite temporário e não alteram o banco de desenvolvimento.

## Regras importantes

- existe no máximo um período ativo;
- a sequência automática começa em 28/09/2026 a 10/10/2026;
- cada colaborador autenticado só preenche o próprio RDV;
- colaborador e período formam uma chave única no RDV;
- RDVs enviados/aprovados não podem ser duplicados;
- RDV rejeitado é reaberto e reenviado no mesmo protocolo;
- somente o analista aprova a primeira etapa e somente o gestor conclui a aprovação;
- assinaturas são feitas fisicamente na folha impressa;
- a gravação do cabeçalho e de todos os dias ocorre em uma única transação;
- nenhum valor monetário é armazenado como `float`.

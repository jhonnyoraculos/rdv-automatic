# RDV — Relatório de Despesas de Viagem

Aplicação Streamlit para envio, análise e exportação dos RDVs de motoristas e ajudantes de motorista. A área do colaborador não exige login; todas as telas de gestão são protegidas por credenciais administrativas.

## Recursos

- formulário responsivo gerado a partir do período ativo;
- local, data e assinatura desenhada obrigatórios no envio, impressos na folha do RDV;
- aprovação em duas etapas, com assinatura do analista e aprovação final assinada pelo gestor;
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

As tabelas e o arquivo `data/rdv.db` são criados automaticamente no primeiro acesso. Entre em `/admin`, cadastre os colaboradores e crie um período ativo antes de liberar o formulário público.

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
- colaborador e período formam uma chave única no RDV;
- RDVs enviados/aprovados não podem ser duplicados;
- RDV rejeitado é reaberto e reenviado no mesmo protocolo;
- somente o analista aprova a primeira etapa e somente o gestor conclui a aprovação;
- a gravação do cabeçalho e de todos os dias ocorre em uma única transação;
- nenhum valor monetário é armazenado como `float`.

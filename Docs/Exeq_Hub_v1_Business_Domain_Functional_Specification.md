# EXEQ Hub v1 — Business Domain & Functional Specification

| Campo | Valor |
|-------|-------|
| Documento | Exeq_Hub_v1 |
| Versão | **1.1.0** (promovido) |
| Status | **Fonte oficial de regras de negócio** |
| Data promoção | 2026-07-19 |
| Origem | Especificação Técnica Fábrica Reconstrução Django (Jul/2026) |
| Nota | Decisões de plataforma (storage, outbox, membership, certificados) estão no v2/v3.1; em conflito de *dados*, prevalece v3.1. Em conflito de *regra funcional*, prevalece este v1. |

---

## Prefácio da promoção

Este arquivo promove o conteúdo da especificação de domínio Django da fábrica para a hierarquia oficial do Contrato EXEQ Hub (Documento 1).

Ajustes de identidade/RBAC do v3.1 (**User global + TenantMembership + TenantRole**, login com 	enant_slug) **substituem** o modelo User 1:1 Tenant e Groups globais descritos abaixo nas seções de ccounts, sem alterar regras fiscais, FSM de emissão, idempotência, DAS ou testes de aceite de negócio.

---

ESPECIFICAÇÃO TÉCNICA PARA A FÁBRICA
Reconstrução do zero em Django/Python da plataforma de
Cobrança + Emissão de NFS-e (base de referência: exeq-nfse-core)
Documento orientador de desenvolvimento — uso interno da fábrica de software
Julho de 2026
Como usar este documento
Este documento é uma especificação cirúrgica para a fábrica construir, do zero, em Django/Python, uma nova versão da plataforma de cobrança e emissão de NFS-e. Não é um resumo — é a referência de trabalho: cada app Django listado deve ser implementado com os models, campos, regras de negócio, endpoints e testes descritos aqui.
Premissas confirmadas para este projeto (registradas aqui para não se perderem ao longo do desenvolvimento):
Não existe cliente em produção nem base de dados real a preservar — este é um desenvolvimento greenfield (do zero), não uma migração de dados.
A base de comparação é o código-fonte atual do repositório exeq-nfse-core (Node.js/TypeScript/Fastify/PostgreSQL), usado aqui apenas como especificação de regras de negócio já validadas — o código em si não será portado nem reaproveitado.
A plataforma de destino é Django (Python), com Django REST Framework para a API.
O desenvolvimento contará com apoio de IA (Cursor). Por isso, cada seção deste documento traz regras de negócio explícitas e testes obrigatórios: a IA acelera a escrita de código, mas não garante sozinha que uma regra fiscal foi implementada corretamente — os testes listados são o critério objetivo de aceite de cada entrega, e devem ser escritos e aprovados por revisão humana antes de considerar o módulo pronto.
Onde o sistema atual usa PostgreSQL com Row-Level Security (RLS) para isolamento entre empresas (tenants), a nova plataforma deve manter PostgreSQL e reproduzir esse isolamento (ver Seção 3.3) — este é o único elemento de infraestrutura do sistema atual que deve ser preservado, por ser um mecanismo de segurança crítico, não um detalhe de implementação descartável.
Regra de ouro para a fábrica
Nenhuma tela ou endpoint pode ser dado como concluído apenas por "funcionar visualmente". Cada item das listas de "Regras de negócio obrigatórias" e "Testes mínimos obrigatórios" deste documento é critério de aceite. Itens não implementados devem ser reportados explicitamente, não silenciosamente ignorados.
1. Visão geral do sistema a construir
A plataforma é um SaaS multi-tenant (multi-empresa) para emissão de Notas Fiscais de Serviço Eletrônicas (NFS-e) e gestão de cobrança, incluindo apuração de tributos do Simples Nacional (DAS). Cada empresa cliente (tenant) tem seus próprios usuários, prestadores, clientes/tomadores, catálogo de serviços, regras fiscais e notas emitidas — visíveis apenas para ela.
O sistema se organiza em sete domínios de negócio, que devem virar sete apps Django (mais os apps técnicos transversais de autenticação e integrações). A ordem abaixo é também a ordem de dependência recomendada para o desenvolvimento (cada app depende dos anteriores):
#
App Django
Domínio de negócio
Depende de
1
accounts
Empresas (tenants), usuários, papéis de acesso (RBAC), login
—
2
master_data
Cadastro de prestadores, clientes/tomadores e catálogo de serviços
accounts
3
fiscal
Perfis fiscais, catálogo de regras tributárias municipais, resolução de alíquota
accounts, master_data
4
issuance
Emissão, cancelamento e reprocessamento de NFS-e (máquina de estados)
master_data, fiscal
5
billing
Cobrança, integração com gateway de pagamento, webhooks
master_data, issuance
6
das
Guias DAS/DARF do Simples Nacional
master_data
7
channel
Atendimento via WhatsApp com extração de dados por IA
issuance, master_data
—
integrations
Adaptadores para provedores externos (Focus NFe, Betha, gateway de pagamento, Receita Federal)
usado por issuance, billing, das
Tabela 1 — Apps Django e ordem de dependência. Esta tabela também define a ordem sugerida de sprints (Seção 12).
2. Arquitetura alvo
2.1 Stack de destino
Camada
Tecnologia recomendada
Linguagem/Framework
Python 3.12+ / Django 5.x
API
Django REST Framework (DRF)
Banco de dados
PostgreSQL 16 (mantido do sistema atual — ver 3.3 sobre RLS)
Autenticação
djangorestframework-simplejwt (JWT) + django.contrib.auth
RBAC
Groups e Permissions nativos do Django, mapeando os papéis atuais
Segredos por tenant
Campo criptografado (django-cryptography ou Fernet manual) — nunca texto plano
Filas / jobs assíncronos
Celery + Redis (equivalente ao BullMQ/Redis atual)
Testes
pytest-django + factory_boy, com suíte equivalente à listada em cada app
Assinatura digital de XML
signxml ou xmlsec (equivalente a xml-crypto/node-forge)
Admin/back-office
Django Admin customizado como primeira versão do painel operacional; front-end dedicado pode vir depois
2.2 Padrão de camadas dentro de cada app
Para evitar "fat models" e "fat views" (antipadrão comum em projetos Django que crescem rápido), cada app deve seguir a mesma separação de responsabilidades já usada com sucesso no sistema atual (routes → service → validação de domínio):
Camada Django
Responsabilidade
Equivalente no sistema atual
models.py
Apenas estrutura de dados e constraints de banco
migrations/*.sql (CREATE TABLE)
serializers.py
Validação de entrada/saída da API
schemas Zod em packages/shared
services.py (por app)
Toda a regra de negócio e orquestração; nunca deixar lógica de negócio em views ou serializers
*.service.ts em cada módulo
views.py / viewsets.py
Só orquestra request → service → response; sem regra de negócio
*.routes.ts em cada módulo
exceptions.py
Exceções de domínio nomeadas (ex.: TaxRuleNotFoundError)
classes de erro exportadas nos *.service.ts atuais
2.3 Isolamento multi-tenant (obrigatório, não opcional)
O sistema atual isola dados entre empresas usando Row-Level Security do PostgreSQL, com uma variável de sessão (app.tenant_id) definida a cada requisição. Esse mecanismo deve ser reproduzido na nova plataforma com o mesmo rigor, combinando duas camadas de defesa (defesa em profundidade):
Camada de aplicação: um middleware Django que resolve o tenant a partir do usuário autenticado e injeta esse tenant_id em todo queryset (via um Manager customizado em um TenantModel base, do qual todos os models de negócio herdam).
Camada de banco (preservar): políticas de RLS equivalentes às hoje existentes em cada tabela, com a mesma variável de sessão, aplicadas via uma conexão que executa SET app.tenant_id no início de cada requisição. Isso garante que, mesmo que um bug de aplicação esqueça o filtro por tenant, o banco ainda bloqueia o vazamento entre empresas.
Atenção — ponto crítico de segurança
O sistema atual usa uma flag de bypass de RLS (app.bypass_rls) apenas no fluxo interno de login, antes de o usuário estar autenticado. Esse padrão deve ser recriado com extremo cuidado: o bypass só pode ser ativado por código de infraestrutura (nunca por parâmetro vindo do cliente) e deve ter teste automatizado dedicado provando que nenhuma outra rota consegue acioná-lo.
3. Especificação por app Django
Cada subseção abaixo é a especificação de um app: models com campos e constraints, endpoints, regras de negócio obrigatórias e testes mínimos. Os nomes de campo foram mantidos em português/inglês conforme já usados no domínio, para facilitar a rastreabilidade com o sistema de referência.
App Django: accounts — Empresas (tenants), usuários e RBAC
Tabelas equivalentes no sistema atual: exeq_core.tenants, exeq_core.users, exeq_core.roles, exeq_core.user_roles
Model: Tenant (empresa)
Campo
Tipo Django
Regra / constraint
id
UUIDField (pk)
gen. automática
slug
SlugField
único, máx. 64
legal_name
CharField
obrigatório (razão social)
document
CharField(14)
CNPJ, validar dígito verificador
status
CharField + choices
active | suspended | provisioning, default active
focus_layout
CharField(16)
default 'nfsen'
settings
JSONField
default dict vazio
created_at / updated_at
DateTimeField
auto_now_add / auto_now
Model: User (usuário)
Recomenda-se estender AbstractBaseUser em vez de usar o User padrão do Django, pois o e-mail é único por tenant (não globalmente único) — o User padrão do Django exige username global único.
Campo
Tipo Django
Regra / constraint
id
UUIDField (pk)
gen. automática
tenant
ForeignKey(Tenant)
obrigatório, on_delete=PROTECT
email
EmailField
único em conjunto com tenant (unique_together)
password
CharField
hash via Django password hasher (PBKDF2/Argon2), nunca reaproveitar hash bcrypt sem migração de hasher
name
CharField
obrigatório
is_active
BooleanField
default True
Model: Role / permissões
Usar Django Groups nativos em vez de tabela própria de roles — reduz código a manter.
Campo
Tipo Django
Regra / constraint
Group (nativo)
—
criar 4 grupos seed: tenant_admin, operator, accountant, readonly
Endpoints (Django REST Framework)
Método
Rota
Auth / Permissão
Descrição
POST
/api/v1/auth/login
Não
Autentica por e-mail+senha dentro do escopo do tenant, retorna JWT
POST
/api/v1/auth/refresh
Refresh token
Renova access token
GET/POST
/api/v1/tenants
Admin de plataforma
Cadastro de empresas (uso interno/onboarding)
GET/POST
/api/v1/users
JWT + tenant_admin
Cadastro/listagem de usuários do tenant
PATCH
/api/v1/users/:id
JWT + tenant_admin
Edição/inativação de usuário
Regras de negócio obrigatórias
E-mail é único por tenant, não globalmente (dois tenants podem ter um usuário com o mesmo e-mail).
Senha nunca é retornada em nenhum serializer de saída, nem em logs.
Usuário inativo (is_active=False) não pode autenticar, mesmo com senha correta.
Todo endpoint (exceto login e health-check) exige JWT válido e tenant resolvido.
Ações de escrita em cadastros exigem papel tenant_admin ou operator (equivalente ao WRITE_ROLES atual); leitura é permitida também a accountant e readonly.
Testes mínimos obrigatórios (pytest-django)
Login com credenciais corretas retorna token; com senha errada, 401; com usuário inativo, 401.
Usuário do tenant A nunca aparece em consultas feitas por um usuário do tenant B (teste de isolamento).
Tentativa de criar usuário sem papel de escrita retorna 403.
Criação de tenant gera automaticamente os 4 grupos/papéis padrão associáveis.
App Django: master_data — Cadastros mestres (prestadores, clientes, serviços)
Tabelas equivalentes no sistema atual: exeq_core.providers, exeq_core.customers, exeq_core.service_catalog_items
Model: Provider (prestador)
Campo
Tipo Django
Regra / constraint
tenant
ForeignKey(Tenant)
obrigatório
document
CharField(14)
CNPJ; único em conjunto com tenant
legal_name
CharField
obrigatório
trade_name
CharField
opcional
municipal_registration
CharField(32)
opcional
tax_regime
CharField + choices
simples_nacional | lucro_presumido | lucro_real
address
JSONField
default dict vazio
is_active
BooleanField
default True
Model: Customer (tomador/cliente)
Campo
Tipo Django
Regra / constraint
tenant
ForeignKey(Tenant)
obrigatório
document
CharField(14)
único em conjunto com tenant
document_type
CharField(4) + choices
cpf | cnpj
name
CharField
obrigatório
email
EmailField
opcional
address
JSONField
default dict vazio
is_active
BooleanField
default True
Model: ServiceCatalogItem (serviço)
Campo
Tipo Django
Regra / constraint
tenant
ForeignKey(Tenant)
obrigatório
service_code
CharField(32)
único em conjunto com tenant
description
TextField
obrigatório
lc116_item
CharField(16)
opcional (item da Lei Complementar 116)
is_active
BooleanField
default True
Endpoints (Django REST Framework)
Método
Rota
Auth / Permissão
Descrição
GET/POST
/api/v1/providers
JWT
Listar/criar prestadores
GET/PATCH
/api/v1/providers/:id
JWT
Detalhe/edição de prestador
GET/POST
/api/v1/customers
JWT
Listar/criar tomadores
GET/PATCH
/api/v1/customers/:id
JWT
Detalhe/edição de tomador
GET/POST
/api/v1/services
JWT
Listar/criar itens de serviço
GET/PATCH
/api/v1/services/:id
JWT
Detalhe/edição de serviço
Regras de negócio obrigatórias
Validação de CPF (11 dígitos, dígito verificador) para customers com document_type=cpf, e de CNPJ (14 dígitos, dígito verificador) para cnpj e para providers — implementar validador reutilizável, não duplicar regex em cada serializer.
Documento (CPF/CNPJ) é único por tenant — dois tenants podem cadastrar o mesmo CNPJ de cliente sem conflito.
Registros não devem ser apagados fisicamente (hard delete); inativação lógica via is_active=False, preservando histórico para notas já emitidas.
Testes mínimos obrigatórios (pytest-django)
CNPJ/CPF com dígito verificador inválido é rejeitado no serializer, com mensagem clara.
Criar cliente com mesmo documento em dois tenants diferentes é permitido; no mesmo tenant, é bloqueado (erro de unicidade).
Inativar um prestador não apaga notas fiscais já emitidas vinculadas a ele.
App Django: fiscal — Perfis fiscais e motor de regras tributárias municipais
Tabelas equivalentes no sistema atual: exeq_core.fiscal_profiles, exeq_core.tax_rule_catalogs, exeq_core.municipal_tax_rules
Model: FiscalProfile (perfil fiscal)
Campo
Tipo Django
Regra / constraint
tenant
ForeignKey(Tenant)
obrigatório
name
CharField
único em conjunto com tenant
tax_regime
CharField + choices
simples_nacional | lucro_presumido | lucro_real
iss_retention_policy
CharField(32)
default 'by_rule'
status
CharField(16)
default 'active'
Model: TaxRuleCatalog (catálogo de regras, versionado)
Campo
Tipo Django
Regra / constraint
tenant
ForeignKey(Tenant)
obrigatório
version
IntegerField
único em conjunto com tenant; incremental
status
CharField + choices
draft | published | superseded
publish_checklist
JSONField
default {csv_validated: false, rules_reviewed: false, terms_accepted: false}
published_at
DateTimeField
nulo até publicação
Model: MunicipalTaxRule (regra de alíquota)
Campo
Tipo Django
Regra / constraint
tenant
ForeignKey(Tenant)
obrigatório
catalog
ForeignKey(TaxRuleCatalog)
obrigatório, on_delete=CASCADE
fiscal_profile
ForeignKey(FiscalProfile)
obrigatório
ibge_code
CharField(7)
código IBGE do município
municipio_nome / uf
CharField
obrigatório
service_code
CharField(32)
código do serviço
tax_regime
CharField + choices
obrigatório
iss_rate, irrf_rate, pis_rate, cofins_rate
DecimalField(7,4)
obrigatório / default 0
iss_retained
BooleanField
obrigatório
simples_codigo_tributacao
SmallIntegerField
opcional
valid_from / valid_to
DateField
valid_to nulo = vigência aberta
priority
IntegerField
default 100 (menor valor = maior prioridade na resolução)
focus_field_overrides
JSONField
default dict vazio
Endpoints (Django REST Framework)
Método
Rota
Auth / Permissão
Descrição
GET/POST
/api/v1/fiscal/profiles
JWT
Perfis fiscais do tenant
GET/PATCH
/api/v1/fiscal/profiles/:id
JWT
Detalhe/edição de perfil
GET/POST
/api/v1/fiscal/catalogs
JWT
Catálogos de regras (versões)
POST
/api/v1/fiscal/catalogs/:id/publish
JWT + papel de escrita
Publica um catálogo em draft (draft→published), supersedendo o anterior
GET/POST
/api/v1/fiscal/catalogs/:id/rules
JWT
Regras de alíquota dentro de um catálogo
POST
/api/v1/tax/resolve
JWT
Resolve a alíquota aplicável para um município/serviço/regime/competência
Regras de negócio obrigatórias
Um catálogo só pode ser editado (adicionar/alterar regras) enquanto status=draft; catálogo published ou superseded é imutável (equivalente a CatalogNotEditableError no sistema atual).
Publicar um catálogo exige o checklist completo: csv_validated, rules_reviewed e terms_accepted todos verdadeiros (equivalente a assertPublishGatesComplete); caso contrário, retornar erro explicando qual item falta.
Ao publicar um novo catálogo, o catálogo published anterior do mesmo tenant deve ser automaticamente marcado como superseded (nunca dois catálogos published simultaneamente para o mesmo tenant).
A resolução de alíquota (/tax/resolve) busca, dentre os catálogos published, a regra que casa com ibge_code + service_code + tax_regime + perfil fiscal, cuja vigência (valid_from/valid_to) cobre a competence_date informada, ordenando por priority (menor primeiro) e depois por valid_from mais recente; se nenhuma regra for encontrada, retornar erro de negócio nomeado (equivalente a TaxRuleNotFoundError), nunca uma exceção genérica.
Regra de unicidade: dentro do mesmo catálogo, não pode haver duas regras para a mesma combinação tenant+catalog+fiscal_profile+ibge_code+service_code+tax_regime+valid_from.
Testes mínimos obrigatórios (pytest-django)
Publicar catálogo com checklist incompleto é bloqueado, com mensagem indicando o item pendente.
Publicar um novo catálogo supersede automaticamente o anterior (não sobra mais de um published).
Resolução de alíquota para município/serviço/regime/competência com regra vigente retorna os percentuais corretos (replicar os casos de tests/fiscal-p0.test.ts e fiscal-p0-extended.test.ts, incluindo o caso de referência: Atibaia, serviço 1.01, Simples Nacional → iss_rate 0.02, simples_codigo_tributacao 3).
Resolução sem regra vigente para a competência retorna erro de negócio específico, não erro 500.
Tentar editar regra de um catálogo já publicado é bloqueado.
App Django: issuance — Emissão de NFS-e (máquina de estados)
Tabelas equivalentes no sistema atual: exeq_core.nf_issue, exeq_core.nf_issue_event, exeq_core.nf_artifact, exeq_core.audit_log
Model: NfIssue (nota em emissão)
Campo status é uma máquina de estados finita — ver regras abaixo.
Campo
Tipo Django
Regra / constraint
tenant
ForeignKey(Tenant)
obrigatório
idempotency_key
CharField(128)
único em conjunto com tenant
status
CharField + choices
draft, pending_tax, queued, submitting, polling, authorized, rejected, cancelled, failed (default draft)
provider / customer / service
ForeignKey
obrigatórios
ibge_code
CharField(7)
obrigatório
competence_date
DateField
obrigatório
amount_cents
BigIntegerField
obrigatório, > 0 (valores monetários sempre em centavos inteiros, nunca float)
resolved_rule_id
ForeignKey(MunicipalTaxRule)
nulo até resolução fiscal
resolved_params / internal_payload / focus_status_raw
JSONField
nulos até preenchidos pelo fluxo
focus_ref
CharField(128)
referência externa no provedor de NFS-e
payload_hash
CharField(64)
hash do payload para auditoria/idempotência de conteúdo
correlation_id
UUIDField
gerado automaticamente, para rastreio ponta a ponta
Model: NfIssueEvent (histórico de transições)
Campo
Tipo Django
Regra / constraint
nf_issue
ForeignKey(NfIssue)
on_delete=CASCADE
from_status / to_status
CharField
to_status obrigatório
actor
CharField(64)
quem/o que disparou a transição (api, worker, provider)
metadata
JSONField
opcional
occurred_at
DateTimeField
auto_now_add
Model: NfArtifact (arquivos gerados)
Campo
Tipo Django
Regra / constraint
nf_issue
ForeignKey(NfIssue)
on_delete=CASCADE
kind
CharField + choices
xml | pdf
storage_path
TextField
obrigatório
checksum_sha256
CharField(64)
obrigatório
Model: AuditLog (trilha de auditoria genérica)
Campo
Tipo Django
Regra / constraint
entity_type / entity_id
CharField / UUIDField
obrigatórios
action
CharField(64)
obrigatório
payload_hash
CharField(64)
opcional
actor
CharField(64)
default 'system'
Endpoints (Django REST Framework)
Método
Rota
Auth / Permissão
Descrição
POST
/api/v1/nf-issue
JWT + papel de escrita
Cria e inicia a emissão de uma NFS-e (idempotente por idempotency_key)
GET
/api/v1/nf-issue/:id
JWT
Consulta o estado atual da nota
POST
/api/v1/nf-issue/:id/cancel
JWT + papel de escrita
Cancela nota autorizada
POST
/api/v1/nf-issue/:id/reprocess
JWT + papel de escrita
Reprocessa nota em estado failed/rejected
Regras de negócio obrigatórias
A emissão é uma máquina de estados estrita: draft → pending_tax → queued → submitting → polling → authorized (ou rejected/failed em qualquer etapa intermediária). Transições fora dessa ordem devem ser bloqueadas no service, não apenas na UI.
Toda transição de status deve gravar um NfIssueEvent (from_status, to_status, actor, metadata) — nunca alterar o status sem registrar o evento correspondente (é a trilha de auditoria da emissão).
idempotency_key garante que reenviar a mesma requisição de emissão não gera nota duplicada — se a chave já existe para o tenant, retornar o registro existente, não criar um novo.
O fluxo de emissão depende do módulo fiscal (resolve a alíquota antes de montar o payload) e do módulo master_data (busca provider/customer/service); se a resolução fiscal falhar (regra não encontrada), a nota deve ir para rejected com o motivo registrado, nunca ficar presa em pending_tax.
amount_cents é sempre inteiro (centavos) — nunca usar float/Decimal impreciso para dinheiro em nenhuma camada (model, serializer, cálculo).
Emissão deve ser processada de forma assíncrona (fila/Celery) por padrão, com opção de processamento síncrono apenas em ambiente de teste/homologação — replicando o padrão atual (variável de ambiente equivalente a NF_SYNC_PROCESSING).
Testes mínimos obrigatórios (pytest-django)
Duas chamadas de emissão com o mesmo idempotency_key retornam a mesma nota, sem duplicar.
Tentar transicionar de draft direto para authorized (pulando etapas) é bloqueado.
Falha na resolução fiscal leva a nota a rejected com o motivo TAX_RULE_NOT_FOUND registrado no evento.
Cada transição de estado gera exatamente um NfIssueEvent correspondente.
Cancelamento só é permitido a partir do estado authorized.
App Django: billing — Cobrança, gateway de pagamento e webhooks
Tabelas equivalentes no sistema atual: exeq_core.charge, exeq_core.payment_event, exeq_core.webhook_inbox
Model: Charge (cobrança)
Campo
Tipo Django
Regra / constraint
tenant
ForeignKey(Tenant)
obrigatório
idempotency_key
CharField(128)
único em conjunto com tenant
status
CharField + choices
pending, registered, paid, overdue, cancelled, failed (default pending)
customer
ForeignKey(Customer)
obrigatório
amount_cents
BigIntegerField
obrigatório, > 0
due_date
DateField
obrigatório
description
TextField
opcional
gateway_ref
CharField(128)
referência no gateway externo
nf_issue
ForeignKey(NfIssue)
opcional (cobrança pode ou não estar ligada a uma nota)
correlation_id
UUIDField
gerado automaticamente
Model: PaymentEvent (evento de pagamento)
Campo
Tipo Django
Regra / constraint
charge
ForeignKey(Charge)
obrigatório
webhook_inbox
ForeignKey(WebhookInbox)
opcional, on_delete=SET_NULL
amount_cents
BigIntegerField
obrigatório, > 0
paid_at
DateTimeField
obrigatório
gateway_ref
CharField(128)
opcional
metadata
JSONField
opcional
Model: WebhookInbox (caixa de entrada de webhooks)
Padrão de inbox: todo webhook recebido é gravado antes de ser processado, permitindo reprocessamento seguro em caso de falha.
Campo
Tipo Django
Regra / constraint
tenant
ForeignKey(Tenant)
obrigatório
idempotency_key
CharField(128)
único em conjunto com tenant
status
CharField + choices
received, processing, processed, failed
signature
CharField(256)
assinatura recebida do provedor
raw_payload
JSONField
obrigatório, payload bruto recebido
payload_hash
CharField(64)
obrigatório
error_message
TextField
opcional
processed_at
DateTimeField
nulo até processado
Endpoints (Django REST Framework)
Método
Rota
Auth / Permissão
Descrição
GET/POST
/api/v1/charges
JWT + papel de escrita (POST)
Criar/listar cobranças
POST
/api/v1/charges/:id/cancel
JWT + papel de escrita
Cancela cobrança
POST
/api/v1/webhooks/gateway
Assinatura do provedor (sem JWT)
Recebe webhook do gateway de pagamento
POST
/api/v1/webhooks/:id/reprocess
JWT + papel operacional
Reprocessa um webhook que falhou
Regras de negócio obrigatórias
Todo webhook recebido é gravado em WebhookInbox antes de qualquer processamento (nunca processar o payload direto na view) — isso garante que uma falha de processamento não perde o evento original.
Assinatura do webhook deve ser validada (HMAC ou equivalente do gateway) antes de aceitar o payload; falha de assinatura retorna 401 e não grava o evento como confiável.
idempotency_key do webhook evita processar o mesmo evento duas vezes (proteção contra reentrega pelo provedor).
Confirmação de pagamento (PaymentEvent) sempre referencia o WebhookInbox de origem, permitindo auditoria completa de onde veio a confirmação.
Charge muda para paid somente a partir de um PaymentEvent válido, nunca por atualização manual direta sem rastro.
Testes mínimos obrigatórios (pytest-django)
Webhook com assinatura inválida é rejeitado e não altera o status de nenhuma cobrança.
Reenvio do mesmo webhook (mesma idempotency_key) não duplica o PaymentEvent.
Reprocessar um webhook em status failed é possível e idempotente.
Cobrança muda para paid apenas quando há PaymentEvent associado com valor compatível.
App Django: das — Guias DAS/DARF do Simples Nacional
Tabelas equivalentes no sistema atual: exeq_das.guia_fiscal
Model: GuiaFiscal
Campo
Tipo Django
Regra / constraint
tenant
ForeignKey(Tenant)
obrigatório
provider
ForeignKey(Provider)
obrigatório
tipo_guia
CharField + choices
DAS | DARF
competencia
CharField
formato AAAA-MM (validar com regex)
data_vencimento
DateField
opcional
valor_principal / valor_multa / valor_juros
DecimalField(14,2)
default 0, >= 0
valor_total
propriedade calculada (não persistida) ou GeneratedField
= principal + multa + juros
linha_digitavel / pix_copia_cola
TextField
opcionais
status
CharField + choices
PROCESSANDO, DISPONIVEL, PAGO, CANCELADO, RETIFICADO, VENCIDO, EM_CONTESTACAO
compliance_status
CharField + choices
pendente, aprovado, bloqueado, dispensado
compliance_motivo
TextField
opcional
pdf_storage_key
TextField
opcional
versao_atual
IntegerField
default 1, >= 1
idempotency_key
CharField
único em conjunto com tenant
metadata
JSONField
default dict vazio
Endpoints (Django REST Framework)
Método
Rota
Auth / Permissão
Descrição
GET
/api/v1/das/guias
JWT
Lista guias com filtro por status/tipo/provider/competência, paginação por cursor
GET
/api/v1/das/guias/:id
JWT
Detalhe de uma guia
POST
/api/v1/das/guias
JWT + papel de escrita
Emite/captura uma guia DAS ou DARF junto à Receita Federal
Regras de negócio obrigatórias
Unicidade dupla obrigatória: (a) idempotency_key por tenant impede reprocessamento duplicado da mesma requisição; (b) combinação tenant+provider+tipo_guia+competencia+versao_atual impede duas guias da mesma competência e tipo para o mesmo prestador na mesma versão.
valor_total nunca é definido manualmente — é sempre a soma de principal + multa + juros, calculada pelo banco ou pela camada de modelo, nunca divergente.
Captura de guia depende do CNPJ do provider (documento limpo, sem máscara) e é feita via adaptador do módulo integrations (ver Seção 4) — o app das nunca deve montar a chamada HTTP à Receita diretamente dentro do service.
Guia recém-criada nasce com status DISPONIVEL e compliance_status conforme retorno do adaptador da Receita (nunca fixo/hardcoded).
Testes mínimos obrigatórios (pytest-django)
Duas chamadas com o mesmo idempotency_key retornam a mesma guia.
Duas guias para o mesmo prestador/tipo/competência/versão são bloqueadas com erro de negócio nomeado.
valor_total sempre reflete a soma correta mesmo quando multa/juros são zero.
App Django: channel — Atendimento via WhatsApp (prioridade menor)
Tabelas equivalentes no sistema atual: exeq_core.channel_session, exeq_core.channel_notification.
Este app depende de todo o restante estar funcionando (issuance, master_data) e envolve integração com um provedor de WhatsApp (Evolution API) e um provedor de IA para extração de dados de mensagens em texto livre. Recomenda-se tratá-lo como a última etapa do desenvolvimento (Sprint 7 na Seção 12), pois não é pré-requisito para a emissão de nota nem para a cobrança funcionarem via API/painel administrativo.
Model
Campos-chave
Observação
ChannelSession
tenant, idempotency_key, phone_e164, status (collecting/ready_to_confirm/emitted/expired/cancelled), draft_payload (JSON), nf_issue (FK opcional)
Sessão conversacional de coleta de dados para emitir nota via WhatsApp
ChannelNotification
tenant, session (FK opcional), nf_issue (FK opcional), phone_e164, event_type, message_body, status (pending/sent/failed)
Fila de notificações a enviar ao contato
Regra de negócio obrigatória: extração de dados por IA deve ser isolada em um serviço próprio, testável com mocks (nunca depender de chamar o provedor de IA real nos testes automatizados).
Regra de negócio obrigatória: deduplicação de mensagens recebidas (debounce) para evitar processar a mesma mensagem do WhatsApp mais de uma vez — replicar o comportamento de channel-inbound-debounce.service.ts.
Teste mínimo obrigatório: mensagens repetidas em curto intervalo geram apenas uma sessão/atualização, não múltiplas.
4. Integrações externas (app integrations)
Todas as chamadas a sistemas de terceiros devem passar por um app dedicado integrations, com uma interface (classe abstrata/protocolo Python) por tipo de provedor, para que o resto do sistema nunca dependa diretamente do formato de payload de um provedor externo específico.
Integração
Interface a definir
Observação de negócio
Focus NFe
NfseProvider.emitir(payload) / .consultar(ref) / .cancelar(ref)
Provedor nacional de emissão; um município pode estar configurado para Focus ou Betha — a resolução de qual usar deve ser uma função pura e testável (equivalente a resolveNfseProviderKind)
Betha
mesma interface NfseProvider
Provedor municipal alternativo; ver docs de referência do sistema atual sobre particularidades de layout
Gateway de pagamento
PaymentGateway.registrar_cobranca() / .cancelar()
Usado pelo app billing; webhook de confirmação chega por rota própria, não por polling
Receita Federal (DAS/DARF)
ReceitaGateway.capturar_das() / .capturar_darf()
Usado pelo app das; retorna valores, linha digitável, PIX copia-e-cola e status de conformidade
Regra obrigatória: nenhum app de domínio (issuance, billing, das) deve montar requisição HTTP diretamente — sempre via a interface do app integrations, para permitir troca/mocking de provedor sem tocar na regra de negócio.
Teste obrigatório: cada adaptador deve ter testes de contrato com respostas simuladas (fixtures) cobrindo sucesso, erro de validação do provedor e indisponibilidade/timeout.
5. Segurança transversal
Item
Especificação
Autenticação
JWT (access + refresh), expiração curta no access token (ex.: 15 min) e refresh mais longo, revogável
RBAC
Django Groups: tenant_admin, operator, accountant, readonly — accountant e readonly nunca têm permissão de escrita em nenhum endpoint
Segredos por tenant
Tokens de provedores (Focus NFe, gateway, WhatsApp) armazenados criptografados, nunca em texto plano nem em log; versionamento de chave de criptografia obrigatório para permitir rotação
Isolamento multi-tenant
Ver Seção 2.3 — obrigatório em toda tabela de negócio, validado por teste automatizado de vazamento entre tenants
Assinatura de webhooks
Toda rota pública de webhook (billing, futuramente channel) valida assinatura antes de processar
Auditoria
Toda transição de estado relevante (emissão de nota, publicação de catálogo, pagamento) grava evento de auditoria com ator e timestamp
6. Padrões de código exigidos da fábrica
Estes padrões existem para que o código gerado com apoio de IA (Cursor) mantenha qualidade e legibilidade consistentes entre desenvolvedores diferentes, e para que a extensa suíte de testes recomendada seja, de fato, escrita e mantida.
Regra de negócio nunca em views/serializers — sempre em services.py, com funções ou classes de serviço puras e testáveis isoladamente do Django (sem precisar subir servidor HTTP para testar regra).
Toda exceção de domínio é uma classe nomeada (ex.: TaxRuleNotFoundError, DuplicateDasIdempotencyError), nunca Exception genérica — isso permite tratamento consistente de erro na API (mapeamento erro→código HTTP em um único lugar).
Toda tabela de negócio herda de um TenantModel abstrato (campo tenant obrigatório + manager que filtra automaticamente pelo tenant do contexto da requisição).
Nenhum valor monetário em float — sempre inteiro em centavos (amount_cents) ou Decimal com precisão fixa (valores fiscais como valor_principal).
Toda operação que pode ser reenviada pelo cliente ou por um provedor externo (emissão, cobrança, webhook, guia DAS) implementa idempotency_key.
Código gerado por IA deve vir acompanhado do teste correspondente na mesma entrega — revisão humana obrigatória de qualquer regra fiscal ou de cálculo monetário antes de aceitar o merge, mesmo que os testes gerados também por IA estejam passando (testes gerados pela mesma IA podem repetir o mesmo erro de interpretação da regra).
Migrations Django versionadas e nunca editadas após aplicadas em qualquer ambiente compartilhado — mesma disciplina hoje seguida nas migrações SQL do sistema de referência.
7. Plano de entrega (sprints sugeridos)
Como não há restrição de dados/produção em operação, a fábrica pode seguir esta ordem de forma direta, sem necessidade de rodar em paralelo com o sistema antigo — cada sprint entrega um app funcionalmente completo antes de iniciar o próximo, na ordem de dependência da Tabela 1.
Sprint
Entrega
Critério de saída (Definition of Done)
1
Setup do projeto Django + app accounts completo
Login funcionando, isolamento multi-tenant comprovado por teste, RBAC com os 4 papéis
2
App master_data completo
CRUD de prestador/cliente/serviço com validação de CPF/CNPJ e testes de unicidade por tenant
3
App fiscal completo
Publicação de catálogo com checklist, resolução de alíquota com paridade nos casos de teste de referência (Seção 3, app fiscal)
4
App integrations (adaptadores) + app issuance completo
Máquina de estados de emissão íntegra, idempotência comprovada, adaptador Focus/Betha com testes de contrato
5
App billing completo
Webhook inbox com idempotência e validação de assinatura, cobrança muda de status apenas via evento de pagamento
6
App das completo
Emissão de guia DAS/DARF com unicidade dupla e valor_total sempre consistente
7
App channel (opcional/pode ser adiado) + Django Admin/back-office funcional
Fluxo de atendimento com deduplicação; painel administrativo cobrindo as jornadas de todos os apps anteriores
8. Checklist final de aceite do projeto
Todos os testes mínimos listados em cada app (Seção 3) implementados e passando.
Isolamento multi-tenant validado por teste automatizado em cada app (nenhum dado de um tenant acessível por outro).
Nenhum valor monetário representado em float em nenhuma camada do sistema.
Todas as rotas de escrita exigem papel adequado (RBAC) e retornam 403 quando o papel é insuficiente.
Todos os adaptadores de integração têm testes de contrato com casos de sucesso e de falha simulados.
Revisão humana registrada (não apenas geração por IA) para as regras de cálculo fiscal e de valores monetários.
— Fim do documento —
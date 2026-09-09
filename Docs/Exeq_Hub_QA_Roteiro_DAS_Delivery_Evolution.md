# EXEQ Hub — Roteiro QA: Entrega DAS/DARF ao Contador + Evolution

| Campo | Valor |
|-------|-------|
| Versão | **0.1.0** |
| Data | 2026-09-08 |
| Escopo | Entrega automática DAS/DARF (e-mail + WhatsApp Evolution) — ADR `ADR_DAS_DELIVERY_001_Entrega_Contador.md` |
| Público | QA júnior (manual) + PO para credenciais |
| Automação de referência | `apps/das/tests/test_das_delivery.py` (11 casos gate merge) |

Convenção de IDs: **DAS-CFG** (configuração), **DAS-HUB** (telas Hub), **DAS-D** (destinatários/fallback), **DAS-E** (e-mail), **DAS-W** (WhatsApp), **DAS-O** (outbox/ops), **DAS-SEC** (segurança).

---

## 1. Credenciais (preencher com PO antes de executar)

> O PO envia link/senha do **Evolution Manager** e logins dos **tenants**. Copie abaixo e **não commitar** este arquivo preenchido.

### 1.1 Evolution API (gerenciador)

| Campo | Valor (PO preenche) |
|-------|---------------------|
| URL do Manager | `________________________` |
| Usuário / senha Manager | `________________________` |
| `EVOLUTION_API_BASE_URL` | ex.: `http://host:8082` |
| `EVOLUTION_API_KEY` | global API key |
| Nome da instância (`EVOLUTION_INSTANCE`) | ex.: `exeq-ale` |
| Instância conectada (QR OK?) | ☐ Sim ☐ Não |
| Número WhatsApp da instância | `+55________________` |

### 1.2 Tenants de teste

Repita a tabela para cada tenant usado no piloto.

| Campo | Tenant A | Tenant B |
|-------|----------|----------|
| `tenant_slug` (login Hub) | ex.: `ALE` | ex.: `CenterCarnes` |
| CNPJ prestador principal | | |
| E-mail login Hub | | |
| Senha login Hub | | |
| Papel mínimo para teste | `tenant_admin` ou `operator` | |
| `tenant.settings.evolution_instance` | (igual instância Evolution) | |
| E-mail contador (teste) | caixa que QA controla | |
| WhatsApp contador (teste) | número real E.164 | |
| WhatsApp ops (`notify_phone`) | número real E.164 | |

### 1.3 Admin plataforma (opcional — auditoria)

| Campo | Valor |
|-------|-------|
| URL | http://127.0.0.1:8000/admin/ |
| Usuário | (PO informa) |
| Senha | (PO informa) |

---

## 2. Subir o ambiente local (Windows)

### 2.1 Pré-requisitos

- Python 3.12 + dependências (`requirements.txt`)
- **Docker Desktop** em execução (Postgres `5433`, Redis `6379`)
- Evolution API acessível (local ou servidor informado pelo PO)
- Celery worker **obrigatório** para entrega (outbox assíncrona)

### 2.2 Comandos (PowerShell, na raiz do repo)

```powershell
cd "c:\Users\riica\OneDrive\Empresas Ricardo\Exeq\Exeq_Hub"

# Se Docker não estiver rodando, abra Docker Desktop e aguarde ~30s

.\bootstrap.ps1 -Bg
```

Saída esperada:

- `Hub V4  http://127.0.0.1:8000/hub/`
- Containers `exeq_hub_db` e `exeq_hub_redis` **healthy**

Health check:

```powershell
.\bootstrap.ps1 -Check
```

Esperado: HTTP **200** em `/app/` e `/hub/login/`.

Parar ambiente:

```powershell
.\bootstrap.ps1 -Down
```

### 2.3 URLs úteis

| Superfície | URL |
|------------|-----|
| Login Hub V4 | http://127.0.0.1:8000/hub/login/ |
| Preferências tenant | http://127.0.0.1:8000/hub/preferencias/ |
| Lista DAS | http://127.0.0.1:8000/hub/das/ |
| Emitir DAS | http://127.0.0.1:8000/hub/das/emitir/ |
| Admin — Notificações canal | http://127.0.0.1:8000/admin/channel/channelnotification/ |
| Webhook Evolution (referência) | `POST /api/v1/webhooks/evolution` |

---

## 3. Configurar Evolution (passo a passo QA)

### 3.1 Arquivo `.env` do Hub (servidor local)

Edite `.env` na raiz do projeto. Reinicie o bootstrap após salvar.

```env
# WhatsApp — modo real (não stub)
EVOLUTION_HTTP_MODE=http
EVOLUTION_API_BASE_URL=<URL base da API, sem barra final>
EVOLUTION_API_KEY=<apikey do manager>
EVOLUTION_INSTANCE=<nome da instância conectada>
EVOLUTION_WEBHOOK_TOKEN=<token forte — mesmo valor no webhook da instância>
EVOLUTION_WEBHOOK_ALLOW_LEGACY=true
WHATSAPP_PROVIDER=evolution

# E-mail lab: imprime no console do runserver
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=EXEQ Hub Lab <noreply@exeq.local>

# DAS em lab (sem SERPRO real)
RECEITA_HTTP_MODE=stub
```

**Checklist DAS-CFG-01**

| # | Verificação | OK |
|---|-------------|-----|
| 1 | Manager Evolution abre e instância aparece **Connected** | ☐ |
| 2 | `.env` salvo com `EVOLUTION_HTTP_MODE=http` | ☐ |
| 3 | Após reiniciar bootstrap, worker Celery está rodando | ☐ |
| 4 | Teste rápido: enviar mensagem pelo Manager para um número de teste | ☐ |

### 3.2 Instância por tenant (Admin Django)

Para cada tenant do piloto:

1. Admin → **Tenants** → editar tenant
2. Campo **Settings (JSON)** — incluir ou ajustar:

```json
{
  "whatsapp_provider": "evolution",
  "evolution_instance": "NOME_DA_INSTANCIA",
  "notify_phone": "+5511999999999",
  "nfe_notify_email": "fiscal@escritorio.com.br",
  "das_delivery": {
    "enabled": true,
    "email_auto": true,
    "whatsapp_auto": true,
    "accountant_email": "contador-teste@exemplo.com.br",
    "accountant_whatsapp": "+5511987654321",
    "use_nfe_notify_email_for_das": false
  }
}
```

> **Importante:** `notify_phone` é só **ops** (texto curto). O PDF vai para `accountant_whatsapp`, não para ops.

### 3.3 Webhook Evolution → Hub (opcional neste roteiro)

Entrega DAS é **outbound** (Hub chama Evolution). Webhook só é necessário se testar conversa NFS-e. Se o PO pedir, configure na instância:

- URL: `http://host.docker.internal:8000/api/v1/webhooks/evolution` (Docker) ou IP LAN do PC
- Header: `X-Exeq-Webhook-Token: <EVOLUTION_WEBHOOK_TOKEN>`

### 3.4 Preferências no Hub (alternativa ao JSON Admin)

Usuário **tenant_admin**:

1. Login → **Preferências** (`/hub/preferencias/`)
2. Seção **Entrega DAS/DARF ao contador**
3. Preencher e salvar:
   - Entrega automática habilitada
   - E-mail do contador
   - WhatsApp do contador (E.164, ex.: `+5511987654321`)
   - WhatsApp ops
   - Toggles e-mail / WhatsApp automático
   - Fallback NF-e (só marcar se for testar DAS-D06/D07)

**Checklist DAS-CFG-02**

| # | Verificação | OK |
|---|-------------|-----|
| 1 | Preferências salvam sem erro | ☐ |
| 2 | Recarregar página mantém valores | ☐ |
| 3 | Usuário `readonly` **não** vê formulário de edição | ☐ |

---

## 4. Pré-condições por caso de teste

| Item | Lab (stub Receita) | Homologação real |
|------|-------------------|------------------|
| Prestador com certificado A1 | Opcional em stub | Obrigatório |
| `RECEITA_HTTP_MODE` | `stub` | `http` + credenciais SERPRO |
| Celery worker | **Obrigatório** | **Obrigatório** |
| Evolution HTTP | **Obrigatório** para DAS-W* | **Obrigatório** |
| Caixa e-mail / WhatsApp de teste | Números reais que QA controla | Idem |

**Emitir guia (lab):** Hub → **DAS** → **Emitir** → escolher prestador + competência → enviar. Com `RECEITA_HTTP_MODE=stub`, a guia fica `DISPONIVEL` com PDF simulado.

Após emitir, aguarde **5–15 s** (outbox + Celery) antes de validar entrega.

---

## 5. Casos de teste manual

### Bloco DAS-HUB — Telas Hub

| ID | Cenário | Passos | Esperado |
|----|---------|--------|----------|
| DAS-HUB-01 | Detalhe guia — status entrega | Emitir guia → abrir detalhe | Seção **Entrega ao contador** com chips E-mail / WhatsApp |
| DAS-HUB-02 | Badges após entrega | Aguardar outbox → F5 no detalhe | E-mail e WhatsApp **Enviado** + destinatários |
| DAS-HUB-03 | Download PDF | Botão **Baixar PDF** | PDF baixa; abre sem erro |
| DAS-HUB-04 | Reenviar | Clicar **Reenviar ao contador** | Toast/mensagem de sucesso; hint “enfileirado”; após F5, timestamps atualizados |
| DAS-HUB-05 | Sem permissão escrita | Login `readonly` → detalhe guia | Sem botão reenviar |

### Bloco DAS-D — Destinatários e fallback

| ID | Cenário | Config | Esperado |
|----|---------|--------|----------|
| DAS-D06 | Fallback OFF | `accountant_email` vazio; `use_nfe_notify_email_for_das: false`; `nfe_notify_email` preenchido | **Sem** e-mail; badge E-mail permanece Pendente; log noop |
| DAS-D07 | Fallback ON | Mesmo cenário + `use_nfe_notify_email_for_das: true` | E-mail vai para `nfe_notify_email` |
| DAS-D08 | WhatsApp sem fallback ops | `accountant_whatsapp` vazio; `notify_phone` preenchido | Ops recebe texto; contador **não** recebe PDF |

### Bloco DAS-E — E-mail contador

| ID | Cenário | Passos | Esperado |
|----|---------|--------|----------|
| DAS-E01 | Happy path | Config completa + emitir guia | Console runserver (ou caixa real) mostra e-mail com **anexo PDF** |
| DAS-E02 | Conteúdo | Ler corpo do e-mail | CNPJ, competência, valores, vencimento, linha digitável/PIX se stub tiver |
| DAS-E09 | DARF | Emitir guia tipo DARF (se disponível no tenant) | Assunto/caption contém **DARF**, não DAS |

### Bloco DAS-W — WhatsApp (Evolution)

| ID | Cenário | Passos | Esperado |
|----|---------|--------|----------|
| DAS-W01 | Happy path contador | Emitir guia | WhatsApp contador: **texto** + **documento PDF** |
| DAS-W02 | Integridade PDF | Comparar PDF do chat com download Hub | Mesmo conteúdo (tamanho/nome coerente) |
| DAS-W07 | Ops + contador | `notify_phone` ≠ `accountant_whatsapp` | Ops: 1 linha texto; contador: PDF |
| DAS-W08 | Ops sem PDF | Ler chat ops | **Nenhum** anexo PDF no ops |
| DAS-W03 | Número inválido | `accountant_whatsapp` inexistente | Admin → ChannelNotification `failed`; guia continua `DISPONIVEL` |
| DAS-W04 | Evolution offline | Parar Evolution → reenviar → subir Evolution | Outbox retenta; entrega quando voltar |

### Bloco DAS-O — Outbox e API

| ID | Cenário | Passos | Esperado |
|----|---------|--------|----------|
| DAS-O02 | Falha não muda guia | Provocar falha SMTP ou Evolution | `GuiaFiscal.status` = **DISPONIVEL** |
| DAS-O03 | Idempotência | Disparar outbox 2× sem `force` | Segundo envio **não** duplica e-mail/PDF |
| DAS-O05 | API resend | `POST /api/v1/das/guias/{id}/resend-delivery/` body `{"channels":["email","whatsapp"],"force":true}` | HTTP **202**; mensagem enfileirada |
| DAS-O06 | Auditoria WhatsApp | Admin → ChannelNotification | Registros `guia_fiscal.available` / `.pdf`; `provider=evolution` |

### Bloco DAS-SEC — Segurança

| ID | Cenário | Passos | Esperado |
|----|---------|--------|----------|
| DAS-S02 | Cross-tenant | Token tenant A → resend guia tenant B | **404** |
| DAS-S03 | PDF autenticado | Abrir URL PDF sem login | **401/403** ou redirect login |

---

## 6. Smoke rápido (15 min — primeiro dia QA)

Ordem sugerida para validar que **tudo está conectado**:

1. ☐ Bootstrap `-Check` verde  
2. ☐ Login Hub com tenant do PO  
3. ☐ Preferências: salvar e-mail + WhatsApp contador + ops  
4. ☐ Evolution Manager: instância **Connected**  
5. ☐ Emitir 1 guia DAS (stub)  
6. ☐ Console: e-mail com PDF  
7. ☐ WhatsApp contador: texto + PDF  
8. ☐ WhatsApp ops: só texto  
9. ☐ Detalhe Hub: badges **Enviado**  
10. ☐ Admin: `ChannelNotification` com status `sent`  

---

## 7. Evidências (obrigatório por caso)

Para cada ID executado, registrar:

| Campo | Exemplo |
|-------|---------|
| Data / executor | 2026-09-08 — Nome QA |
| Tenant | `ALE` |
| ID do caso | DAS-W01 |
| Resultado | Pass / Fail |
| Guia (UUID) | `xxxxxxxx-....` |
| Screenshot | WhatsApp + Hub detalhe + Admin notificação |
| Observação | ref Evolution, número usado |

Pasta sugerida: `Docs/qa_evidence/das_delivery_YYYY-MM-DD/` (não commitar dados sensíveis).

---

## 8. Troubleshooting

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| Badges ficam **Pendente** forever | Celery parado | `.\bootstrap.ps1 -Down` then `-Bg` ou verificar processo `celery worker` |
| WhatsApp não chega | `EVOLUTION_HTTP_MODE=stub` | Trocar para `http` e reiniciar |
| Evolution 401 | API key errada | Conferir Manager → instância → API Key |
| E-mail não aparece | Backend SMTP vs console | Lab: `EMAIL_BACKEND=console`; ver terminal do runserver |
| PDF pendente no Hub | Stub sem arquivo | Reemitir guia; checar `has_pdf` no detalhe |
| Ops recebe PDF | Números iguais | Separar `notify_phone` e `accountant_whatsapp` |
| Docker error na subida | Docker Desktop off | Abrir Docker Desktop; aguardar; repetir bootstrap |

---

## 9. Regressão automatizada (dev/CI — referência)

QA júnior **não precisa** rodar, mas se quiser confirmar gate merge:

```powershell
$env:EXEQ_TEST_SQLITE="1"
python -m pytest apps/das/tests/test_das_delivery.py apps/das/tests/test_das.py -q
```

Esperado: **16 passed**.

---

## 10. Gate de aceite desta entrega

- [ ] Smoke §6 completo em **≥ 1 tenant** real  
- [ ] DAS-W01, DAS-W07, DAS-W08, DAS-E01, DAS-HUB-04 executados manualmente  
- [ ] DAS-D06 **ou** DAS-D07 (fallback) executado conforme config PO  
- [ ] Evidências salvas na pasta do dia  
- [ ] PO assina registro abaixo  

---

## Registro de execução

| Data | Executor | Tenant(s) | Casos | Resultado | Observações |
|------|----------|-----------|-------|-----------|-------------|
| | | | | | |

---

## Referências

- `Docs/ADR_DAS_DELIVERY_001_Entrega_Contador.md`
- `Docs/Exeq_Hub_QA_Roteiro_WhatsApp_NFSe.md` (Evolution gateway — WA-GW)
- `README.md` — bootstrap e variáveis Evolution

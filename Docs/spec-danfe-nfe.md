# Especificação de Layout — DANFE (NF-e modelo 55, Retrato)

> Documento de referência gerado a partir da análise da NF-e nº 3.925, Série 1, emitida pela CONSTRUFORTI MATERIAIS PARA CONSTRUÇÃO LTDA (UniDANFE 3.9.13).  
> **Implementação EXEQ:** `integrations/sefaz_nfe/danfe/render_moc.py` — versão `exeq-danfe-2.7.5-spec`.

---

## 1. Estrutura geral da página

O DANFE segue o layout padrão SEBRAE/SEFAZ em blocos retangulares empilhados, cada um com rótulo em caixa alta no canto superior esquerdo do quadro. Ordem de cima para baixo:

1. Cabeçalho (Emitente + Caixa DANFE + Código de barras)
2. Natureza da Operação
3. Inscrição Estadual / Inscrição Estadual Subst. Tributário / CNPJ (emitente)
4. Destinatário / Remetente
5. Informações do Local de Entrega (condicional — só aparece se entrega ≠ endereço do destinatário)
6. Fatura / Duplicata (condicional — só aparece se houver parcelas)
7. Cálculo do Imposto
8. Transportador / Volumes Transportados
9. Dados dos Produtos / Serviços (tabela, quebra de página se necessário)
10. Dados Adicionais (Informações Complementares + Reservado ao Fisco)
11. Rodapé do software emissor + linha tracejada (corte)
12. Canhoto do destinatário (recibo de entrega) — sempre no rodapé da primeira página

Cada bloco é uma região com borda de 1px preta, sem espaçamento entre blocos (bordas coladas).

---

## 2. Bloco: Cabeçalho

| Campo | Conteúdo do exemplo | Regras |
|---|---|---|
| Identificação do emitente (razão social) | CONSTRUFORTI MATERIAIS PARA CONSTRUCAO LTDA | Caixa alta, negrito, fonte maior |
| Endereço do emitente | AVENIDA SAO JOAO, 1830 - BAIRRO DA PONTE / 12944-376 ATIBAIA - SP | 2 linhas: logradouro+bairro / CEP+cidade-UF |
| Telefone do emitente | (11) 4411-6980 | Formato `(DD) NNNN-NNNN` ou `(DD) NNNNN-NNNN` |
| Logo (opcional) | — | Área reservada acima/ao lado da razão social |
| Título "DANFE" | fixo | Sempre "DANFE" + "Documento Auxiliar da Nota Fiscal Eletrônica" |
| Tipo (Entrada/Saída) | 1-SAÍDA destacado em caixa | 0 = Entrada, 1 = Saída — dígito em caixa quadrada separada |
| Número da NF-e | 3.925 | Formatado com ponto de milhar |
| Série | SÉRIE 1 | — |
| Folha | FOLHA 1/1 | `página_atual/total_páginas` |
| Chave de acesso | 44 dígitos em grupos de 4 | Code128 da chave |
| Texto de consulta | Portal NF-e / SEFAZ autorizadora | Texto fixo conforme UF |

---

## 3. Bloco: Natureza da Operação / Inscrições / CNPJ

| Campo | Exemplo | Regras |
|---|---|---|
| Natureza da Operação | VENDA | Texto curto |
| Protocolo de Autorização de Uso | 135263327385284 14/08/2026 15:18:55 | Faixa natureza, linha 1 (spec §3) |
| Inscrição Estadual | 190.446.031.111 | Máscara conforme UF |
| Inscrição Estadual Subst. Tributário | (vazio) | Coluna dedicada |
| CNPJ do emitente | 52.866.007/0001-94 | Máscara `NN.NNN.NNN/NNNN-NN` |

---

## 4. Bloco: Destinatário / Remetente

Grade com razão social, CNPJ, datas, endereço, bairro, CEP, município, UF, fone, IE, hora saída — campos sempre renderizados (vazios quando sem dado).

---

## 5. Bloco: Local de Entrega (condicional)

Mesma estrutura de campos do destinatário (sem datas). **Omitir** quando não houver nó `<entrega>` no XML ou endereço igual ao destinatário.

---

## 6. Bloco: Fatura / Duplicata (condicional)

Tabela: `Número | Vencimento | Valor`. Omitir se à vista sem duplicatas.

---

## 7. Bloco: Cálculo do Imposto

Duas linhas. Linha 2 inclui **Valor Aprox. Trib.** e **Total da Nota** em negrito.

---

## 8. Bloco: Transportador / Volumes

Frete: `0-Remetente`, `1-Destinatário`, `2-Terceiros`, `9-Sem frete`. Pesos com 3 casas decimais.

---

## 9. Bloco: Produtos / Serviços

13 colunas (UniDANFE): Código, Descrição, NCM, CSOSN/CST, CFOP, Un, Qtd, V.Unit, V.Total, BC ICMS, V.ICMS, Alíq ICMS, V.Aprox Tributos.

- CSOSN (4 dígitos) se CRT Simples Nacional; CST (2 dígitos) se Regime Normal.
- GTIN/EAN como segunda linha: `Cód. Barras: …`

---

## 10. Dados Adicionais

- **Informações Complementares** (~75%): tributos Lei 12.741/2012 + observações.
- **Reservado ao Fisco** (~25%).
- Rodapé técnico: `EXEQ Hub DANFE | exeq-danfe-2.7-spec | Gerado em …`

Formato tributos: `VALOR APROXIMADO DOS TRIBUTOS R$ 100,44 (16,2000%)`

---

## 11. Canhoto

Linha tracejada de corte + texto completo com emitente, nº, emissão, valor total, destinatário/endereço + caixa NF-e à direita.

---

## 12. Regras transversais

1. Moeda: vírgula decimal, 2 casas (peso: 3 casas). Sem `R$` nas células de valor.
2. Datas: `dd/mm/aaaa`; data+hora: `dd/mm/aaaa hh:mm:ss`.
3. CNPJ/CPF/CEP/telefone: máscaras pt-BR.
4. Textos impressos em **CAIXA ALTA**.
5. Fonte sans-serif condensada (Arial/Helvetica 6–8pt).
6. P&B, bordas 1px.

---

## 13. Checklist de conformidade EXEQ

| Item | Status |
|---|---|
| Chave 44 dígitos agrupada | ✅ |
| Barcode Code128 | ✅ |
| Total Produtos ≠ Total Nota | ✅ |
| Local Entrega condicional | ✅ |
| Fatura condicional | ✅ |
| CST/CSOSN por CRT | ✅ |
| GTIN 2ª linha | ✅ |
| Formato moeda/peso | ✅ |
| Caixa alta | ✅ |
| CNPJ/CPF validação DV na impressão | ✅ `format_document(validate=True)` |
| Paginação FOLHA n/N | ✅ |
| Tributos infCpl + % IBPT | ✅ (2.5.1) |
| Caixa quadrada Entrada/Saída | ✅ (2.5.1) |
| Protocolo na faixa natureza | ✅ (2.5.2) |
| Bordas 0,5pt (geometria fina) | ✅ (2.5.2) |
| Colunas produtos calibradas CONSTRUFORTI | ✅ (2.6) |
| Blocos dest/transporte/tax calibrados CONSTRUFORTI | ✅ (2.7) |
| Valores numéricos alinhados à direita (grid + impostos) | ✅ (2.7) |
| Canhoto + linha corte | ✅ |

---

## 14. Prompt Cursor (revisão)

```
Revise o componente de geração de DANFE (NF-e) usando Docs/spec-danfe-nfe.md como fonte da verdade.
Compare seções 2–11 com integrations/sefaz_nfe/danfe/render_moc.py e corrija divergências.
Ao final, atualize a seção 13 com o que foi corrigido.
```

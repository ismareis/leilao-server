# Trabalho Prático 2 - Leilão Virtual em Rede (UDP e TCP)

**Disciplina:** Redes de Computadores: Aplicação e Transporte
**Professor:** Elvandi da Silva Júnior

**Integrantes:**
- Gabriel Pacheco
- Gustavo Rezende
- Ismael Reis  
- Vitor Auricchio

---

## 1. Tema escolhido

**Opção 3 - Leilão virtual em rede.**

Um servidor central controla um leilão de um item fictício. Os clientes se cadastram, enviam lances e recebem o resultado. O servidor mantém o estado oficial do leilão (maior lance, vencedor, histórico e tempo restante), valida todos os lances e encerra o leilão automaticamente após **60 segundos**, contados a partir do `start`.

### Funções de cada protocolo

| Protocolo | Função |
|---|---|
| **TCP** | Cadastro, início do leilão, envio e confirmação de lances (com o motivo da rejeição), consulta de situação e resultado final com o histórico. É o canal **oficial**. |
| **UDP** | Avisos rápidos de novo maior lance e de encerramento, com número de atualização (`seq`). É apenas **informativo**: não substitui a informação oficial por TCP. |

---

## 2. Linguagem e versão

- **Python 3.8 ou superior** (versão utilizada nos testes: `(3.15)`).

## 3. Dependências

Nenhuma dependência externa. Apenas a biblioteca padrão do Python: `json`, `socket`, `threading`, `time` e `datetime`.

---

## 4. Arquivos do projeto

| Arquivo | Descrição |
|---|---|
| `server.py` | Servidor do leilão. |
| `cliente.py` | Cliente (participante). |
| `log_servidor.txt` | Log gerado pelo servidor durante a execução. |
| `log_cliente_<nome>.txt` | Log gerado por cada cliente (um arquivo por nome). |

Não há arquivo de configuração: o item, o lance mínimo e o mínimo de participantes são informados no terminal do servidor ao iniciá-lo (veja a seção 5).

---

## 5. Comandos de execução

### Servidor

```bash
python server.py
```

O servidor não recebe argumentos. Ao iniciar, ele pergunta:

```
Nome do item: Ferrari F40
Lance mínimo: 100
Mínimo de usuários para iniciar: 3
```
O lance mínimo e o mínimo de usuários devem ser números inteiros positivos; o nome do item não pode ficar vazio

Em seguida ele fica aguardando os clientes (estado `aguardando`). O terminal do servidor funciona como **organizador** do leilão: quando houver clientes suficientes conectados, digite:

```
start
```

O comando só é aceito se o número de clientes cadastrados for pelo menos o mínimo informado. Depois do `start`, o servidor avisa os clientes por TCP e o cronômetro de 60 segundos começa.

### Cliente

Execute **uma instância por participante**, cada uma em um terminal:

```bash
python cliente.py
```

O cliente não recebe argumentos. Ele pergunta, nesta ordem:

```
IP do servidor [127.0.0.1]:
Porta TCP do servidor [5000]:
Seu nome:
Porta UDP para receber avisos (ex: 5001):
```

Os valores entre colchetes são os padrões (basta apertar Enter). A porta UDP de cada cliente deve ser **diferente** quando os clientes estão no mesmo computador; se a porta já estiver em uso, o cliente pede outra.

#### Comandos do cliente

| Comando | Ação |
|---|---|
| `lance <valor>` (ou só o número) | Envia um lance. |
| `status` | Consulta a situação do leilão. |
| `ajuda` | Mostra os comandos. |
| `sair` | Encerra o cliente. |

### Exemplo de execução com 3 clientes no mesmo computador

| Terminal | Comando | Dados informados |
|---|---|---|
| 1 | `python server.py` | item, lance mínimo e mínimo de usuários |
| 2 | `python cliente.py` | `127.0.0.1`, `5000`, `ana`, `5001` |
| 3 | `python cliente.py` | `127.0.0.1`, `5000`, `bruno`, `5002` |
| 4 | `python cliente.py` | `127.0.0.1`, `5000`, `carla`, `5003` |

Depois, digite `start` no terminal 1 e envie lances nos terminais 2, 3 e 4.

---

## 6. Configuração dos endereços e das portas

### Servidor

As constantes ficam no início do arquivo `server.py`:

```python
HOST = "127.0.0.1"
PORTA_TCP = 5000
ARQUIVO_LOG = "log_servidor.txt"
DURACAO = 60
```

| Constante | Valor padrão | Descrição |
|---|---|---|
| `HOST` | `127.0.0.1` | IP em que o servidor escuta. |
| `PORTA_TCP` | `5000` | Porta TCP de cadastro, lances, consultas e resultado. |
| `DURACAO` | `60` | Duração do leilão, em segundos. |

**Teste entre computadores:** troque `HOST` pelo IP da máquina do servidor na rede (o servidor mostra esse IP no log ao iniciar, na linha "IP local da máquina na rede") ou por `"0.0.0.0"`. Nos clientes, informe esse IP quando o programa perguntar o "IP do servidor".

### Portas utilizadas

| Porta | Protocolo | Quem usa | Uso |
|---|---|---|---|
| `5000` (configurável) | TCP | Servidor | Recebe conexões e mensagens dos clientes. |
| Efêmera (escolhida pelo sistema) | UDP | Servidor | Porta de origem dos avisos enviados aos clientes. |
| Informada pelo usuário (ex.: `5001`, `5002`, `5003`) | UDP | Cada cliente | Recebe os avisos do servidor. O cliente faz `bind()` nessa porta **antes** do cadastro e a informa na mensagem `register`. |

### Identificação dos participantes

Cada cliente se identifica pelo **nome** informado no cadastro, associado ao seu IP. O servidor identifica cada usuário pela dupla `(nome, ip)`, então várias instâncias no mesmo computador são distinguidas pelo nome. O cadastro é rejeitado se o nome for vazio, se a porta UDP for inválida ou se a mesma dupla já estiver conectada.

---

## 7. Protocolo de aplicação

### Formato e delimitação das mensagens

- Todas as mensagens são **JSON em UTF-8**.
- **TCP:** cada mensagem é um JSON em **uma única linha**, terminada por `\n`. Cliente e servidor acumulam em um *buffer* os bytes recebidos por `recv()` e só processam uma mensagem quando o `\n` aparece, então uma única leitura não é considerada uma mensagem completa.
- **UDP:** um datagrama por mensagem, sem `\n`. Cada aviso tem um campo `seq` crescente; o cliente descarta avisos com `seq` menor ou igual ao último recebido.

### 7.1. Requisições TCP (Cliente → Servidor)

**Cadastro**

```json
{"action": "register", "nome": "ana", "udp_port": 5001}
```

**Lance** (o valor deve ser um número inteiro positivo)

```json
{"action": "bid", "valor": 250}
```

**Consulta de situação**

```json
{"action": "status"}
```

### 7.2. Respostas e avisos TCP (Servidor → Cliente)

**Resposta ao cadastro (aceito)**

```json
{"action": "register_response", "status": "ok", "msg": "Conectado ao leilão."}
```

**Resposta ao cadastro (rejeitado)**. Mensagens possíveis em `msg`: `Usuário já conectado com este IP.` e `Leilão já em andamento. Cadastro encerrado.`

```json
{"action": "register_response", "status": "error", "msg": "Leilão já em andamento. Cadastro encerrado."}
```

**Início do leilão** (enviado a todos os clientes quando o servidor digita `start`)

```json
{"action": "auction_start", "item": "Ferrari F40", "lance_minimo": 100, "duracao_segundos": 60}
```

**Resposta ao lance (aceito)**

```json
{"action": "bid_response", "status": "accepted", "maior_lance": 250}
```

**Resposta ao lance (rejeitado)**. Todo lance recebe uma resposta com o motivo:

```json
{"action": "bid_response", "status": "rejected", "motivo": "Lance inferior ou igual ao atual. Maior lance é 250."}
```

```json
{"action": "bid_response", "status": "rejected", "motivo": "Lance abaixo do mínimo. O lance mínimo é 100."}
```

```json
{"action": "bid_response", "status": "rejected", "motivo": "Valor inválido. O lance deve ser um número inteiro positivo."}
```

```json
{"action": "bid_response", "status": "rejected", "motivo": "Leilão ainda não foi iniciado."}
```

```json
{"action": "bid_response", "status": "rejected", "motivo": "Leilão já foi encerrado."}
```

**Resposta de consulta** (o campo `estado` pode ser `aguardando`, `em_andamento` ou `encerrado`)

```json
{"action": "status_response", "estado": "aguardando", "item": "Ferrari F40", "lance_minimo": 100, "duracao_segundos": 60}
```

```json
{"action": "status_response", "estado": "em_andamento", "item": "Ferrari F40", "lance_minimo": 100, "tempo_restante_segundos": 42, "maior_lance": 250, "vencedor_atual": "ana"}
```

Em `em_andamento`, os campos `maior_lance` e `vencedor_atual` só aparecem depois do primeiro lance aceito.

```json
{"action": "status_response", "estado": "encerrado", "item": "Ferrari F40", "vencedor": "ana", "valor_final": 250}
```

**Encerramento do leilão (com vencedor e histórico de lances aceitos)**

```json
{"action": "auction_end", "vencedor": "ana", "valor_final": 250, "historico_lances": [{"autor": "bruno", "valor": 100}, {"autor": "carla", "valor": 150}, {"autor": "ana", "valor": 250}]}
```

**Encerramento sem lances**

```json
{"action": "auction_end", "vencedor": null, "msg": "Ausencia de vencedor"}
```

**Erro genérico.** Enviado para mensagem inválida; a conexão continua aberta. Mensagens possíveis em `msg`: `Mensagem inválida: JSON malformado.`, `Ação desconhecida.`, `Campo obrigatório ausente: <campo>.`, `Cadastro necessário antes de enviar lances.`, `Cliente já cadastrado.`, `Nome inválido.` e `Porta UDP inválida.`

```json
{"action": "error", "msg": "Ação desconhecida."}
```

### 7.3. Avisos UDP (Servidor → Cliente)

Enviados por unicast para a porta UDP informada por cada cliente no cadastro.

**Novo maior lance**

```json
{"event": "new_bid", "valor": 250, "autor": "ana", "seq": 3}
```

**Encerramento do leilão**

```json
{"event": "end", "vencedor": "ana", "valor_final": 250, "seq": 4}
```

**Encerramento sem lances**

```json
{"event": "end", "vencedor": null, "valor_final": null, "seq": 1}
```

---

## 8. Funcionamento interno (resumo)

- **Atendimento dos clientes:** o servidor usa uma *thread* por cliente conectado e uma *thread* para o cronômetro do leilão. Um cliente lento ou desconectado não impede os demais.
- **Estado consistente:** o estado do leilão (`estado`, `maior_lance`, `vencedor_atual`, histórico e `seq`) é protegido por um `Lock`. Lances simultâneos são processados um de cada vez, na ordem de chegada: se dois lances de mesmo valor chegam juntos, o primeiro é aceito e o segundo é rejeitado. O envio por TCP e a gravação do log também têm seus próprios `Lock`.
- **Cliente:** possui uma *thread* dedicada à leitura contínua do TCP e outra para escutar os avisos UDP, enquanto a *thread* principal lê os comandos do teclado.
- **Falhas:** JSON malformado, campos ausentes, valores inválidos e desconexão de cliente são tratados sem derrubar o servidor. O servidor responde com `error` e o cliente desconectado é removido da lista. Falhas no envio UDP são registradas no log.
- **Perda de UDP:** a perda de um datagrama não altera o estado oficial. O cliente pode usar `status` (TCP) para consultar a situação atual.
- **Encerramento do leilão:** quando o cronômetro termina, o servidor muda o estado para `encerrado`, envia o aviso UDP e depois o `auction_end` por TCP a todos os clientes conectados.

---

## 9. Logs

Servidor e clientes gravam seus eventos em arquivo, no formato:

```
[YYYY-MM-DD HH:MM:SS] | [PROTOCOLO] | [DIREÇÃO] | [ORIGEM -> DESTINO] | [AÇÃO]
```

| Campo | Valores |
|---|---|
| Protocolo | `TCP`, `UDP` ou `SISTEMA` (mudanças de estado) |
| Direção | `ENVIO`, `RECEBIMENTO` ou `-` |
| Ação | Conteúdo da mensagem (JSON) ou descrição do evento |

Exemplo de linhas do log do servidor:

```
[2026-11-09 18:30:01] | [SISTEMA] | [-] | [-] | [Servidor ouvindo em 127.0.0.1:5000 (Aguardando Participantes)]
[2026-11-09 18:30:10] | [TCP] | [RECEBIMENTO] | [127.0.0.1:51234 -> 127.0.0.1:5000] | [{"action": "register", "nome": "ana", "udp_port": 5001}]
[2026-11-09 18:30:10] | [SISTEMA] | [-] | [-] | [Cliente 'ana' entrou (127.0.0.1:51234, UDP 5001)]
[2026-11-09 18:31:02] | [UDP] | [ENVIO] | [127.0.0.1:49876 -> 127.0.0.1:5001] | [{"event": "new_bid", "valor": 250, "autor": "ana", "seq": 1}]
```

O servidor também registra entradas e saídas de clientes, cadastros rejeitados, lances aceitos e rejeitados (com o motivo), início e fim do leilão.

---

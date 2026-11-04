# Planejamento da Arquitetura e Funcionamento do Sistema (Requisitos Gerais)

A seguir estão as decisões adotadas para cumprir as regras gerais do trabalho, organizando a base do sistema antes de entrar nos detalhes específicos do tema.

### 1. Participantes e Identificação (Req. 2.1)

* **Decisão:** A identificação de cada cliente será feita por um **nome de usuário** (string) único. O servidor será executado **sem nenhum argumento** (`python server.py`), com o IP e a porta TCP definidos como constantes no próprio código. O cliente também será executado **sem nenhum argumento** (`python client.py`) e, já com o programa rodando, pedirá pelo terminal o IP do servidor, a porta TCP, o nome e a porta UDP. Assim que conecta, o cliente envia uma mensagem de cadastro com o nome e a porta UDP onde deseja receber os avisos. O valor padrão das constantes do servidor será o IP `127.0.0.1` e a porta TCP `5000`, e deverão ser alteradas no código caso o teste ocorra entre computadores. Cada cliente deverá usar uma porta UDP diferente (sugestão: `5001`, `5002` e `5003`).

* **Justificativa:** O trabalho não permite usar só o IP para identificar os clientes, já que os testes ocorrerão no mesmo computador (localhost). Além disso, o servidor precisa saber a porta UDP de cada participante logo no início para conseguir enviar as notificações depois. Fixar os valores padrão do servidor e a sequência de perguntas do cliente evita que os dois sejam desenvolvidos com configurações diferentes, e atende a exigência de documentar os endereços e as portas utilizados. Deixar o IP e a porta do servidor no código simplifica a execução, e pedir os dados do cliente pelo terminal, em vez de argumentos, simplifica a execução de várias instâncias e atende à exigência de que o IP do servidor possa ser informado ou configurado.

### 2. Comunicação, Delimitação e Buffering TCP (Req. 2.2)

* **Decisão:** As mensagens serão estruturadas em **JSON codificado em UTF-8**. No TCP, o envio será feito em uma **linha única terminada com um `\n` (quebra de linha)**. Para ler os dados, tanto o cliente quanto o servidor terão um *buffer* (uma variável em memória) para ir acumulando os bytes que chegam do `recv()`. O JSON só será processado de fato quando o `\n` aparecer nesse buffer.

* **Justificativa:** Fazer esse acúmulo no buffer garante que o sistema cumpra a regra de não considerar que um único `recv()` já traz a mensagem inteira, protegendo o código caso a rede fragmente os pacotes. A escolha por JSON com `\n` ocorreu porque facilita bastante a leitura e a explicação do tráfego no Wireshark depois.

### 3. Concorrência e Gerenciamento de Estado (Req. 2.3)

* **Decisão:** O servidor utilizará **Multithreading** (com a biblioteca nativa `threading` do Python). Cada cliente conectado ganhará uma thread exclusiva, e o cronômetro do leilão rodará em outra thread separada. Para evitar conflitos no acesso aos dados, o estado do leilão (variáveis como `maior_lance` e `leilao_ativo`), além da rotina de gravação do arquivo de log, ficarão protegidos por **Locks (mutex)** (`threading.Lock()`).

* **Justificativa:** Alocar uma thread para cada cliente garante que o servidor atenda todos ao mesmo tempo. O *Lock* no lance impede contadores incorretos; o *Lock* na flag de estado impede que um lance seja aceito no milissegundo exato do encerramento; e o *Lock* no log evita que múltiplas threads corrompam o arquivo escrevendo simultaneamente.

### 4. Tratamento de Falhas e Robustez (Req. 2.4)

* **Decisão:** As chamadas de rede e as conversões do JSON ficarão isoladas dentro de blocos `try/except`. Se um cliente fechar o terminal de forma abrupta (gerando um erro no socket) ou mandar um JSON quebrado, a exceção vai estourar apenas na thread daquele cliente. O servidor principal seguirá rodando normalmente, apenas retirando o cliente desconectado da lista e avisando no log. Mensagens malformadas, com `action` desconhecida ou com campos obrigatórios ausentes receberão do servidor uma resposta `error` com o motivo, e a conexão continuará aberta.

* **Justificativa:** Isso atende diretamente à exigência de que comandos inválidos ou a queda de um cliente não podem derrubar o servidor. Responder ao cliente, em vez de apenas ignorar a mensagem, também facilita a demonstração do tratamento de entradas inválidas.

### 5. Sistema de Logs (Req. 2.5)

* **Decisão:** Será criada uma rotina para gravar os eventos num arquivo `.txt`. Cada linha seguirá um padrão organizado para facilitar o rastreamento: `[YYYY-MM-DD HH:MM:SS] | [TCP/UDP] | [ENVIO/RECEBIMENTO] | [IP:PORTA Origem -> IP:PORTA Destino] | [AÇÃO]`. O sistema também registrará no log quando o leilão iniciar, encerrar ou tiver um novo maior lance, além da entrada e saída de clientes e das rejeições de lance (com o motivo). A rotina de gravação será protegida por um `Lock` (`threading.Lock()`), para que várias threads não escrevam no arquivo ao mesmo tempo.

* **Justificativa:** Essa estrutura cobre a lista de campos obrigatórios exigida na seção de logs do trabalho, facilitando a demonstração dos testes na hora de apresentar.

# Planejamento Específico - Tema 3: Leilão Virtual

Esta seção detalha como o sistema implementará as regras de negócio exclusivas do leilão virtual, distribuindo as responsabilidades entre o servidor e os clientes.

### 1. Fluxo de Início e Controle de Tempo (Reqs. 1, 2 e 9)

* **Decisão:** O servidor iniciará em um estado de "Aguardando Participantes". Ele carregará os dados de um item fictício (nome, lance mínimo e duração de 60 segundos). O **terminal do próprio servidor** funcionará como o "organizador": aguardará o comando `start`, que só será aceito se houver pelo menos 3 clientes conectados. Cadastros só serão aceitos enquanto o servidor estiver em "Aguardando Participantes"; depois do `start`, novos clientes serão rejeitados. Assim que iniciado, o servidor avisará os clientes via TCP e acionará a thread com o contador exato de 60 segundos.

* **Justificativa:** Usar o terminal do servidor simplifica a implementação. A exigência estabelece que o tempo seja controlado pelo servidor, logo qualquer lance que chegue antes do aviso de início ou após o estouro do cronômetro será automaticamente rejeitado com mensagem de erro. Bloquear cadastros tardios mantém a lista de participantes fixa durante o leilão e simplifica o envio dos avisos.

### 2. Validação e Processamento de Lances (Reqs. 3, 4, 5 e 8)

* **Decisão:** O servidor vai aceitar apenas lances que sejam valores inteiros e positivos. O primeiro lance será aceito se for maior ou igual ao mínimo estipulado. Os lances subsequentes só serão aceitos se superarem estritamente o maior lance atual. Por conta do uso do `Lock`, lances de mesmo valor enviados ao mesmo tempo serão processados na ordem de chegada: o primeiro atualiza o valor atual, e o segundo será rejeitado por ser igual (e não maior) ao lance recém-atualizado. Toda rejeição usará um motivo padronizado: leilão não iniciado, leilão encerrado, valor inválido, lance abaixo do mínimo (primeiro lance) e lance inferior ou igual ao atual (demais lances).

* **Justificativa:** Isso atende diretamente a regra do trabalho de tratar lances simultâneos pela ordem de processamento do servidor, além de manter o histórico exato do participante que detém o maior lance no momento. Padronizar os motivos garante que servidor e cliente usem as mesmas mensagens, o que também facilita a demonstração dos casos de lance inferior ou repetido.

### 3. Confirmações e Respostas via TCP (Reqs. 6, 10 e 11)

* **Decisão:** Toda tentativa de lance enviada por um cliente receberá uma resposta síncrona obrigatória via TCP. Se aceito, o cliente recebe um "OK". Se rejeitado, a mensagem conterá o motivo exato. Ao final dos 60 segundos, o servidor enviará o histórico de lances aceitos (com o autor de cada lance) e o vencedor via TCP. Se não houver lances, enviará a mensagem de "ausência de vencedor". A consulta de situação (`status`) será respondida em qualquer momento, com um campo `estado` (`aguardando`, `em_andamento` ou `encerrado`); os campos de lance e de tempo só aparecem quando fazem sentido para aquele estado. **Para receber essa notificação assíncrona, o cliente implementará *multithreading*, mantendo uma thread dedicada exclusivamente para a leitura contínua do socket TCP.**

* **Justificativa:** Os requisitos exigem que a validação de lances ocorra via TCP com os devidos motivos. A adoção de *multithreading* no cliente contorna o bloqueio de I/O do teclado (ex: `input()` no Python), garantindo que mensagens de encerramento sejam recebidas imediatamente.

### 4. Distribuição de Avisos via UDP (Protocolos Específicos do Tema)

* **Decisão:** Sempre que um novo lance maior for aceito ou o leilão for encerrado, o servidor fará **envios individuais via unicast** de um datagrama UDP para a porta registrada de cada cliente ativo. **Do lado do cliente, é obrigatório executar um `bind()` no socket UDP para escutar esses avisos.** As mensagens UDP terão um campo `seq` (número de atualização sequencial).

* **Justificativa:** O envio unicast é mais seguro contra bloqueios de firewall. O `bind()` é requisito técnico para o SO entregar o pacote ao cliente. O UDP cumpre o requisito de avisos rápidos, e o número `seq` permite que o cliente ignore datagramas fora de ordem.

# Especificação do Protocolo de Aplicação (Mensagens TCP e UDP)

Documentação da estrutura exata dos pacotes JSON que vão trafegar entre cliente e servidor. Todas as mensagens TCP são enviadas em uma única linha e obrigatoriamente terminadas com o caractere de quebra de linha (`\n`).

### 1. Requisições TCP (Cliente ➔ Servidor)

**Cadastro de Participante**
Enviado assim que o cliente conecta ao servidor.

```json
{"action": "register", "nome": "nomedapessoa", "udp_port": 5001}
```

**Envio de Lance**
O valor deve ser numérico e inteiro.

```json
{"action": "bid", "valor": 250}
```

**Consulta de Situação**

```json
{"action": "status"}
```

### 2. Respostas TCP (Servidor ➔ Cliente)

**Confirmação de Cadastro (Aceito / Rejeitado)**

```json
{"action": "register_response", "status": "ok", "msg": "Conectado ao leilão."}
```

```json
{"action": "register_response", "status": "error", "msg": "Nome de usuário já em uso."}
```

```json
{"action": "register_response", "status": "error", "msg": "Leilão já em andamento. Cadastro encerrado."}
```

**Aviso de Início do Leilão**
Disparado pelo servidor quando o comando `start` é ativado.

```json
{"action": "auction_start", "item": "Ferrari F40", "lance_minimo": 100, "duracao_segundos": 60}
```

**Resposta ao Lance (Aceito / Rejeitado)**
Valida a tentativa de lance com os motivos explícitos exigidos no edital.

```json
{"action": "bid_response", "status": "accepted", "maior_lance": 250}
```

```json
{"action": "bid_response", "status": "rejected", "motivo": "Lance inferior ao atual. Maior lance é 250."}
```

```json
{"action": "bid_response", "status": "rejected", "motivo": "Leilão ainda não foi iniciado."}
```

```json
{"action": "bid_response", "status": "rejected", "motivo": "Valor inválido. O lance deve ser um número inteiro positivo."}
```

```json
{"action": "bid_response", "status": "rejected", "motivo": "Lance abaixo do mínimo. O lance mínimo é 100."}
```

```json
{"action": "bid_response", "status": "rejected", "motivo": "Leilão já foi encerrado."}
```

**Resposta de Consulta**
Retorna o estado atualizado do leilão, com o campo `estado` indicando a fase atual.

```json
{"action": "status_response", "estado": "em_andamento", "item": "Ferrari F40", "lance_minimo": 100, "maior_lance": 250, "vencedor_atual": "nomedapessoa", "tempo_restante_segundos": 42}
```

```json
{"action": "status_response", "estado": "aguardando", "item": "Ferrari F40", "lance_minimo": 100, "duracao_segundos": 60}
```

```json
{"action": "status_response", "estado": "encerrado", "item": "Ferrari F40", "vencedor": "nomedapessoa", "valor_final": 250}
```

**Encerramento do Leilão e Histórico**
Enviado quando o tempo esgota.

```json
{"action": "auction_end", "vencedor": "nomedapessoa", "valor_final": 250, "historico_lances": [{"autor": "ana", "valor": 100}, {"autor": "bruno", "valor": 150}, {"autor": "carla", "valor": 200}, {"autor": "nomedapessoa", "valor": 250}]}
```

*(Obs: Se não houver vencedor, o retorno será `{"action": "auction_end", "vencedor": null, "msg": "Ausencia de vencedor"}`)*

**Resposta de Erro Genérico**
Enviada quando a mensagem recebida é inválida (JSON malformado, `action` desconhecida ou campo obrigatório ausente). A conexão não é encerrada.

```json
{"action": "error", "msg": "Mensagem inválida: JSON malformado."}
```

```json
{"action": "error", "msg": "Ação desconhecida."}
```

```json
{"action": "error", "msg": "Campo obrigatório ausente: valor."}
```

### 3. Avisos UDP (Servidor ➔ Cliente)

Os datagramas UDP não precisam do delimitador `\n`. Carregam o campo numérico `seq` para descarte de mensagens atrasadas.

**Aviso de Novo Maior Lance**

```json
{"event": "new_bid", "valor": 250, "autor": "nomedapessoa", "seq": 1}
```

**Aviso de Encerramento**

```json
{"event": "end", "vencedor": "nomedapessoa", "valor_final": 250, "seq": 2}
```

## INTEGRANTES: Gabriel Müller Pacheco, Gustavo Sbardelotto Rezende, Ismael Scheele Reis, Vitor Rolim Rubio Auricchio
import json
import socket
import threading
import time
from datetime import datetime

# Constantes fixas
HOST = "0.0.0.0"
PORTA_TCP = 5000
ARQUIVO_LOG = "log_servidor.txt"
DURACAO = 60

# Configuração
ITEM = None
LANCE_MINIMO = None
MIN_CLIENTES = None

# Estado do leilão
estado = "aguardando" # aguardando | em_andamento | encerrado
clientes = {} # (nome, ip) -> Usuario
maior_lance = None # None enquanto não houver nenhum lance aceito
vencedor_atual = None
historico = [] # lista de {"autor": ..., "valor": ...}
seq = 0 # número sequencial dos avisos UDP
fim_leilao = 0.0 # instante (time.time) em que o leilão termina

# Locks
lock_estado = threading.Lock()
lock_log = threading.Lock()
lock_envio = threading.Lock()

# Socket UDP usado para enviar os avisos (unicast)
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


class Usuario:
    def __init__(self, nome, conn, addr, porta_udp):
        self.nome = nome
        self.conn = conn                      # socket TCP do usuário
        self.addr = addr                      # (ip, porta) TCP do usuário
        self.ip = addr[0]
        self.udp_addr = (addr[0], porta_udp)  # onde ele recebe os avisos UDP

    def chave(self):
        # Identificação única: tupla (nome, ip)
        return (self.nome, self.ip)



# Logs
def log(proto, direcao, rota, acao):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = f"[{agora}] | [{proto}] | [{direcao}] | [{rota}] | [{acao}]"
    with lock_log:
        with open(ARQUIVO_LOG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")

# Logs do Sistema
def log_evento(texto):
    print(texto)
    log("SISTEMA", "-", "-", texto)

def formatar_socket(addr):
    return f"{addr[0]}:{addr[1]}"



def enviar_tcp(conn, addr, msg):
    dados = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        with lock_envio:
            conn.sendall(dados)
        origem = formatar_socket(conn.getsockname())
        log("TCP", "ENVIO", f"{origem} -> {formatar_socket(addr)}", json.dumps(msg, ensure_ascii=False))
    except OSError:
        pass


def enviar_udp_para_todos(msg):
    dados = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    for u in clientes.values():
        try:
            udp_sock.sendto(dados, u.udp_addr)
            origem = formatar_socket(udp_sock.getsockname())
            log("UDP", "ENVIO", f"{origem} -> {formatar_socket(u.udp_addr)}", json.dumps(msg, ensure_ascii=False))
        except OSError:
            log_evento(f"Falha ao enviar UDP para {u.nome}")


def enviar_erro(conn, addr, texto):
    enviar_tcp(conn, addr, {"action": "error", "msg": texto})


# Registro
def tratar_register(conn, addr, sessao, msg):
    if sessao["usuario"] is not None:
        enviar_erro(conn, addr, "Cliente já cadastrado.")
        return

    for campo in ("nome", "udp_port"):
        if campo not in msg:
            enviar_erro(conn, addr, f"Campo obrigatório ausente: {campo}.")
            return

    nome = msg["nome"]
    porta_udp = msg["udp_port"]
    if not isinstance(nome, str) or nome.strip() == "":
        enviar_erro(conn, addr, "Nome inválido.")
        return
    if isinstance(porta_udp, bool) or not isinstance(porta_udp, int) or not (1 <= porta_udp <= 65535):
        enviar_erro(conn, addr, "Porta UDP inválida.")
        return

    novo = Usuario(nome, conn, addr, porta_udp)

    with lock_estado:
        if estado != "aguardando":
            resposta = {"action": "register_response", "status": "error",
                        "msg": "Leilão já em andamento. Cadastro encerrado."}
        elif novo.chave() in clientes:
            # Mesma tupla (nome, ip) já conectada
            resposta = {"action": "register_response", "status": "error",
                        "msg": "Usuário já conectado com este IP."}
        else:
            clientes[novo.chave()] = novo
            sessao["usuario"] = novo
            resposta = {"action": "register_response", "status": "ok",
                        "msg": "Conectado ao leilão."}

    enviar_tcp(conn, addr, resposta)
    if resposta["status"] == "ok":
        log_evento(f"Cliente '{nome}' entrou ({formatar_socket(addr)}, UDP {porta_udp})")
    else:
        log_evento(f"Cadastro rejeitado de '{nome}' ({formatar_socket(addr)}): {resposta['msg']}")


# Lance
def tratar_bid(conn, addr, sessao, msg):
    global maior_lance, vencedor_atual, seq

    usuario = sessao["usuario"]
    if usuario is None:
        enviar_erro(conn, addr, "Cadastro necessário antes de enviar lances.")
        return
    if "valor" not in msg:
        enviar_erro(conn, addr, "Campo obrigatório ausente: valor.")
        return

    valor = msg["valor"]
    motivo = None

    with lock_estado:
        if estado == "aguardando":
            motivo = "Leilão ainda não foi iniciado."
        elif estado == "encerrado":
            motivo = "Leilão já foi encerrado."
        elif isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
            motivo = "Valor inválido. O lance deve ser um número inteiro positivo."
        elif maior_lance is None and valor < LANCE_MINIMO:
            motivo = f"Lance abaixo do mínimo. O lance mínimo é {LANCE_MINIMO}."
        elif maior_lance is not None and valor <= maior_lance:
            motivo = f"Lance inferior ou igual ao atual. Maior lance é {maior_lance}."

        if motivo is None:
            # Lance aceito
            maior_lance = valor
            vencedor_atual = usuario.nome
            historico.append({"autor": usuario.nome, "valor": valor})
            seq += 1
            # UDP dentro do lock para manter a ordem dos seq
            enviar_udp_para_todos({"event": "new_bid", "valor": valor, "autor": usuario.nome, "seq": seq})
            resposta = {"action": "bid_response", "status": "accepted", "maior_lance": valor}
        else:
            resposta = {"action": "bid_response", "status": "rejected", "motivo": motivo}

    enviar_tcp(conn, addr, resposta)
    if motivo is None:
        log_evento(f"Novo maior lance: {valor} por '{usuario.nome}'")
    else:
        log_evento(f"Lance rejeitado de '{usuario.nome}' (valor={valor!r}): {motivo}")

# Status
def tratar_status(conn, addr):
    with lock_estado:
        if estado == "aguardando":
            resposta = {"action": "status_response", "estado": "aguardando", "item": ITEM,
                        "lance_minimo": LANCE_MINIMO, "duracao_segundos": DURACAO}
        elif estado == "em_andamento":
            resposta = {"action": "status_response", "estado": "em_andamento", "item": ITEM,
                        "lance_minimo": LANCE_MINIMO,
                        "tempo_restante_segundos": max(0, int(fim_leilao - time.time()))}
            if maior_lance is not None:
                resposta["maior_lance"] = maior_lance
                resposta["vencedor_atual"] = vencedor_atual
        else:
            resposta = {"action": "status_response", "estado": "encerrado", "item": ITEM,
                        "vencedor": vencedor_atual}
            if maior_lance is not None:
                resposta["valor_final"] = maior_lance
    enviar_tcp(conn, addr, resposta)

# Leitura
def processar_linha(conn, addr, linha, sessao):
    try:
        texto = linha.decode("utf-8")
        msg = json.loads(texto)
        if not isinstance(msg, dict):
            raise ValueError("não é objeto")
    except (UnicodeDecodeError, ValueError):
        log("TCP", "RECEBIMENTO", f"{formatar_socket(addr)} -> {formatar_socket(conn.getsockname())}", "JSON malformado")
        enviar_erro(conn, addr, "Mensagem inválida: JSON malformado.")
        return

    log("TCP", "RECEBIMENTO", f"{formatar_socket(addr)} -> {formatar_socket(conn.getsockname())}", texto)

    if "action" not in msg:
        enviar_erro(conn, addr, "Campo obrigatório ausente: action.")
        return

    acao = msg["action"]
    if acao == "register":
        tratar_register(conn, addr, sessao, msg)
    elif acao == "bid":
        tratar_bid(conn, addr, sessao, msg)
    elif acao == "status":
        tratar_status(conn, addr)
    else:
        enviar_erro(conn, addr, "Ação desconhecida.")


def lidar_cliente(conn, addr):
    sessao = {"usuario": None}
    buffer = b""
    try:
        while True:
            dados = conn.recv(4096)
            if not dados:
                break
            buffer += dados
            while b"\n" in buffer:
                linha, buffer = buffer.split(b"\n", 1)
                if linha.strip() == b"":
                    continue
                processar_linha(conn, addr, linha, sessao)
    except OSError:
        pass
    finally:
        usuario = sessao["usuario"]
        if usuario is not None:
            with lock_estado:
                clientes.pop(usuario.chave(), None)
            log_evento(f"Cliente '{usuario.nome}' saiu ({formatar_socket(addr)})")
        else:
            log_evento(f"Conexão encerrada: {formatar_socket(addr)}")
        conn.close()


def aceitar_conexoes(servidor):
    while True:
        try:
            conn, addr = servidor.accept()
        except OSError:
            break
        log_evento(f"Nova conexão TCP de {formatar_socket(addr)}")
        threading.Thread(target=lidar_cliente, args=(conn, addr), daemon=True).start()


# Tempo
def encerrar_leilao():
    global estado, seq
    time.sleep(DURACAO)

    with lock_estado:
        estado = "encerrado"
        seq += 1
        if maior_lance is None:
            fim_tcp = {"action": "auction_end", "vencedor": None, "msg": "Ausencia de vencedor"}
            aviso_udp = {"event": "end", "vencedor": None, "valor_final": None, "seq": seq}
        else:
            fim_tcp = {"action": "auction_end", "vencedor": vencedor_atual,
                       "valor_final": maior_lance, "historico_lances": list(historico)}
            aviso_udp = {"event": "end", "vencedor": vencedor_atual,
                         "valor_final": maior_lance, "seq": seq}
        enviar_udp_para_todos(aviso_udp)
        destinatarios = list(clientes.values())

    log_evento(f"Leilão encerrado. Vencedor: {fim_tcp['vencedor']}")
    for u in destinatarios:
        enviar_tcp(u.conn, u.addr, fim_tcp)


def iniciar_leilao():
    global estado, fim_leilao
    with lock_estado:
        if estado != "aguardando":
            print("O leilão já foi iniciado.")
            return
        if len(clientes) < MIN_CLIENTES:
            print(f"São necessários pelo menos {MIN_CLIENTES} clientes (conectados: {len(clientes)}).")
            return
        estado = "em_andamento"
        fim_leilao = time.time() + DURACAO
        destinatarios = list(clientes.values())

    log_evento(f"Leilão iniciado: {ITEM}, lance mínimo {LANCE_MINIMO}, duração {DURACAO}s")
    aviso = {"action": "auction_start", "item": ITEM,
             "lance_minimo": LANCE_MINIMO, "duracao_segundos": DURACAO}
    for u in destinatarios:
        enviar_tcp(u.conn, u.addr, aviso)

    threading.Thread(target=encerrar_leilao, daemon=True).start()


# Leitura de Inteiros
def ler_inteiro_positivo(pergunta):
    while True:
        texto = input(pergunta).strip()
        if texto.isdigit() and int(texto) > 0:
            return int(texto)
        print("Valor inválido. Digite um número inteiro positivo.")


# IP Local
def obter_ip_local():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()

# Configuração
def configurar():
    global ITEM, LANCE_MINIMO, MIN_CLIENTES

    # Nome do item
    while True:
        nome_item = input("Nome do item: ").strip()
        if nome_item != "":
            ITEM = nome_item
            break
        print("O nome do item não pode ser vazio.")

    LANCE_MINIMO = ler_inteiro_positivo("Lance mínimo: ")
    MIN_CLIENTES = ler_inteiro_positivo("Mínimo de usuários para iniciar: ")


# Inicialização
def main():
    configurar()

    udp_sock.bind((HOST, 0))

    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind((HOST, PORTA_TCP))
    servidor.listen()
    log_evento(f"Servidor ouvindo em {HOST}:{PORTA_TCP} (Aguardando Participantes)")
    log_evento(f"IP local da máquina na rede: {obter_ip_local()}")
    log_evento(f"Item: {ITEM} | Lance mínimo: {LANCE_MINIMO} | Mínimo de usuários: {MIN_CLIENTES}")

    threading.Thread(target=aceitar_conexoes, args=(servidor,), daemon=True).start()

    print(f"Digite 'start' para iniciar o leilão (mínimo de {MIN_CLIENTES} clientes).")
    try:
        while True:
            comando = input().strip().lower()
            if comando == "start":
                iniciar_leilao()
            elif comando != "":
                print("Comando desconhecido. Use: start")
    except (KeyboardInterrupt, EOFError):
        log_evento("Servidor finalizado")
    finally:
        servidor.close()


main()

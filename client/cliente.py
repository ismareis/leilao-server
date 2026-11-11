## INTEGRANTES: Gabriel Müller Pacheco, Gustavo Sbardelotto Rezende, Ismael Scheele Reis, Vitor Rolim Rubio Auricchio
import json
import socket
import threading
from datetime import datetime

# Padrões sugeridos (o usuário pode só apertar Enter)
IP_PADRAO = "127.0.0.1"
PORTA_TCP = 5000

# Estado do cliente
nome = None
arquivo_log = None
ultimo_seq = 0 # maior seq UDP já recebido
conectado = threading.Event() # limpo quando o servidor cai

# Locks
lock_log = threading.Lock()
lock_envio = threading.Lock()


# Logs
def log(proto, direcao, rota, acao):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = f"[{agora}] | [{proto}] | [{direcao}] | [{rota}] | [{acao}]"
    with lock_log:
        with open(arquivo_log, "a", encoding="utf-8") as f:
            f.write(linha + "\n")


def log_evento(texto):
    log("SISTEMA", "-", "-", texto)


def formatar_socket(addr):
    return f"{addr[0]}:{addr[1]}"


# Envio TCP
def enviar_tcp(sock, msg):
    texto = json.dumps(msg, ensure_ascii=False)
    try:
        with lock_envio:
            sock.sendall((texto + "\n").encode("utf-8"))
        rota = f"{formatar_socket(sock.getsockname())} -> {formatar_socket(sock.getpeername())}"
        log("TCP", "ENVIO", rota, texto)
        return True
    except OSError:
        print("Erro: não foi possível enviar a mensagem ao servidor.")
        return False


# Leitura TCP
def ler_linhas(sock, buffer):
    while True:
        while b"\n" in buffer:
            linha, buffer = buffer.split(b"\n", 1)
            if linha.strip() == b"":
                continue
            texto = linha.decode("utf-8", errors="replace")
            rota = f"{formatar_socket(sock.getpeername())} -> {formatar_socket(sock.getsockname())}"
            log("TCP", "RECEBIMENTO", rota, texto)
            try:
                msg = json.loads(texto)
            except ValueError:
                print("Aviso: mensagem malformada recebida do servidor.")
                continue
            if isinstance(msg, dict):
                yield msg
        dados = sock.recv(4096)
        if not dados:
            return
        buffer += dados


# Exibição das respostas do servidor
def mostrar_tcp(msg):
    acao = msg.get("action")

    if acao == "auction_start":
        print(f"\n*** LEILÃO INICIADO: {msg.get('item')} | lance mínimo {msg.get('lance_minimo')} "
              f"| duração {msg.get('duracao_segundos')}s ***")

    elif acao == "bid_response":
        if msg.get("status") == "accepted":
            print(f"\n[OK] Lance aceito. Maior lance agora: {msg.get('maior_lance')}")
        else:
            print(f"\n[REJEITADO] {msg.get('motivo')}")

    elif acao == "status_response":
        est = msg.get("estado")
        print(f"\n--- Situação: {est} | item: {msg.get('item')} ---")
        if est == "aguardando":
            print(f"Lance mínimo: {msg.get('lance_minimo')} | duração: {msg.get('duracao_segundos')}s")
        elif est == "em_andamento":
            print(f"Lance mínimo: {msg.get('lance_minimo')} | tempo restante: {msg.get('tempo_restante_segundos')}s")
            if "maior_lance" in msg:
                print(f"Maior lance: {msg['maior_lance']} ({msg.get('vencedor_atual')})")
            else:
                print("Nenhum lance ainda.")
        else:
            if msg.get("vencedor") is None:
                print("Encerrado sem vencedor.")
            else:
                print(f"Vencedor: {msg['vencedor']} com {msg.get('valor_final')}")

    elif acao == "auction_end":
        print("\n========== LEILÃO ENCERRADO ==========")
        if msg.get("vencedor") is None:
            print(msg.get("msg", "Ausência de vencedor"))
        else:
            print("Histórico de lances:")
            for lance in msg.get("historico_lances", []):
                print(f"  {lance.get('autor')}: {lance.get('valor')}")
            print(f"Vencedor: {msg['vencedor']} com {msg.get('valor_final')}")
            if msg["vencedor"] == nome:
                print("Parabéns, você venceu!")
        print("======================================")

    elif acao == "error":
        print(f"\n[ERRO DO SERVIDOR] {msg.get('msg')}")

    else:
        print(f"\nMensagem desconhecida do servidor: {msg}")

    print("> ", end="", flush=True)


# Thread que fica lendo o TCP o tempo todo
def thread_tcp(sock, buffer):
    try:
        for msg in ler_linhas(sock, buffer):
            mostrar_tcp(msg)
    except OSError:
        pass
    conectado.clear()
    log_evento("Conexão com o servidor encerrada")
    print("\nConexão com o servidor encerrada. Pressione Enter para sair.")


# Thread que escuta os avisos UDP
def thread_udp(udp_sock):
    global ultimo_seq
    while True:
        try:
            dados, addr = udp_sock.recvfrom(4096)
        except OSError:
            break
        texto = dados.decode("utf-8", errors="replace")
        log("UDP", "RECEBIMENTO", f"{formatar_socket(addr)} -> {formatar_socket(udp_sock.getsockname())}", texto)
        try:
            msg = json.loads(texto)
            seq = int(msg["seq"])
        except (ValueError, KeyError, TypeError):
            log_evento("Datagrama UDP inválido ignorado")
            continue

        # Descarta avisos atrasados / duplicados
        if seq <= ultimo_seq:
            log_evento(f"Aviso UDP seq={seq} descartado (último={ultimo_seq})")
            continue
        ultimo_seq = seq

        if msg.get("event") == "new_bid":
            print(f"\n[AVISO] Novo maior lance: {msg.get('valor')} por {msg.get('autor')}")
        elif msg.get("event") == "end":
            if msg.get("vencedor") is None:
                print("\n[AVISO] Leilão encerrado sem vencedor.")
            else:
                print(f"\n[AVISO] Leilão encerrado! Vencedor: {msg['vencedor']} ({msg.get('valor_final')})")
        print("> ", end="", flush=True)


# Leitura dos dados pelo terminal
def perguntar(pergunta, padrao=None):
    texto = input(f"{pergunta}" + (f" [{padrao}]" if padrao is not None else "") + ": ").strip()
    return texto if texto != "" else (str(padrao) if padrao is not None else "")


def ler_porta(pergunta, padrao=None):
    while True:
        texto = perguntar(pergunta, padrao)
        if texto.isdigit() and 1 <= int(texto) <= 65535:
            return int(texto)
        print("Porta inválida. Digite um número entre 1 e 65535.")


def configurar():
    global nome, arquivo_log
    ip = perguntar("IP do servidor", IP_PADRAO)
    while True:
        nome = perguntar("Seu nome")
        if nome != "":
            break
        print("O nome não pode ser vazio.")
    udp_sock, porta_udp = abrir_udp()
    arquivo_log = f"log_cliente_{nome}.txt"
    return ip, porta_udp, udp_sock


# bind() do UDP: se a porta estiver em uso, pede outra sem recomeçar tudo
def abrir_udp():
    while True:
        porta_udp = ler_porta("Porta UDP para receber avisos (ex: 5001)")
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            udp_sock.bind(("", porta_udp))
            return udp_sock, porta_udp
        except OSError:
            udp_sock.close()
            print(f"A porta UDP {porta_udp} já está em uso. Escolha outra.")


def mostrar_ajuda():
    print("Comandos:")
    print("  lance <valor>  (ou só o número) - envia um lance")
    print("  status                          - consulta a situação do leilão")
    print("  sair                            - encerra o cliente")


# Inicialização
def main():
    # O bind() do UDP é feito em configurar(), ANTES do cadastro, para não perder nenhum aviso
    ip, porta_udp, udp_sock = configurar()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((ip, PORTA_TCP))
    except OSError:
        print(f"Não foi possível conectar ao servidor {ip}:{PORTA_TCP}.")
        udp_sock.close()
        return
    conectado.set()
    log_evento(f"Conectado ao servidor {ip}:{PORTA_TCP} (UDP local {porta_udp})")

    # Cadastro: espera a resposta antes de liberar os comandos
    enviar_tcp(sock, {"action": "register", "nome": nome, "udp_port": porta_udp})
    buffer = b""
    resposta = None
    try:
        while b"\n" not in buffer:
            dados = sock.recv(4096)
            if not dados:
                break
            buffer += dados
        if b"\n" in buffer:
            linha, buffer = buffer.split(b"\n", 1)
            log("TCP", "RECEBIMENTO",
                f"{formatar_socket(sock.getpeername())} -> {formatar_socket(sock.getsockname())}",
                linha.decode("utf-8", errors="replace"))
            resposta = json.loads(linha.decode("utf-8"))
    except (OSError, ValueError):
        resposta = None

    if not isinstance(resposta, dict) or resposta.get("status") != "ok":
        motivo = resposta.get("msg") if isinstance(resposta, dict) else "sem resposta do servidor"
        print(f"Cadastro recusado: {motivo}")
        log_evento(f"Cadastro recusado: {motivo}")
        sock.close()
        udp_sock.close()
        return

    print(resposta.get("msg", "Cadastrado."))
    log_evento(f"Cadastrado como '{nome}'")
    mostrar_ajuda()

    threading.Thread(target=thread_tcp, args=(sock, buffer), daemon=True).start()
    threading.Thread(target=thread_udp, args=(udp_sock,), daemon=True).start()

    # Loop de comandos
    try:
        while conectado.is_set():
            entrada = input("> ").strip()
            if not conectado.is_set():
                break
            if entrada == "":
                continue
            partes = entrada.split()
            comando = partes[0].lower()

            if comando == "sair":
                break
            elif comando == "status":
                enviar_tcp(sock, {"action": "status"})
            elif comando == "ajuda":
                mostrar_ajuda()
            elif comando == "lance" or partes[0].lstrip("-").isdigit():
                texto_valor = partes[1] if comando == "lance" and len(partes) > 1 else partes[0]
                if comando == "lance" and len(partes) < 2:
                    print("Uso: lance <valor>")
                    continue
                try:
                    valor = int(texto_valor)
                except ValueError:
                    valor = texto_valor
                enviar_tcp(sock, {"action": "bid", "valor": valor})
            else:
                print("Comando desconhecido. Digite 'ajuda' para ver os comandos.")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        log_evento("Cliente finalizado")
        sock.close()
        udp_sock.close()
        print("Até mais!")


main()

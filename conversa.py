import json
import re
import urllib.request
import urllib.error
import logging

from acoes_sistema import AcoesSistema


class Conversa:
    URL = "http://localhost:11434/api/chat"
    URL_MODELOS = "http://localhost:11434/api/tags"
    URL_MODELOS_ATIVOS = "http://localhost:11434/api/ps"
    MODEL = "qwen3:4b-instruct"
    LIMITE_HISTORICO = 12
    RESPOSTA_ERRO_MODELO = (
        "Não consegui obter uma resposta. Verifique se o Ollama está em execução."
    )
    INSTRUCOES = """
    Seu nome é Mike. Você é o agente pessoal do usuário.
    Responda SEMPRE em português brasileiro, nunca em outro idioma.
    Responda apenas ao que foi perguntado, de forma direta, sem descrever
    o que está fazendo e sem explicações desnecessárias.
    Use somente texto simples: sem listas, markdown, asteriscos, emojis ou símbolos.
    Responda em no máximo 2 frases curtas, a menos que o usuário peça mais detalhes.
    Se não entender a mensagem, peça para o usuário repetir.
    Não invente informações sobre o usuário.
    """

    # Fim de frase: pontuação seguida de espaço ou quebra de linha
    PADRAO_FIM_FRASE = re.compile(r"[.!?:\n]\s")

    def __init__(self, db, reconhecedor, sintetizador, acoes_sistema=None):
        self.db = db
        self.reconhecedor = reconhecedor
        self.sintetizador = sintetizador
        self.acoes_sistema = acoes_sistema or AcoesSistema()
        self._dispositivo_ollama = None

    # ------------------------------------------------------------------
    # Modo texto
    # ------------------------------------------------------------------
    def iniciar_conversa_por_texto(self):
        if not self.verificar_modelo():
            logging.warning(
                "Ollama indisponível. Comandos do sistema continuarão ativos; "
                "respostas de conversa dependem do Ollama."
            )

        logging.info("Mike iniciado. Digite 'sair' para encerrar.")
        while True:
            try:
                mensagem = input("\nVocê: ").strip()
            except (KeyboardInterrupt, EOFError):
                logging.info("\nMike encerrado.")
                break

            if mensagem.lower() == "sair":
                logging.info("Até mais!")
                break

            if not mensagem:
                continue

            try:
                resposta = self.conversar(mensagem)
                logging.info(f"\nMike: {resposta}")
            except Exception as e:
                logging.error(f"Mike não conseguiu responder: {e}")

    # ------------------------------------------------------------------
    # Modo voz
    # ------------------------------------------------------------------
    def iniciar_conversa_por_voz(self):
        if not self.verificar_modelo():
            logging.warning(
                "Ollama indisponível. Comandos do sistema continuarão ativos; "
                "respostas de conversa dependem do Ollama."
            )

        self.sintetizador.criar_sintetizador()
        self.reconhecedor.iniciar_modelo_voz()

        if self.reconhecedor.modelo_voz is None:
            logging.error("Reconhecimento de voz indisponível. Use o modo texto: python app.py --texto")
            return

        logging.info("Mike iniciado. Modo de voz ativo. Pressione Ctrl+C para sair.")

        try:
            while True:
                logging.info("\nMike: Pode falar. Estou ouvindo.")
                try:
                    audio = self.reconhecedor.capturar_audio()
                except Exception as e:
                    logging.error(f"Erro ao acessar o microfone: {e}")
                    break

                if audio is None:
                    logging.warning("Não detectei fala. Vou tentar ouvir novamente.")
                    continue

                try:
                    mensagem = self.reconhecedor.transcrever_audio(audio)
                except Exception as e:
                    logging.error(f"Erro ao transcrever o áudio localmente: {e}")
                    continue

                if len(mensagem) < 2:
                    logging.warning("Não consegui reconhecer uma mensagem. Pode repetir.")
                    continue

                logging.info(f"\nVocê: {mensagem}")
                if self.verificar_saida(mensagem):
                    logging.info("Até mais!")
                    break

                try:
                    # Fala cada frase assim que ela fica pronta
                    resposta = self.conversar_falando(mensagem)
                    logging.info(f"\nMike: {resposta}")
                except Exception as e:
                    logging.error(f"Mike não conseguiu responder: {e}")
                    self.sintetizador.falar_resposta(self.RESPOSTA_ERRO_MODELO)
        except KeyboardInterrupt:
            logging.info("\nMike encerrado.")
        finally:
            self.sintetizador.encerrar_sintetizador()

    def verificar_modelo(self):
        """
        Confirma que o modelo existe no Ollama. Se não existir, tenta usar
        outro qwen3 "instruct" já instalado; se não houver, explica o que fazer.
        """
        try:
            with urllib.request.urlopen(self.URL_MODELOS, timeout=10) as resposta:
                dados = json.loads(resposta.read().decode("utf-8"))
            instalados = [m["name"] for m in dados.get("models", [])]
        except Exception as e:
            logging.error(f"Não foi possível falar com o Ollama (ele está rodando?): {e}")
            return False

        if self.MODEL in instalados or f"{self.MODEL}:latest" in instalados:
            return True

        candidatos = [n for n in instalados if n.startswith("qwen3") and "instruct" in n]
        if candidatos:
            logging.warning(f"Modelo '{self.MODEL}' não encontrado. Usando '{candidatos[0]}'.")
            self.MODEL = candidatos[0]
            return True

        logging.error(
            f"O modelo '{self.MODEL}' não está instalado. "
            f"Instalados: {', '.join(instalados) or 'nenhum'}. "
            f"Rode no terminal: ollama pull {self.MODEL}"
        )
        return False

    def verificar_saida(self, mensagem):
        return mensagem.lower() in {"sair", "encerrar", "parar"}

    # ------------------------------------------------------------------
    # Conversa (resposta completa, usada no modo texto)
    # ------------------------------------------------------------------
    def montar_mensagens(self, mensagem):
        return [
            {"role": "system", "content": self.INSTRUCOES},
            *self.db.carregar_historico(self.LIMITE_HISTORICO),
            {"role": "user", "content": mensagem}
        ]

    def conversar(self, mensagem):
        resposta_acao = self.acoes_sistema.processar(mensagem)
        if resposta_acao is not None:
            self.salvar_turno(mensagem, resposta_acao)
            return resposta_acao

        mensagens = self.montar_mensagens(mensagem)

        try:
            resposta_mike = self.consultar_modelo(mensagens)
        except Exception as e:
            logging.error(f"Erro ao consultar o modelo: {e}")
            raise

        self.salvar_turno(mensagem, resposta_mike)

        return resposta_mike

    # ------------------------------------------------------------------
    # Conversa com streaming (usada no modo voz)
    # ------------------------------------------------------------------
    def conversar_falando(self, mensagem):
        """
        Recebe a resposta do modelo aos poucos e fala cada frase
        assim que ela termina, sem esperar a resposta inteira.
        """
        resposta_acao = self.acoes_sistema.processar(mensagem)
        if resposta_acao is not None:
            self.salvar_turno(mensagem, resposta_acao)
            self.sintetizador.falar_resposta(resposta_acao)
            return resposta_acao

        mensagens = self.montar_mensagens(mensagem)

        completo = ""
        buffer = ""

        for trecho in self.consultar_modelo_stream(mensagens):
            completo += trecho
            buffer += trecho

            frases, buffer = self.extrair_frases(buffer)
            for frase in frases:
                self.sintetizador.falar_resposta(frase)

        # Sobra do final (última frase, que costuma não ter espaço depois)
        resto = self.limpar_think(buffer).strip()
        if resto:
            self.sintetizador.falar_resposta(resto)

        completo = self.limpar_think(completo).strip()
        if not completo:
            raise RuntimeError("O Ollama retornou uma resposta vazia.")

        self.salvar_turno(mensagem, completo)

        return completo

    def salvar_turno(self, mensagem, resposta):
        self.db.salvar_historico([
            {"role": "user", "content": mensagem},
            {"role": "assistant", "content": resposta},
        ])

    def extrair_frases(self, buffer):
        """
        Separa do buffer as frases já completas.
        Retorna (lista_de_frases, texto_restante).
        Blocos <think> são removidos e nunca chegam a ser falados.
        """
        # Remove blocos <think>...</think> completos
        buffer = re.sub(r"<think>.*?</think>", "", buffer, flags=re.DOTALL)

        # Se há um <think> ainda aberto, segura esse trecho até ele fechar
        inicio_think = buffer.find("<think>")
        if inicio_think != -1:
            seguro, pendente = buffer[:inicio_think], buffer[inicio_think:]
        else:
            seguro, pendente = buffer, ""

        frases = []
        while True:
            fim = self.PADRAO_FIM_FRASE.search(seguro)
            if not fim:
                break
            frase = seguro[:fim.end()].strip()
            seguro = seguro[fim.end():]
            if frase:
                frases.append(frase)

        return frases, seguro + pendente

    def limpar_think(self, texto):
        # Alguns modelos "thinking" omitem o <think> de abertura e só escrevem o </think>:
        # nesse caso, tudo antes do último </think> é raciocínio.
        if "</think>" in texto:
            texto = texto.rsplit("</think>", 1)[1]
        texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL)
        # Remove também um <think> que ficou aberto até o final
        return re.sub(r"<think>.*", "", texto, flags=re.DOTALL)

    # ------------------------------------------------------------------
    # Comunicação com o Ollama
    # ------------------------------------------------------------------
    def criar_dados(self, mensagens, stream):
        return {
            "model": self.MODEL,
            "messages": mensagens,
            "stream": stream,
            "keep_alive": "60m",
            "think": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 64,
                "num_ctx": 2048
            }
        }

    def criar_requisicao(self, dados):
        return urllib.request.Request(
            self.URL,
            data=json.dumps(dados, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )

    def consultar_modelo(self, mensagens):
        dados = self.criar_dados(mensagens, stream=False)

        try:
            requisicao = self.criar_requisicao(dados)

            with urllib.request.urlopen(requisicao, timeout=180) as resposta:
                resultado = json.loads(resposta.read().decode("utf-8"))

            conteudo = resultado["message"]["content"]
            conteudo = self.limpar_think(conteudo).strip()
            if not conteudo:
                raise RuntimeError("O Ollama retornou uma resposta vazia.")
            self.verificar_dispositivo_ollama()
            return conteudo

        except urllib.error.URLError as e:
            logging.error(f"Não foi possível conectar ao Ollama (Verifique se o serviço está rodando): {e}")
            raise
        except json.JSONDecodeError as e:
            logging.error(f"Erro ao decodificar resposta JSON: {e}")
            raise
        except Exception as e:
            logging.error(f"Erro ao consultar o modelo: {e}")
            raise

    def consultar_modelo_stream(self, mensagens):
        """Gera os pedaços de texto da resposta conforme o Ollama os produz."""
        dados = self.criar_dados(mensagens, stream=True)

        try:
            requisicao = self.criar_requisicao(dados)

            with urllib.request.urlopen(requisicao, timeout=180) as resposta:
                for linha in resposta:
                    linha = linha.strip()
                    if not linha:
                        continue

                    parte = json.loads(linha.decode("utf-8"))

                    trecho = parte.get("message", {}).get("content", "")
                    if trecho:
                        yield trecho

                    if parte.get("done"):
                        break

            self.verificar_dispositivo_ollama()

        except urllib.error.URLError as e:
            logging.error(f"Não foi possível conectar ao Ollama (Verifique se o serviço está rodando): {e}")
            raise
        except json.JSONDecodeError as e:
            logging.error(f"Erro ao decodificar resposta JSON: {e}")
            raise
        except Exception as e:
            logging.error(f"Erro ao consultar o modelo: {e}")
            raise

    def verificar_dispositivo_ollama(self):
        try:
            with urllib.request.urlopen(self.URL_MODELOS_ATIVOS, timeout=3) as resposta:
                dados = json.loads(resposta.read().decode("utf-8"))
        except Exception as e:
            logging.warning(f"Não consegui confirmar o uso da GPU pelo Ollama: {e}")
            return

        modelo = next(
            (
                item for item in dados.get("models", [])
                if item.get("name") == self.MODEL or item.get("model") == self.MODEL
            ),
            None,
        )
        if modelo is None:
            logging.warning(
                "O Ollama não informou o dispositivo do modelo '%s'. "
                "Confira com 'ollama ps'.",
                self.MODEL,
            )
            return

        size_vram = modelo.get("size_vram", 0)
        dispositivo = "gpu" if size_vram else "cpu"
        if dispositivo == self._dispositivo_ollama:
            return

        self._dispositivo_ollama = dispositivo
        if size_vram:
            logging.info(
                "Ollama alocou %.2f GiB do modelo na GPU.",
                size_vram / (1024 ** 3),
            )
        else:
            logging.warning(
                "Aviso: Ollama está executando '%s' na CPU, não na GPU. "
                "A resposta continuará, mas pode ficar mais lenta; confira 'ollama ps'.",
                self.MODEL,
            )

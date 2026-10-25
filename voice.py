import logging
import os
import re
import tempfile
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd
from pywhispercpp.model import Model

try:
    from piper import PiperVoice
except ImportError:
    PiperVoice = None


class Voice:
    MODELO_WHISPER = "small"
    FREQUENCIA_AUDIO = 16_000
    DURACAO_BLOCO = 0.25
    LIMITE_ESPERA_FALA = 15
    DURACAO_MAXIMA_FALA = 30
    LIMITE_SILENCIO = 1.2
    LIMIAR_AUDIO = 0.02

    # False = o Mike só mostra a resposta em texto no terminal (sem falar).
    # True  = o Mike também fala a resposta em voz alta.
    FALAR_RESPOSTA = True
    LIMITE_CARACTERES_FALA = 400   # trava de segurança: nunca fala mais que isso por vez

    VOZ_PIPER = "Voices/pt_BR-faber-medium.onnx"
    ESCALA_DURACAO_PIPER = 1.15  # Acima de 1 desacelera a fala sem alterar o tom.

    # Correções de pronúncia: palavra que o Piper fala errado -> como escrever para soar certo.
    # Só afeta a fala; o texto mostrado no terminal e salvo no banco não muda.
    CORRECOES_PRONUNCIA = {
    }

    # Efeito de voz robótica (companheiro robô: leve e simpático)
    EFEITO_ROBO = True
    FATOR_TOM = 1.0            # Mantém o tom e a duração originais.
    FREQ_MODULACAO = 70        # Hz. Menor = vibrante/rouco, maior = metálico (30 a 120)
    MISTURA_ROBO = 0.06        # Modulação sutil para preservar as consoantes.
    FREQ_TREMOLO = 5           # Oscilação lenta de volume com efeito caricatural.
    PROFUNDIDADE_TREMOLO = 0.08
    ATRASO_METALICO_MS = 0     # Eco pode borrar as consoantes.
    INTENSIDADE_ECO = 0.0
    BITS = 0                  # menos bits = mais "videogame antigo" (0 desliga; 6 a 12)
    VOLUME_FINAL = 0.9         # 0 a 1

    def __init__(self):
        self.sintetizador = None
        self.modelo_voz = None

    # ------------------------------------------------------------------
    # Síntese de voz (Piper)
    # ------------------------------------------------------------------
    def criar_sintetizador(self):
        if PiperVoice is None:
            logging.error("A biblioteca 'piper-tts' não está instalada no ambiente.")
            logging.warning("O Mike continuará a responder apenas em modo de texto.")
            return

        try:
            # Procura o arquivo na pasta do script, não na pasta de execução
            caminho_modelo = Path(__file__).resolve().parent / self.VOZ_PIPER

            if not caminho_modelo.exists():
                logging.error(f"Arquivo de voz não encontrado em: {caminho_modelo}")
                logging.warning("O Mike continuará a responder apenas em modo de texto.")
                self.sintetizador = None
                return

            self.sintetizador = PiperVoice.load(str(caminho_modelo))
            self.sintetizador.config.length_scale = self.ESCALA_DURACAO_PIPER
            logging.info("Sintetizador de voz local (Piper) inicializado com sucesso.")
        except Exception as e:
            logging.error(f"Erro ao preparar o sintetizador Piper: {e}")
            logging.warning("O Mike continuará a responder apenas em modo de texto.")
            self.sintetizador = None

    def encerrar_sintetizador(self):
        self.sintetizador = None

    def _sintetizar(self, texto):
        """
        Gera o áudio com o Piper e retorna (amostras_float32, taxa_amostragem).
        Funciona tanto com piper-tts >= 1.3 quanto com versões anteriores.
        """
        # API nova (piper-tts >= 1.3): synthesize(texto) retorna blocos de áudio
        try:
            blocos = []
            taxa = None
            for bloco in self.sintetizador.synthesize(texto):
                blocos.append(bloco.audio_int16_array)
                taxa = getattr(bloco, "sample_rate", None) or taxa

            if blocos:
                amostras = np.concatenate(blocos).astype(np.float32) / 32768.0
                if not taxa:
                    taxa = self.sintetizador.config.sample_rate
                return amostras, taxa
            return None, None
        except TypeError:
            # API antiga (piper-tts <= 1.2): synthesize(texto, arquivo_wav)
            pass

        caminho_audio = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as arquivo_temp:
                caminho_audio = arquivo_temp.name

            with wave.open(caminho_audio, "wb") as wav_file:
                self.sintetizador.synthesize(texto, wav_file)

            with wave.open(caminho_audio, "rb") as wav_file:
                taxa = wav_file.getframerate()
                frames = wav_file.readframes(wav_file.getnframes())

            amostras = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            if not taxa or taxa <= 0:
                taxa = 22050
            return amostras, taxa
        finally:
            if caminho_audio and os.path.exists(caminho_audio):
                try:
                    os.unlink(caminho_audio)
                except OSError:
                    pass

    def _aplicar_efeito_robo(self, amostras, taxa):
        """Deixa a voz levemente robótica e caricata. Ajuste pelas constantes da classe."""
        if not self.EFEITO_ROBO:
            return amostras

        # 1. Muda o tom (e a velocidade junto): dá um jeito de "robozinho"
        if self.FATOR_TOM != 1.0:
            novo_tamanho = int(len(amostras) / self.FATOR_TOM)
            if novo_tamanho > 1:
                amostras = np.interp(
                    np.linspace(0, len(amostras) - 1, novo_tamanho),
                    np.arange(len(amostras)),
                    amostras
                ).astype(np.float32)

        # 2. Modulação em anel: multiplica a voz por uma senoide (som clássico de robô)
        if self.MISTURA_ROBO > 0:
            t = np.arange(len(amostras)) / taxa
            portadora = np.sin(2 * np.pi * self.FREQ_MODULACAO * t).astype(np.float32)
            amostras = (
                (1 - self.MISTURA_ROBO) * amostras
                + self.MISTURA_ROBO * (amostras * portadora)
            )

        # 3. Tremolo lento e discreto para dar personalidade sem alterar os fonemas.
        if self.PROFUNDIDADE_TREMOLO > 0:
            t = np.arange(len(amostras)) / taxa
            tremolo = 1 - self.PROFUNDIDADE_TREMOLO * (
                0.5 + 0.5 * np.sin(2 * np.pi * self.FREQ_TREMOLO * t)
            )
            amostras = amostras * tremolo.astype(np.float32)

        # 4. Eco curtinho: deixa o som metálico, de "lata"
        atraso = int(taxa * self.ATRASO_METALICO_MS / 1000)
        if atraso > 0 and len(amostras) > atraso:
            eco = np.zeros_like(amostras)
            eco[atraso:] = amostras[:-atraso]
            amostras = amostras + self.INTENSIDADE_ECO * eco

        # 5. Redução de bits: som digital levemente "quebrado"
        if self.BITS and self.BITS > 0:
            niveis = 2 ** (self.BITS - 1)
            amostras = np.round(amostras * niveis) / niveis

        # 6. Normaliza o volume para não estourar e manter todas as frases iguais
        pico = np.max(np.abs(amostras))
        if pico > 0:
            amostras = amostras / pico * self.VOLUME_FINAL

        return amostras.astype(np.float32)

    def _limpar_para_fala(self, texto):
        texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL)
        texto = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", texto)   # links markdown
        texto = re.sub(r"[^\w\s.,!?;:'\-]", " ", texto)          # símbolos e emojis
        texto = re.sub(r"\s+", " ", texto).strip()

        for palavra, pronuncia in self.CORRECOES_PRONUNCIA.items():
            texto = re.sub(
                rf"\b{re.escape(palavra)}\b", pronuncia, texto, flags=re.IGNORECASE
            )

        return texto[:self.LIMITE_CARACTERES_FALA]

    def falar_resposta(self, texto):
        # A resposta em texto já é mostrada pelo Conversa; aqui só decidimos se fala.
        if not self.FALAR_RESPOSTA:
            return

        if self.sintetizador is None:
            print(f"\nMike (Texto): {texto}")
            return

        try:
            texto = self._limpar_para_fala(texto)
            if not texto:
                return

            amostras, taxa = self._sintetizar(texto)
            if amostras is None or len(amostras) == 0:
                return

            amostras = self._aplicar_efeito_robo(amostras, taxa)

            # Não passar 'channels' aqui: o sounddevice deduz do formato do array
            sd.play(amostras, samplerate=taxa, blocking=True)
        except Exception as e:
            logging.error(f"Erro ao reproduzir a resposta em áudio com Piper: {e}")
            print(f"\nMike (Texto alternativo): {texto}")

    # ------------------------------------------------------------------
    # Reconhecimento de voz (Whisper)
    # ------------------------------------------------------------------
    def iniciar_modelo_voz(self):
        try:
            logging.info("Carregando o modelo Whisper local...")
            self.modelo_voz = Model(
                self.MODELO_WHISPER,
                n_threads=4,
                print_realtime=False,
                print_progress=False
            )
            logging.info("Modelo Whisper carregado com sucesso.")
        except Exception as e:
            logging.error(f"Não foi possível preparar o reconhecimento de voz local: {e}")
            self.modelo_voz = None

    def capturar_audio(self):
        bloco = int(self.FREQUENCIA_AUDIO * self.DURACAO_BLOCO)
        amostras = []
        inicio = time.monotonic()
        inicio_fala = None
        amostras_silencio = 0
        limite_amostras_silencio = int(self.FREQUENCIA_AUDIO * self.LIMITE_SILENCIO)

        try:
            with sd.InputStream(
                samplerate=self.FREQUENCIA_AUDIO,
                channels=1,
                dtype="float32",
                blocksize=bloco
            ) as microfone:
                while True:
                    agora = time.monotonic()
                    if inicio_fala is None and agora - inicio >= self.LIMITE_ESPERA_FALA:
                        break
                    if inicio_fala is not None and agora - inicio_fala >= self.DURACAO_MAXIMA_FALA:
                        break

                    audio, estouro = microfone.read(bloco)
                    if estouro:
                        logging.warning("Aviso do microfone: overflow de áudio.")

                    audio = audio[:, 0].copy()
                    nivel = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))

                    if inicio_fala is None:
                        if nivel < self.LIMIAR_AUDIO:
                            continue
                        inicio_fala = time.monotonic()
                        logging.info("Estou ouvindo...")

                    amostras.append(audio)

                    if nivel < self.LIMIAR_AUDIO:
                        amostras_silencio += len(audio)
                        if amostras_silencio >= limite_amostras_silencio:
                            break
                    else:
                        amostras_silencio = 0

            if not amostras:
                return None

            return np.concatenate(amostras)
        except sd.PortAudioError as e:
            logging.error(f"Erro ao acessar o microfone: {e}")
            return None

    def transcrever_audio(self, audio):
        if self.modelo_voz is None:
            raise RuntimeError("O modelo Whisper não foi carregado.")

        caminho_temporario = None
        try:
            audio_pcm = np.clip(audio * 32767, -32768, 32767).astype("<i2")
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as arquivo:
                caminho_temporario = Path(arquivo.name)

            with wave.open(str(caminho_temporario), "wb") as arquivo:
                arquivo.setnchannels(1)
                arquivo.setsampwidth(2)
                arquivo.setframerate(self.FREQUENCIA_AUDIO)
                arquivo.writeframes(audio_pcm.tobytes())

            segmentos = self.modelo_voz.transcribe(
                str(caminho_temporario),
                language="pt"
            )
            texto = " ".join(segmento.text.strip() for segmento in segmentos)
            # Remove marcações que o Whisper inventa com ruído: [MÚSICA], (risos), etc.
            texto = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", texto)
            return re.sub(r"\s+", " ", texto).strip()
        finally:
            if caminho_temporario is not None:
                caminho_temporario.unlink(missing_ok=True)

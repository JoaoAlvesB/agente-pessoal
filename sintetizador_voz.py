import logging
import os
import re
import tempfile
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

try:
    from piper import PiperVoice
except ImportError:
    PiperVoice = None

try:
    from piper import SynthesisConfig
except ImportError:
    SynthesisConfig = None


class SintetizadorVoz:
    FALAR_RESPOSTA = True
    LIMITE_CARACTERES_FALA = 400
    VOZ_PIPER = "Voices/pt_BR-faber-medium.onnx"

    ESCALA_DURACAO_PIPER = 1.25
    NOISE_SCALE = 0.4
    NOISE_W_SCALE = 0.35

    REFORCO_FONEMAS = True
    REPETICOES_REFORCO = 2
    REFORCAR_R = True
    REFORCAR_S = True
    REFORCAR_L = True
    REFORCAR_VOGAL_FINAL = True
    MOSTRAR_FONEMAS = False
    SILENCIO_FINAL_MS = 80

    CORRECOES_PRONUNCIA = {
        "IA": "I-A",
        "Whisper": "Uísper",
        "Python": "Paiton",
        "API": "A-P-I",
        "Piper": "Paíper",
        "conversa": "convérrsa",
    }

    EFEITO_ROBO = True              # Liga/desliga os efeitos robóticos.
    FATOR_TOM = 1.0                  # 1.0 mantém a voz; >1 mais lenta/grave; <1 mais rápida/aguda.
    FREQ_MODULACAO = 60              # Modulação metálica em Hz; experimente 30–100.
    MISTURA_ROBO = 0.30              # Intensidade metálica: 0 desliga; use entre 0 e 1.
    FREQ_TREMOLO = 4                  # Velocidade da oscilação de volume, em Hz.
    PROFUNDIDADE_TREMOLO = 0.03      # Intensidade do tremolo: 0 desliga; use entre 0 e 1.
    ATRASO_METALICO_MS = 0           # Atraso do eco em ms; 0 desliga; experimente 2–20.
    INTENSIDADE_ECO = 0            # Volume do eco: 0 desliga; valores baixos preservam clareza.
    BITS = 0                          # Bitcrush: 0 desliga; valores baixos aumentam distorção.
    VOLUME_FINAL = 0.9                # Volume final: entre 0 e 1; acima de 1 pode distorcer.

    _RE_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
    _RE_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
    _RE_SIMBOLOS = re.compile(r"[^\w\s.,!?;:'\-]")
    _RE_ESPACOS = re.compile(r"\s+")

    _VOGAIS = frozenset("aeiouɐɛɔəɪʊɨɑæɜɞyøœʌɯɚãẽĩõũ")
    _SEMIVOGAIS = frozenset("wjɰ")
    _R_BATIDO = frozenset("ɾrɹɻ")
    _R_FORTE = frozenset("xhʁɣχʀ")
    _SIBILANTES = frozenset("szʃʒ")
    _LATERAIS = frozenset("lɫ")
    _IGNORAR = frozenset("ˈˌːˑʲ\u0303\u0329\u032f,.;:!?…-—'\"()")

    def __init__(self):
        self.sintetizador = None
        self._config_sintese = None
        self._reforco_indisponivel = False
        self._chave_correcoes = None
        self._regex_correcoes = []

    def criar_sintetizador(self):
        if PiperVoice is None:
            logging.error("A biblioteca 'piper-tts' não está instalada no ambiente.")
            logging.warning("O Mike continuará a responder apenas em modo de texto.")
            return

        try:
            caminho_modelo = Path(__file__).resolve().parent / self.VOZ_PIPER
            if not caminho_modelo.exists():
                logging.error(f"Arquivo de voz não encontrado em: {caminho_modelo}")
                logging.warning("O Mike continuará a responder apenas em modo de texto.")
                self.sintetizador = None
                return

            self.sintetizador = PiperVoice.load(str(caminho_modelo))
            if SynthesisConfig is not None:
                self._config_sintese = SynthesisConfig(
                    length_scale=self.ESCALA_DURACAO_PIPER,
                    noise_scale=self.NOISE_SCALE,
                    noise_w_scale=self.NOISE_W_SCALE,
                )

            logging.info("Sintetizador de voz local (Piper) inicializado com sucesso.")
        except Exception as e:
            logging.error(f"Erro ao preparar o sintetizador Piper: {e}")
            logging.warning("O Mike continuará a responder apenas em modo de texto.")
            self.sintetizador = None
            return

        try:
            self._sintetizar("Olá.")
        except Exception as e:
            logging.debug(f"Aquecimento do Piper não concluído: {e}")

    def encerrar_sintetizador(self):
        self.sintetizador = None

    def _sintetizar(self, texto):
        if self._config_sintese is not None:
            if self.REFORCO_FONEMAS and not self._reforco_indisponivel:
                try:
                    return self._sintetizar_com_reforco(texto)
                except Exception as e:
                    self._reforco_indisponivel = True
                    logging.warning(
                        f"Reforço de fonemas indisponível nesta versão do Piper ({e}). "
                        "Usando a síntese padrão."
                    )

            blocos = []
            taxa = None
            for bloco in self.sintetizador.synthesize(texto, syn_config=self._config_sintese):
                blocos.append(bloco.audio_int16_array)
                taxa = getattr(bloco, "sample_rate", None) or taxa

            if not blocos:
                return None, None

            amostras = np.concatenate(blocos).astype(np.float32) / 32768.0
            if not taxa:
                taxa = getattr(self.sintetizador.config, "sample_rate", 22050)
            return amostras, taxa

        caminho_audio = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as arquivo_temp:
                caminho_audio = arquivo_temp.name

            with wave.open(caminho_audio, "wb") as wav_file:
                self.sintetizador.synthesize(
                    texto,
                    wav_file,
                    length_scale=self.ESCALA_DURACAO_PIPER,
                    noise_scale=self.NOISE_SCALE,
                    noise_w=self.NOISE_W_SCALE,
                )

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

    def _sintetizar_com_reforco(self, texto):
        voz = self.sintetizador
        blocos = []

        for fonemas in voz.phonemize(texto):
            if not fonemas:
                continue

            reforcados = self._reforcar_fonemas(fonemas)
            if self.MOSTRAR_FONEMAS:
                logging.info("Fonemas:     %s", "".join(fonemas))
                logging.info("Reforçados:  %s", "".join(reforcados))

            ids = voz.phonemes_to_ids(reforcados)
            audio = voz.phoneme_ids_to_audio(ids, self._config_sintese)
            if isinstance(audio, tuple):
                audio = audio[0]

            audio = np.asarray(audio, dtype=np.float32)
            pico = float(np.max(np.abs(audio))) if audio.size else 0.0
            if pico > 1e-8:
                audio = audio / pico
            blocos.append(audio)

        if not blocos:
            return None, None
        return np.concatenate(blocos), voz.config.sample_rate

    def _reforcar_fonemas(self, fonemas):
        n = max(1, int(self.REPETICOES_REFORCO))
        if n == 1:
            return fonemas

        saida = []
        palavra = []
        for fonema in fonemas:
            if fonema == " ":
                saida.extend(self._reforcar_palavra(palavra, n))
                saida.append(" ")
                palavra = []
            else:
                palavra.append(fonema)
        saida.extend(self._reforcar_palavra(palavra, n))
        return saida

    def _reforcar_palavra(self, palavra, n):
        reais = [i for i, fonema in enumerate(palavra) if fonema not in self._IGNORAR]
        if not reais:
            return palavra

        posicao = {i: k for k, i in enumerate(reais)}
        saida = []
        for i, fonema in enumerate(palavra):
            k = posicao.get(i)
            if k is None:
                saida.append(fonema)
                continue

            anterior = palavra[reais[k - 1]] if k > 0 else None
            seguinte = palavra[reais[k + 1]] if k + 1 < len(reais) else None
            vogal_antes = anterior in self._VOGAIS
            vogal_depois = seguinte in self._VOGAIS
            reforcar = False

            if self.REFORCAR_R and fonema in self._R_BATIDO:
                reforcar = (
                    anterior is not None
                    and not (vogal_antes and vogal_depois)
                    and seguinte not in self._SIBILANTES
                )
            elif self.REFORCAR_R and fonema in self._R_FORTE:
                reforcar = vogal_antes and not vogal_depois
            elif self.REFORCAR_S and fonema in self._SIBILANTES:
                reforcar = (vogal_antes or anterior in self._SEMIVOGAIS) and not vogal_depois
            elif self.REFORCAR_L and fonema in self._LATERAIS:
                reforcar = anterior is not None and not vogal_antes
            elif (
                self.REFORCAR_VOGAL_FINAL
                and fonema == "ɐ"
                and k == len(reais) - 1
                and len(reais) <= 3
            ):
                proximo = palavra[i + 1] if i + 1 < len(palavra) else None
                reforcar = proximo != "\u0303"

            if reforcar:
                saida.extend([fonema] * n)
            else:
                saida.append(fonema)
        return saida

    def _aplicar_efeito_robo(self, amostras, taxa):
        if not self.EFEITO_ROBO or len(amostras) == 0:
            return amostras

        if self.FATOR_TOM != 1.0:
            novo_tamanho = int(len(amostras) / self.FATOR_TOM)
            if novo_tamanho > 1:
                amostras = np.interp(
                    np.linspace(0, len(amostras) - 1, novo_tamanho),
                    np.arange(len(amostras)),
                    amostras,
                ).astype(np.float32)

        t = np.arange(len(amostras), dtype=np.float32) / taxa
        if self.MISTURA_ROBO > 0:
            portadora = np.sin(2 * np.pi * self.FREQ_MODULACAO * t).astype(np.float32)
            amostras = (1.0 - self.MISTURA_ROBO) * amostras + self.MISTURA_ROBO * (amostras * portadora)

        if self.PROFUNDIDADE_TREMOLO > 0:
            tremolo = 1.0 - self.PROFUNDIDADE_TREMOLO * (
                0.5 + 0.5 * np.sin(2 * np.pi * self.FREQ_TREMOLO * t)
            )
            amostras = amostras * tremolo.astype(np.float32)

        atraso = int(taxa * self.ATRASO_METALICO_MS / 1000)
        if atraso > 0 and self.INTENSIDADE_ECO > 0 and len(amostras) > atraso:
            eco = np.zeros_like(amostras)
            eco[atraso:] = amostras[:-atraso]
            amostras = amostras + self.INTENSIDADE_ECO * eco

        if self.BITS and self.BITS > 0:
            niveis = 2 ** (self.BITS - 1)
            amostras = np.round(amostras * niveis) / niveis

        pico = np.max(np.abs(amostras))
        if pico > 0:
            amostras = (amostras / pico) * self.VOLUME_FINAL
        return amostras.astype(np.float32)

    def _correcoes_compiladas(self):
        chave = tuple(self.CORRECOES_PRONUNCIA.items())
        if chave != self._chave_correcoes:
            self._regex_correcoes = [
                (
                    re.compile(
                        rf"\b{re.escape(palavra)}\b",
                        0 if palavra.isupper() else re.IGNORECASE,
                    ),
                    pronuncia,
                )
                for palavra, pronuncia in chave
            ]
            self._chave_correcoes = chave
        return self._regex_correcoes

    def _limpar_para_fala(self, texto):
        texto = self._RE_THINK.sub("", texto)
        texto = self._RE_LINK.sub(r"\1", texto)
        for padrao, pronuncia in self._correcoes_compiladas():
            texto = padrao.sub(pronuncia, texto)
        texto = self._RE_SIMBOLOS.sub(" ", texto)
        texto = self._RE_ESPACOS.sub(" ", texto).strip()
        return texto[:self.LIMITE_CARACTERES_FALA]

    def falar_resposta(self, texto):
        if not self.FALAR_RESPOSTA:
            return

        if self.sintetizador is None:
            print(f"\nMike (Texto): {texto}")
            return

        try:
            texto_limpo = self._limpar_para_fala(texto)
            if not texto_limpo:
                return

            amostras, taxa = self._sintetizar(texto_limpo)
            if amostras is None or len(amostras) == 0:
                return

            amostras = self._aplicar_efeito_robo(amostras, taxa)
            n_silencio = int(taxa * self.SILENCIO_FINAL_MS / 1000)
            if n_silencio > 0:
                amostras = np.concatenate(
                    [amostras, np.zeros(n_silencio, dtype=np.float32)]
                )

            sd.play(amostras, samplerate=taxa, blocking=True)
        except Exception as e:
            logging.error(f"Erro ao reproduzir a resposta em áudio com Piper: {e}")
            print(f"\nMike (Texto alternativo): {texto}")

    def parar_fala(self):
        try:
            sd.stop()
        except Exception:
            pass

    def enfileirar_fala(self, texto):
        self.falar_resposta(texto)

    def aguardar_fala(self):
        pass

    def falar(self, texto):
        self.falar_resposta(texto)

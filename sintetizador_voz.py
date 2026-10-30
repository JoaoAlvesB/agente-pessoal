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
    LIMITE_CARACTERES_FALA = 600 # Aumentado para respostas mais ricas
    VOZ_PIPER = "Voices/pt_BR-faber-medium.onnx"

    # Ajustes de Naturalidade (Régua ChatGPT)
    ESCALA_DURACAO_PIPER = 1.0  # 1.0 é a velocidade natural da voz
    NOISE_SCALE = 0.65          # Aumentado levemente para dar mais "vida" e menos artificialidade
    NOISE_W_SCALE = 0.8         # Melhora a variação tonal

    REFORCO_FONEMAS = True
    REPETICOES_REFORCO = 2
    REFORCAR_R = True
    REFORCAR_S = True
    REFORCAR_L = True
    REFORCAR_VOGAL_FINAL = True
    MOSTRAR_FONEMAS = False
    SILENCIO_FINAL_MS = 100

    CORRECOES_PRONUNCIA = {
        "IA": "I-A",
        "Whisper": "Uísper",
        "Python": "Paiton",
        "API": "A-P-I",
        "Piper": "Paíper",
        "conversa": "convérrsa",
    }

    # Efeitos Robóticos desativados por padrão para naturalidade máxima
    EFEITO_ROBO = False
    FATOR_TOM = 1.0
    FREQ_MODULACAO = 0
    MISTURA_ROBO = 0.0
    FREQ_TREMOLO = 0
    PROFUNDIDADE_TREMOLO = 0.0
    ATRASO_METALICO_MS = 0
    INTENSIDADE_ECO = 0
    BITS = 0
    VOLUME_FINAL = 1.0

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
    _IGNORAR = frozenset("ˈˌːˑʲ̩̃̏,.;:!?…-—'\"()")

    def __init__(self):
        self.sintetizador = None
        self._config_sintese = None
        self._reforco_indisponivel = False
        self._chave_correcoes = None
        self._regex_correcoes = []

    def criar_sintetizador(self):
        if PiperVoice is None:
            logging.error("A biblioteca 'piper-tts' não está instalada no ambiente.")
            return

        try:
            caminho_modelo = Path(__file__).resolve().parent / self.VOZ_PIPER
            if not caminho_modelo.exists():
                logging.error(f"Arquivo de voz não encontrado em: {caminho_modelo}")
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
            self.sintetizador = None

    def encerrar_sintetizador(self):
        self.sintetizador = None

    def _sintetizar(self, texto):
        if self._config_sintese is not None:
            if self.REFORCO_FONEMAS and not self._reforco_indisponivel:
                try:
                    return self._sintetizar_com_reforco(texto)
                except Exception as e:
                    self._reforco_indisponivel = True
                    logging.warning(f"Reforço de fonemas indisponível: {e}")

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

        return None, None

    def _sintetizar_com_reforco(self, texto):
        voz = self.sintetizador
        blocos = []

        for fonemas in voz.phonemize(texto):
            if not fonemas:
                continue

            reforcados = self._reforcar_fonemas(fonemas)
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
                reforcar = (anterior is not None and not (vogal_antes and vogal_depois) and seguinte not in self._SIBILANTES)
            elif self.REFORCAR_R and fonema in self._R_FORTE:
                reforcar = vogal_antes and not vogal_depois
            elif self.REFORCAR_S and fonema in self._SIBILANTES:
                reforcar = (vogal_antes or anterior in self._SEMIVOGAIS) and not vogal_depois
            elif self.REFORCAR_L and fonema in self._LATERAIS:
                reforcar = anterior is not None and not vogal_antes
            elif (self.REFORCAR_VOGAL_FINAL and fonema == "ɐ" and k == len(reais) - 1 and len(reais) <= 3):
                proximo = palavra[i + 1] if i + 1 < len(palavra) else None
                reforcar = proximo != "̃"

            if reforcar:
                saida.extend([fonema] * n)
            else:
                saida.append(fonema)
        return saida

    def _aplicar_efeito_robo(self, amostras, taxa):
        if not self.EFEITO_ROBO or len(amostras) == 0:
            return amostras
        # (Manutenção do código de efeito robo para caso o usuário queira reativar)
        return amostras

    def _correcoes_compiladas(self):
        chave = tuple(self.CORRECOES_PRONUNCIA.items())
        if chave != self._chave_correcoes:
            self._regex_correcoes = [
                (re.compile(rf"\b{re.escape(palavra)}\b", 0 if palavra.isupper() else re.IGNORECASE), pronuncia)
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
                amostras = np.concatenate([amostras, np.zeros(n_silencio, dtype=np.float32)])

            # blocking=False permite que o sistema continue processando
            # Mas para conversas simples, mantemos o controle de fluxo no conversa.py
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

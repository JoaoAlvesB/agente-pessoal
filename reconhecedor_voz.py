import logging
import re
import tempfile
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd
from pywhispercpp.model import Model


class ReconhecedorVoz:
    MODELO_WHISPER = "small"
    FREQUENCIA_AUDIO = 16_000
    DURACAO_BLOCO = 0.25
    LIMITE_ESPERA_FALA = 15
    DURACAO_MAXIMA_FALA = 30
    LIMITE_SILENCIO = 0.8
    LIMIAR_AUDIO = 0.02

    _RE_MARCACOES = re.compile(r"\[[^\]]*\]|\([^)]*\)")
    _RE_ESPACOS = re.compile(r"\s+")

    def __init__(self):
        self.modelo_voz = None

    def iniciar_modelo_voz(self):
        try:
            logging.info("Carregando o modelo Whisper local...")
            self.modelo_voz = Model(
                self.MODELO_WHISPER,
                n_threads=4,
                print_realtime=False,
                print_progress=False,
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
                blocksize=bloco,
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

                    audio_mono = audio[:, 0].copy()
                    nivel = float(np.sqrt(np.dot(audio_mono, audio_mono) / len(audio_mono)))

                    if inicio_fala is None:
                        if nivel < self.LIMIAR_AUDIO:
                            continue
                        inicio_fala = time.monotonic()
                        logging.info("Estou ouvindo...")

                    amostras.append(audio_mono)

                    if nivel < self.LIMIAR_AUDIO:
                        amostras_silencio += len(audio_mono)
                        if amostras_silencio >= limite_amostras_silencio:
                            break
                    else:
                        amostras_silencio = 0

            return np.concatenate(amostras) if amostras else None
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
                language="pt",
                initial_prompt="Transcrição clara em português brasileiro, contendo perguntas e interrogações.",
            )
            texto = " ".join(segmento.text.strip() for segmento in segmentos)
            texto = self._RE_MARCACOES.sub(" ", texto)
            return self._RE_ESPACOS.sub(" ", texto).strip()
        finally:
            if caminho_temporario is not None:
                caminho_temporario.unlink(missing_ok=True)

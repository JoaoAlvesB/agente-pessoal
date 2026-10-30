import importlib
import logging
import os
import re
from collections import deque
from pathlib import Path

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

class ReconhecedorVoz:
    MODELO_WHISPER = "small"
    DEVICE = "cuda"
    COMPUTE_TYPE = "float16"

    FREQUENCIA_AUDIO = 16_000
    LIMIAR_SILENCIO = 0.7
    LIMIAR_VOLUME_FALLBACK = 0.02
    DURACAO_PRE_ROLAGEM = 0.3

    _RE_MARCACOES = re.compile(r"\[[^\]]*\]|\([^)]*\)")
    _RE_ESPACOS = re.compile(r"\s+")

    def __init__(self):
        self.modelo_voz = None
        self.device = None
        self._cuda_dll_handles = []

    def iniciar_modelo_voz(self):
        try:
            self._registrar_bibliotecas_cuda()
            logging.info(
                "Carregando Faster-Whisper (%s) na GPU CUDA...",
                self.MODELO_WHISPER,
            )
            self.modelo_voz = WhisperModel(
                self.MODELO_WHISPER,
                device=self.DEVICE,
                compute_type=self.COMPUTE_TYPE
            )
            self.device = self.DEVICE
            logging.info("Reconhecimento de voz carregado na GPU CUDA.")
        except Exception as erro_gpu:
            logging.warning(
                "Aviso: não foi possível carregar o Whisper na GPU (%s). "
                "Continuando com CPU; a transcrição pode ficar mais lenta.",
                erro_gpu,
            )
            try:
                self.modelo_voz = WhisperModel(
                    self.MODELO_WHISPER,
                    device="cpu",
                    compute_type="int8"
                )
                self.device = "cpu"
                logging.warning(
                    "Whisper está operando na CPU. A conversa continuará, "
                    "mas com maior latência."
                )
            except Exception as erro_cpu:
                self.modelo_voz = None
                raise RuntimeError(
                    "Não foi possível carregar o Whisper nem na GPU nem na CPU."
                ) from erro_cpu

    def _registrar_bibliotecas_cuda(self):
        if os.name != "nt":
            return

        caminhos_dll = []
        for nome_pacote in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc"):
            try:
                pacote = importlib.import_module(nome_pacote)
            except ImportError:
                continue

            for caminho_pacote in pacote.__path__:
                caminho_dll = Path(caminho_pacote) / "bin"
                if caminho_dll.is_dir():
                    caminhos_dll.append(str(caminho_dll))

        caminhos_existentes = {
            caminho.casefold()
            for caminho in os.environ.get("PATH", "").split(os.pathsep)
        }
        novos_caminhos = [
            caminho for caminho in caminhos_dll
            if caminho.casefold() not in caminhos_existentes
        ]
        if novos_caminhos:
            os.environ["PATH"] = os.pathsep.join(
                caminho
                for caminho in novos_caminhos
                + os.environ.get("PATH", "").split(os.pathsep)
                if caminho
            )
        self._cuda_dll_handles.extend(
            os.add_dll_directory(caminho) for caminho in caminhos_dll
        )

    def capturar_audio(self):
        logging.info("Mike: Estou ouvindo...")
        amostras = []
        window_size = 512
        blocos_anteriores = deque(
            maxlen=max(
                1,
                round(
                    self.DURACAO_PRE_ROLAGEM
                    * self.FREQUENCIA_AUDIO
                    / window_size
                ),
            )
        )
        falando = False
        silencio_contador = 0

        try:
            with sd.InputStream(
                samplerate=self.FREQUENCIA_AUDIO,
                channels=1,
                dtype="float32",
                blocksize=window_size,
            ) as microfone:
                while True:
                    audio_chunk, _ = microfone.read(window_size)
                    audio_flat = audio_chunk.flatten()

                    nivel = float(np.sqrt(np.dot(audio_flat, audio_flat) / len(audio_flat)))
                    is_speech = nivel > self.LIMIAR_VOLUME_FALLBACK

                    if is_speech:
                        if not falando:
                            amostras.extend(blocos_anteriores)
                        falando = True
                        silencio_contador = 0
                        amostras.append(audio_flat)
                    elif falando:
                        amostras.append(audio_flat)
                        silencio_contador += window_size
                        if silencio_contador >= int(self.FREQUENCIA_AUDIO * self.LIMIAR_SILENCIO):
                            break
                    else:
                        blocos_anteriores.append(audio_flat)

            return np.concatenate(amostras) if amostras else None
        except Exception as e:
            logging.error(f"Erro na captura de áudio: {e}")
            return None

    def transcrever_audio(self, audio):
        if self.modelo_voz is None:
            raise RuntimeError("O modelo Whisper não foi carregado.")

        try:
            return self._transcrever_com_modelo(audio)
        except Exception as erro_gpu:
            if self.device != "cuda":
                raise RuntimeError(f"Erro na transcrição de voz: {erro_gpu}") from erro_gpu

            logging.warning(
                "Falha na transcrição pela GPU (%s). Tentando novamente na CPU; "
                "a transcrição poderá demorar mais.",
                erro_gpu,
            )
            try:
                self.modelo_voz = WhisperModel(
                    self.MODELO_WHISPER,
                    device="cpu",
                    compute_type="int8",
                )
                self.device = "cpu"
                logging.warning(
                    "Whisper continuará usando CPU. Reinicie o agente após "
                    "corrigir o CUDA para voltar à GPU."
                )
                return self._transcrever_com_modelo(audio)
            except Exception as erro_cpu:
                self.modelo_voz = None
                raise RuntimeError(
                    "A transcrição falhou na GPU e também na CPU."
                ) from erro_cpu

    def _transcrever_com_modelo(self, audio):
        segmentos, _ = self.modelo_voz.transcribe(
            audio,
            beam_size=3,
            language="pt",
            condition_on_previous_text=False,
        )
        texto = " ".join(segmento.text.strip() for segmento in segmentos)
        texto = self._RE_MARCACOES.sub(" ", texto)
        return self._RE_ESPACOS.sub(" ", texto).strip()

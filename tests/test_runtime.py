import json
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import numpy as np

from conversa import Conversa
from reconhecedor_voz import ReconhecedorVoz


class ReconhecedorVozTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "DLL directory registration is Windows-only")
    def test_registra_diretorios_cuda_no_path_do_windows(self):
        with tempfile.TemporaryDirectory() as pasta:
            pacotes = {}
            for nome in ("cublas", "cudnn", "cuda_nvrtc"):
                diretorio = Path(pasta) / nome / "bin"
                diretorio.mkdir(parents=True)
                pacotes[f"nvidia.{nome}"] = SimpleNamespace(
                    __path__=[str(diretorio.parent)]
                )

            reconhecedor = ReconhecedorVoz()
            with (
                patch("reconhecedor_voz.os.add_dll_directory") as add_dll_directory,
                patch(
                    "reconhecedor_voz.importlib.import_module",
                    side_effect=pacotes.__getitem__,
                ),
                patch.dict(os.environ, {"PATH": ""}),
            ):
                reconhecedor._registrar_bibliotecas_cuda()
                caminhos_path = os.environ["PATH"].split(os.pathsep)

            self.assertEqual(len(caminhos_path), 3)
            self.assertEqual(add_dll_directory.call_count, 3)
            self.assertEqual(len(reconhecedor._cuda_dll_handles), 3)

    @patch("reconhecedor_voz.WhisperModel")
    def test_inicia_whisper_na_gpu_cuda(self, whisper_model):
        modelo = object()
        whisper_model.return_value = modelo
        reconhecedor = ReconhecedorVoz()

        reconhecedor.iniciar_modelo_voz()

        whisper_model.assert_called_once_with(
            ReconhecedorVoz.MODELO_WHISPER,
            device="cuda",
            compute_type="float16",
        )
        self.assertIs(reconhecedor.modelo_voz, modelo)
        self.assertEqual(reconhecedor.device, "cuda")

    @patch("reconhecedor_voz.sd.InputStream")
    def test_captura_preserva_audio_antes_do_inicio_detectado(self, input_stream):
        blocos = [0.001] * 10 + [0.03] + [0.0] * 24
        audio = iter(
            (np.full((512, 1), valor, dtype=np.float32), False)
            for valor in blocos
        )
        stream = Mock()
        stream.read.side_effect = lambda _: next(audio)
        input_stream.return_value.__enter__.return_value = stream
        reconhecedor = ReconhecedorVoz()

        resultado = reconhecedor.capturar_audio()

        self.assertIsNotNone(resultado)
        self.assertEqual(len(resultado), (9 + 1 + 22) * 512)
        self.assertTrue(np.allclose(resultado[:512], 0.001))
        self.assertTrue(np.allclose(resultado[9 * 512], 0.03))

    @patch("reconhecedor_voz.WhisperModel")
    def test_avisa_e_faz_fallback_para_cpu_se_gpu_falhar(self, whisper_model):
        modelo_cpu = object()
        whisper_model.side_effect = [RuntimeError("CUDA indisponível"), modelo_cpu]
        reconhecedor = ReconhecedorVoz()

        with self.assertLogs(level="WARNING") as logs:
            reconhecedor.iniciar_modelo_voz()

        self.assertEqual(
            whisper_model.call_args_list,
            [
                call(ReconhecedorVoz.MODELO_WHISPER, device="cuda", compute_type="float16"),
                call(ReconhecedorVoz.MODELO_WHISPER, device="cpu", compute_type="int8"),
            ],
        )
        self.assertIs(reconhecedor.modelo_voz, modelo_cpu)
        self.assertEqual(reconhecedor.device, "cpu")
        self.assertIn("Continuando com CPU", "\n".join(logs.output))

    @patch("reconhecedor_voz.WhisperModel")
    def test_falha_explicitamente_se_gpu_e_cpu_nao_carregarem(self, whisper_model):
        whisper_model.side_effect = [
            RuntimeError("CUDA indisponível"),
            RuntimeError("Falha ao carregar o modelo"),
        ]
        reconhecedor = ReconhecedorVoz()

        with self.assertRaisesRegex(RuntimeError, "nem na GPU nem na CPU"):
            reconhecedor.iniciar_modelo_voz()

        self.assertIsNone(reconhecedor.modelo_voz)

    @patch("reconhecedor_voz.WhisperModel")
    def test_repete_na_cpu_se_inferencia_cuda_falhar(self, whisper_model):
        modelo_gpu = Mock()
        modelo_gpu.transcribe.side_effect = RuntimeError(
            "Library cublas64_12.dll is not found or cannot be loaded"
        )
        modelo_cpu = Mock()
        modelo_cpu.transcribe.return_value = ([Mock(text=" Olá Mike. ")], None)
        whisper_model.return_value = modelo_cpu
        reconhecedor = ReconhecedorVoz()
        reconhecedor.modelo_voz = modelo_gpu
        reconhecedor.device = "cuda"

        with self.assertLogs(level="WARNING") as logs:
            texto = reconhecedor.transcrever_audio([0.0])

        self.assertEqual(texto, "Olá Mike.")
        whisper_model.assert_called_once_with(
            ReconhecedorVoz.MODELO_WHISPER,
            device="cpu",
            compute_type="int8",
        )
        self.assertEqual(reconhecedor.device, "cpu")
        self.assertIn("Tentando novamente na CPU", "\n".join(logs.output))

    def test_transcricao_usa_beam_maior_sem_prompt_generico(self):
        modelo = Mock()
        modelo.transcribe.return_value = ([Mock(text=" A química orgânica.")], None)
        reconhecedor = ReconhecedorVoz()
        reconhecedor.modelo_voz = modelo
        reconhecedor.device = "cuda"

        texto = reconhecedor.transcrever_audio(np.zeros(16000, dtype=np.float32))

        self.assertEqual(texto, "A química orgânica.")
        modelo.transcribe.assert_called_once()
        argumentos = modelo.transcribe.call_args.kwargs
        self.assertEqual(argumentos["beam_size"], 3)
        self.assertEqual(argumentos["language"], "pt")
        self.assertFalse(argumentos["condition_on_previous_text"])
        self.assertNotIn("initial_prompt", argumentos)


class MemoriaConversaTests(unittest.TestCase):
    def test_salva_turno_de_comando_local_no_historico(self):
        banco = Mock()
        acoes = Mock()
        acoes.processar.return_value = "Abrindo o Chrome."
        conversa = Conversa(banco, Mock(), Mock(), acoes_sistema=acoes)

        resposta = conversa.conversar("Abra o Chrome")

        self.assertEqual(resposta, "Abrindo o Chrome.")
        banco.salvar_historico.assert_called_once_with([
            {"role": "user", "content": "Abra o Chrome"},
            {"role": "assistant", "content": "Abrindo o Chrome."},
        ])
        banco.carregar_historico.assert_not_called()

    def test_salva_resposta_de_conversa_no_historico(self):
        banco = Mock()
        banco.carregar_historico.return_value = []
        acoes = Mock()
        acoes.processar.return_value = None
        conversa = Conversa(banco, Mock(), Mock(), acoes_sistema=acoes)
        conversa.consultar_modelo = Mock(return_value="Tudo bem.")

        resposta = conversa.conversar("Como você está?")

        self.assertEqual(resposta, "Tudo bem.")
        banco.salvar_historico.assert_called_once_with([
            {"role": "user", "content": "Como você está?"},
            {"role": "assistant", "content": "Tudo bem."},
        ])
        banco.carregar_historico.assert_called_once_with(12)

    def test_opcoes_mantem_modelo_carregado_e_limita_resposta(self):
        conversa = Conversa(Mock(), Mock(), Mock())

        dados = conversa.criar_dados([], stream=True)

        self.assertEqual(dados["keep_alive"], "60m")
        self.assertEqual(dados["options"]["num_predict"], 64)
        self.assertTrue(dados["stream"])

    @patch("conversa.urllib.request.urlopen")
    def test_avisa_quando_ollama_esta_usando_cpu(self, urlopen):
        urlopen.return_value = BytesIO(
            json.dumps({
                "models": [{"name": "qwen3:4b-instruct", "size_vram": 0}],
            }).encode("utf-8")
        )
        conversa = Conversa(Mock(), Mock(), Mock())

        with self.assertLogs(level="WARNING") as logs:
            conversa.verificar_dispositivo_ollama()

        self.assertIn("na CPU, não na GPU", "\n".join(logs.output))

    def test_informa_por_voz_quando_a_consulta_ao_modelo_falha(self):
        reconhecedor = Mock()
        reconhecedor.modelo_voz = object()
        reconhecedor.capturar_audio.side_effect = [object(), KeyboardInterrupt()]
        reconhecedor.transcrever_audio.return_value = "Olá"
        sintetizador = Mock()
        conversa = Conversa(Mock(), reconhecedor, sintetizador)
        conversa.verificar_modelo = Mock(return_value=True)
        conversa.conversar_falando = Mock(side_effect=RuntimeError("Ollama offline"))

        with self.assertLogs(level="ERROR"):
            conversa.iniciar_conversa_por_voz()

        sintetizador.falar_resposta.assert_called_once_with(
            Conversa.RESPOSTA_ERRO_MODELO
        )
        sintetizador.encerrar_sintetizador.assert_called_once()


if __name__ == "__main__":
    unittest.main()

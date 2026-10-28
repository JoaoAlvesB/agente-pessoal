import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from acoes_sistema import AcoesSistema
from conversa import Conversa


class AcoesSistemaTests(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.destinos_abertos = []
        self.acoes = AcoesSistema(
            diretorios_menu=[self.raiz / "menu"],
            diretorio_notas=self.raiz / "notas",
            abrir_caminho=self.destinos_abertos.append,
            abrir_nota=self.destinos_abertos.append,
        )

    def test_abre_notepad_por_alias_portugues(self):
        resposta = self.acoes.processar("Abra o bloco de notas")

        self.assertEqual(resposta, "Abrindo o Bloco de Notas.")
        self.assertEqual(self.destinos_abertos, ["notepad.exe"])

    def test_reconhece_pedido_de_abertura_em_forma_de_pergunta(self):
        resposta = self.acoes.processar("Você pode abrir o bloco de notas?")

        self.assertEqual(resposta, "Abrindo o Bloco de Notas.")
        self.assertEqual(self.destinos_abertos, ["notepad.exe"])

    def test_reconhece_pedido_com_sujeito_e_cortesia(self):
        resposta = self.acoes.processar("Por favor, quero que você abra o Spotify para mim")

        self.assertEqual(resposta, "Abrindo o Spotify.")
        self.assertEqual(self.destinos_abertos, ["spotify:"])

    def test_abre_aplicativo_pelo_atalho_do_menu_iniciar(self):
        pasta_menu = self.raiz / "menu"
        pasta_menu.mkdir()
        atalho = pasta_menu / "Spotify.lnk"
        atalho.touch()

        resposta = self.acoes.processar("Abra o Spotify")

        self.assertEqual(resposta, "Abrindo o Spotify.")
        self.assertEqual(self.destinos_abertos, [atalho])

    def test_chrome_corresponde_ao_nome_alternativo_do_atalho(self):
        pasta_menu = self.raiz / "menu"
        pasta_menu.mkdir()
        atalho = pasta_menu / "Google Chrome.lnk"
        atalho.touch()

        self.acoes.processar("Abra o Chrome")

        self.assertEqual(self.destinos_abertos, [atalho])

    def test_anotacao_inline_cria_arquivo_e_abre_no_notepad(self):
        resposta = self.acoes.processar("Anote: comprar leite e pão")

        self.assertEqual(resposta, "Anotação salva e aberta no Bloco de Notas.")
        arquivo = self.destinos_abertos[0]
        self.assertTrue(arquivo.is_file())
        self.assertEqual(arquivo.read_text(encoding="utf-8"), "comprar leite e pão\n")

    def test_anotacao_com_acento_preserva_o_inicio_e_o_conteudo(self):
        resposta = self.acoes.processar("Desejo fazer uma anotação: reunião amanhã")

        self.assertEqual(resposta, "Anotação salva e aberta no Bloco de Notas.")
        arquivo = self.destinos_abertos[0]
        self.assertEqual(arquivo.read_text(encoding="utf-8"), "reunião amanhã\n")

    def test_pedido_de_anotacao_aguarda_o_texto_da_proxima_fala(self):
        resposta_pedido = self.acoes.processar("Desejo anotar um texto")
        resposta_texto = self.acoes.processar("Ligar para a Ana amanhã")

        self.assertEqual(resposta_pedido, "O que você quer anotar? Diga o texto em uma única fala.")
        self.assertEqual(resposta_texto, "Anotação salva e aberta no Bloco de Notas.")
        self.assertEqual(
            self.destinos_abertos[0].read_text(encoding="utf-8"),
            "Ligar para a Ana amanhã\n",
        )

    def test_cancelar_pedido_de_anotacao_nao_cria_arquivo(self):
        self.acoes.processar("Desejo anotar um texto")

        resposta = self.acoes.processar("cancelar")

        self.assertEqual(resposta, "Tudo bem, cancelei a anotação.")
        self.assertEqual(self.destinos_abertos, [])

    def test_fala_sem_intencao_de_sistema_segue_para_conversa(self):
        self.assertIsNone(self.acoes.processar("Como está o tempo hoje?"))

    def test_nao_interpreta_comando_arbitrario_como_aplicativo(self):
        resposta = self.acoes.processar("Abra Chrome; Remove-Item")

        self.assertIn("Não encontrei", resposta)
        self.assertEqual(self.destinos_abertos, [])

    def test_comando_do_sistema_nao_consulta_modelo_no_modo_texto(self):
        acoes = Mock()
        acoes.processar.return_value = "Abrindo o Chrome."
        conversa = Conversa(Mock(), Mock(), Mock(), acoes_sistema=acoes)

        resposta = conversa.conversar("Abra o Chrome")

        self.assertEqual(resposta, "Abrindo o Chrome.")
        conversa.db.carregar_historico.assert_not_called()

    def test_comando_do_sistema_e_falado_no_modo_voz(self):
        acoes = Mock()
        acoes.processar.return_value = "Abrindo o Spotify."
        sintetizador = Mock()
        conversa = Conversa(Mock(), Mock(), sintetizador, acoes_sistema=acoes)

        resposta = conversa.conversar_falando("Abra o Spotify")

        self.assertEqual(resposta, "Abrindo o Spotify.")
        sintetizador.falar_resposta.assert_called_once_with("Abrindo o Spotify.")

    def test_modo_texto_continua_ativo_sem_ollama(self):
        conversa = Conversa(Mock(), Mock(), Mock())
        conversa.verificar_modelo = Mock(return_value=False)

        with patch("builtins.input", return_value="sair"):
            conversa.iniciar_conversa_por_texto()

        conversa.verificar_modelo.assert_called_once()

    def test_modo_voz_continua_ativo_sem_ollama(self):
        reconhecedor = Mock()
        reconhecedor.modelo_voz = object()
        reconhecedor.capturar_audio.side_effect = KeyboardInterrupt
        sintetizador = Mock()
        conversa = Conversa(Mock(), reconhecedor, sintetizador)
        conversa.verificar_modelo = Mock(return_value=False)

        conversa.iniciar_conversa_por_voz()

        reconhecedor.iniciar_modelo_voz.assert_called_once()
        sintetizador.encerrar_sintetizador.assert_called_once()


if __name__ == "__main__":
    unittest.main()

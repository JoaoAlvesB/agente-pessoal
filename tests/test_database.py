import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database import Database


class DatabaseTests(unittest.TestCase):
    def test_salva_historico_de_forma_persistente(self):
        mensagens = [
            {"role": "user", "content": "Me explique química orgânica."},
            {"role": "assistant", "content": "Ela estuda compostos de carbono."},
        ]

        with tempfile.TemporaryDirectory() as diretorio:
            caminho_banco = Path(diretorio) / "mensagens.db"
            with patch.object(Database, "CAMINHO_BANCO", caminho_banco):
                banco = Database()

                banco.salvar_historico(mensagens)

                self.assertEqual(banco.carregar_historico(), mensagens)


if __name__ == "__main__":
    unittest.main()

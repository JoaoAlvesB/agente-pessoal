import sqlite3
from contextlib import closing
from pathlib import Path
from datetime import datetime

class Database:
    CAMINHO_BANCO = Path(__file__).resolve().parent / "mensagens.db"
    LIMITE_HISTORICO = 12

    def __init__(self):
        self.inicializar_banco()

    def inicializar_banco(self):
        with closing(sqlite3.connect(self.CAMINHO_BANCO)) as conexao:
            # Ativa o modo WAL para melhor performance de escrita e leitura simultânea
            conexao.execute("PRAGMA journal_mode=WAL;")
            conexao.execute(
                """
                CREATE TABLE IF NOT EXISTS historico (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT NOT NULL,
                    mensagem TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )

    def carregar_historico(self, limite=LIMITE_HISTORICO):
        with closing(sqlite3.connect(self.CAMINHO_BANCO)) as conexao:
            registros = conexao.execute(
                """
                SELECT usuario, mensagem
                FROM historico
                ORDER BY id DESC
                LIMIT ?
                """,
                (limite,)
            ).fetchall()

        registros.reverse()
        return [
            {"role": usuario, "content": mensagem}
            for usuario, mensagem in registros
        ]

    def salvar_historico(self, mensagens):
        timestamp = datetime.now().isoformat(timespec="seconds")
        registros = [
            (mensagem["role"], mensagem["content"], timestamp)
            for mensagem in mensagens
        ]

        with closing(sqlite3.connect(self.CAMINHO_BANCO)) as conexao:
            conexao.executemany(
                """
                INSERT INTO historico (usuario, mensagem, timestamp)
                VALUES (?, ?, ?)
                """,
                registros
            )
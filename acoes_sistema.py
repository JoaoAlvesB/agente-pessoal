import logging
import os
import re
import shutil
import subprocess
import unicodedata
from datetime import datetime
from pathlib import Path


class AcoesSistema:
    ALIASES = {
        "bloco de notas": "notepad",
        "notepad": "notepad",
        "spotify": "spotify",
        "chrome": "chrome",
        "google chrome": "chrome",
    }

    COMANDO_ABRIR = re.compile(
        r"(?:^|\s)(?:abra|abrir|abre|abrisse|inicie|iniciar|execute|executar|rode|rodar)"
        r"\s+(?:(?:o|a)\s+)?(?:(?:aplicativo|app|programa)\s+)?(.+?)(?:\s*(?:por favor|pra mim|para mim|agora|no computador|no pc|[?!.])\s*)?$",
        re.IGNORECASE,
    )
    COMANDO_NOTA = re.compile(
        r"(?:anote|anotar|anotacao|anotação|registre|registrar|salve|salvar|escreva|escrever)"
        r"\s*(?::|,|-|de|\bque\b|\bpara\b)?\s*(.*)$",
        re.IGNORECASE,
    )
    CANCELAR_NOTA = {"cancelar", "cancela", "deixa", "esquece"}

    def __init__(
        self,
        diretorios_menu=None,
        diretorio_notas=None,
        abrir_caminho=None,
        abrir_nota=None,
    ):
        self.diretorios_menu = (
            [Path(diretorio) for diretorio in diretorios_menu]
            if diretorios_menu is not None
            else self._diretorios_menu_padrao()
        )
        self.diretorio_notas = (
            Path(diretorio_notas)
            if diretorio_notas is not None
            else Path.home() / "Documents" / "Mike" / "Notas"
        )
        self._abrir_caminho = abrir_caminho or self._abrir_no_windows
        self._abrir_nota = abrir_nota or self._abrir_no_notepad
        self.aguardando_nota = False

    def processar(self, mensagem):
        texto = mensagem.strip()
        normalizado = self._normalizar(texto)

        if self.aguardando_nota:
            if normalizado in self.CANCELAR_NOTA:
                self.aguardando_nota = False
                return "Tudo bem, cancelei a anotação."
            return self._salvar_nota(texto)

        comando_nota = self.COMANDO_NOTA.search(texto)
        if comando_nota:
            conteudo = comando_nota.group(1).strip(" \t\r\n:,-?!.")
            if not conteudo or self._normalizar(conteudo) in {"um texto", "uma nota", "o texto", "uma anotacao", "um texto para mim"}:
                self.aguardando_nota = True
                return "O que você quer anotar? Diga o texto em uma única fala."
            return self._salvar_nota(conteudo)

        comando_abrir = self.COMANDO_ABRIR.search(texto)
        if not comando_abrir:
            return None

        nome = comando_abrir.group(1).strip(" \t\r\n\"'`.,;:?!")
        nome = re.sub(r"\s+(?:por favor|pra mim|para mim|agora|no computador|no pc)$", "", nome, flags=re.IGNORECASE)
        if not nome:
            return None

        destino = self._resolver_aplicativo(nome)
        if destino is None:
            return f"Não encontrei '{nome}' nos aplicativos instalados do Menu Iniciar."

        try:
            self._abrir_caminho(destino)
        except OSError:
            logging.exception("Não foi possível iniciar o aplicativo '%s'.", nome)
            return f"Não consegui abrir {nome}. Verifique se o aplicativo está instalado."

        return f"Abrindo {self._nome_amigavel(nome)}."

    def _salvar_nota(self, texto):
        self.aguardando_nota = False
        try:
            self.diretorio_notas.mkdir(parents=True, exist_ok=True)
            nome_arquivo = datetime.now().strftime("nota-%Y%m%d-%H%M%S-%f.txt")
            caminho = self.diretorio_notas / nome_arquivo
            caminho.write_text(texto + "\n", encoding="utf-8")
            self._abrir_nota(caminho)
        except OSError:
            logging.exception("Não foi possível criar ou abrir a anotação.")
            return "Não consegui criar ou abrir a anotação. Verifique o log."

        return "Anotação salva e aberta no Bloco de Notas."

    def _resolver_aplicativo(self, nome):
        chave = self._normalizar(nome)
        alias = self.ALIASES.get(chave, chave)

        if alias == "notepad":
            return "notepad.exe"

        atalhos = self._atalhos_menu_iniciar()
        for titulo, caminho in atalhos:
            titulo_normalizado = self._normalizar(titulo)
            if self.ALIASES.get(titulo_normalizado, titulo_normalizado) == alias:
                return caminho

        if alias == "spotify":
            return "spotify:"
        if alias == "chrome":
            executavel = shutil.which("chrome.exe")
            if executavel:
                return executavel
            for base in (
                os.environ.get("PROGRAMFILES"),
                os.environ.get("PROGRAMFILES(X86)"),
                os.environ.get("LOCALAPPDATA"),
            ):
                if base:
                    caminho = Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
                    if caminho.is_file():
                        return caminho
        return None

    def _atalhos_menu_iniciar(self):
        atalhos = []
        for diretorio in self.diretorios_menu:
            if not diretorio.is_dir():
                continue
            for caminho in diretorio.rglob("*"):
                if caminho.is_file() and caminho.suffix.lower() in {".lnk", ".url"}:
                    atalhos.append((caminho.stem, caminho))
        return sorted(atalhos, key=lambda item: (self._normalizar(item[0]), str(item[1]).lower()))

    @staticmethod
    def _diretorios_menu_padrao():
        diretorios = []
        appdata = os.environ.get("APPDATA")
        programdata = os.environ.get("PROGRAMDATA")
        if appdata:
            diretorios.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
        if programdata:
            diretorios.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
        return diretorios

    @staticmethod
    def _abrir_no_windows(destino):
        startfile = getattr(os, "startfile", None)
        if startfile is None:
            raise OSError("A abertura de aplicativos só está disponível no Windows.")
        startfile(str(destino))

    @staticmethod
    def _abrir_no_notepad(caminho):
        subprocess.Popen(["notepad.exe", str(caminho)], shell=False, close_fds=True)

    @staticmethod
    def _normalizar(texto):
        return AcoesSistema._normalizar_com_mapa(texto)[0]

    @staticmethod
    def _normalizar_com_mapa(texto):
        caracteres = []
        indices = []
        for indice_original, caractere in enumerate(texto):
            decomposicao = unicodedata.normalize("NFKD", caractere)
            sem_acentos = "".join(
                item for item in decomposicao if not unicodedata.combining(item)
            ).lower()
            for item in sem_acentos:
                normalizado = item if item.isascii() and (item.isalnum() or item == " ") else " "
                caracteres.append(normalizado)
                indices.append(indice_original)

        texto_normalizado = []
        mapa_indices = []
        espaco_pendente = False
        indice_espaco = 0
        for caractere, indice_original in zip(caracteres, indices):
            if caractere == " ":
                if texto_normalizado:
                    espaco_pendente = True
                    indice_espaco = indice_original
                continue
            if espaco_pendente:
                texto_normalizado.append(" ")
                mapa_indices.append(indice_espaco)
                espaco_pendente = False
            texto_normalizado.append(caractere)
            mapa_indices.append(indice_original)
        return "".join(texto_normalizado), mapa_indices

    @staticmethod
    def _nome_amigavel(nome):
        aliases_legiveis = {
            "notepad": "o Bloco de Notas",
            "bloco de notas": "o Bloco de Notas",
            "google chrome": "o Google Chrome",
            "chrome": "o Chrome",
            "spotify": "o Spotify",
        }
        return aliases_legiveis.get(AcoesSistema._normalizar(nome), nome)

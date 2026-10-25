import argparse
import logging

from database import Database
from voice import Voice
from conversa import Conversa

def main():
    parser = argparse.ArgumentParser(description="Agente pessoal Mike")
    parser.add_argument(
        "--texto",
        action="store_true",
        help="Inicia no modo de conversa por texto"
    )
    argumentos = parser.parse_args()

    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # Inicializar o sistema
    db = Database()
    voz = Voice()
    conversa = Conversa(db, voz)

    if argumentos.texto:
        conversa.iniciar_conversa_por_texto()
    else:
        conversa.iniciar_conversa_por_voz()

if __name__ == "__main__":
    main()
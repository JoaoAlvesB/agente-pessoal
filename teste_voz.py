import logging
from sintetizador_voz import SintetizadorVoz

logging.basicConfig(level=logging.INFO, format="%(message)s")

# Frase de teste padrão para verificar clareza, pontuação e velocidade
FRASE_TESTE = (
    "Olá! Este é um teste de voz para o meu agente de inteligência artificial. "
    "Estamos ajustando a velocidade da fala e a pronúncia das palavras para garantir uma conversa natural. "
    "No momento, o sistema está funcionando a cem por cento da sua capacidade."
)

def main():
    print("Inicializando o sintetizador de voz (Piper)...")
    voz = SintetizadorVoz()

    # Garante que a fala está ativada para o teste
    voz.FALAR_RESPOSTA = True

    voz.criar_sintetizador()

    if voz.sintetizador is None:
        print("\n[Erro] Não foi possível carregar a voz do Piper.")
        return

    print("\n" + "=" * 50)
    print("Falando a frase de teste com as configurações atuais do sintetizador Piper...")
    print(f'"{FRASE_TESTE}"')
    print("=" * 50 + "\n")

    # Nome do método corrigido para bater com a classe Voice
    try:
        voz.falar_resposta(FRASE_TESTE)
    finally:
        voz.encerrar_sintetizador()

    print("\nTeste concluído!")

if __name__ == "__main__":
    main()
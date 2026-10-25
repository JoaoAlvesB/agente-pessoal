"""
Teste de voz interativo: digite o texto no terminal e escolha o nível de efeito.
Uso:  python teste_voz.py
"""
import logging

from voice import Voice

logging.basicConfig(level=logging.INFO, format="%(message)s")

PRESETS = [
    ("1) SEM efeito (voz pura do Piper)", {
        "EFEITO_ROBO": False,
    }),
    ("2) Efeito SUAVE", {
        "EFEITO_ROBO": True, "FATOR_TOM": 1.0, "MISTURA_ROBO": 0.15,
        "ATRASO_METALICO_MS": 0, "BITS": 0,
    }),
    ("3) Efeito FORTE (o antigo)", {
        "EFEITO_ROBO": True, "FATOR_TOM": 1.08, "MISTURA_ROBO": 0.35,
        "ATRASO_METALICO_MS": 5, "BITS": 10,
    }),
]

voz = Voice()
voz.FALAR_RESPOSTA = True
voz.criar_sintetizador()

if voz.sintetizador is None:
    raise SystemExit("Não foi possível carregar a voz do Piper. Veja a mensagem acima.")

print("-" * 50)
texto_usuario = input("Digite o texto que deseja testar: ").strip()
print("-" * 50)

if not texto_usuario:
    print("Nenhum texto foi digitado. Encerrando.")
    exit()

print("\nEscolha o nível de efeito:")
print("0) Testar TODOS os níveis em sequência")
print("1) Apenas SEM efeito")
print("2) Apenas Efeito SUAVE")
print("3) Apenas Efeito FORTE")

escolha = input("\nDigite o número da opção desejada (0-3): ").strip()

if escolha == "0":
    presets_para_rodar = PRESETS
elif escolha in ["1", "2", "3"]:
    indice = int(escolha) - 1
    presets_para_rodar = [PRESETS[indice]]
else:
    print("Opção inválida. Executando todos por padrão.")
    presets_para_rodar = PRESETS

for nome, config in presets_para_rodar:
    print(f"\n{nome}")
    for chave, valor in config.items():
        setattr(voz, chave, valor)
    voz.falar_resposta(texto_usuario)
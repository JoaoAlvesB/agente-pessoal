# Mike: agente pessoal por voz (100% local)

Assistente de conversa em português do Brasil que roda inteiramente no seu computador, sem enviar nada para a nuvem. Você fala, o Mike entende, responde em texto e (opcionalmente) em voz, com um efeito leve de "robô companheiro".

## Como funciona

```
Microfone -> Whisper (voz para texto) -> Ollama / Qwen3 (resposta) -> Piper (texto para voz) -> Alto-falante
                                              |
                                        SQLite (histórico)
```

| Etapa | Tecnologia |
|---|---|
| Reconhecimento de voz | [pywhispercpp](https://github.com/absadiki/pywhispercpp) (Whisper `small`) |
| Modelo de linguagem | [Ollama](https://ollama.com) com Qwen3-4B Instruct |
| Síntese de voz | [Piper](https://github.com/OHF-Voice/piper1-gpl) (`piper-tts`) |
| Histórico de conversa | SQLite (`mensagens.db`, criado automaticamente) |
| Áudio (entrada e saída) | `sounddevice` + `numpy` |

As respostas são faladas **frase por frase** enquanto o modelo ainda está gerando o resto, o que reduz bastante a espera.

## Estrutura do projeto

| Arquivo | Função |
|---|---|
| `app.py` | Ponto de entrada. Escolhe modo voz ou texto. |
| `conversa.py` | Lógica da conversa, comunicação com o Ollama (com streaming) e controle do fluxo. |
| `voice.py` | Captura do microfone, transcrição (Whisper), síntese (Piper) e efeito robótico. |
| `database.py` | Histórico das mensagens em SQLite. |
| `requirements.txt` | Dependências Python. |

## Requisitos

- Python 3.10 ou superior
- [Ollama](https://ollama.com/download) instalado e em execução
- Microfone e alto-falantes funcionando
- Cerca de 4 GB de RAM livres para o modelo de linguagem (mais o Whisper)
- Testado no Windows (PowerShell). Em Linux e macOS deve funcionar, mas pode exigir a instalação do PortAudio para o `sounddevice`.

## Instalação

### 1. Ambiente virtual e dependências

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Modelo de linguagem (Ollama)

Com o Ollama instalado e rodando:

```
ollama pull qwen3:4b-instruct
```

> **Importante:** use a versão **Instruct**. A tag `qwen3:4b` pode ser uma versão que só funciona "pensando" e despeja o raciocínio (em inglês) na resposta. O `conversa.py` verifica na inicialização se o modelo existe e, se não achar, tenta usar outro `qwen3` "instruct" instalado.

### 3. Voz do Piper

Baixe **os dois arquivos** de uma voz em português do Brasil:

- Repositório: https://huggingface.co/rhasspy/piper-voices (pasta `pt` > `pt_BR` > voz > qualidade)
- Amostras para ouvir: https://rhasspy.github.io/piper-samples

Exemplo (voz padrão do projeto):

```
pt_BR-faber-medium.onnx
pt_BR-faber-medium.onnx.json
```

Coloque os dois na **mesma pasta do `voice.py`**. O `.json` precisa ter o mesmo nome do `.onnx`. Para usar outra voz, altere `VOZ_PIPER` em `voice.py`.

### 4. Modelo do Whisper

Nada a fazer: o `pywhispercpp` baixa o modelo `small` automaticamente na primeira execução (cerca de 480 MB).

## Uso

```powershell
python app.py            # modo voz
python app.py --texto    # modo texto (não usa microfone nem alto-falante)
```

- No modo voz, fale quando aparecer "Pode falar. Estou ouvindo."
- Para encerrar: diga "sair", "encerrar" ou "parar", ou pressione `Ctrl+C`.
- No modo texto, digite `sair`.

Dica: para testar só a parte do Ollama e do banco, comece pelo `--texto`.

## Configuração

Tudo é ajustado por constantes no início de cada classe.

### `conversa.py`

| Constante | O que faz |
|---|---|
| `MODEL` | Modelo do Ollama usado. |
| `LIMITE_HISTORICO` | Quantas mensagens anteriores entram no contexto (padrão: 6). |
| `INSTRUCOES` | Prompt de sistema (personalidade e regras de resposta). |
| `criar_dados` | Opções do Ollama: `num_ctx`, `num_predict`, `temperature`, `keep_alive`. |

### `voice.py`

| Constante | O que faz |
|---|---|
| `FALAR_RESPOSTA` | `True` fala a resposta; `False` mostra só em texto no terminal. |
| `VOZ_PIPER` | Arquivo `.onnx` da voz. |
| `MODELO_WHISPER` | `base` (mais rápido) ou `small` (mais preciso). |
| `LIMIAR_AUDIO` | Sensibilidade do microfone. Suba se captar ruído, baixe se não ouvir você. |
| `LIMITE_SILENCIO` | Segundos de silêncio para considerar que você terminou de falar. |
| `CORRECOES_PRONUNCIA` | Dicionário para corrigir palavras que o Piper pronuncia mal. |
| `EFEITO_ROBO` | Liga ou desliga o efeito robótico. |
| `FATOR_TOM`, `FREQ_MODULACAO`, `MISTURA_ROBO`, `ATRASO_METALICO_MS`, `INTENSIDADE_ECO`, `BITS` | Ajustam o timbre do efeito (veja os comentários no código). |

## Solução de problemas

**`ImportError: cannot import name 'Voice' from 'voice'`**
O `voice.py` da pasta está vazio ou incompleto. Substitua o arquivo, apague a pasta `__pycache__` e teste com `python -c "from voice import Voice; print('ok')"`.

**O Mike responde em inglês, "pensando em voz alta"**
O modelo é uma versão que só raciocina. Use a tag `qwen3:4b-instruct-2507-q4_K_M` e **apague o histórico** (veja abaixo), porque o raciocínio antigo fica salvo e é imitado pelo modelo.

**Respostas estranhas ou fora de contexto**
Apague `mensagens.db`, `mensagens.db-wal` e `mensagens.db-shm`. Eles são recriados vazios na próxima execução.

**"Não detectei fala" mesmo falando**
Baixe `LIMIAR_AUDIO` (por exemplo, para `0.015`). Confira também o microfone padrão do sistema.

**O Mike capta ruído e responde coisas que você não disse**
Suba `LIMIAR_AUDIO` (por exemplo, para `0.02` ou mais).

**Não sai voz**
Verifique `FALAR_RESPOSTA = True`, se o log mostra "Sintetizador de voz local (Piper) inicializado com sucesso" e o dispositivo de saída de áudio do sistema.

**"Arquivo de voz não encontrado"**
O nome em `VOZ_PIPER` não bate com o arquivo na pasta, ou o `.onnx` e o `.onnx.json` estão em pastas diferentes.

**Erro de conexão com o Ollama**
Confirme que o Ollama está rodando e responde em `http://localhost:11434`. Use `ollama list` para ver os modelos instalados.

**Pronúncia errada de alguma palavra (ex.: "problema" soando como "poblema")**
Primeiro teste com `EFEITO_ROBO = False` para saber se o efeito é o culpado. Se a voz em si errar, use `CORRECOES_PRONUNCIA` ou troque a voz do Piper.

**`synthesize() takes 2 positional arguments...`**
O `voice.py` já lida com as duas APIs do Piper (versões antigas e a partir da 1.3). Se aparecer algo parecido, informe a versão: `pip show piper-tts`.

## Limitações conhecidas

- Mono-usuário: um único histórico global, sem separação por sessão ou usuário.
- Não há detecção de interrupção: enquanto o Mike fala, o microfone fica desligado.
- A divisão em frases é simples (pontuação seguida de espaço), então abreviações como "Sr. Silva" podem ser cortadas no meio.
- O Whisper pode "alucinar" texto com ruído de fundo; por isso existem o limiar de áudio e o filtro de marcações como `[MÚSICA]`.
- Respostas limitadas a 150 tokens por padrão (`num_predict`).

## Privacidade

Áudio, transcrição, conversa e histórico ficam na sua máquina. O único acesso de rede é ao Ollama local (`localhost`) e ao download inicial dos modelos.

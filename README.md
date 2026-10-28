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
| `acoes_sistema.py` | Interpreta comandos locais permitidos para abrir aplicativos e criar anotações. |
| `reconhecedor_voz.py` | Captura do microfone e transcrição de áudio com Whisper. |
| `sintetizador_voz.py` | Síntese e reprodução de fala com Piper, incluindo os ajustes de pronúncia e o efeito robótico. |
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

#### Git Bash no Windows

Se estiver usando Git Bash (terminal `MINGW64` ou `UCRT64`), os comandos de ativação e os caminhos são diferentes dos do PowerShell. Na pasta do projeto, use:

```bash
Mínimas configurações para rodar o agente especial 
Instalar python mais recente ou compatível
python --version
py -3.12 -m venv .venv
source .venv/Scripts/activate
python --version
python -m pip install -r requirements.txt
python app.py
```

Se `python` não for encontrado ou apontar para outra versão, invoque diretamente o Python do ambiente virtual:

```bash
./.venv/Scripts/python.exe --version
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Confira se a versão mostrada é Python 3.10 ou superior. Para executar o programa sem depender da ativação do ambiente, use:

```bash
./.venv/Scripts/python.exe app.py --texto
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

Coloque os dois arquivos na pasta `Voices` do projeto. O `.json` precisa ter o mesmo nome do `.onnx`, seguido de `.json`. Para usar outra voz, altere `VOZ_PIPER` em `sintetizador_voz.py`.

### 4. Modelo do Whisper

Nada a fazer: o `pywhispercpp` baixa o modelo `small` automaticamente na primeira execução (cerca de 480 MB).

## Uso

```powershell
python app.py            # modo voz
python app.py --texto    # modo texto (não usa microfone nem alto-falante)
```

- No modo voz, fale quando aparecer "Pode falar. Estou ouvindo."
- Para abrir um aplicativo, diga "abra o Spotify", "abra o Chrome" ou o nome do aplicativo disponível no Menu Iniciar.
- Para criar uma anotação, diga "desejo anotar um texto" e depois dite o conteúdo; também é possível dizer "anote: [texto]" de uma vez.
- As anotações ficam em `Documentos\Mike\Notas` e são abertas no Bloco de Notas.
- Comandos locais continuam disponíveis sem o Ollama; respostas de conversa dependem do Ollama em execução.
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

### `reconhecedor_voz.py` (escuta)

| Constante | O que faz |
|---|---|
| `MODELO_WHISPER` | Modelo Whisper: `base` (mais rápido) ou `small` (mais preciso). |
| `LIMIAR_AUDIO` | Sensibilidade do microfone. Suba se captar ruído, baixe se não ouvir você. |
| `LIMITE_SILENCIO` | Segundos de silêncio para considerar que você terminou de falar. |

### `sintetizador_voz.py` (fala)

| Constante | O que faz |
|---|---|
| `FALAR_RESPOSTA` | `True` fala a resposta; `False` mostra só em texto no terminal. |
| `VOZ_PIPER` | Arquivo `.onnx` da voz. |
| `CORRECOES_PRONUNCIA` | Dicionário para corrigir palavras que o Piper pronuncia mal. |
| `EFEITO_ROBO` | Liga ou desliga o efeito robótico. |
| `FATOR_TOM`, `FREQ_MODULACAO`, `MISTURA_ROBO`, `ATRASO_METALICO_MS`, `INTENSIDADE_ECO`, `BITS` | Ajustam o timbre do efeito (veja os comentários no código). |

## Solução de problemas

**`pip install requirements.txt` diz que não encontrou o pacote**
Use `-r` para instalar os pacotes listados no arquivo:

```bash
python -m pip install -r requirements.txt
```

**`pip` mostra `no such option: -m`**
O `-m` é uma opção do Python, não do `pip`. Use `python -m pip ...`, ou o caminho completo do Python do ambiente virtual:

```bash
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Não use `pip -m install ...` nem `pip install -m ...`.

**`python` não é encontrado no Windows ou abre a Microsoft Store**
O terminal pode não estar encontrando o Python instalado ou o ambiente virtual pode não estar ativado. No Git Bash, primeiro entre na pasta do projeto e ative o ambiente:

```bash
cd ~/desktop/GitHub/agente-pessoal
source .venv/Scripts/activate
```

Se ainda assim `python` não funcionar, use `./.venv/Scripts/python.exe` no lugar de `python`. No PowerShell, o comando de ativação é `.venv\Scripts\Activate.ps1`. Se a pasta `.venv` ainda não existir, crie o ambiente com `python -m venv .venv` usando uma instalação do Python disponível.

**`pip` informa `ResolutionImpossible`, não encontra `onnxruntime` ou menciona `cp315`**
`cp315` indica que o `pip` está usando Python 3.15. O `piper-tts` depende do `onnxruntime`, que pode não disponibilizar um pacote compatível com essa versão. Use uma versão estável do Python compatível com as dependências (por exemplo, Python 3.12), crie novamente o ambiente virtual com essa versão e instale as dependências dentro dele:

```bash
py -3.12 -m venv .venv
source .venv/Scripts/activate
python --version
python -m pip install -r requirements.txt
```

Se o comando `py` não for encontrado, instale o Python 3.12 e marque a opção para instalar o Python Launcher; alternativamente, crie o ambiente usando o caminho completo do executável instalado. Se `.venv` já existir com outra versão do Python, desative o ambiente, remova somente a pasta `.venv` deste projeto e crie-a novamente:

```powershell
py -3.12 -m venv .venv
```

Depois, ative o ambiente conforme o terminal utilizado e confirme com `python --version` que ele mostra Python 3.12 antes de instalar os requisitos. No Git Bash, se necessário, instale usando `./.venv/Scripts/python.exe -m pip install -r requirements.txt`. Não instale os requisitos com um `pip` global ou de outro ambiente virtual.

**`ModuleNotFoundError` ao importar os módulos de voz**
Confirme que está executando os comandos na pasta do projeto e que os arquivos `reconhecedor_voz.py` e `sintetizador_voz.py` estão presentes. O projeto separa a escuta (Whisper) da fala (Piper); imports antigos como `from voice import Voice` devem ser substituídos pelos módulos novos.

**O Mike responde em inglês, "pensando em voz alta"**
O modelo é uma versão que só raciocina. Use a tag `qwen3:4b-instruct-2507-q4_K_M` e **apague o histórico** (veja abaixo), porque o raciocínio antigo fica salvo e é imitado pelo modelo.

**Respostas estranhas ou fora de contexto**
Apague `mensagens.db`, `mensagens.db-wal` e `mensagens.db-shm`. Eles são recriados vazios na próxima execução.

**"Não detectei fala" mesmo falando**
Baixe `LIMIAR_AUDIO` em `reconhecedor_voz.py` (por exemplo, para `0.015`). Confira também o microfone padrão do sistema.

**O Mike capta ruído e responde coisas que você não disse**
Suba `LIMIAR_AUDIO` em `reconhecedor_voz.py` (por exemplo, para `0.02` ou mais).

**Não sai voz**
Verifique `FALAR_RESPOSTA = True` em `sintetizador_voz.py`, se o log mostra "Sintetizador de voz local (Piper) inicializado com sucesso" e o dispositivo de saída de áudio do sistema.

**"Arquivo de voz não encontrado"**
O caminho em `VOZ_PIPER` de `sintetizador_voz.py` não bate com o arquivo, ou o `.onnx` e o `.onnx.json` estão em pastas diferentes.

**Erro de conexão com o Ollama**
Confirme que o Ollama está rodando e responde em `http://localhost:11434`. Use `ollama list` para ver os modelos instalados.

**Pronúncia errada de alguma palavra (ex.: "problema" soando como "poblema")**
Primeiro teste com `EFEITO_ROBO = False` para saber se o efeito é o culpado. Se a voz em si errar, use `CORRECOES_PRONUNCIA` ou troque a voz do Piper.

**Erro de argumentos em `synthesize()`**
O `sintetizador_voz.py` lida com as APIs antigas do Piper e com a API a partir da versão 1.3. Se aparecer um erro de argumentos, informe a versão instalada: `pip show piper-tts`.

## Limitações conhecidas

- Mono-usuário: um único histórico global, sem separação por sessão ou usuário.
- Não há detecção de interrupção: enquanto o Mike fala, o microfone fica desligado.
- A divisão em frases é simples (pontuação seguida de espaço), então abreviações como "Sr. Silva" podem ser cortadas no meio.
- O Whisper pode "alucinar" texto com ruído de fundo; por isso existem o limiar de áudio e o filtro de marcações como `[MÚSICA]`.
- Respostas limitadas a 150 tokens por padrão (`num_predict`).

## Privacidade

Áudio, transcrição, conversa e histórico ficam na sua máquina. O único acesso de rede é ao Ollama local (`localhost`) e ao download inicial dos modelos.

Os comandos de sistema usam uma lista controlada de ações: o Mike abre atalhos do Menu Iniciar, o Notepad, o Spotify ou o Chrome, e salva texto como anotação. A fala não é executada como comando PowerShell, terminal ou código arbitrário.

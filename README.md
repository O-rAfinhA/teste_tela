# suno-dl

Baixa as músicas da **sua própria** biblioteca do Suno para uma pasta local, e
lê a sua tela (captura + OCR) quando você precisa inspecionar ou clicar em algo
por texto.

Roda na sua máquina — precisa da sua sessão logada no Suno e, para o modo de
tela, do seu monitor e do seu mouse.

## Instalação

```bash
git clone https://github.com/O-rAfinhA/teste_tela.git
cd teste_tela

python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

O OCR precisa do binário do tesseract, além do pacote Python:

| Sistema | Comando |
|---|---|
| Ubuntu/Debian | `sudo apt install tesseract-ocr tesseract-ocr-por` |
| macOS | `brew install tesseract tesseract-lang` |
| Windows | [instalador UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki) |

Só os comandos `screen ...` dependem disso — o download funciona sem tesseract.

## Uso

### 1. Login (uma vez só)

```bash
python -m suno_dl login
```

Abre uma janela do navegador. Faça login no Suno, espere sua biblioteca
aparecer, volte ao terminal e aperte Enter. A sessão fica salva em
`~/.suno-dl/profile`, então as próximas execuções já entram logadas.

### 2. Conferir o que ele enxerga

```bash
python -m suno_dl list
```

Lista as faixas encontradas sem baixar nada. Bom para verificar se ele achou
tudo antes de disparar o download.

### 3. Baixar

```bash
python -m suno_dl download                      # tudo, para ~/Music/Suno
python -m suno_dl download -o ~/Musicas/Suno    # outra pasta
python -m suno_dl download --limit 5            # testa com 5 primeiro
python -m suno_dl download --headless           # sem janela (após o login)
```

Cada execução escreve um `manifest.json` na pasta de destino com id, título,
data e arquivo de cada faixa. Rodar de novo pula o que já está baixado, então
dá para usar como sincronização incremental. Use `--redownload` para forçar.

Se o download direto falhar (o Suno mudou a API), tem o plano B, que clica no
botão de download da própria página:

```bash
python -m suno_dl download --via-ui
```

### 4. Ler a tela

```bash
python -m suno_dl screen read                     # todo o texto visível agora
python -m suno_dl screen read --save tela.png     # e salva a captura
python -m suno_dl screen find "Download"          # coordenadas do texto
python -m suno_dl screen click "Download"         # move o mouse e clica
python -m suno_dl screen click "Baixar" --dry-run # mostra onde clicaria
```

Útil quando a automação não acha um botão: você localiza pelo texto que está
na tela e clica pelas coordenadas reais.

## Como ele acha as músicas

Três camadas, da mais confiável para a mais frágil — se uma falhar, a seguinte
cobre:

1. **Rede** — enquanto a biblioteca carrega e rola, o app faz chamadas JSON com
   id, título e URL de cada faixa. O código varre qualquer resposta JSON em
   busca desses objetos, sem depender de um endereço fixo de API.
2. **DOM** — `<audio src>`, links `.mp3` e o payload do Next.js da página.
3. **Interface** (`--via-ui`) — clica no botão de download, igual você faria.

As duas primeiras sobrevivem a mudanças de layout; a terceira sobrevive a
mudanças de API.

## Quando algo dá errado

**"Nenhuma faixa apareceu"** — a sessão expirou. Rode `python -m suno_dl login`
de novo.

**Faltaram músicas** — a biblioteca carrega conforme você rola. Aumente a
paciência da rolagem editando `scroll_until_settled` em `suno_dl/suno.py`, ou
rode sem `--headless` para acompanhar.

**"Executable doesn't exist"** — rode `playwright install chromium`. Se você
prefere usar o Chrome que já tem instalado:

```bash
python -m suno_dl download --channel chrome
export SUNO_DL_CHROMIUM=/caminho/para/o/chrome   # caminho não-padrão
```

## Variáveis de ambiente

| Variável | Para quê |
|---|---|
| `SUNO_DL_PROFILE` | Pasta do perfil do navegador (padrão `~/.suno-dl/profile`) |
| `SUNO_DL_CHROMIUM` | Caminho de um Chrome/Chromium já instalado |

## Escopo

A ferramenta baixa o que a sua conta já pode baixar pela interface do Suno —
as suas criações. Não contorna proteção nem acessa a biblioteca de terceiros.

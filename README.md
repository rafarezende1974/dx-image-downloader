# DX Image Downloader (Windows) — DX Labs

App para Windows que baixa **imagens e vídeos de uma página** em lote.

Cole a URL de uma página, o app lista tudo que encontrou (fotos e vídeos),
você marca o que quer e baixa tudo para uma pasta — cada lote numa subpasta
com o nome do site + data/hora.

## O que a v1 faz
- **Fotos de uma página:** `<img>`, `<picture>`, `srcset` (pega a maior versão),
  `data-src`, links diretos `.jpg/.png/.webp/.gif/.avif`, `og:image`, fundo em CSS
- **Vídeos de uma página:** `<video>/<source>`, links `.mp4/.mov/.webm`, `og:video`
- **Página de vídeo (Reels, TikTok, YouTube, X, Facebook):** baixa o vídeo
  original via **yt-dlp** (mesmo motor do DX Downloader) — se pedir login,
  use `cookies.txt` (extensão “Get cookies.txt LOCALLY” no navegador logado)
- **Carrossel:** um post `/p/<id>/` com várias fotos/vídeos baixa **todas** as mídias do carrossel, não só a primeira
- **Perfil inteiro (Instagram/TikTok):** colar `instagram.com/<usuario>/` ou `tiktok.com/@<usuario>` baixa todos os posts do perfil via yt-dlp (pode demorar e pedir login — use `cookies.txt`)
- **Filtros:** tipo (Fotos / Vídeos / Todas), largura mínima, só mesmo domínio,
  ignorar imagens de interface (ícones/logos)
- Lista com marcação (duplo clique ou Espaço), selecionar todas / desmarcar todas
- Pasta padrão: `Downloads\DX Image Downloader` (pode trocar na tela)
- Barra de progresso, botão **Cancelar**, registro na tela e em log
  (`%LOCALAPPDATA%\DXImageDownloader\dx-image-downloader.log`)
- Colar sem travar a tela (PowerShell `Get-Clipboard` primeiro, Win32 depois)

## Como gerar o .exe
1. Suba este projeto para um repositório no GitHub.
2. O workflow **Build Windows EXE** (`.github/workflows/build-windows.yml`) roda sozinho a cada push na `main`
   (usa o runner `windows-latest`, baixa o ffmpeg, gera o ícone e compila com PyInstaller).
3. Baixe o artefato **dx-image-downloader-windows** na aba **Actions** → contém `DXImageDownloader.exe` (arquivo único, portátil).

> Se o workflow não puder ser criado pela integração, crie o arquivo manualmente pela interface web
> do GitHub com o mesmo conteúdo — cópia dele em `WORKFLOW-BUILD-WINDOWS.yml.txt` na raiz.

## Uso
Use apenas para baixar conteúdo que você tem direito de baixar / para uso pessoal.
Não use para conteúdo vazado, sem consentimento ou protegido por direitos autorais.

## Versões
- **v1.0.5** — erro “Could not copy Chrome cookie database”: o app agora traduz o erro e orienta fechar o navegador, usar **Cookies do Firefox** (feche o Firefox antes) ou `cookies.txt` — o Chrome trava/criptografa o banco de cookies.
- **v1.0.4** — Instagram “Unable to extract data” mesmo com `cookies.txt`: yt-dlp agora imita o Chrome (impersonation, via curl_cffi) para Instagram/TikTok, e nova opção **Cookies do Chrome/Firefox/Edge** direto do navegador logado (o `cookies.txt` nem sempre traz a sessão).
- **v1.0.3** — perfil/carrossel agora **lista cada post** (via yt-dlp, sem baixar) em vez de mostrar 1 item “post-perfil”. Se o Instagram pedir login, a lista vem vazia e o app avisa para usar `cookies.txt`.
- **v1.0.2** — carrossel e perfil inteiro (Instagram/TikTok) via yt-dlp.
- **v1.0.1** — botão **Limpar** ao lado de Buscar mídias (limpa o link, a lista e a seleção para colar outra URL; cancela a tarefa em andamento, sem apagar arquivos já baixados).
- **v1.0.0** — primeira versão (imagens + vídeos, Reels via yt-dlp).

## Estrutura
- `app.py` — GUI (Tkinter) + varredura da página + downloads
- `generate_icon.py` — gera `assets/icon.ico` no build (ícone próprio: foto + play + seta)
- `requirements.txt` — requests + beautifulsoup4 + Pillow + yt-dlp

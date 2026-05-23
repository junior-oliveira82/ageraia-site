#!/usr/bin/env python3
"""
Agente de publicação automática — Agera IA
Lê PDFs e docs Word da pasta conteudo/, pesquisa atualizações na web,
gera artigo em HTML e atualiza posts.json
"""

import os
import json
import re
import random
import requests
from datetime import datetime, timedelta
from pathlib import Path

# ── Dependências de leitura de arquivos ──────────────────────────
try:
    import fitz  # PyMuPDF para PDF
except ImportError:
    fitz = None

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

# ── Configurações ────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TAVILY_API_KEY = os.environ["TAVILY_API_KEY"]
CONTEUDO_DIR = Path("conteudo")
BLOG_DIR = Path("blog")
POSTS_JSON = BLOG_DIR / "posts.json"
PROGRESSO_FILE = Path(".agente_progresso.json")

# Data de início retroativo
DATA_INICIO = datetime(2026, 1, 6)  # primeira segunda de janeiro 2026
DIAS_PUBLICACAO = [0, 1, 2]  # segunda, terça, quarta (0=seg)

CATEGORIAS = {
    "ia": "Inteligência Artificial",
    "vendas": "Vendas & Marketing",
    "erp": "Gestão & ERP",
    "varejo": "Varejo & CX",
    "transformacao": "Transformação Digital",
}


def carregar_progresso():
    if PROGRESSO_FILE.exists():
        with open(PROGRESSO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"arquivos_processados": [], "ultima_data": None}


def salvar_progresso(progresso):
    with open(PROGRESSO_FILE, "w", encoding="utf-8") as f:
        json.dump(progresso, f, ensure_ascii=False, indent=2)


def listar_arquivos():
    """Lista PDFs e docs Word ordenados do mais antigo para o mais recente."""
    arquivos = []
    for ext in ["*.pdf", "*.docx", "*.doc"]:
        arquivos.extend(CONTEUDO_DIR.glob(ext))
    return sorted(arquivos, key=lambda f: f.stat().st_mtime)


def extrair_texto_pdf(caminho):
    if fitz is None:
        raise ImportError("PyMuPDF não instalado")
    doc = fitz.open(str(caminho))
    texto = ""
    for page in doc:
        texto += page.get_text()
    doc.close()
    return texto[:8000]  # limita para não estourar tokens


def extrair_texto_docx(caminho):
    if DocxDocument is None:
        raise ImportError("python-docx não instalado")
    doc = DocxDocument(str(caminho))
    texto = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    return texto[:8000]


def extrair_texto(caminho):
    ext = caminho.suffix.lower()
    if ext == ".pdf":
        return extrair_texto_pdf(caminho)
    elif ext in [".docx", ".doc"]:
        return extrair_texto_docx(caminho)
    return ""


def pesquisar_web(tema):
    """Busca informações atualizadas sobre o tema via Tavily."""
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": f"{tema} pequenas empresas vendas marketing 2025 2026",
        "search_depth": "basic",
        "max_results": 5,
        "include_answer": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        data = resp.json()
        resultados = []
        if data.get("answer"):
            resultados.append(f"Síntese atual: {data['answer']}")
        for r in data.get("results", [])[:3]:
            resultados.append(f"Fonte: {r.get('url', '')}\n{r.get('content', '')[:500]}")
        return "\n\n".join(resultados)
    except Exception as e:
        print(f"Erro na busca web: {e}")
        return ""


def gerar_artigo_claude(texto_base, pesquisa_web, nome_arquivo):
    """Chama a API da Anthropic para gerar o artigo."""
    prompt = f"""Você é um especialista em vendas, marketing e inteligência artificial para pequenas e médias empresas.

Com base no material de referência abaixo e nas informações atualizadas da web, escreva um artigo original em português brasileiro para o blog da Agera IA.

REGRAS IMPORTANTES:
1. NÃO copie o texto base — use-o apenas como referência conceitual
2. Atualize dados e estatísticas com base nas informações da web quando disponível
3. O artigo deve ser relevante para donos de pequenas e médias empresas brasileiras
4. Tom: profissional, direto, sem jargão excessivo
5. Tamanho: 600 a 900 palavras
6. Inclua dados e fontes verificáveis quando usar estatísticas
7. Termine com uma conclusão prática e acionável

MATERIAL DE REFERÊNCIA:
{texto_base}

INFORMAÇÕES ATUALIZADAS DA WEB:
{pesquisa_web if pesquisa_web else "Nenhuma informação adicional disponível."}

Retorne SOMENTE um JSON válido com esta estrutura (sem markdown, sem texto antes ou depois):
{{
  "titulo": "Título do artigo (máximo 80 caracteres)",
  "resumo": "Resumo de 1-2 frases para o card do blog (máximo 160 caracteres)",
  "categoria": "uma das opções: vendas, ia, erp, varejo, transformacao",
  "corpo": "HTML do artigo com parágrafos em <p>, subtítulos em <h2> e <h3>, listas em <ul><li>",
  "fontes": ["lista de fontes utilizadas como strings"]
}}"""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 4000,
        "messages": [{"role": "user", "content": prompt}],
    }

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers,
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["content"][0]["text"]

    # Remove possíveis marcadores markdown
    content = re.sub(r"```json\s*", "", content)
    content = re.sub(r"```\s*", "", content)
    return json.loads(content.strip())


def calcular_proxima_data(progresso):
    """Calcula a próxima data de publicação retroativa."""
    if progresso["ultima_data"]:
        ultima = datetime.fromisoformat(progresso["ultima_data"])
    else:
        ultima = DATA_INICIO - timedelta(days=1)

    # Avança para o próximo dia de publicação
    candidata = ultima + timedelta(days=1)
    for _ in range(30):  # máximo 30 dias de busca
        if candidata.weekday() in DIAS_PUBLICACAO:
            # Não ultrapassa a data atual
            if candidata.date() <= datetime.now().date():
                return candidata
        candidata += timedelta(days=1)

    # Se já passou de hoje, usa a data de hoje
    return datetime.now()


def criar_html_artigo(artigo, data_pub, slug):
    """Gera o HTML completo do artigo no padrão do blog."""
    categoria_display = CATEGORIAS.get(artigo["categoria"], "Insights")
    data_exibida = data_pub.strftime("%-d %b %Y").replace(
        "Jan", "Jan").replace("Feb", "Fev").replace("Mar", "Mar").replace(
        "Apr", "Abr").replace("May", "Mai").replace("Jun", "Jun").replace(
        "Jul", "Jul").replace("Aug", "Ago").replace("Sep", "Set").replace(
        "Oct", "Out").replace("Nov", "Nov").replace("Dec", "Dez")

    fontes_html = ""
    if artigo.get("fontes"):
        itens = "\n".join([f"    <li>{f}</li>" for f in artigo["fontes"]])
        fontes_html = f"""
<div class="fontes-section">
  <h4>Fontes utilizadas neste artigo</h4>
  <ul>
{itens}
  </ul>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{artigo['titulo']} — Agera IA</title>
<meta name="description" content="{artigo['resumo']}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Space+Grotesk:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0a0a0a; --bg2: #111111;
    --em: #10b981; --em2: #059669;
    --white: #ffffff; --gray1: #f0f0f0; --gray2: #a0a0a0;
    --gray3: #444444; --gray4: #222222;
    --font-title: 'Rajdhani', sans-serif;
    --font-body: 'Space Grotesk', sans-serif;
  }}
  body {{ background: var(--bg); color: var(--white); font-family: var(--font-body); -webkit-font-smoothing: antialiased; }}
  nav {{ position: fixed; top: 0; left: 0; right: 0; z-index: 100; display: flex; align-items: center; justify-content: space-between; padding: 1.25rem 5vw; background: rgba(10,10,10,0.9); backdrop-filter: blur(12px); border-bottom: 1px solid rgba(16,185,129,0.12); }}
  .nav-logo {{ font-family: var(--font-title); font-size: 1.4rem; font-weight: 800; color: var(--white); text-decoration: none; }}
  .nav-logo .arrow {{ color: var(--em); margin: 0 0.2rem; }}
  .nav-logo span {{ color: var(--em); }}
  .nav-back {{ color: var(--gray2); font-size: 0.9rem; text-decoration: none; transition: color 0.2s; }}
  .nav-back:hover {{ color: var(--em); }}
  .post-header {{ padding: 8rem 5vw 3rem; max-width: 780px; margin: 0 auto; }}
  .post-cat {{ font-size: 0.75rem; font-weight: 500; letter-spacing: 0.12em; text-transform: uppercase; color: var(--em); margin-bottom: 1rem; display: flex; align-items: center; gap: 8px; }}
  .post-cat::before {{ content: ''; width: 24px; height: 1px; background: var(--em); }}
  .post-header h1 {{ font-family: var(--font-title); font-size: clamp(1.8rem, 4vw, 2.8rem); font-weight: 800; line-height: 1.1; letter-spacing: -0.02em; margin-bottom: 1rem; }}
  .post-meta {{ color: var(--gray2); font-size: 0.85rem; display: flex; gap: 1.5rem; }}
  .post-divider {{ border: none; border-top: 1px solid var(--gray4); margin: 2rem auto; max-width: 780px; }}
  .post-body {{ max-width: 780px; margin: 0 auto; padding: 0 5vw 5rem; }}
  .post-body p {{ font-size: 1.15rem; color: var(--gray2); line-height: 1.85; font-weight: 300; margin-bottom: 1.5rem; }}
  .post-body h2 {{ font-family: var(--font-title); font-size: 1.5rem; font-weight: 700; color: var(--white); margin: 2.5rem 0 1rem; }}
  .post-body h3 {{ font-family: var(--font-title); font-size: 1.2rem; font-weight: 600; color: var(--white); margin: 2rem 0 0.75rem; }}
  .post-body ul {{ padding-left: 1.25rem; margin-bottom: 1.5rem; }}
  .post-body ul li {{ font-size: 1.15rem; color: var(--gray2); line-height: 1.85; font-weight: 300; margin-bottom: 0.5rem; }}
  .post-body strong {{ color: var(--white); font-weight: 500; }}
  .post-body .highlight {{ background: var(--bg2); border-left: 3px solid var(--em); padding: 1.25rem 1.5rem; margin: 2rem 0; font-size: 1.05rem; color: var(--gray1); line-height: 1.7; font-style: italic; }}
  .post-cta {{ background: var(--bg2); border: 1px solid var(--gray4); padding: 2.5rem; margin-top: 3rem; text-align: center; }}
  .post-cta h3 {{ font-family: var(--font-title); font-size: 1.4rem; font-weight: 700; margin-bottom: 0.5rem; }}
  .post-cta p {{ color: var(--gray2); font-size: 0.95rem; margin-bottom: 1.5rem; font-weight: 300; }}
  .post-cta a {{ display: inline-flex; align-items: center; gap: 8px; background: var(--em); color: #000; font-family: var(--font-body); font-size: 0.95rem; font-weight: 500; padding: 0.85rem 1.75rem; text-decoration: none; border-radius: 3px; transition: background 0.2s; }}
  .post-cta a:hover {{ background: var(--em2); }}
  .fontes-section {{ max-width: 780px; margin: 0 auto; padding: 2rem 5vw 3rem; border-top: 1px solid var(--gray4); }}
  .fontes-section h4 {{ font-family: var(--font-title); font-size: 1rem; font-weight: 600; color: var(--gray2); margin-bottom: 1rem; }}
  .fontes-section ul {{ list-style: none; padding: 0; }}
  .fontes-section ul li {{ font-size: 0.82rem; color: var(--gray3); margin-bottom: 0.5rem; line-height: 1.6; }}
  footer {{ padding: 2rem 5vw; text-align: center; border-top: 1px solid var(--gray4); font-size: 0.8rem; color: var(--gray3); }}
</style>
</head>
<body>

<nav>
  <a href="/" class="nav-logo">AGERA <span class="arrow">▸</span> <span>IA</span></a>
  <a href="/blog/" class="nav-back">← Voltar ao blog</a>
</nav>

<div class="post-header">
  <div class="post-cat">{categoria_display}</div>
  <h1>{artigo['titulo']}</h1>
  <div class="post-meta">
    <span>{data_exibida}</span>
    <span>5 min de leitura</span>
  </div>
</div>

<hr class="post-divider">

<div class="post-body">
{artigo['corpo']}

  <div class="post-cta">
    <h3>Quer aplicar isso no seu negócio?</h3>
    <p>Fazemos um diagnóstico gratuito para mostrar onde a inteligência artificial pode gerar resultado real para você.</p>
    <a href="https://wa.me/5548984445624?text=Ol%C3%A1!%20Gostaria%20de%20agendar%20meu%20diagn%C3%B3stico%20gratuito%20com%20a%20Agera%20IA." target="_blank" rel="noopener">Agendar diagnóstico gratuito</a>
  </div>
</div>
{fontes_html}

<footer>Agera IA — Inteligência Comercial © 2026</footer>

</body>
</html>"""


def atualizar_posts_json(artigo, data_pub, slug):
    """Adiciona o novo artigo ao posts.json."""
    if POSTS_JSON.exists():
        with open(POSTS_JSON, "r", encoding="utf-8") as f:
            posts = json.load(f)
    else:
        posts = []

    categoria_display = CATEGORIAS.get(artigo["categoria"], "Insights")
    data_exibida = data_pub.strftime("%-d %b %Y")

    novo_post = {
        "slug": f"{slug}.html",
        "titulo": artigo["titulo"],
        "resumo": artigo["resumo"],
        "categoria": categoria_display,
        "data": data_pub.strftime("%Y-%m-%d"),
        "dataExibida": data_exibida,
        "leitura": "5 min",
    }

    # Insere mantendo ordem cronológica decrescente
    posts.insert(0, novo_post)

    with open(POSTS_JSON, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


def gerar_slug(titulo):
    """Gera um slug URL-friendly a partir do título."""
    slug = titulo.lower()
    slug = re.sub(r"[áàãâä]", "a", slug)
    slug = re.sub(r"[éèêë]", "e", slug)
    slug = re.sub(r"[íìîï]", "i", slug)
    slug = re.sub(r"[óòõôö]", "o", slug)
    slug = re.sub(r"[úùûü]", "u", slug)
    slug = re.sub(r"[ç]", "c", slug)
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug[:80]


def main():
    print("Iniciando agente de publicação Agera IA...")

    # Carrega progresso
    progresso = carregar_progresso()

    # Lista arquivos disponíveis
    arquivos = listar_arquivos()
    if not arquivos:
        print("Nenhum arquivo encontrado na pasta conteudo/")
        return

    # Filtra arquivos já processados
    pendentes = [a for a in arquivos if str(a) not in progresso["arquivos_processados"]]
    if not pendentes:
        print("Todos os arquivos já foram processados.")
        return

    # Seleciona o próximo arquivo
    arquivo = pendentes[0]
    print(f"Processando: {arquivo.name}")

    # Extrai texto
    texto = extrair_texto(arquivo)
    if not texto.strip():
        print(f"Arquivo vazio ou ilegível: {arquivo.name}")
        progresso["arquivos_processados"].append(str(arquivo))
        salvar_progresso(progresso)
        return

    # Pesquisa web para atualização
    print("Pesquisando informações atualizadas na web...")
    # Usa as primeiras palavras do texto como tema
    tema = " ".join(texto.split()[:15])
    pesquisa = pesquisar_web(tema)

    # Gera artigo via Claude
    print("Gerando artigo com Claude...")
    artigo = gerar_artigo_claude(texto, pesquisa, arquivo.name)

    # Calcula data de publicação
    data_pub = calcular_proxima_data(progresso)
    print(f"Data de publicação: {data_pub.strftime('%d/%m/%Y')}")

    # Gera slug
    slug = gerar_slug(artigo["titulo"])

    # Cria HTML
    html = criar_html_artigo(artigo, data_pub, slug)

    # Salva arquivo HTML
    caminho_html = BLOG_DIR / f"{slug}.html"
    with open(caminho_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Artigo salvo: {caminho_html}")

    # Atualiza posts.json
    atualizar_posts_json(artigo, data_pub, slug)
    print("posts.json atualizado")

    # Atualiza progresso
    progresso["arquivos_processados"].append(str(arquivo))
    progresso["ultima_data"] = data_pub.isoformat()
    salvar_progresso(progresso)

    print(f"Concluído: {artigo['titulo']}")


if __name__ == "__main__":
    main()

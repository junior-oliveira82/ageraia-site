# Como usar o agente de publicação

## Estrutura
- `gerar_artigo.py` — script principal do agente
- `.github/workflows/publicar_artigo.yml` — automação (roda seg/ter/qua às 9h)
- `conteudo/` — pasta onde você coloca os PDFs e docs Word
- `.agente_progresso.json` — controle de arquivos já processados (não apague)

## Como adicionar conteúdo
1. Coloque seus PDFs e arquivos Word na pasta `conteudo/`
2. O agente vai processar na ordem dos mais antigos para os mais recentes
3. A cada execução, um arquivo é processado e um artigo é publicado

## Como rodar manualmente
1. Acesse github.com/junior-oliveira82/ageraia-site
2. Clique em Actions
3. Selecione "Publicar Artigo Agera IA"
4. Clique em "Run workflow"

## Datas retroativas
O agente publica com datas retroativas a partir de janeiro de 2026,
avançando sequencialmente às segundas, terças e quartas.
Quando alcançar a data atual, passa a publicar em tempo real.

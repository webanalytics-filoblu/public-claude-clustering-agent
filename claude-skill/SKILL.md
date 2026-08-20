---
name: seo-keyword-clustering
description: Clusterizza keyword SEO esportate da Semrush/Ahrefs/GSC in un CSV, aggiungendo colonne Cluster e Sotto Cluster (più colonne opzionali come Genere, Stagionalità, Sport). Usa questa skill quando l'utente carica un CSV di keyword e chiede di clusterizzarlo, categorizzarlo, o taggarlo per brand/settore moda-abbigliamento.
---

# SEO Keyword Clustering Agent (Claude Skill)

Skill proprietaria dell'organizzazione (ID `be71789f-9195-4df2-83ae-88e14cdb94ef`).

Questa skill non porta con sé script, regole né istruzioni di flusso: tutto vive nel repo GitHub privato, unica fonte di verità del progetto — così il team vede sempre il comportamento più aggiornato senza dover mai ricaricare questa skill su claude.ai.

Repo: `https://github.com/webanalytics-filoblu/claude-clustering-agent`

## Step 0 — Bootstrap (SEMPRE, a inizio sessione, prima di qualunque altra cosa)

Il repo è **privato**. Questa modalità non scrive mai direttamente sul repo (vedi `WORKFLOW.md`): il token deve avere solo permesso di **lettura** sui contents.

**Token di questa copia** (se manca o non è presente in questa sessione, chiedi prima di procedere: _"Questa copia della skill non ha un token GitHub configurato: puoi fornirlo?"_):

```bash
export REPO="webanalytics-filoblu/claude-clustering-agent"
export BRANCH="main"
```

Scarica script e istruzioni di flusso complete via API Contents di GitHub (un file alla volta, senza `git clone` — questo host non è soggetto ad alcun blocco). Il ruleset (regole cluster/attributi/brand) **non** vive più in questo repo: vive in Google Sheet condivisi su Drive (cartella "chiunque abbia il link"). Il connettore Google Drive già collegato a questa chat serve sia per trovare gli ID dei file (`search_files`) sia per scaricarne il contenuto (`download_file_content`/`read_file_content`) — **non** un `curl` anonimo diretto: in questo ambiente il sandbox nega in modo permanente la connessione verso l'host di redirect di Drive (`*.googleusercontent.com`), a differenza dell'host `api.github.com` usato qui sotto — vedi `WORKFLOW.md` Step 0 per il dettaglio.

```bash
mkdir -p work/scripts

curl -sL \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.raw+json" \
  "https://api.github.com/repos/$REPO/contents/scripts/cluster.py?ref=$BRANCH" \
  -o "work/scripts/cluster.py"

curl -sL \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.raw+json" \
  "https://api.github.com/repos/$REPO/contents/claude-skill/WORKFLOW.md?ref=$BRANCH" \
  -o "work/WORKFLOW.md"
```

Verifica che ogni file scaricato non contenga un messaggio di errore JSON (token invalido, path errato, rate limit) prima di proseguire — `work/scripts/cluster.py` deve iniziare con `#!/usr/bin/env python3`, `work/WORKFLOW.md` deve iniziare con `#`. Se qualcosa non torna, mostra l'errore all'utente invece di continuare.

**Verifica anche che il connettore Google Drive sia disponibile in questa sessione**: qui serve sia per trovare gli ID dei file in "Clustering rules" via `search_files` sia per scaricarne il contenuto via `download_file_content`/`read_file_content` — non c'è un percorso `curl` alternativo in questo ambiente. Se i tool Drive non sono richiamabili, fermati e chiedi all'utente di autorizzarlo nelle impostazioni connettori di claude.ai prima di procedere.

## Step 1 in poi

Leggi **`work/WORKFLOW.md`** e segui **esattamente** quelle istruzioni per l'intero flusso di clustering: come comportarti, la scelta del vertical e la sincronizzazione del relativo ruleset da Google Drive, gli step 1-6 (prepara, analizza, regole, batch, merge, brand competitor — con i blocchi da incollare a mano sugli Sheet), le regole di clustering, l'intento di ricerca, la gestione multilingua e i limiti noti.

Non duplicare qui quei dettagli e non improvvisare uno step alternativo: se il flusso cambia, si aggiorna solo `claude-skill/WORKFLOW.md` nel repo — questa copia di SKILL.md resta valida senza bisogno di essere ricaricata su claude.ai.

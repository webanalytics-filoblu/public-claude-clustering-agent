---
name: seo-keyword-clustering
description: Clusterizza keyword SEO esportate da Semrush/Ahrefs/GSC in un CSV, aggiungendo colonne Cluster e Sotto Cluster (più colonne opzionali come Genere, Stagionalità, Sport). Usa questa skill quando l'utente carica un CSV di keyword e chiede di clusterizzarlo, categorizzarlo, o taggarlo per brand/settore moda-abbigliamento.
---

# SEO Keyword Clustering Agent (Claude Skill)

Skill proprietaria dell'organizzazione (ID `be71789f-9195-4df2-83ae-88e14cdb94ef`).

Questa skill non porta con sé script, regole né istruzioni di flusso: tutto vive nel repo GitHub pubblico, unica fonte di verità del progetto — così il team vede sempre il comportamento più aggiornato senza dover mai ricaricare questa skill su claude.ai.

Repo: `https://github.com/webanalytics-filoblu/public-claude-clustering-agent`

## Step 0 — Bootstrap (SEMPRE, a inizio sessione, prima di qualunque altra cosa)

Il repo è **pubblico**: lo script e le istruzioni di flusso si scaricano in lettura anonima, senza alcun token/credenziale GitHub.

```bash
export REPO="webanalytics-filoblu/public-claude-clustering-agent"
export BRANCH="main"
```

Scarica script e istruzioni di flusso complete via raw GitHub (un file alla volta, senza `git clone` — questo host non è soggetto ad alcun blocco). Il ruleset (regole cluster/attributi/brand) **non** vive in questo repo: vive in Google Sheet condivisi su Drive, in una cartella che richiede un account autorizzato (non è condivisa "chiunque abbia il link"). Il canale di **default** per scaricare il *contenuto* di quegli Sheet non è il connettore Google Drive: è il fast path OAuth a refresh token (`--mode fetch-sheets` in `cluster.py`, vedi `WORKFLOW.md` Step 0) — chiama direttamente `oauth2.googleapis.com`/`www.googleapis.com` con un token, non passa dall'host di redirect anonimo `*.googleusercontent.com` che questo sandbox nega in modo permanente. Il connettore Google Drive già collegato a questa chat resta necessario solo per: trovare gli ID dei file (`search_files`) e recuperare, una volta per sessione, il file di credenziali `google_auth.json` (`read_file_content`, file piccolo e piatto, non un export CSV) dalla sua cartella privata — **non** più come canale primario per il contenuto degli Sheet di regole, dove `download_file_content`/`read_file_content` restano solo il fallback se il fast path non è disponibile in questa sessione — vedi `WORKFLOW.md` Step 0 per il dettaglio.

```bash
mkdir -p work/scripts

curl -sL \
  "https://raw.githubusercontent.com/$REPO/$BRANCH/scripts/cluster.py" \
  -o "work/scripts/cluster.py"

curl -sL \
  "https://raw.githubusercontent.com/$REPO/$BRANCH/claude-skill/WORKFLOW.md" \
  -o "work/WORKFLOW.md"

curl -sL \
  "https://raw.githubusercontent.com/$REPO/$BRANCH/clustering-config.json" \
  -o "work/clustering-config.json"

export CLUSTERING_RULES_FOLDER_ID=$(python3 -c "import json;print(json.load(open('work/clustering-config.json'))['clustering_rules_folder_id'])")
```

Verifica che ogni file scaricato non contenga una pagina di errore (404, path errato) prima di proseguire — `work/scripts/cluster.py` deve iniziare con `#!/usr/bin/env python3`, `work/WORKFLOW.md` deve iniziare con `#`. Se qualcosa non torna, mostra l'errore all'utente invece di continuare.

**`CLUSTERING_RULES_FOLDER_ID`** è l'ID della cartella Drive "Clustering rules", letto da `clustering-config.json` — lo stesso identico file/valore usato dal repo lato VS Code (vedi `CLAUDE.md`), tracciato in chiaro nel repo pubblico perché quella cartella non è più condivisa "chiunque abbia il link" (serve comunque un account autorizzato). Se il valore letto è vuoto o è ancora il placeholder `<CLUSTERING_RULES_FOLDER_ID>` (repository forkato senza configurarlo), fermati e chiedi all'utente l'ID della sua cartella prima di proseguire — non indovinarlo né usarne uno di un'altra organizzazione.

**Verifica anche che il connettore Google Drive sia disponibile in questa sessione**: serve per trovare gli ID dei file in "Clustering rules" via `search_files` e per recuperare `google_auth.json` (necessario per il fast path OAuth, vedi sopra) — resta inoltre l'unico fallback per il contenuto degli Sheet se il fast path non è disponibile, non c'è un percorso `curl` alternativo in questo ambiente. Se i tool Drive non sono richiamabili, fermati e chiedi all'utente di autorizzarlo nelle impostazioni connettori di claude.ai prima di procedere.

## Step 1 in poi

Leggi **`work/WORKFLOW.md`** e segui **esattamente** quelle istruzioni per l'intero flusso di clustering: come comportarti, la scelta del vertical e la sincronizzazione del relativo ruleset da Google Drive, gli step 1-6 (prepara, analizza, regole, batch, merge, brand competitor — con i blocchi da incollare a mano sugli Sheet), le regole di clustering, l'intento di ricerca, la gestione multilingua e i limiti noti.

Non duplicare qui quei dettagli e non improvvisare uno step alternativo: se il flusso cambia, si aggiorna solo `claude-skill/WORKFLOW.md` nel repo — questa copia di SKILL.md resta valida senza bisogno di essere ricaricata su claude.ai.

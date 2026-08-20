# /cluster — Avvia il clustering keyword

Sei un agente SEO specializzato in keyword clustering. Quando questo comando viene invocato, esegui il flusso completo **senza richiedere API key**: sei tu (Claude Code) a fare il clustering direttamente. Il ruleset (Cluster, Sotto Cluster, attributi, brand correlati, città) non vive più in questo repo: vive in Google Sheet condivisi su Drive nella cartella "Clustering rules" — vedi [CLAUDE.md](../../CLAUDE.md) per il dettaglio completo del flusso di sincronizzazione.

## Utilizzo

```
/cluster input/keyword-competitors.csv
/cluster input/keyword-competitors.csv --brand "Falconeri"
/cluster input/keyword-competitors.csv --sector "abbigliamento e moda" --batch-size 80
/cluster input/keyword-competitors.csv --resume
/cluster input/keyword-competitors.csv --no-interactive
```

## Flusso completo

### Step 0 — Colonne obbligatorie (verifica prima di tutto)

Il CSV di input **deve** contenere le colonne **Keyword**, **Brand** e **Brand/Not Brand** (alias accettati: vedi `detect_columns` in `scripts/cluster.py`). Questa verifica è fatta automaticamente da `--mode prepare` allo Step 3: se una o più colonne mancano, lo script stampa `[ERRORE]` con l'elenco preciso di cosa manca e termina **senza** creare `output/workdir` né avviare alcuna classificazione.

Se vedi questo errore:

1. **Non procedere** con nessuno degli step successivi.
2. Mostra all'utente esattamente quali colonne mancano (copia l'elenco dall'output dello script).
3. Chiedi di ricaricare il file con le colonne corrette, ad esempio: *"Al file mancano le colonne X, Y — puoi ricaricare il CSV con queste colonne incluse?"*

### Step 0bis — Colonne opzionali (sempre attive)

Aggiungi **sempre** tutte le colonne opzionali senza chiedere all'utente. L'elenco non è fisso: ogni tab/attributo presente nello Sheet `_Attributi/<lingua>` diventa automaticamente una colonna in output alla sincronizzazione (vedi Step 1). Tipicamente oggi:
- **Stagionalità** — estate, primavera, autunno, inverno, year-round
- **Evento** — natale, capodanno, san valentino, black friday, compleanno, matrimonio, ecc.
- **Outfit** — casual, formale, business, sportivo, sera, spiaggia, outdoor
- **Recensioni** — recensioni, confronto competitor, sostenibilità, qualità, prezzo, trends
- **Materiale/Colore** — estrae materiale o colore dalla keyword
- **Genere** — uomo, donna, kids, unisex
- **Sport** — calcio, calcetto, basket, tennis, padel, running, trekking, golf, ciclismo, sci, nuoto, ecc.
- **Intento di Ricerca** — Navigational / Informational / Transactional / Commercial Investigation

Le colonne opzionali sono classificate **sempre da regole** (zero AI), quindi non aumentano il numero di batch.

### Step 0ter — Scegli il vertical (prima di sincronizzare/prepare)

Il vertical **non è una lista fissa nel codice**: elenca le sottocartelle reali sotto "Clustering rules" (`search_files` con `parentId = '<CLUSTERING_RULES_FOLDER_ID>' and mimeType = 'application/vnd.google-apps.folder'` — l'ID va letto da `clustering-config.json`, vedi [CLAUDE.md](../../CLAUDE.md) sezione "Configurazione: ID della cartella Drive", escludendo quelle con prefisso `_` come `_Attributi`) e proponi all'utente il nome più plausibile **tra quelli effettivamente presenti** (in base a brand/settore), con una domanda tipo: *"Per [brand], quale vertical uso: [elenco cartelle trovate]?"*

Il vertical scelto viene salvato in `output/workdir/vertical.json` e riletto automaticamente dagli step successivi (analyze, add-rules) per tutta la sessione — richiedilo di nuovo solo se non sei sicuro sia lo stesso brand/sessione di prima.

### Step 1 — Sincronizza le regole da Google Drive

Prima di ogni `--mode prepare` (una sola volta per vertical/lingua/sessione), materializza le regole da Drive in locale — vedi [CLAUDE.md](../../CLAUDE.md), sezione "Sincronizza da Google Drive", per il dettaglio di `search_files`/download/`sync-rules`. In breve:

1. Trova gli ID degli Sheet con `search_files` (naming: `cluster_<vertical>_<lingua>` nella cartella del vertical, `attributi_<lingua>` dentro `_Attributi`, `brands` e `cities` sotto "Clustering rules"). Ogni Sheet deve essere monotab (formato compresso, vedi CLAUDE.md) — l'export `.csv` copre solo il primo/unico tab.
2. Scarica ogni Sheet come `.csv` in `output/workdir/sheets_raw/...` con il tool connettore Drive `download_file_content(exportMimeType="text/csv")` + scrittura su disco — stesso canale in VS Code e su claude.ai, la cartella richiede un account autorizzato quindi niente `curl` anonimo.
3. Materializza:
   ```bash
   python scripts/cluster.py --mode sync-rules --workdir output/workdir
   ```

Sincronizza solo le lingue presenti nel CSV (colonna Country, default IT); brand e città sono unici, una sola volta per sessione. Se `download_file_content` restituisce un errore di permesso, fermati e segnalalo all'utente invece di procedere con regole parziali.

### Step 2 — Classifica con ruleset
```bash
python scripts/cluster.py \
  --mode prepare \
  --input [file] \
  --sector "[settore]" \
  --vertical [vertical scelto allo Step 0ter] \
  --batch-size 250 \
  --workdir output/workdir
```
Lo script carica le regole materializzate in `output/workdir/rules/[vertical]/*.json` (una per lingua), classifica automaticamente la maggior parte delle keyword (zero AI), e salva le keyword non coperte in `output/workdir/ai_needed.json`.

Output generato:
- `output/workdir/base.csv` — CSV con colonne Cluster, Sotto Cluster (+ opzionali) pre-compilate dalle regole
- `output/workdir/ai_needed.json` — keyword non classificate
- `output/workdir/manifest.json` — batch già generati (ma non ancora inviati all'AI)
- `output/workdir/prompts/batch_NNNN.txt` — prompt per le keyword ambigue

### Step 3 — Analisi pattern e proposta nuove regole
```bash
python scripts/cluster.py --mode analyze --workdir output/workdir
```
Lo script analizza le keyword non coperte e identifica token e bigrammi frequenti. Salva i pattern in `output/workdir/rule_proposals.json`.

**Poi TU (Claude) leggi `rule_proposals.json` e:**
1. Per ogni pattern con count ≥ 3, proponi all'utente cluster e sotto_cluster appropriati (solo tra i Cluster realmente configurati per questo vertical — vedi README.md "Cluster disponibili" per l'elenco chiuso)
2. Presenta la proposta in formato tabella con esempi:

```
💡 Pattern identificati nelle keyword non classificate:

| Termine         | Count | Esempio keyword               | Cluster proposto        | Sotto Cluster proposto |
|----------------|-------|-------------------------------|-------------------------|------------------------|
| lookbook        |  18   | "falconeri lookbook 2024"     | Ispirazionale           | Lookbook               |
| capsule         |  12   | "collezione capsule primavera"| Abbigliamento           | Capsule Collection     |
| total look      |   8   | "total look cerimonia donna"  | Ispirazionale           | Look Cerimonia         |

Aggiungo queste regole alla sessione corrente e ricalcolo i batch? [sì/no/modifica]
```

3. Se l'utente approva (anche parzialmente), compila `suggested_cluster` e `suggested_sotto_cluster` nei record approvati del JSON e procedi allo Step 4. Se l'utente dice "no" o "salta", vai direttamente allo Step 5.

### Step 4 — Aggiungi le nuove regole alla sessione (dopo approvazione utente)
```bash
python scripts/cluster.py --mode add-rules --workdir output/workdir --lang IT
```
Ripeti con `--lang EN`/`--lang ES`/ecc. se il CSV ha una colonna Country e sono emerse proposte anche per quelle lingue (il vertical viene letto automaticamente da `output/workdir/vertical.json`, non serve ripeterlo). Lo script legge `rule_proposals.json` (con i campi `suggested_cluster` compilati), aggiorna **solo la copia effimera di sessione** in `output/workdir/rules/[vertical]/[lang].json` (utile per riclassificare subito), salva un report in `output/workdir/rules_added.json` e scrive il blocco da incollare in `output/workdir/paste_rules_<vertical>_<lingua>.txt`.

**Poi riesegui lo Step 2** con lo stesso file di input per riclassificare con le regole aggiornate. Questo riduce ulteriormente le keyword da mandare all'AI.

**A questo punto presenta sempre** il contenuto di `paste_rules_<vertical>_<lingua>.txt` all'utente, indicando esplicitamente in quale Sheet/tab va incollato (es. *"Apri Clustering rules/Fashion/IT, tab 'Ispirazionale' (o la tab unica se usi il formato compresso), e incolla queste righe"*). Non c'è alcun commit/push da fare: la fonte di verità è lo Sheet, non file in questo repo.

### Step 5 — Invia i batch all'AI (TU stesso li processi)
```bash
python scripts/cluster.py --mode process-batches --workdir output/workdir
```
Mostra i batch pendenti. Ogni prompt include già la lista dei brand correlati noti (`output/workdir/rules/brands.json`, materializzato da Drive) e i cluster validi per il vertical corrente, così puoi distinguere un brand già in lista da un competitor nuovo e usare solo cluster realmente configurati. Per ogni batch:
1. Leggi `prompt_file` (es. `output/workdir/prompts/batch_0001.txt`)
2. Clusterizza le keyword e produci il JSON. Se noti un nome di brand competitor/terzo ricorrente **non presente** nella lista brand correlati del prompt, aggiungilo a `new_brands` (solo se sei certo, max 5 per batch)
3. Salva in `result_file` (es. `output/workdir/results/batch_0001.json`)

Formato JSON risposta:
```json
{
  "r": [["Cluster", "Sotto Cluster"], ...],
  "new_rules": [{"rule": "nome", "term": "termine", "cluster": "...", "sotto_cluster": "..."}],
  "new_brands": ["nome brand competitor", ...]
}
```

Logga il progresso: `✓ batch 0001/0042 — 250 kw`

### Step 6 — Merge finale
```bash
python scripts/cluster.py \
  --mode merge \
  --output output/[nome-file]-clustered.csv \
  --workdir output/workdir
```

Output: il CSV con le colonne Cluster, Sotto Cluster (+ opzionali). Se sono stati rilevati brand competitor nuovi (non ancora in `output/workdir/rules/brands.json`), viene salvato anche `output/brands_suggestions.json`.

Lo script salva inoltre `output/[nome-file]-clustered-summary.json` (stesso prefisso del CSV) con tutti i numeri della sintesi finale.

**Presenta sempre all'utente**, subito dopo il merge, una mini tabella di riepilogo (leggi i valori da questo JSON, o dall'output console se il file non è disponibile):

```
📊 Riepilogo clustering

| Metrica                            | Valore                          |
|-------------------------------------|----------------------------------|
| Keyword analizzate                  | righe_totali                     |
| Cluster trovati                     | cluster_distinti                 |
| Sotto Cluster trovati                | sotto_cluster_distinti          |
| Classificate da regole/cache/fuzzy  | classificate_regole_cache_fuzzy  |
| Classificate via AI                 | classificate_ai                  |
| Batch AI processati                 | batch_processati (media media_keyword_per_batch kw/batch) |
| Token stimati (batch AI)            | token_stimati_totale (input token_stimati_input + output token_stimati_output) |
| Tempo classificazione regole        | tempo_classificazione_ruleset     |
| Tempo elaborazione batch AI         | tempo_batch_ai                   |
| Brand processati                    | brand                            |
```

Aggiungi anche i top cluster per volume (`top_cluster`) e gli errori batch (`errori_batch`, solo se > 0). Specifica sempre che i token sono una **stima** (lunghezza testo prompt/risposte, ~4 caratteri/token), non un conteggio API reale — il clustering lo fai tu in chat, senza chiamate a un endpoint misurabile.

### Step 7 — Revisiona e aggiungi i brand competitor rilevati (opzionale)
Se `output/brands_suggestions.json` esiste, presenta all'utente la lista dei brand rilevati:

```
🏷️  Brand competitor rilevati (non ancora in rules/brands.json):
   - Supercompetitorbrand
   - Altrobrand
```

Se l'utente approva (anche parzialmente, modifica manualmente `output/brands_suggestions.json` togliendo quelli scartati), esegui:
```bash
python scripts/cluster.py --mode add-brands --brands-suggestions output/brands_suggestions.json --workdir output/workdir
```
Lo script aggiorna **solo la copia effimera di sessione** in `output/workdir/rules/brands.json` (condivisa fra tutte le lingue/vertical) e scrive il blocco da incollare in `output/paste_brands.txt`. Da quel momento in avanti, per il resto di questa sessione, keyword che citano quei competitor verranno riconosciute automaticamente nella colonna **Brand correlati** senza passare per l'AI.

**A questo punto presenta sempre** il contenuto di `output/paste_brands.txt` all'utente, indicando di incollarlo in `Clustering rules/Brands`. Non c'è alcun commit/push da fare.

## Gestione --resume
Se `output/workdir/results/` contiene già file JSON, skippa quei batch e riprendi dai mancanti.

## Argomenti
| Argomento | Default | Descrizione |
|---|---|---|
| `[file]` | — | CSV da processare (obbligatorio) |
| `--brand [nome]` | tutti | Processa solo un brand |
| `--sector [testo]` | `"abbigliamento e calzature"` | Contesto settoriale |
| `--batch-size [n]` | 250 | Keyword per batch AI |
| `--resume` | — | Riprende da dove era rimasto |
| `--no-interactive` | — | Salta tutte le domande interattive (le colonne opzionali vengono comunque aggiunte) |

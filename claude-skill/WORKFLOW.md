# Flusso operativo — SEO Keyword Clustering Agent

Questo file è la fonte di verità del flusso di clustering, scaricato da `SKILL.md` a inizio sessione in `work/WORKFLOW.md`. Presuppone che lo Step 0 di `SKILL.md` sia già stato eseguito: `GITHUB_TOKEN`, `REPO`, `BRANCH` sono già in ambiente, e `work/scripts/cluster.py` è già stato scaricato.

Il ruleset (cluster, attributi, brand correlati) vive in Google Sheet condivisi su Drive, nella cartella **"Clustering rules"** — non in questo repo. Ogni Sheet è monotab (formato compresso, vedi CLAUDE.md nel repo): questo flusso scarica e materializza solo `.csv`, mai `.xlsx`, perché l'export CSV di Drive copre sempre e solo un tab. La cartella e i file al suo interno sono condivisi "chiunque abbia il link" (in lettura), ma **in questo ambiente (claude.ai) il `curl` anonimo verso l'host di redirect di Drive è bloccato in modo permanente dal sandbox**: non è un problema di permessi, non si risolve e non va ritentato. Il percorso primario qui è quindi il tool connettore Drive `download_file_content` (vedi Step 0) — il connettore serve anche per trovare gli ID dei file (`search_files`), ma per il *contenuto* delle Sheet di regole passa da `download_file_content`, non da `read_file_content` (quello resta riservato ai soli file piatti e piccoli, `brands`/`cities`, vedi Step 0). **Il connettore sa comunque solo creare file nuovi o leggere quelli esistenti: non può scrivere/aggiungere righe su uno Sheet già esistente.** Per questo, quando emergono nuove regole o brand competitor durante il clustering, non vengono scritti automaticamente da nessuna parte: li applichi solo alla copia locale in `work/output/workdir/rules/` (utile per riclassificare subito in questa sessione) e produci un blocco di testo pronto da incollare a mano nello Sheet giusto, che presenti sempre all'utente.

## Come ti comporti

- Parli italiano per default.
- Sei operativo: quando l'utente carica un CSV, inizi subito il clustering.
- Se il settore non è chiaro, chiedi solo: *"Per quale settore sono queste keyword?"*

## Step 0 — Scegli il vertical e sincronizza il ruleset da Google Drive

Elenca le sottocartelle reali sotto la cartella Drive "Clustering rules" (id `1sBd0k1QSc23E_5ii6Nc1DtZ0oD1GjusS`) con `search_files` (`parentId = '1sBd0k1QSc23E_5ii6Nc1DtZ0oD1GjusS' and mimeType = 'application/vnd.google-apps.folder'`), escludendo quelle con prefisso `_` (es. `_Attributi`, non un vertical). Chiedi sempre all'utente quale vertical usare **tra quelli effettivamente trovati**, proponendo il più plausibile in base a brand/settore — non esiste una lista fissa da indovinare.

Una volta scelto il vertical, sincronizza il ruleset. **Il contenuto degli Sheet non passa quasi mai per il tuo contesto** — ma qui, a differenza del repo VS Code, il `curl` anonimo diretto su disco **non è disponibile**: il sandbox di questo ambiente nega la connessione verso l'host di redirect di Drive (`*.googleusercontent.com`) in modo permanente. Non è un problema di permessi, non si risolve e non va ritentato con varianti di flag/redirect.

1. **Trova l'ID di ogni Sheet** con `search_files` (solo il campo `id`, non il contenuto). Naming convention osservata su Drive (verificala comunque, può cambiare):
   - cluster del vertical/lingua: dentro la cartella del vertical scelto, titolo `cluster_<vertical>_<lingua>` (es. `cluster_fashion_it`)
   - attributi condivisi: dentro `_Attributi`, titolo `attributi_<lingua>` (es. `attributi_it`)
   - brand correlati: sotto "Clustering rules", titolo `brands`
   - città note: sotto "Clustering rules", titolo `cities`

   Ognuno di questi Sheet deve essere **monotab** (formato compresso, vedi CLAUDE.md nel repo, sezione "Formato compresso delle tab-cluster") — l'export `.csv` copre sempre e solo il primo/unico tab, quindi se un Sheet ha ancora più tab in formato legacy questo flusso ne leggerebbe solo uno, perdendo silenziosamente gli altri.
2. **Scarica ogni Sheet come `.csv`**, un file per Sheet (un solo tab). Per `cluster_<vertical>_<lingua>` e `attributi_<lingua>` (regole vere e proprie: centinaia di righe) usa il connettore Drive:
   ```text
   download_file_content(fileId=<ID_SHEET>, exportMimeType="text/csv")
   ```
   restituisce il file come base64 via API Drive autenticata: decodificalo e scrivilo su disco con un comando bash/python locale:
   ```bash
   work/output/workdir/sheets_raw/<vertical>/<lingua>.csv
   work/output/workdir/sheets_raw/_attributi/<lingua>.csv
   ```
   **Non è gratis**: il base64 passa per intero nel tuo contesto. Il CSV non ha l'overhead del contenitore xlsx (drawing/theme/styles/persons/content-types): solo il testo delle celle, gonfiato di un ulteriore ~33% dalla codifica base64 — molto più leggero da scaricare/scrivere del vecchio flusso `.xlsx`, e con meno rischio di troncamento su file grandi.

   Per i soli file piccoli e piatti `brands` e `cities` (poche colonne, liste corte) preferisci invece `read_file_content`: restituisce il contenuto in una singola chiamata come testo pulito, senza overhead base64. Il compromesso è che bypassa il parser Python: trascrivi tu a mano il contenuto nel JSON interno (`work/output/workdir/rules/brands.json` / `cities.json`) invece di produrre un `.csv` da passare a `sync-rules` per questi due file — va bene solo perché il rischio di errore di trascrizione è basso su liste corte. Lo stesso fallback (trascrizione manuale via `read_file_content`) vale anche per cluster/attributi se il base64 di un CSV grande si tronca comunque in scrittura — in quel caso verifica a campione righe e liste `Terms`/`Richiede Anche`.
3. Materializza i soli `.csv` scaricati (cluster/attributi):
   ```bash
   python work/scripts/cluster.py --mode sync-rules --workdir work/output/workdir
   ```
   Lo script legge ogni `.csv` come tab unica e riconosce automaticamente il formato compresso dall'header. Segnala all'utente eventuali valori di Cluster/Attributo non riconosciuti (probabile typo), senza bloccare il resto.

Se il fetch (da Drive via `search_files`, `download_file_content` o `read_file_content`) fallisce o il connettore non è disponibile, fermati e segnalalo all'utente invece di procedere con regole parziali o mancanti — non ritentare con `curl` in questo ambiente.

## Step 1 — Prepara con ruleset

```bash
python work/scripts/cluster.py \
  --mode prepare \
  --input [file.csv] \
  --sector "[settore]" \
  --vertical $VERTICAL \
  --batch-size 250 \
  --workdir work/output/workdir
```

Classifica la maggior parte delle keyword via regole (colonne opzionali Stagionalità/Evento/Outfit/Materiale-Colore/Genere/Recensioni/Sport incluse in automatico, zero domande — derivate dinamicamente dagli attributi sincronizzati, non da una lista fissa). Le keyword non coperte finiscono in `work/output/workdir/ai_needed.json` e nei batch prompt in `work/output/workdir/prompts/`.

**Colonne obbligatorie**: lo script verifica automaticamente che il CSV contenga **Keyword**, **Brand** e **Brand/Not Brand** (alias accettati: vedi `detect_columns` in `cluster.py`). Se una manca, l'output contiene `[ERRORE]` con l'elenco preciso di cosa manca e nessun `work/output/workdir` viene creato.

Se vedi questo errore, **fermati subito**:
- Non inventare né generare tu le colonne mancanti (né dedurle dal nome del file, né da pattern nella keyword, né con logiche di fuzzy match improvvisate) — anche se sembra un modo rapido per sbloccare il flusso, altera l'input in modi che l'utente non ha validato.
- Mostra all'utente esattamente quali colonne mancano (copia l'elenco dall'output dello script).
- Chiedi di ricaricare il CSV con le colonne corrette, ad esempio: *"Al file mancano le colonne X, Y — puoi ricaricare il CSV con queste colonne incluse?"*
- Riprendi il flusso solo dopo aver ricevuto un CSV che passa questa verifica.

## Step 2 — Analizza pattern non coperti

```bash
python work/scripts/cluster.py --mode analyze --workdir work/output/workdir
```

Genera `work/output/workdir/rule_proposals.json` con i pattern (token/bigrammi) più frequenti tra le keyword non classificate. Presenta all'utente una tabella con i pattern (count ≥ 3) e proponi cluster/sotto cluster. Se l'utente approva, compila i campi `suggested_cluster`/`suggested_sotto_cluster` nel JSON.

## Step 3 — Regole nuove: applica in sessione, presenta il blocco da incollare

```bash
python work/scripts/cluster.py --mode add-rules --workdir work/output/workdir --vertical $VERTICAL --lang IT
```

Ripeti con `--lang EN`/`--lang ES`/ecc. se il CSV ha una colonna Country e sono emerse proposte anche per quelle lingue. Questo comando aggiorna la copia locale in `work/output/workdir/rules/`, utile per riclassificare subito nella sessione corrente (rilancia lo Step 1), e scrive un blocco pronto da incollare in `work/output/workdir/paste_rules_<vertical>_<lingua>.txt` (diviso per tab di destinazione).

Presenta sempre all'utente quel blocco, indicando esplicitamente dove va incollato, ad esempio:

> *"Ho aggiunto N regole. Apri **Clustering rules/[Vertical]/[LINGUA]**, tab **'[Nome Cluster]'**, e incolla queste righe:"* (poi il contenuto del blocco).

## Step 4 — Clusterizza i batch rimanenti (tu stesso, senza AI esterna)

```bash
python work/scripts/cluster.py --mode process-batches --workdir work/output/workdir
```

Mostra i batch pendenti. Ogni `prompt_file` include già la lista dei brand correlati noti e i cluster validi per il vertical corrente (entrambi sincronizzati da Drive), così puoi distinguere un brand già in lista da un competitor nuovo e usare solo cluster realmente configurati. Per ciascun batch:
1. Leggi il `prompt_file` indicato (es. `work/output/workdir/prompts/batch_0001.txt`)
2. Clusterizza tu le keyword elencate, seguendo le regole di clustering di questo progetto (vedi tabella sotto). Se noti un nome di brand competitor/terzo ricorrente **non presente** nella lista brand correlati del prompt, aggiungilo a `new_brands` (solo se sei certo, max 5 per batch)
3. Scrivi il JSON risultato nel `result_file` indicato, formato:
```json
{
  "r": [["Cluster", "Sotto Cluster"], ...],
  "new_rules": [],
  "new_brands": []
}
```

## Step 5 — Merge finale

```bash
python work/scripts/cluster.py \
  --mode merge \
  --output work/output/[nome-file]-clustered.csv \
  --workdir work/output/workdir
```

Genera il CSV finale. Fornisci questo file all'utente come download. Se sono stati rilevati brand competitor nuovi, viene salvato anche `work/output/brands_suggestions.json`.

Lo script salva inoltre `work/output/[nome-file]-clustered-summary.json` (stesso prefisso del CSV finale) con i numeri della sintesi finale.

**Presenta sempre all'utente**, subito dopo il merge, una mini tabella di riepilogo (leggi i valori da questo JSON, o dall'output console se il file non è disponibile):

```text
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

## Step 6 — Brand competitor rilevati: applica in sessione, presenta il blocco da incollare

Se `work/output/brands_suggestions.json` esiste, presentalo sempre all'utente in formato leggibile:

```
🏷️  Brand competitor rilevati (non ancora in Clustering rules/Brands):
   - Supercompetitorbrand
   - Altrobrand
```

Se l'utente vuole applicarli **in questa sessione** (per riclassificare subito keyword simili), esegui:

```bash
python work/scripts/cluster.py --mode add-brands --brands-suggestions work/output/brands_suggestions.json --workdir work/output/workdir
```

Questo aggiorna la copia locale `work/output/workdir/rules/brands.json` e scrive un blocco pronto da incollare in `work/output/paste_brands.txt`. Presenta sempre quel blocco all'utente, ad esempio:

> *"Ho aggiunto N brand alla sessione corrente. Apri **Clustering rules/Brands**, tab **'Brand'**, e incolla queste righe:"* (poi il contenuto del blocco).

## Regole di clustering che applichi sempre

| Segnale nella keyword | Cluster | Sotto Cluster |
|---|---|---|
| Solo nome brand, typo, varianti | Brand Navigation | Ricerca Brand Principale |
| outlet, saldi, sconti, offerta | Outlet e Sconti | Outlet Online / Outlet Fisico |
| store, negozio, boutique, dove comprare | Punti Vendita | Store [città] |
| cashmere, lana, vigogna, tessuto, filato | Tessuti e Materie Prime | per materiale |
| maglione, cardigan, pullover, maglia, golf | Maglieria e Cashmere | per genere/materiale |
| scarpe, mocassini, stivali, sneaker, loafer | Calzature | per tipo/genere |
| giacca, cappotto, abito, pantalone, camicia | Abbigliamento | per genere/capo |
| borsa, cintura, sciarpa, cappello, guanti | Accessori | per tipo |
| storia, fondatore, valori, about, film, libro | Storia e Valori Brand | per topic |
| lavora con noi, candidatura, carriere, jobs | Carriere e HR | — |
| investor, bilancio, spa, sede legale, IR | Istituzionale | — |
| profumo, parfum, fragrance, colonia | Profumeria | per linea |
| outfit, look, stile, moda, abbinamento, elegante (senza prodotto specifico) | Ispirazionale | per genere/stagione |
| nessuna regola/sotto cluster ma brand terzo riconosciuto | Brand correlato | nome del brand correlato |

Nota: bambino, bambina, kids, child, junior ecc. **non** generano un cluster dedicato — valorizzano solo la colonna **Genere** con il valore `Kids`. Il genere non va mai inserito nel Sotto Cluster.

## Intento di ricerca

- **Navigational** — ricerche brand/prodotto/sito specifico
- **Informational** — come, guida, cos'è, storia, tutorial
- **Transactional** — acquisto, prezzo, compra, shop, order
- **Commercial Investigation** — migliori, vs, recensione, alternative

## Gestione multilingua

Il CSV può contenere una colonna **Country** (`IT`, `EN`, `ES`, `FR`, `DE`). Ogni riga viene classificata con le regole della sua lingua, dentro il vertical scelto allo Step 0 (Sheet `Clustering rules/<Vertical>/<LINGUA>`). Gli attributi (Genere, Stagionalità, ...) sono condivisi fra tutti i vertical ma restano per-lingua (Sheet `_Attributi/<LINGUA>`). Se la colonna Country è assente, si usano le regole italiane per default.

## Limiti noti di questa modalità

- **Nessuna scrittura diretta sugli Sheet**: le regole/brand approvati in sessione restano nella copia locale della sandbox (`work/output/workdir/rules/`) e nei blocchi `paste_*.txt`. Diventano permanenti solo quando qualcuno (in questa sessione o in un'altra) li incolla a mano nello Sheet giusto — non c'è più un giro di "esporta e importa altrove": chi ha accesso allo Sheet incolla e basta.
- Il token GitHub usato in `SKILL.md` serve solo a scaricare `scripts/cluster.py` e questo file (in **lettura**): non serve più per le regole, che non sono mai state nel repo da quando vivono su Drive.
- Serve il **connettore Google Drive** autorizzato sull'account claude.ai del collega, sia per trovare gli ID dei file in "Clustering rules" via `search_files`, sia per scaricarne il contenuto via `download_file_content`/`read_file_content` (vedi Step 0) — qui, a differenza del repo VS Code, non esiste un percorso via `curl` anonimo: il sandbox blocca in modo permanente la connessione verso l'host di redirect di Drive. Se il connettore non è autorizzato, fermati e chiedi di attivarlo dalle impostazioni connettori di claude.ai.
- Se la condivisione della cartella Drive dovesse tornare privata, anche `download_file_content`/`read_file_content` falliranno (permesso negato invece del contenuto): non c'è un'alternativa di fetch in questo ambiente — segnalalo all'utente invece di improvvisare con dati parziali.
- Nessuna persistenza tra conversazioni diverse: l'utente deve ricaricare il CSV a ogni nuova sessione, e se le regole/brand approvati in sessione non vengono incollati sugli Sheet prima di chiudere, si perdono (restano solo nella sandbox effimera).
- Nessuna cache tra run: keyword già viste in run precedenti (in altre sessioni) non vengono ricordate, solo le regole esplicite lo sono.
- Su CSV molto grandi (decine di migliaia di righe), valuta di suddividere il lavoro per brand per stare dentro ai limiti di tempo/esecuzione della sandbox.
- Se il fetch da GitHub o da Google Drive fallisce (token scaduto, rate limit, repo/cartella rinominata, connettore non autorizzato), fermati e segnalalo all'utente invece di procedere con regole parziali o mancanti.

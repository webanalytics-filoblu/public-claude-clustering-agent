# SEO Keyword Clustering Agent

Agente Claude Code per il clustering automatico di keyword SEO. Funziona con **account Claude Pro su VS Code** — nessuna API key, nessuna spesa di token separata.

## Come funziona

Il flusso è a tre fasi:

1. **Prepare** — lo script Python classifica automaticamente le keyword tramite regole + fuzzy match + cache, e genera prompt solo per le keyword ambigue
2. **Clustering AI** — Claude Code legge ogni batch e scrive il JSON risultante (è Claude che clusterizza, non un'API esterna)
3. **Merge** — lo script unisce tutto nel CSV finale

La maggior parte delle keyword viene classificata automaticamente (zero AI), riservando i batch Claude solo ai casi ambigui.

Le regole usate nella fase 1 (Cluster, Sotto Cluster, brand correlati, attributi come Genere o Stagionalità) **non sono scritte nel codice**: vivono in Google Sheet condivisi su Drive e vengono sincronizzate in locale a inizio sessione. Chiunque abbia accesso a quegli Sheet può aggiungere o modificare una regola senza toccare questo repo — vedi [Regole di clustering: dove vivono e come modificarle](#regole-di-clustering-dove-vivono-e-come-modificarle).

## Setup (una volta sola)

```bash
# 1. Installa l'unica dipendenza Python
pip install pandas

# 2. Apri la cartella in VS Code
code public-claude-clustering-agent/

# 3. Avvia Claude Code ed effettua il login con il tuo account Pro
```

Alla prima richiesta che tocca la cartella Drive "Clustering rules", Claude Code ti chiederà l'ID di quella cartella (o della tua copia, se stai partendo da zero) e lo salverà in **`clustering-config.json`** (gitignored — vedi `clustering-config.example.json` per il formato) per le sessioni successive. Non serve farlo a mano, ma puoi anche precompilarlo tu prima di iniziare. È lo stesso identico file usato anche dalle skill claude.ai (`claude-skill`, `brand-cluster-rules-builder-skill`): un solo file da tenere aggiornato, riusabile in entrambi i contesti — puoi anche allegarlo/incollarlo in una chat claude.ai invece di reinserire l'ID a mano.

## Utilizzo

Copia il CSV nella cartella `input/` e scrivi nella chat di Claude Code:

```
/cluster input/keyword-competitors.csv

# Solo un brand
/cluster input/keyword-competitors.csv --brand "Falconeri"

# Con settore specifico (migliora la qualità)
/cluster input/keyword-competitors.csv --sector "abbigliamento e moda"

# Riprendi se interrotto
/cluster input/keyword-competitors.csv --resume
```

## Formato CSV atteso

Il file deve avere almeno una colonna keyword. Le altre colonne sono opzionali ma migliorano la qualità del clustering.

Utilizzando il tool online **[SEMrush Keyword Cleaner - Configurable Master Launcher](https://docs.google.com/spreadsheets/d/1PBfbuUJEpl6m5O0KrruyGY9WhaHzVvqdN4wgubGj_GI)** è possibile creare parzialmente in automatico il csv richiesto partendo dalle esportazioni di SemRush

### Colonne riconosciute in input

| Colonna | Alias accettati | Obbligatoria | Descrizione |
|---|---|---|---|
| `Keyword` | `keyword`, `kw`, `query`, `keywords`, `parola chiave` | ✅ | La keyword da classificare |
| `Brand` | `brand`, `marchio`, `competitor` | No | Nome del brand associato. Usato per il riconoscimento brand navigation e fuzzy match |
| `Brand/Not Brand` | `type`, `tipo`, `brand_not_brand` | No | Indica se la keyword è ricerca diretta del brand (`Brand`) o generica (`Not Brand`) |

> Le intestazioni non sono case-sensitive: `Keyword`, `keyword` e `KEYWORD` sono equivalenti.

Qualsiasi altra colonna presente (es. `Volume`, `CPC`, `Difficulty`) viene conservata intatta nel file di output.

### Esempio CSV di input

| Brand | Country | Keyword | Brand/Not Brand |
|---|---|---|---|
| Falconeri | IT | falconeri outlet | Brand |
| Falconeri | IT | falconeri maglioni donna | Brand |
| Falconeri | IT | maglione cashmere donna | Not Brand |
| Falconeri | IT | maglione lana uomo | Not Brand |
| Brunello Cucinelli | IT | brunello cucinelli | Brand |
| Brunello Cucinelli | IT | cucinelli shop | Brand |
| Brunello Cucinelli | IT | abiti eleganti uomo | Not Brand |
| Gucci | IT | gucci scarpe | Brand |
| Gucci | IT | borse eleganti marrone | Not Brand |

### Esempio CSV di output (risultato)

Le colonne `Cluster`, `Sotto Cluster` e le colonne opzionali vengono aggiunte automaticamente:

| Brand | Country | Keyword | Brand/Not Brand | Cluster | Sotto Cluster | Stagionalità | Genere | Materiale/Colore | Outfit | Evento | Recensioni |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Falconeri | IT | falconeri outlet | Brand | Outlet e Sconti | Outlet Online | | | | | | |
| Falconeri | IT | falconeri maglioni donna | Brand | Brand Navigation | Ricerca Brand Principale | | donna | | | | |
| Falconeri | IT | maglione cashmere donna | Not Brand | Maglieria e Cashmere | Maglieria Donna | | donna | cashmere | | | |
| Falconeri | IT | maglione lana uomo | Not Brand | Maglieria e Cashmere | Maglieria Uomo | | uomo | lana | | | |
| Brunello Cucinelli | IT | brunello cucinelli | Brand | Brand Navigation | Ricerca Brand Principale | | | | | | |
| Brunello Cucinelli | IT | cucinelli shop | Brand | Brand Navigation | Ricerca Brand Principale | | | | | | |
| Brunello Cucinelli | IT | abiti eleganti uomo | Not Brand | Abbigliamento | Abito Uomo | | uomo | | formale | | |
| Gucci | IT | gucci scarpe | Brand | Brand Navigation | Ricerca Brand Principale | | | | | | |
| Gucci | IT | borse eleganti marrone | Not Brand | Accessori | Borse | | | marrone | | | |

## Colonne aggiunte automaticamente

Oltre a `Cluster` e `Sotto Cluster`, lo script aggiunge sempre queste colonne opzionali (classificate da regole, senza AI):

| Colonna | Cosa contiene |
|---|---|
| `Stagionalità` | estate, primavera, autunno, inverno, year-round |
| `Evento` | natale, black friday, san valentino, matrimonio, ecc. |
| `Outfit` | casual, formale, business, sportivo, sera, spiaggia |
| `Materiale/Colore` | materiale o colore estratto dalla keyword |
| `Genere` | uomo, donna, unisex |
| `Recensioni` | recensioni, confronto, sostenibilità, qualità, prezzo |
| `Brand correlati` | brand rivenduti o correlati nella keyword |

## Cluster disponibili

I Cluster sono interamente dinamici, come i vertical e gli attributi: il nome che scrivi nella colonna `Cluster` dello Sheet diventa direttamente la chiave interna, senza nessuna whitelist in [scripts/cluster.py](scripts/cluster.py) — un Cluster mai visto prima funziona subito (vedi [Aggiungere un Sotto Cluster o un termine](#aggiungere-un-sotto-cluster-o-un-termine-il-caso-più-comune)). Solo questi nomi hanno in più una logica di discriminazione dedicata (typo/fuzzy sul brand, online-vs-fisico, near-me, ...) o una confidence specifica invece del flat 0.85 usato per un Cluster qualsiasi — un Cluster rinominato o nuovo perde solo questo bonus, non smette di funzionare:

| Cluster | Esempi di keyword |
|---|---|
| Brand Navigation | `falconeri`, `brunello cucinelli shop` |
| Outlet e Sconti | `falconeri outlet`, `saldi maglioni` |
| Punti Vendita | `falconeri negozio milano`, `store cucinelli roma` |
| Profumeria | `profumo donna`, `fragranze lusso` |
| Calzature | `mocassini uomo`, `stivali donna pelle` |
| Costumi e Beachwear | `costume da bagno donna`, `bikini mare` |
| Abbigliamento | `cappotto donna`, `abito elegante uomo` |
| Accessori | `borsa pelle`, `sciarpa cashmere`, `cintura uomo` |
| Istituzionale | `investor relations`, `bilancio annuale` |
| Brand correlato | keyword con brand terzo riconosciuto (`Clustering rules/Brands`), non da una tab dedicata |

Altri Cluster comuni (es. Squadre di Calcio, Maglieria e Cashmere, Tessuti e Materie Prime, Ispirazionale, Carriere e HR) funzionano allo stesso modo con il match generico su Sottocluster/Terms/Richiede Anche — nessuna logica dedicata, nessuna differenza pratica per chi scrive lo Sheet.

> `bambino`/`bambina`/`kids`/`junior` **non** generano un Cluster dedicato: valorizzano solo la colonna opzionale `Genere` (vedi sotto). Né i Cluster né i Sotto Cluster sono un set chiuso: si aggiungono entrambi direttamente sugli Sheet condivisi, senza toccare il codice — vedi la sezione seguente.

## Regole di clustering: dove vivono e come modificarle

Le regole che determinano Cluster, Sotto Cluster e le colonne opzionali **non sono nel codice**: vivono in Google Sheet condivisi su Drive, nella cartella **"Clustering rules"**. Chiunque abbia accesso a quella cartella può aggiungere un termine, un Sotto Cluster o un nuovo valore di attributo senza scrivere una riga di Python — la modifica diventa effettiva alla sincronizzazione successiva (`--mode sync-rules`, eseguita dall'agente Claude Code a inizio sessione di clustering, vedi [CLAUDE.md](CLAUDE.md)).

L'ID di questa cartella **non è in questo repo pubblico** (equivarrebbe a un permesso di lettura, dato che la condivisione è "chiunque abbia il link"): ognuno lo configura nel proprio `clustering-config.json` locale (gitignored, alla radice del repo) — vedi [CLAUDE.md](CLAUDE.md), sezione "Configurazione: ID della cartella Drive", e `clustering-config.example.json` per il formato.

### Struttura della cartella Drive

```text
Clustering rules/                              (id <CLUSTERING_RULES_FOLDER_ID>, vedi clustering-config.json)
├── <Vertical>/              es. Fashion, Shoes, Intimo, Multibrand — una sottocartella per settore
│   └── cluster_<vertical>_<lingua>   uno Google Sheet per lingua (es. cluster_fashion_it)
│       └── <una o più tab>           vedi "Aggiungere un Sotto Cluster o un termine"
├── _Attributi/               prefisso `_`: non è un vertical, va escluso quando si elenca la cartella
│   └── attributi_<lingua>    uno Sheet per lingua, condiviso da tutti i vertical (es. attributi_it)
│       └── <una o più tab>           vedi "Aggiungere un attributo o un suo valore"
├── brands                    Sheet unico, condiviso da tutto
└── cities                    Sheet unico, condiviso da tutto
```

Il vertical **non è una lista fissa**: basta creare una nuova sottocartella sotto "Clustering rules" (con dentro lo Sheet `cluster_<vertical>_<lingua>` per ogni lingua) per aprire un nuovo settore, senza alcuna modifica al repo. La naming convention dei titoli Sheet (`cluster_<vertical>_<lingua>`, `attributi_<lingua>`, `brands`, `cities`) è quella osservata oggi su Drive: va comunque riverificata a ogni sincronizzazione, può cambiare.

### Aggiungere un Sotto Cluster o un termine (il caso più comune)

Ogni Sheet `cluster_<vertical>_<lingua>` può contenere le sue tab in due formati (riconosciuti automaticamente dalla prima cella dell'header, possono coesistere nello stesso Sheet durante una migrazione graduale):

**Formato compresso (preferibile)** — una tab unica per tutto il vertical/lingua, colonna `Cluster` esplicita, una riga per (Cluster, Sottocluster):

| Cluster | Sottocluster | Cluster Order | Sottocluster Order | Terms | Richiede Anche | Note |
|---|---|---|---|---|---|---|
| Maglieria e Cashmere | Maglieria Donna | 4 | 1 | cardigan donna \| maglione donna | | |
| Outlet e Sconti | Outlet Online | 2 | 1 | outlet | shop, online | |
| Outlet e Sconti | Outlet Fisico | 2 | 2 | outlet | negozio, store | |

- **Cluster Order** / **Sottocluster Order** (opzionali, un numero) — decidono l'ordine di valutazione quando più righe potrebbero matchare la stessa keyword: tra Cluster diversi (`Cluster Order`) e tra Sottocluster dello stesso Cluster (`Sottocluster Order`), a parità di altre condizioni vince il valore più basso. Se assenti, si torna al comportamento storico (un ordine fisso nel codice per i cluster noti, l'ordine delle righe nello Sheet per i sottocluster). Basta un valore sulla prima riga di quel (Cluster) / (Cluster, Sottocluster): le righe successive possono lasciarlo vuoto.
- **Terms** — lista di parole/frasi separate da `|`; se una di queste è presente nella keyword (come parola intera, non come sottostringa), fa scattare la regola.
- **Richiede Anche** (opzionale, più valori separati da virgola o `|`) — quando più righe condividono lo stesso Cluster ma vanno smistate su Sottocluster diversi (es. Outlet Online vs Outlet Fisico), la keyword deve contenere anche uno di questi termini per finire in quel Sottocluster specifico; altrimenti finisce nel Sottocluster di default. Si applica all'intero Sottocluster, non al singolo termine della lista.
- **Note** — libera, solo per chi legge lo Sheet, non usata dallo script.
- Righe aggiuntive per lo stesso (Cluster, Sottocluster) sono valide: si uniscono a quella esistente alla sincronizzazione successiva, non serve editare a mano la lista `|`.

**Formato legacy (ancora supportato)** — una tab per Cluster (il nome della tab è il nome del cluster), una riga per termine:

| Sotto Cluster | Termine | Richiede anche | Note |
|---|---|---|---|
| Maglieria Donna | cardigan donna | | |
| Outlet Online | outlet | shop, online | |
| Outlet Fisico | outlet | negozio, store | |

Stesse colonne/logica del formato compresso, solo una riga per termine invece che una lista `|`.

In entrambi i formati basta una nuova riga: nessuna modifica di codice necessaria.

**Due convenzioni speciali (in entrambi i formati):**

- `(default)` nella colonna Terms/Termine — la riga non definisce un termine ma il **Sotto Cluster di default** del Cluster: se la keyword matcha il Cluster ma nessun altro termine più specifico, finisce qui.
- `(stop word)` come valore di Sottocluster/Sotto Cluster, solo per il Cluster **Brand Navigation**: definisce parole (es. "shop", "official", "srl") che, se sono tutto ciò che resta della keyword dopo aver rimosso il nome brand, non fanno deviare la classificazione verso un Cluster prodotto.

### Aggiungere un Cluster interamente nuovo (caso meno comune)

Un Cluster **mai visto prima** (una nuova tab in formato legacy, o un nuovo valore nella colonna `Cluster` in formato compresso) funziona già dalla prossima sincronizzazione: nessuna modifica di codice, nessuna whitelist da aggiornare in [scripts/cluster.py](scripts/cluster.py). Le sue keyword vengono classificate dal match generico su Sottocluster/Terms/Richiede Anche, con la stessa confidence di un Cluster qualsiasi non elencato tra quelli con logica dedicata (vedi [Cluster disponibili](#cluster-disponibili)). Se in futuro serve dargli una logica di discriminazione ad hoc (come Brand Navigation o Outlet e Sconti) o una priorità di valutazione esplicita rispetto agli altri quando non basta `Cluster Order` nello Sheet, quella resta l'unica parte che richiede toccare il codice (rispettivamente in `classify_by_rules` e in `PRIORITY_ORDER_BASE`).

### Aggiungere un attributo o un suo valore

Le colonne opzionali (Genere, Stagionalità, Evento, Outfit, Materiale/Colore, Sport, Recensioni, Intento di Ricerca, ...) sono **interamente gestibili da Sheet**, con la stessa filosofia dei Cluster: ogni tab/attributo presente nello Sheet `attributi_<lingua>` diventa automaticamente una colonna in output, senza whitelist. Sono supportati tre formati (coesistono durante una migrazione, si riconoscono dall'header):

**Compresso a tab unica (preferibile)** — tutti gli attributi nella stessa tab, colonna `Attributo` esplicita, una riga per (Attributo, Valore):

| Attributo | Valore | Terms | Cluster Fallback |
|---|---|---|---|
| Stagionalità | Estate | estate \| summer | |
| Evento | Natale | natale \| christmas \| regalo natale | |

**Compresso per-attributo** — una tab per attributo, una riga per Valore:

| Valore | Terms | Cluster Fallback |
|---|---|---|
| Estate | estate, summer | |
| Natale | natale, christmas, regalo natale | Evento |

**Legacy** — una tab per attributo, una riga per termine:

| Valore | Termine | Cluster fallback |
|---|---|---|
| Estate | estate | |
| Estate | summer | |
| Natale | natale | Evento |

In tutti e tre i formati:

- **Valore** — cosa viene scritto nella colonna opzionale quando uno dei Terms/Termine matcha.
- **Cluster fallback/Cluster Fallback** (opzionale, basta compilarlo su una riga dell'attributo) — se una keyword non matcha **nessun** Cluster prodotto ma matcha questo attributo, l'attributo stesso diventa il Cluster (e Valore diventa il Sotto Cluster). Resta un unico valore per l'intero attributo, non per singolo Valore/termine.
- Un **attributo interamente nuovo** (una tab nuova nei formati per-attributo, o un nuovo valore di `Attributo` nel formato a tab unica) produce automaticamente una nuova colonna in output alla sincronizzazione successiva: qui non serve mai una modifica di codice.

### Aggiungere un brand correlato o una città

- **`Clustering rules/brands`**: due colonne, `Brand | Canonico` (Canonico opzionale — se vuoto, il brand è il canonico di se stesso). Righe con lo stesso Canonico si uniscono, utile per unificare grafie diverse dello stesso brand (es. "dr martens"/"dr. martens"/"drmartens" → canonico "Dr. Martens"). Se un brand compare in una keyword (ed è diverso dal brand principale della riga) → Cluster "Brand correlato".
- **`Clustering rules/cities`**: una città per riga, minuscolo. Riconosce il pattern "brand + città" (es. "yamamay milano") → instradato a Punti Vendita/Store.

Entrambi sono condivisi da tutti i vertical e lingue: non vanno duplicati.

### Dopo la modifica

Le modifiche allo Sheet non sono immediate: vanno prima riscaricate come `.csv` (`Clustering rules` è condivisa "chiunque abbia il link", quindi via `curl` anonimo diretto su disco — o via il connettore Drive `download_file_content(exportMimeType="text/csv")` nell'ambiente claude.ai, dove il `curl` è bloccato) e poi materializzate in locale con

```bash
python scripts/cluster.py --mode sync-rules --workdir output/workdir
```

Nel normale utilizzo non serve farlo a mano: l'agente Claude Code lo fa da solo prima di ogni `--mode prepare`, quando lavori dentro la chat con `/cluster` — vedi [CLAUDE.md](CLAUDE.md), sezione "Sincronizza da Google Drive", per il dettaglio del download.

## Struttura cartelle

```text
public-claude-clustering-agent/
├── CLAUDE.md                        ← istruzioni persistenti per l'agente
├── README.md
├── .claude/
│   └── commands/
│       └── cluster.md               ← definizione del comando /cluster
├── scripts/
│   └── cluster.py                   ← sync-rules | prepare | analyze | add-rules | add-brands | process-batches | merge
├── input/                           ← CSV da processare
└── output/                          ← non versionato (.gitignore)
    ├── workdir/
    │   ├── vertical.json             ← vertical scelto per la sessione
    │   ├── sheets_raw/               ← staging .csv scaricato dagli Sheet monotab (input di --mode sync-rules)
    │   │   ├── brands.csv
    │   │   ├── cities.csv
    │   │   ├── _attributi/<lingua>.csv
    │   │   └── <vertical>/<lingua>.csv
    │   ├── rules/                   ← regole materializzate da --mode sync-rules (copia effimera di sessione)
    │   │   ├── brands.json
    │   │   ├── cities.json
    │   │   ├── _attributi/<lingua>.json
    │   │   └── <vertical>/<lingua>.json
    │   ├── manifest.json             ← mappa di tutti i batch AI
    │   ├── base.csv                  ← CSV con colonne pre-compilate da regole
    │   ├── prompts/                  ← batch_NNNN.txt — prompt da leggere
    │   └── results/                  ← batch_NNNN.json — risultati scritti da Claude
    ├── [nome-file]-clustered.csv           ← CSV finale con tutti i cluster
    ├── [nome-file]-clustered-summary.json  ← sintesi finale (keyword, cluster, token stimati, tempi...)
    └── paste_rules_*.txt / paste_brands.txt ← blocchi pronti da incollare sugli Sheet (dopo add-rules/add-brands)
```

Le regole vere e proprie non compaiono in questa struttura: vivono su Google Drive, non in questo repo (vedi sezione precedente).

## Argomenti del comando /cluster

| Argomento | Default | Descrizione |
|---|---|---|
| `[file]` | — | CSV da processare (obbligatorio) |
| `--brand [nome]` | tutti | Processa solo il brand specificato |
| `--sector [testo]` | `"abbigliamento e moda"` | Contesto settoriale per migliorare la qualità AI |
| `--batch-size [n]` | 250 | Keyword per batch AI |
| `--resume` | — | Riprende da dove era rimasto (salta batch già completati) |
| `--no-interactive` | — | Salta le domande interattive |

---
name: brand-cluster-rules-builder
description: "Genera il CSV completo (regole standard + nuove righe brand con Cluster Order/Sottocluster Order coerenti, meno gli eventuali Cluster/Sottocluster non pertinenti che l'utente sceglie di rimuovere) di un vertical/lingua nel formato compresso Cluster/Sottocluster/Terms usato da seo-keyword-clustering, come file dedicato al brand pronto da caricare nella sua cartella Google Drive, a partire da: URL della piattaforma e-commerce del brand, URL delle voci di menu estratte dalla piattaforma, link alle linee guida/tone of voice del brand, e un CSV di keyword del brand già assegnate a un cluster/tema generico. Usa SEMPRE questa skill quando l'utente chiede di creare, generare, estendere o integrare le regole di clustering specifiche per un brand (fashion/shoes/intimo/multibrand), o parla di 'regole cluster per il brand X', 'sottocluster dedicati al brand', o fornisce menu + keyword di un brand e chiede di produrre il csv di regole aggiornato. Non usare per la clusterizzazione delle keyword stesse (quella è seo-keyword-clustering) né per la pulizia di export Semrush grezzi (semrush-keyword-cleaner)."
---

# Brand Cluster Rules Builder

Skill proprietaria dell'organizzazione (ID `be71789f-9195-4df2-83ae-88e14cdb94ef`).

**Configurazione — Step -1, sempre prima di tutto**: questa skill referenzia più avanti l'ID della cartella Drive "Clustering rules" come `<CLUSTERING_RULES_FOLDER_ID>`, letto da `clustering-config.json` — lo stesso identico file/valore usato dal repo lato VS Code e dalla skill `seo-keyword-clustering` (`https://github.com/webanalytics-filoblu/public-claude-clustering-agent`, vedi `CLAUDE.md`), tracciato in chiaro nel repo pubblico perché quella cartella non è più condivisa "chiunque abbia il link" (serve comunque un account autorizzato):

```bash
curl -sL \
  "https://raw.githubusercontent.com/webanalytics-filoblu/public-claude-clustering-agent/main/clustering-config.json" \
  -o work/clustering-config.json

export CLUSTERING_RULES_FOLDER_ID=$(python3 -c "import json;print(json.load(open('work/clustering-config.json'))['clustering_rules_folder_id'])")
```

Se il valore letto è vuoto o è ancora il placeholder `<CLUSTERING_RULES_FOLDER_ID>` (repository forkato senza configurarlo), fermati e chiedi all'utente l'ID della sua cartella prima di proseguire — non indovinarlo né usarne uno di un'altra organizzazione.

Produce il **CSV completo** (righe standard del vertical/lingua + nuove righe brand-specifiche già unite, con `Cluster Order`/`Sottocluster Order` compilati in modo coerente dove serve, meno gli eventuali Cluster/Sottocluster non pertinenti che l'utente ha scelto di rimuovere) nel formato compresso `Cluster,Sottocluster,Cluster Order,Sottocluster Order,Terms,Richiede Anche,Note`, come **file dedicato al brand**, separato dallo Sheet condiviso `cluster_<vertical>_<lingua>` che resta la baseline di riferimento per tutti i brand del vertical — non un frammento da incollare a mano in coda, ma il file intero pronto all'uso per quel brand.

## Input attesi

1. **URL piattaforma e-commerce** del brand.
2. **URL delle voci di menu** estratte dalla piattaforma (lista di URL o testo con le voci del menu, tipicamente una "treemap" di link esportata dalla piattaforma). Se l'utente non ha già questo elenco, suggerisci di estrarlo con l'estensione Chrome [Link Grabber](https://chromewebstore.google.com/detail/link-grabber/caodelkhipncidmoebgbbeemedohcdma): aperta sulla home o sulle pagine di navigazione del sito del brand, esporta tutti i link della pagina in un click, producendo il CSV di URL da fornire in input a questo step.
3. **Link alle linee guida / tone of voice** del brand (es. brand guidelines, naming ufficiale di prodotto).
4. **CSV di keyword del brand**, con almeno due colonne: una colonna keyword e una colonna cluster/tema generico assegnato (es. `Keyword,Tema`). Le keyword NON sono ancora raggruppate in pattern regex-like: è la skill a doverle raggruppare in `Terms` con la sintassi `termine1|termine2|termine3`. Se il CSV ha una colonna `Country`/lingua, trattala come nello step 0 (una lingua alla volta); se assente, assumi italiano (`it`).

Se manca uno di questi quattro input, chiedilo esplicitamente prima di procedere — non inventare URL o contenuti di linee guida.

## Step 0 — Scegli vertical e lingua, scarica lo Sheet delle regole standard

Le regole standard vivono in Google Drive, cartella "Clustering rules" (id `<CLUSTERING_RULES_FOLDER_ID>`). Al suo interno una sottocartella per vertical (es. `fashion`, `shoes`, `intimo`, `multibrand`), ciascuna con un Google Sheet per lingua, titolo `cluster_<vertical>_<lingua>` (es. `cluster_fashion_it`).

**Ignora sempre**: la cartella `_Attributi` (attributi condivisi come Genere/Stagionalità, non regole cluster) e gli Sheet `brands` / `cities` (liste di normalizzazione, non regole di clustering). Ignora anche eventuali cartelle già dedicate a un brand specifico: non sono il file "standard" da estendere, sono già un output di una run precedente di questa skill.

```
Google Drive:search_files query="parentId = '<CLUSTERING_RULES_FOLDER_ID>' and mimeType = 'application/vnd.google-apps.folder'"
```

Elenca all'utente i vertical trovati (escludendo `_Attributi`) e chiedi quale vuole estendere, a meno che l'utente non l'abbia già specificato (es. "brand X, settore scarpe"). Poi chiedi la lingua se non è ovvia dal CSV keyword (default `it`).

Trova l'ID del Google Sheet `cluster_<vertical>_<lingua>` con `search_files` (solo il campo `id`, non il contenuto) dentro la cartella del vertical. **Precondizione: lo Sheet deve essere monotab** (un solo tab, formato compresso) — l'export CSV copre sempre e solo il primo/unico tab. Se sospetti che lo Sheet abbia più tab legacy, fermati e segnalalo all'utente invece di leggerne solo uno perdendo silenziosamente gli altri.

Scarica il tab come CSV, **senza farlo passare per il tuo contesto quando possibile**: usa il tool connettore `download_file_content(fileId=<ID_SHEET>, exportMimeType="text/csv")`, decodifica il base64 e scrivilo su disco. La cartella richiede un account Google autorizzato (non è condivisa "chiunque abbia il link"): niente `curl` verso `docs.google.com`/`*.googleusercontent.com`, in nessun ambiente — riceveresti solo una pagina di login al posto del CSV.

Solo come ultimo fallback (base64 troncato su file molto grandi), usa `read_file_content` e trascrivi a mano le righe rilevanti — verificando a campione numero di righe e liste `Terms`/`Richiede Anche` separate da `|`.

Verifica che l'header del CSV scaricato inizi con `Cluster` (formato compresso: `Cluster,Sottocluster,Cluster Order,Sottocluster Order,Terms,Richiede Anche,Note`). Se trovi invece il formato legacy a singolo cluster (`Sotto Cluster,Termine,Richiede anche,Note`), segnalalo all'utente: quel vertical/lingua non è ancora stato migrato al formato compresso e questa skill non deve scrivervi sopra nel formato vecchio — chiedi conferma su come procedere prima di continuare.

Questo file scaricato è la **baseline**: la userai sia per la deduplica (Step 3) sia come contenuto di partenza del CSV completo che produrrai (Step 4) — non ricostruirla a mano, non ometterne righe.

## Step 1 — Leggi tutti gli input del brand

- **CSV keyword+tema**: leggilo per intero. Raggruppa le keyword per il tema/cluster generico assegnato dall'utente.
- **URL menu**: usa `web_fetch` su ciascun URL per vedere le voci di navigazione reali del brand (nomi di categoria, sottocategorie). Questi ti dicono la tassonomia "ufficiale" del brand, spesso più granulare o con naming diverso da quello delle keyword.
- **Linee guida brand**: fetcha il link. Estrai in particolare: naming ufficiale di prodotto/collezioni, termini che il brand preferisce o evita, eventuale terminologia di iconic/hero product da trattare come sottocluster a sé.
- **Piattaforma e-commerce**: se serve disambiguare una voce di menu ambigua, naviga anche lì.

## Step 2 — Raggruppa le keyword in Terms (pattern con `|`)

Per ogni tema generico del CSV di input:

1. Individua le keyword che condividono la stessa radice semantica/prodotto (es. `mocassino`, `mocassini`, `loafer`, `loafers` → un unico `Terms`).
2. Componi il campo `Terms` unendo le varianti con `|`, seguendo lo stile della baseline già scaricata (minuscolo, plurali e singolari entrambi presenti, sinonimi IT/EN, variabili di spelling comuni).
3. Se dentro lo stesso tema generico convivono più prodotti/concetti distinti (es. tema "Calzature" ma keyword miste tra sneaker, stivali, sandali), **spacca in più righe/sottocluster distinti** — non forzare tutto in un unico Terms indifferenziato.
4. Usa le voci di menu e le linee guida per capire se un gruppo di keyword merita un Sottocluster proprio con naming brand-specifico (es. il brand chiama una categoria "Urban Collection" invece di "Sneaker generiche": in questo caso valuta se creare un sottocluster dedicato, spiegando la scelta in Note).

## Step 3 — Assegna Cluster e Sottocluster, deduplicando contro la baseline

Per ogni nuovo gruppo di Terms:

1. **Cerca prima un match nella baseline** (scaricata allo Step 0): se un termine è già coperto da un pattern esistente in un Cluster/Sottocluster standard (es. `sneaker` è già in `Calzature/Sneaker`), **non duplicarlo** in una nuova riga — se serve comunque un `Richiede Anche` o naming diverso legato al brand, segnalalo in `Note` spiegando che la keyword è già coperta dalle regole standard e perché la includi comunque (o la escludi).
2. Se il gruppo va ad **arricchire un (Cluster, Sottocluster) già esistente in baseline** (stesso nome esatto), non creare una riga duplicata: unisci i nuovi termini a quelli già presenti nella cella `Terms` di quella riga con `|` (stessa logica di `--mode add-rules`: righe multiple per lo stesso Sottocluster sono valide, ma qui puoi anche accorpare direttamente dato che riscrivi il file intero).
3. Per i gruppi non coperti dalla baseline:
   - **Preferisci aggiungere un nuovo Sottocluster sotto un Cluster esistente** (es. nuovo Sottocluster "Mules" sotto il Cluster "Calzature" già esistente), se il Cluster è pertinente.
   - Crea un **nuovo Cluster** dedicato solo se il tema non è riconducibile a nessun Cluster esistente nella baseline (es. una linea di prodotto totalmente specifica del brand, come una capsule collection con nome proprio). I Cluster sono interamente dinamici in `scripts/cluster.py` (nessuna whitelist): un nome mai visto prima funziona già dalla prossima `--mode sync-rules`, classificato con il match generico su Sottocluster/Terms/Richiede Anche. Solo un piccolo set di nomi noti (`Brand Navigation`, `Outlet e Sconti`, `Punti Vendita`, `Calzature`, `Costumi e Beachwear`, `Abbigliamento`, `Accessori`, `Profumeria`, `Istituzionale`) ha in più una logica di discriminazione dedicata o una confidence specifica — un Cluster nuovo con un nome diverso funziona comunque, solo senza quel bonus; non serve avvisare l'utente di alcun passaggio di codice.
4. Segui esattamente le convenzioni di colonna del formato compresso:
   - `Cluster`: nome del cluster (esistente o nuovo).
   - `Sottocluster`: nome del sottocluster; usa `Terms="(default)"` per la riga di fallback quando crei un Cluster nuovo (il Sottocluster con quella riga diventa il default del cluster).
   - `Cluster Order` / `Sottocluster Order`: vedi Step 3ter — vanno sempre valorizzati in modo coerente per le righe nuove, e corretti se necessario in quelle di baseline.
   - `Terms`: pattern `|`-separated.
   - `Richiede Anche`: solo se il match del Sottocluster richiede la compresenza di un secondo termine (stessa logica delle righe standard, es. "online" per "Outlet Online").
   - `Note`: **sempre valorizzata** con una breve motivazione — cita la fonte (menu, linee guida, o dedup da baseline) che ha portato a quella riga.

## Step 3bis — Proponi la rimozione dei Cluster/Sottocluster non pertinenti (sceglie sempre l'utente)

Oltre ad aggiungere, individua nella **baseline** i Cluster/Sottocluster di prodotto che con ogni evidenza non c'entrano nulla con questo brand (es. Cluster "Profumeria" su un brand che vende solo calzature, Sottocluster "Cashmere" su un brand che non tratta maglieria).

**Non proporre mai la rimozione** dei Cluster strutturali/trasversali, validi per qualunque brand indipendentemente dal catalogo prodotto (vedi tabella "Regole di clustering che applichi sempre" in CLAUDE.md): `Brand Navigation`, `Outlet e Sconti`, `Punti Vendita`, `Storia e Valori Brand`, `Carriere e HR`, `Istituzionale`, `Ispirazionale`, `Brand correlato`. Questi si applicano anche se il brand non ha ancora keyword di quel tipo.

Per ogni Cluster/Sottocluster **di prodotto** in baseline, considera candidato alla rimozione solo se **non trovi nessun segnale** da nessuna delle tre fonti:
1. nessuna voce di menu della piattaforma e-commerce lo richiama;
2. nessuna keyword del CSV di input lo copre, nemmeno indirettamente;
3. non è citato nelle linee guida/tone of voice del brand.

L'assenza di keyword nel solo CSV di input **non basta**: il campione potrebbe essere parziale o il brand potrebbe ampliare il catalogo in futuro — richiedi l'assenza su tutte e tre le fonti prima di proporre la rimozione.

Presenta all'utente l'elenco dei candidati così individuati, uno per riga, con la motivazione (quale fonte hai controllato e perché risulta non pertinente) — insieme alle eventuali correzioni di `Cluster Order`/`Sottocluster Order` individuate allo Step 3ter, in un'unica domanda di conferma — e chiedi esplicitamente quali applicare — con una domanda a scelta multipla (es. tramite `AskUserQuestion`, un'opzione per candidato più "nessuno"), mai una rimozione o correzione automatica. Se non emerge nessun candidato con queste condizioni stringenti, dillo e passa direttamente allo Step 4 senza proporre nulla.

Ricorda inoltre all'utente, prima che scelga, che questa rimozione riguarda **solo il file dedicato a questo brand** (Step 4): lo Sheet condiviso `cluster_<vertical>_<lingua>`, usato come baseline da tutti i brand del vertical, resta invariato — non viene mai sovrascritto o modificato da questa skill. Rimuovere un Cluster/Sottocluster qui significa semplicemente che, per questo brand, quella riga non compare nel suo file di regole dedicato; altri brand che partono dalla stessa baseline non ne sono in alcun modo impattati.

## Step 3ter — Riorganizza sempre Cluster Order e Sottocluster Order

Come funzionano (vedi `materialize_cluster_rules_from_sheets`/`_parse_cluster_tab_compressed` in `scripts/cluster.py`): valore più basso = valutato prima, a parità di altre condizioni vince il primo match. `Cluster Order` è un ordine **globale allo Sheet**: i Cluster con un valore esplicito vengono *sempre* valutati prima di *tutti* quelli senza (l'ordine tra i cluster senza valore resta il fallback storico `PRIORITY_ORDER_BASE`/ordine di lettura). `Sottocluster Order` è la stessa logica ma **locale al singolo Cluster**, tra i suoi Sottocluster. Il Sottocluster di default (riga `Terms="(default)"`) non è mai soggetto a Order: è sempre la rete di sicurezza valutata per ultima, non serve mai valorizzarlo.

**Questo step va eseguito ad ogni run, non solo quando aggiungi un Cluster/Sottocluster nuovo con Terms sovrapposti.** Non limitarti a valorizzare l'Order della singola riga nuova che sembra in conflitto: prima di generare il CSV finale, ricalcola e riorganizza l'intera scala `Cluster Order` dello Sheet (e, per ciascun Cluster toccato, la scala `Sottocluster Order`), verificando sistematicamente i Terms di ogni Cluster/Sottocluster nuovo contro **tutti** i Cluster/Sottocluster esistenti — non solo quelli apparentemente affini per nome — perché un Cluster con un nome distante (es. "Intimo e Lingerie" vs "Abbigliamento") può comunque condividere Terms generici (es. "slip", "reggiseno") con un Cluster preesistente con Order più basso, intercettando la keyword prima che arrivi alla riga nuova.

**Conseguenza importante**: un valore esplicito scavalca sempre *tutti* i valori impliciti dello stesso scope (l'intero Sheet per `Cluster Order`, il singolo Cluster per `Sottocluster Order`). Quindi non introdurre mai un Order esplicito isolato su una riga nuova se questo rischia di farla passare davanti a righe impliciti che devono restare prima di lei: in quel caso valorizza esplicitamente anche quelle, con valori coerenti con la loro posizione/priorità attuale, non solo la riga nuova — altrimenti la aggiungi silenziosamente prima di cose che oggi vincono a ragione.

**Procedura di riorganizzazione (ad ogni run)**:
1. Elenca tutti i Cluster della baseline (con o senza Order esplicito) e tutti i nuovi Cluster proposti in questa run.
2. Per ogni coppia Cluster-nuovo/Cluster-esistente, calcola l'insieme dei Terms di ciascun Sottocluster e verifica le sovrapposizioni testuali (stesso termine o termine contenuto). Fai lo stesso, a un livello più fine, tra i Sottocluster **dentro** ogni singolo Cluster (nuovo o toccato da un'aggiunta).
3. Costruisci un ordine totale coerente: i Cluster/Sottocluster più specifici devono avere un Order più basso (= vincere) di quelli più generici con cui condividono Terms. Se non emerge nessuna sovrapposizione per un dato Cluster/Sottocluster, può comunque restare con Order esplicito coerente con la sua posizione logica (non è necessario lasciarlo implicito solo perché non ci sono conflitti).
4. **Riscrivi l'intera scala `Cluster Order` dello Sheet con incrementi larghi** (multipli di 10: 10, 20, 30…), anche quando la baseline aveva già valori tutti espliciti ma con incrementi stretti (es. 1,2,3…): l'obiettivo è avere sempre margine per inserire in futuro un Cluster intermedio senza dover rinumerare di nuovo tutto. Mantieni l'ordine *relativo* preesistente tra i Cluster che non hanno conflitti con le righe nuove; sposta solo quanto serve per far vincere le righe più specifiche.
5. Fai lo stesso a livello di `Sottocluster Order`, per ogni Cluster (esistente o nuovo) i cui Sottocluster abbiano Terms sovrapposti tra loro.
6. Segui comunque l'ordine di buon senso replicato da `PRIORITY_ORDER_BASE` (dal più prioritario al più generico) per i Cluster strutturali: `Brand Navigation, Outlet e Sconti, Punti Vendita, Profumeria, Calzature, Costumi e Beachwear, Squadre di Calcio, Abbigliamento, Accessori, Ispirazionale, Carriere e HR, Istituzionale` (Maglieria e Cashmere e Tessuti e Materie Prime non sono in questa lista fissa: senza Order esplicito finiscono in coda). Inserisci i Cluster nuovi rispetto a questa sequenza in base a dove si collocano per specificità (es. un Cluster nuovo con Terms che si sovrappongono ad "Abbigliamento" va inserito con Order minore di quello di "Abbigliamento").

**Correggi anche i valori di baseline se incoerenti** (segnalalo sempre all'utente con motivazione, stessa logica dello Step 3bis — è comunque una modifica rispetto ai valori della baseline di partenza, non un'azione silenziosa, anche se applicata solo al file dedicato di questo brand):
- due righe con lo stesso identico Order nello stesso scope (ambiguo, quasi sempre un refuso);
- un Cluster/Sottocluster più generico con un valore più basso (quindi più prioritario) di uno più specifico che dovrebbe vincere prima;
- celle con testo non numerico (`_parse_order_value` le ignora silenziosamente tornando al fallback — probabile typo).

Presenta le correzioni proposte insieme ai candidati alla rimozione dello Step 3bis, e chiedi conferma prima di includerle nel CSV finale. Dopo aver applicato la riorganizzazione, **verifica sempre a posteriori** (prima di consegnare il file) che non restino conflitti: per ogni Terms nuovo, controlla se lo stesso termine esatto compare in un altro Cluster/Sottocluster con Order più basso — se sì, la riorganizzazione non è completa, correggi prima di procedere allo Step 4.

## Step 4 — Genera il CSV completo, pronto da caricare

- Parti dalla **baseline** scaricata allo Step 0: tutte le sue righe restano, invariate, nel file di output, **tranne** quelle che l'utente ha scelto esplicitamente di rimuovere allo Step 3bis o di cui ha approvato una correzione di `Cluster Order`/`Sottocluster Order` allo Step 3ter (nessuna altra riga standard va persa o riscritta, a meno che non sia stata arricchita di nuovi Terms come da Step 3.2).
- Aggiungi in fondo le nuove righe brand-specifiche prodotte allo Step 3 (o inseriscile subito sotto le righe dello stesso Cluster esistente, se preferisci mantenere il file leggibile per Cluster contigui — l'ordine delle righe non cambia la logica di matching quando `Cluster Order`/`Sottocluster Order` sono espliciti, ma è comunque una buona pratica raggrupparle).
- Stesso header, stesso ordine colonne, stesso stile di quoting della baseline: `Cluster,Sottocluster,Cluster Order,Sottocluster Order,Terms,Richiede Anche,Note`.
- **Verifica il conteggio righe** prima di consegnare: `righe file output` = `righe baseline` + `righe nuove aggiunte` − `righe rimosse allo Step 3bis` (meno eventuali righe accorpate per lo Step 3.2). Se non torna, hai perso righe della baseline non volute: correggi prima di procedere.
- **Nome file**: `cluster_{nome_brand}_{lingua}.csv`, dove `{nome_brand}` è il nome del brand in minuscolo (es. `cluster_yamamay_it.csv`, `cluster_nomebrand_en.csv` per la lingua inglese). `{lingua}` è il codice lingua a due lettere usato nello Step 0 (`it`, `en`, …).
- **Output csv**: questo output è dedicato al brand, non va confuso con la baseline del vertical condiviso. Indica all'utente di crare una cartella dedicata al brand dentro `Clustering rules/<nome_brand>/` e di caricare lì il CSV, così che sia tracciabile e riutilizzabile in futuro. Non sovrascrivere mai la baseline condivisa `cluster_<vertical>_<lingua>`.
- Nel messaggio di consegna, indica esplicitamente all'utente: *"Questo è il file di regole dedicato al brand <nome_brand> (vertical <vertical>, lingua <lingua>): parte dalla baseline condivisa `cluster_<vertical>_<lingua>` (che resta invariata) e la estende con le righe brand-specifiche, applicando le eventuali rimozioni/correzioni che hai approvato solo a questa copia. Carica questo CSV nel foglio dedicato al brand (cartella `Clustering rules/<nome_brand>/`, Sheet `cluster_{nome_brand}_{lingua}`), poi ri-sincronizza con `--mode sync-rules` puntando a quel foglio nella prossima sessione di clustering per questo brand."* Riepiloga quali righe hai rimosso (se l'utente ne ha approvate) e come hai riorganizzato `Cluster Order`/`Sottocluster Order` (Step 3ter) così che sia tracciabile anche dopo l'upload. Segnala anche dove hai salvato/creato la copia dedicata al brand (cartella `Clustering rules/<nome_brand>/`, nome file `cluster_{nome_brand}_{lingua}.csv`), utile come archivio della run per confronti futuri.

## Note finali

- Non inventare mai contenuti delle linee guida o del menu che non sei riuscito a fetchare: se un `web_fetch` fallisce, dillo esplicitamente all'utente invece di procedere con supposizioni.
- Se il CSV di keyword in input ha una struttura diversa da "Keyword,Tema" (es. più colonne, formato export Semrush grezzo), chiedi conferma delle colonne rilevanti prima di procedere, oppure suggerisci di passare prima da `semrush-keyword-cleaner` se il file sembra un export non pulito.
- Mantieni la stessa lingua e lo stesso stile di scrittura dei `Terms` (minuscolo, niente accenti dove la baseline non li usa, plurali+singolari) per coerenza con le regole esistenti in quella lingua.
- Se le keyword del brand coprono più lingue (colonna `Country`/`Lang` con più valori), ripeti Step 0/3/4 una lingua alla volta: ogni lingua ha una baseline e un file di output distinti (`cluster_{nome_brand}_{lingua}.csv`, es. `cluster_yamamay_it.csv` e `cluster_yamamay_en.csv`), non mescolare righe di lingue diverse nello stesso CSV.
- Non toccare mai `_Attributi/<lingua>` in questa skill: se noti un attributo (Genere/Stagionalità/...) con un valore mai visto, segnalalo all'utente ma non produrre un CSV per quel tab — non è nello scope di questa skill.
- Non rimuovere mai un Cluster/Sottocluster di tua iniziativa: la rimozione (Step 3bis) è sempre e solo una proposta con motivazione, la decisione finale spetta all'utente riga per riga. Vale comunque solo per il file dedicato a questo brand: la baseline condivisa `cluster_<vertical>_<lingua>` non viene mai modificata da questa skill.
- Stesso principio per `Cluster Order`/`Sottocluster Order` (Step 3ter): la riorganizzazione dell'intera scala va fatta ad ogni run (non solo sulle righe nuove), ma qualsiasi correzione a un valore già presente in baseline è una proposta da confermare, mai una riscrittura silenziosa.
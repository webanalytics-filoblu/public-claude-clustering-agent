---
name: feedback-optional-columns
description: Aggiungi sempre tutte le colonne opzionali senza chiedere all'utente
metadata:
  type: feedback
---

Aggiungi sempre tutte le colonne opzionali (Stagionalità, Evento, Outfit, Recensioni, Materiale/Colore, Genere) senza chiedere conferma all'utente.

**Why:** L'utente non vuole essere interrotto da domande sulle colonne opzionali ad ogni esecuzione.

**How to apply:** In `cluster.py`, `optional_cols` è sempre `list(OPTIONAL_COLUMNS.values())`. La funzione `ask_optional_columns()` e gli argomenti CLI `--no-interactive`/`--optional-cols` sono stati rimossi.

---
name: feedback-genere-donna
description: donna/uomo/unisex definiscono solo la colonna Genere, non proporre mai come regola cluster
metadata:
  type: feedback
---

Termini come "donna", "uomo", "unisex" servono **solo** per classificare la colonna **Genere**. Non devono mai diventare regole autonome di `cluster` o `sotto_cluster`.

**Why:** L'utente ha corretto esplicitamente quando l'agente ha proposto `"donna" → cluster Abbigliamento / sotto Donna` come nuova regola.

**How to apply:** Quando `new_rules` nel JSON AI contiene termini di genere (donna, uomo, unisex, bambino, bambina, kids), scartarli silenziosamente — non proporli all'utente.

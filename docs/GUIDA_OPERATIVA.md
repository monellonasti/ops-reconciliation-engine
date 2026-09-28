# Guida operativa

*Per chi gestisce il processo: responsabili operations, HR operations, amministrazione del personale, controllo di gestione.*

Questa guida spiega come inserire l'Ops Reconciliation Engine in un ciclo di
lavoro ricorrente, come leggere ciò che produce e cosa si può regolare senza
toccare il codice. Non richiede competenze tecniche; dove serve l'intervento
dell'IT è indicato esplicitamente. La documentazione tecnica, in inglese, è
in [TECHNICAL.md](TECHNICAL.md).

## Indice

1. [A cosa serve e quando usarlo](#1-a-cosa-serve-e-quando-usarlo)
2. [Il ciclo di lavoro, passo per passo](#2-il-ciclo-di-lavoro-passo-per-passo)
3. [Come leggere il riepilogo e la coda](#3-come-leggere-il-riepilogo-e-la-coda)
4. [Catalogo delle segnalazioni](#4-catalogo-delle-segnalazioni)
5. [Decidere: accettare, correggere, riaprire](#5-decidere-accettare-correggere-riaprire)
6. [Modifiche attese: dire prima cosa è già approvato](#6-modifiche-attese-dire-prima-cosa-è-già-approvato)
7. [Regolare le soglie senza programmare](#7-regolare-le-soglie-senza-programmare)
8. [I file in ingresso](#8-i-file-in-ingresso)
9. [Dati, privacy e conservazione](#9-dati-privacy-e-conservazione)
10. [Esecuzione programmata e report](#10-esecuzione-programmata-e-report)
11. [Domande frequenti](#11-domande-frequenti)
12. [Glossario](#12-glossario)

---

## 1. A cosa serve e quando usarlo

Lo strumento confronta due versioni dello stesso elenco, quella del ciclo
precedente e quella del ciclo corrente, e produce un elenco di eccezioni da
guardare. Non sostituisce il gestionale che produce i file e non prende
decisioni: mette in fila ciò che merita attenzione, spiega perché, e registra
cosa avete deciso.

Casi d'uso tipici, con la versione dimostrativa che copre il primo:

| Processo | Ciclo precedente | Ciclo corrente | Cosa cerca |
|---|---|---|---|
| Chiusura mensile del personale | Export HR del mese scorso | Export HR di questo mese | Entrate e uscite, variazioni di retribuzione, cambi IBAN, dati mancanti |
| Anagrafica fornitori | Estrazione precedente | Estrazione corrente | Cambi di coordinate bancarie, duplicati, dati incompleti (richiede l'adattamento delle colonne, vedi sezione 11) |
| Controllo tra due sistemi | Export del sistema A | Export del sistema B | Record presenti in uno solo dei due, valori diversi per lo stesso record |

Il momento giusto per usarlo è **prima** che il file corrente venga usato per
qualcosa di irreversibile: un ciclo di pagamento, un invio al consulente, un
caricamento in un altro sistema.

## 2. Il ciclo di lavoro, passo per passo

Una sessione tipica dura il tempo di leggere la coda. La parte meccanica la fa
lo strumento.

1. **Preparare i due file.** Servono l'export del ciclo precedente e quello
   corrente, in CSV o Excel, con le stesse colonne (sezione 8). Se avete già
   l'elenco delle modifiche approvate nel periodo (aumenti, trasferimenti,
   uscite, assunzioni), preparate anche quello (sezione 6).
2. **Aprire lo strumento** nel browser (chi lo ha installato vi ha dato
   l'indirizzo, di solito `http://localhost:8501`) e caricare i file nei box
   "Ciclo precedente", "Ciclo corrente" e, se c'è, "Modifiche attese". Poi
   **Esegui riconciliazione**. Il pulsante **Carica dati demo** serve solo a
   fare pratica su dati inventati.
3. **Leggere il riepilogo** (sezione 3): sette numeri che dicono quanto
   lavoro c'è e di che tipo.
4. **Lavorare la coda** dall'alto: le segnalazioni critiche vengono prima.
   Per ognuna, la casella a sinistra apre il dettaglio con cosa è cambiato,
   perché è stato segnalato, quale regola è scattata e quali verifiche fare.
5. **Registrare la decisione** (sezione 5): accettata, da correggere o
   lasciata aperta, con una nota e il nome di chi ha deciso.
6. **Esportare** il report completo e la coda di revisione in CSV
   (**Scarica report completo**, **Scarica coda di revisione**) e archiviarli
   con il ciclo, se il vostro processo lo prevede.
7. **Correggere alla fonte** ciò che è risultato sbagliato nel gestionale e,
   se serve, rifare l'export e ripetere il controllo.

Il ciclo successivo riparte dal punto 1 con il file corrente di oggi come
"precedente". Le decisioni registrate al punto 5 vengono ritrovate
automaticamente (sezione 5).

## 3. Come leggere il riepilogo e la coda

### Il riepilogo

| Riquadro | Cosa conta |
|---|---|
| **Record elaborati** | Righe lette dal file corrente; il ciclo precedente è indicato accanto. |
| **Nuovi record** | Presenti oggi e non nel ciclo precedente. |
| **Record rimossi** | Presenti nel ciclo precedente e assenti oggi. |
| **Segnalazioni critiche** | Segnalazioni con severità critica, di qualsiasi tipo. |
| **Avvisi** | Segnalazioni con severità avviso. |
| **Variazioni rilevate** | Differenze di valore tra i due cicli (retribuzione, IBAN, contratto, orario, reparto, date). |
| **Record da revisionare** | Quanti record hanno almeno una segnalazione che richiede una decisione umana e non è ancora stata accettata. È il numero che dice quanto lavoro resta. |

Sotto il riepilogo compaiono le note: righe saltate perché malformate,
ID duplicati esclusi dal confronto, esito delle modifiche attese.

### La coda

Ogni riga è una segnalazione, non un record: un dipendente con tre problemi
occupa tre righe. Le colonne:

- **ID dipendente**: la chiave del record; "riga 205" quando l'ID manca.
- **Ciclo**: da quale file viene il dato (precedente, corrente, entrambi).
- **Categoria** e **Campo**: di cosa si tratta e quale colonna riguarda.
- **Precedente**, **Corrente**, **Variazione**: i valori a confronto e la
  percentuale, quando ha senso.
- **Severità**: informativa (🔵), avviso (🟠), critica (🔴).
- **Revisione richiesta**: se le regole chiedono una decisione umana.
- **Stato**: aperta, accettata, da correggere (sezione 5).
- **Attesa**: come la segnalazione si rapporta alle modifiche approvate
  (sezione 6).
- **Spiegazione**: una frase che descrive il fatto.

I filtri in alto restringono la coda per severità, categoria, revisione
richiesta, stato e ID. Per impostazione predefinita le segnalazioni già
accettate sono nascoste: sono lavoro fatto.

### Il dettaglio

Spuntando una riga si apre il pannello con quattro blocchi: **cosa è
cambiato**, **perché è stato segnalato** (con la soglia che è scattata),
**regola attivata** e **azione suggerita all'operatore**. Sotto, la **scheda
del record** mostra tutti i campi nei due cicli con l'indicazione di quali
sono cambiati; per un ID duplicato mostra tutte le righe candidate, perché
nessuna viene scelta al posto vostro.

## 4. Catalogo delle segnalazioni

Le severità indicate sono quelle predefinite; quasi tutte si possono cambiare
(sezione 7). "Revisione" indica se la segnalazione entra nella coda di
revisione con le impostazioni predefinite.

### Ciclo di vita del record

| Segnalazione | Significato | Severità | Revisione | Cosa verificare |
|---|---|---|---|---|
| Nuovo record | L'ID non esisteva nel ciclo precedente | Info | No | Che l'inserimento sia completo alla fonte; che non sia una persona già presente con un nuovo ID |
| Record rimosso | L'ID esisteva e oggi non c'è | Avviso | Sì | Che l'uscita sia stata gestita e registrata; che il record non sia sparito per un filtro dell'export |
| Data di inizio cambiata | `start_date` è diversa | Avviso | Sì | Il contratto firmato; se anche altri campi dovevano cambiare |
| Data di fine aggiunta | Compare una `end_date` | Avviso | Sì | La comunicazione di cessazione e la sua data |
| Data di fine cambiata | La `end_date` è diversa o è sparita | Avviso | Sì | Come sopra |

### Variazioni di valore

| Segnalazione | Significato | Severità | Revisione | Cosa verificare |
|---|---|---|---|---|
| Variazione retribuzione fino al 15% | Cambio di `monthly_salary` entro la tolleranza | Info | No | Nulla, salvo che sia inattesa |
| Variazione retribuzione oltre il 15% | Oltre la soglia di avviso | Avviso | Sì | Approvazione della modifica e chi l'ha data; decorrenza; permanente o una tantum |
| Variazione retribuzione oltre il 30% | Oltre la soglia critica | Critico | Sì | Come sopra, con priorità |
| Retribuzione da zero o da vuoto | Non si può calcolare una percentuale | Avviso o Info | Sì / No | Perché il valore precedente mancava |
| Cambio IBAN | Le coordinate bancarie sono diverse, aggiunte o rimosse | Critico, non modificabile | Sempre | Che la richiesta sia arrivata dal canale approvato e firmata; che l'intestatario sia il dipendente; se ci sono pagamenti in sospeso sul vecchio conto |
| Cambio tipo contratto | `contract_type` diverso | Avviso | Sì | La modifica contrattuale firmata; coerenza di ore e retribuzione |
| Cambio orario | `working_hours` diverse | Avviso | Sì | L'accordo sull'orario e la sua data; se la retribuzione è stata adeguata |
| Cambio reparto | `department` diverso | Info | No | Il trasferimento con il responsabile; centri di costo collegati |

Le percentuali si calcolano sul valore precedente e valgono in valore
assoluto: un -35% è critico come un +35%. Le soglie sono strette: 15,00% è
informativo, 15,01% è un avviso.

### Qualità dei dati (su un solo file)

| Segnalazione | Significato | Severità | Revisione | Cosa verificare |
|---|---|---|---|---|
| Campo obbligatorio vuoto | Manca uno dei campi richiesti | Critico | Sì | Recuperare il valore alla fonte; decidere se il record può passare senza |
| ID duplicato | Lo stesso `employee_id` compare più volte | Critico, non modificabile | Sempre | Quale riga è quella giusta; se l'export ha unito una tabella che produce più righe per persona |
| Email condivisa | Due persone diverse con la stessa email | Avviso | Sì | A chi appartiene davvero; che non sia la stessa persona inserita due volte |
| IBAN condiviso | Due persone diverse con lo stesso IBAN | Avviso | Sì | Come sopra, con attenzione: è un segnale classico di frode o di errore di inserimento |
| Numero non valido | Un campo numerico non è leggibile o è infinito | Critico | Sì | Correggere alla fonte; verificare il formato dei numeri (sezione 8) |
| Data non valida | Data inesistente (30/02) o in un formato non previsto | Critico | Sì | Correggere alla fonte; verificare il formato delle date |
| Retribuzione negativa | `monthly_salary` sotto zero | Critico | Sì | Correggere alla fonte |
| Fine prima dell'inizio | `end_date` precedente a `start_date` | Critico | Sì | Correggere alla fonte |
| Email malformata | L'indirizzo non ha la forma attesa | Avviso | Sì | Correggere alla fonte |
| Riga malformata | Una riga del file ha un numero di campi diverso dall'intestazione; è stata saltata | Critico | Sì | Aprire il file e correggere la riga; verificare che il ciclo di vita non risulti falsato da righe mancanti |

### Anomalie sul ciclo corrente

| Segnalazione | Significato | Severità | Revisione | Cosa verificare |
|---|---|---|---|---|
| Bonus oltre il 50% della retribuzione | Importo sproporzionato | Avviso | Sì | Approvazione del bonus; errori di unità (annuale inserito come mensile) |
| Bonus oltre il 100% della retribuzione | Come sopra, oltre la soglia critica | Critico | Sì | Come sopra, con priorità |
| Straordinari oltre 60 ore | Ore fuori dal plausibile | Avviso | Sì | Il cartellino o il sistema presenze; errori di digitazione |
| Straordinari oltre 100 ore | Come sopra, oltre la soglia critica | Critico | Sì | Come sopra |
| Straordinari negativi | Valore impossibile | Critico | Sì | Errore di segno o di inserimento |

### Modifiche attese

| Segnalazione | Significato | Severità | Revisione |
|---|---|---|---|
| Corrisponde a una modifica attesa | Il cambiamento era approvato e il valore coincide | Declassata a Info (l'IBAN resta critico) | No (IBAN: sì) |
| Diverso dal valore atteso | Il cambiamento era approvato ma con un altro importo o valore | Invariata | Sì |
| Approvazione non applicata | Una modifica approvata non risulta nel file corrente | Avviso | Sì |

## 5. Decidere: accettare, correggere, riaprire

Il motore rileva; decidere spetta a chi conosce il contesto. Nel pannello di
dettaglio, sotto la scheda del record, c'è il blocco **Decisione di
revisione** con tre stati:

- **Accettata**: la segnalazione è stata verificata e non richiede altro. Esce
  dalla coda e dal conteggio "Record da revisionare". Se al ciclo successivo
  la stessa segnalazione ricompare con gli stessi valori, resta accettata
  senza che nessuno debba riguardarla. Se il valore cambia (lo stipendio
  accettato a 3.000 diventa 3.200), torna aperta.
- **Da correggere**: il problema è noto e aspetta una correzione alla fonte.
  Resta in coda, etichettato, finché il file corrente non cambia.
- **Aperta**: nessuna decisione. Salvare "Aperta" cancella una decisione
  precedente.

La nota e il nome del revisore sono facoltativi ma consigliati: sono ciò che
un collega, o un revisore esterno, leggerà tra sei mesi. Non inserite nelle
note dati riservati; gli IBAN riconoscibili vengono comunque mascherati.

Ogni decisione e ogni annullamento vengono registrati con data e ora in un
archivio locale (sezione 9). Non esiste una "decisione automatica": lo
strumento non accetta nulla da solo.

## 6. Modifiche attese: dire prima cosa è già approvato

La maggior parte delle variazioni legittime è nota prima che arrivi l'export:
un aumento deliberato, un trasferimento, una dimissione, un'assunzione. Un
terzo file, facoltativo, le elenca perché non debbano essere reinvestigate.

Formato (CSV o Excel), una riga per modifica:

| Colonna | Contenuto | Esempio |
|---|---|---|
| `employee_id` | L'ID del record | `EMP-00077` |
| `field` | Il campo che deve cambiare | `monthly_salary` |
| `expected_value` | Il nuovo valore approvato | `2400` |
| `reference` (facoltativa) | Riferimento all'approvazione | `HR-2024-118 revisione annuale` |

I campi ammessi sono `monthly_salary`, `iban`, `contract_type`,
`working_hours`, `department`, `start_date`, `end_date`, più gli eventi
`new_record` e `removed_record` con `expected_value` vuoto.

Cosa succede in esecuzione:

- **Il valore applicato coincide** con quello approvato: la segnalazione
  scende a informativa e riporta il riferimento. Il fatto (importi,
  percentuale) resta visibile ed esportato. **Eccezione: un cambio IBAN
  approvato resta critico** e viene solo marcato, perché le coordinate
  bancarie si confermano sempre di persona.
- **Il valore applicato è diverso**: la segnalazione mantiene la sua severità
  e dice quale valore era atteso. Serve a scoprire un aumento inserito male.
- **La modifica non risulta**: nasce una segnalazione "approvazione non
  applicata". Serve a scoprire un aumento dimenticato.

Il file deve essere pulito: un campo non ammesso, una riga doppia o un ID
vuoto bloccano l'esecuzione con un messaggio che indica la riga. È voluto: il
file rappresenta approvazioni e una riga ignorata in silenzio sarebbe peggio
di uno stop.

## 7. Regolare le soglie senza programmare

Tutte le soglie stanno in un file di testo leggibile,
`rules/validation_rules.yaml` (versione italiana:
`rules/validation_rules.it.yaml`). Si modifica con un editor di testo; alla
prossima esecuzione l'interfaccia avvisa che le regole sono cambiate e chiede
di rieseguire.

Le voci che un responsabile può voler regolare:

| Voce | Predefinito | Effetto |
|---|---|---|
| `salary_change.warning_percentage` | 15 | Sopra questa percentuale una variazione di retribuzione è un avviso |
| `salary_change.critical_percentage` | 30 | Sopra questa è critica |
| `bonus.warning_salary_ratio` / `critical_salary_ratio` | 0.5 / 1.0 | Bonus oltre il 50% / 100% della retribuzione mensile |
| `overtime.warning_hours` / `critical_hours` | 60 / 100 | Ore di straordinario oltre cui segnalare |
| `required_fields` | ID, nome, cognome, tipo contratto, retribuzione | Campi che non possono essere vuoti |
| `review_policy` | info: no, avviso: sì, critico: sì | Quali severità entrano nella coda di revisione |
| `contract_changes` e `lifecycle` | vedi sezione 4 | Severità di cambi contratto, orario, reparto, ingressi, uscite, date |
| `expected_changes.missing_severity` | avviso | Severità di un'approvazione non applicata |
| `masked_fields` | iban | Colonne mai mostrate per intero; aggiungete `first_name` e `last_name` se i nomi non devono comparire |
| `language`, `formats` | inglese, formati internazionali | Lingua e convenzioni di numeri e date (sezione 8) |

Due cose **non** si possono abbassare, e il file viene rifiutato se si prova:
il cambio IBAN resta critico e sempre da revisionare, l'ID duplicato resta
critico e sempre da revisionare. Sono le due situazioni in cui un errore
costa di più.

Un errore di battitura nel file di regole viene segnalato all'avvio con il
nome della voce sbagliata, invece di essere ignorato.

## 8. I file in ingresso

**Formati accettati**: CSV (separatore virgola, punto e virgola o
tabulazione, riconosciuto da solo; codifica UTF-8 o Windows) ed Excel `.xlsx`
(primo foglio, intestazione nella riga 1).

**Colonne**: `employee_id`, `first_name`, `last_name`, `email`, `iban`,
`contract_type`, `department`, `working_hours`, `monthly_salary`, `bonus`,
`overtime_hours`, `start_date`, `end_date`. Le maiuscole e gli spazi
nell'intestazione non contano. Le colonne obbligatorie sono quelle in
`required_fields`; le altre possono mancare, e i controlli che le riguardano
vengono saltati con una nota. Colonne in più vengono ignorate.

**Numeri e date**: la convenzione va dichiarata una volta nel file di regole,
perché `2.100` vale duemilacento in un sistema e due virgola uno in un altro e
nessun programma può indovinarlo dal testo.

| Profilo | Numeri | Date |
|---|---|---|
| Predefinito | `2,100.50` | `2024-09-30` oppure `30/09/2024` |
| Italiano (`validation_rules.it.yaml`) | `2.100,50` | `30/09/2024` oppure `2024-09-30` |

Un numero scritto nell'altra convenzione viene segnalato come non valido,
non letto male. I file Excel non hanno questo problema: numeri e date
arrivano già come tali.

**Messaggi di errore all'apertura del file** e cosa significano:

| Messaggio | Causa | Rimedio |
|---|---|---|
| Il file è vuoto / ha l'intestazione ma nessuna riga di dati | Export vuoto o filtrato | Rifare l'export |
| Colonne obbligatorie mancanti | L'intestazione non ha uno dei campi richiesti | Verificare i nomi delle colonne |
| Nomi di colonna duplicati | Due colonne con lo stesso nome | Rinominarne una |
| La riga N ha X campi invece di Y | Una riga con separatori in più o in meno; viene saltata | Correggere la riga nel file |
| Impossibile interpretare il file come CSV | Virgolette non chiuse o file non CSV | Riesportare; salvare come CSV UTF-8 |
| Impossibile leggere il file Excel | File danneggiato o formato diverso da `.xlsx` | Salvare come `.xlsx` o CSV |
| File delle modifiche attese: riga N ... | Un problema nel terzo file, indicato per riga | Correggere la riga indicata |

## 9. Dati, privacy e conservazione

- **Dove girano i dati**: sul computer in cui lo strumento è installato.
  Nessun dato lascia la macchina; l'unica funzione che contatta un servizio
  esterno è la spiegazione generata da un modello linguistico, disattivata
  finché l'IT non configura esplicitamente una chiave, e attivata per singola
  segnalazione con un pulsante.
- **Cosa resta in memoria**: i due file e il risultato, per la durata della
  sessione nel browser. Chiudendo la sessione spariscono. "Azzera sessione"
  li elimina subito.
- **Cosa viene salvato su disco**: solo le decisioni di revisione, in un
  file locale (`history/review_history.sqlite`): ID del record, regola,
  campo, valori come mostrati (IBAN mascherato), stato, nota, revisore, data.
  Cancellare il file cancella tutte le decisioni; l'IT può disattivare del
  tutto il salvataggio.
- **Cosa non viene mai mostrato per intero**: l'IBAN, in tabella, nel
  dettaglio, negli export e nelle note. Altre colonne si possono aggiungere
  all'elenco dei campi mascherati. I nomi compaiono dove aiutano a
  identificare il record; se non è accettabile nel vostro contesto, vanno
  mascherati.
- **Export**: i due CSV scaricati contengono i valori come mostrati, quindi
  con l'IBAN mascherato, e lo stato di revisione. Trattateli come qualsiasi
  altro estratto del personale.
- **Conservazione**: lo strumento non conserva gli export. Se il processo
  richiede di archiviare i report per ciclo, l'archiviazione avviene nei
  vostri sistemi, secondo le vostre regole di conservazione.

## 10. Esecuzione programmata e report

Lo stesso motore gira senza interfaccia. L'IT può programmarlo, per esempio
la mattina del primo del mese sui file depositati in una cartella, in modo
che i due report CSV siano pronti prima che qualcuno apra lo strumento:

```bash
python -m src.engine precedente.csv corrente.csv --expected approvazioni.csv --rules rules/validation_rules.it.yaml --output-dir report/2026-10
```

Produce `reconciliation_report.csv` (tutte le segnalazioni) e
`review_required.csv` (solo quelle che richiedono una decisione e non sono
state accettate), più un riepilogo a video con gli stessi numeri
dell'interfaccia. Le decisioni registrate valgono anche qui.

## 11. Domande frequenti

**Una variazione legittima viene segnalata come critica. È un errore?**
No. Lo strumento non sa se un +42% è una promozione o un refuso: lo mette in
cima alla coda perché qualcuno lo guardi. Per non riguardarlo ogni mese si
accetta (sezione 5); per non vederlo nemmeno la prima volta si dichiara tra le
modifiche attese (sezione 6).

**Perché un cambio IBAN approvato resta critico?**
Perché la truffa più comune contro le aziende passa proprio da una richiesta
di cambio coordinate che sembra legittima. Il costo di una conferma in più è
basso; il costo di un bonifico sul conto sbagliato no.

**Ho due righe con lo stesso ID. Quale usa lo strumento?**
Nessuna. Il confronto per quell'ID viene sospeso, la segnalazione è critica e
la scheda del record mostra tutte le righe. Si corregge alla fonte e si
riesegue.

**Un dipendente cessato il mese scorso oggi non c'è più nel file. Perché è
un avviso?**
Perché lo strumento non distingue una cessazione gestita da un record perso
per un filtro dell'export. Se la cessazione era prevista, si dichiara come
`removed_record` tra le modifiche attese e la segnalazione scende a
informativa.

**Posso usarlo per fornitori o inventario?**
Il metodo è lo stesso, ma oggi i nomi delle colonne sono quelli
dell'esempio HR e sono scritti nel codice. Adattarli richiede un intervento
dell'IT, non una modifica alle regole. È il primo dei limiti noti.

**Cosa succede se cambio le soglie a metà mese?**
L'interfaccia rileva che le regole sono cambiate, scarta il risultato
precedente e chiede di rieseguire. Le decisioni già registrate restano
valide.

**Chi vede le decisioni?**
Chiunque usi lo strumento sulla stessa installazione. Non esistono utenti né
permessi: l'accesso è quello del computer, o della rete, su cui è installato.

## 12. Glossario

- **Ciclo**: una versione dell'export; "precedente" e "corrente" sono i due
  cicli confrontati.
- **Segnalazione**: un fatto rilevato su un record, con severità e regola.
- **Severità**: informativa, avviso, critico. Misura quanto il fatto merita
  attenzione, non se è un errore.
- **Revisione richiesta**: la segnalazione entra nella coda finché una
  persona non decide.
- **Coda di revisione**: l'elenco delle segnalazioni ancora da decidere.
- **Decisione**: accettata, da correggere o aperta; registrata con autore e
  data.
- **Modifica attesa**: un cambiamento approvato prima dell'export, dichiarato
  nel terzo file.
- **Regole**: il file di testo con soglie, campi obbligatori e severità.
- **Mascheramento**: la sostituzione della parte centrale di un valore
  sensibile con asterischi (`IT60X****3456`).

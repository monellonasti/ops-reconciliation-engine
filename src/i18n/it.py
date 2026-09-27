"""Testi in italiano. Le chiavi sono le stesse del catalogo inglese; i segnaposto usano str.format."""

MESSAGES: dict[str, str | tuple[str, ...]] = {
    # --- etichette ------------------------------------------------------------------
    "category.lifecycle": "Ciclo di vita",
    "category.duplicate": "Duplicato",
    "category.missing_data": "Dato mancante",
    "category.invalid_value": "Valore non valido",
    "category.salary_change": "Variazione retribuzione",
    "category.iban_change": "Cambio IBAN",
    "category.contract_change": "Variazione contrattuale",
    "category.bonus_anomaly": "Anomalia bonus",
    "category.overtime_anomaly": "Anomalia straordinari",
    "category.expected_change": "Modifica attesa",
    "severity.info": "Info",
    "severity.warning": "Avviso",
    "severity.critical": "Critico",
    "status.open": "Aperta",
    "status.accepted": "Accettata",
    "status.needs_action": "Da correggere",
    "record.row": "riga {line}",
    "record.unknown": "record sconosciuto",
    "value.empty": "vuoto",
    "dataset.previous": "precedente",
    "dataset.current": "corrente",
    "dataset.both": "entrambi",
    # --- caricamento file -----------------------------------------------------------
    "loader.empty": "Il file è vuoto.",
    "loader.nul": "Il file contiene caratteri NUL. Salvalo come CSV UTF-8 e riprova.",
    "loader.not_utf8": "Il file non era in UTF-8; decodificato come {encoding}.",
    "loader.not_found": "File non trovato: {name}",
    "loader.unreadable": "Impossibile leggere {name}: {error}",
    "loader.encoding": "Codifica del file non supportata. Salvalo come UTF-8 e riprova.",
    "loader.no_header": "Il file non ha la riga di intestazione.",
    "loader.parse_error": "Impossibile interpretare il file come CSV: {error}",
    "loader.parse_error_near": "Impossibile interpretare il file come CSV vicino alla riga {line}: {error}",
    "loader.no_rows": "Il file ha l'intestazione ma nessuna riga di dati.",
    "loader.reserved_header": "L'intestazione contiene la colonna riservata source_row; rinominala prima di caricare.",
    "loader.unnamed_columns": "L'intestazione ha colonne senza nome in posizione {positions}.",
    "loader.duplicate_columns": "Nomi di colonna duplicati: {names}.",
    "loader.malformed_row": "La riga {line} ha {found} campi invece di {expected}; la riga è stata saltata.",
    "loader.missing_required_columns": "Colonne obbligatorie mancanti: {missing}. Trovate: {found}.",
    "loader.optional_missing": "Colonne facoltative assenti, controlli collegati saltati: {columns}",
    "loader.extra_columns": "Colonne non usate da alcuna regola: {columns}",
    "loader.excel_sheet": "Cartella Excel: letto il primo foglio '{sheet}' ({count} fogli nel file).",
    "loader.excel_error": "Impossibile leggere il file Excel. Salvalo come .xlsx o CSV e riprova.",
    # --- validazioni ----------------------------------------------------------------
    "validators.invalid_number": "{column} ha un valore numerico non valido o non finito.",
    "validators.invalid_date": "{column} '{value}' non è una data valida (formati attesi: {formats}).",
    "validators.missing_key": (
        "Il campo obbligatorio employee_id è vuoto; il record non può essere abbinato tra i cicli."
    ),
    "validators.missing_field": "Il campo obbligatorio {column} è vuoto.",
    "validators.duplicate_key": "employee_id {key} compare {count} volte (righe {rows}).",
    "validators.duplicate_value": "{column} è condiviso con {others}.",
    "validators.negative_salary": "monthly_salary è negativa.",
    "validators.end_before_start": "end_date {end} è precedente a start_date {start}.",
    "validators.malformed_email": "email '{email}' non sembra un indirizzo valido.",
    # --- riconciliazione ------------------------------------------------------------
    "recon.new_record": "Nuovo record{name}: assente nel ciclo precedente.",
    "recon.removed_record": "Record rimosso{name}: presente solo nel ciclo precedente.",
    "recon.salary_set": "Retribuzione mensile impostata a {current}; nessun valore precedente da confrontare.",
    "recon.salary_from_zero": "Retribuzione mensile passata da 0 a {current}; percentuale non significativa.",
    "recon.salary_increased": "Retribuzione mensile aumentata del {pct}% (da {previous} a {current}).",
    "recon.salary_decreased": "Retribuzione mensile diminuita del {pct}% (da {previous} a {current}).",
    "recon.iban_added": "IBAN aggiunto ({current}); nessun IBAN nel ciclo precedente.",
    "recon.iban_removed": "IBAN rimosso (era {previous}).",
    "recon.iban_changed": "IBAN cambiato da {previous} a {current}.",
    "recon.field_changed": "{field} cambiato da {previous} a {current}.",
    "recon.end_date_added": "end_date aggiunta: {current}.",
    # --- anomalie -------------------------------------------------------------------
    "anomaly.bonus": "Il bonus {bonus} è il {ratio}% della retribuzione mensile {salary} (soglia {threshold}).",
    "anomaly.overtime_negative": "Le ore di straordinario sono negative ({hours}).",
    "anomaly.overtime_below": "Straordinario di {hours} ore sotto il minimo di {minimum} ore.",
    "anomaly.overtime_exceeds": "Straordinario di {hours} ore oltre la soglia di {limit} ore.",
    # --- modifiche attese -----------------------------------------------------------
    "expected.matches": "Corrisponde a una modifica attesa ({reference}).",
    "expected.iban_reviewed": "I cambi IBAN vengono sempre revisionati.",
    "expected.differs": "Diverso dal valore atteso {expected} ({reference}).",
    "expected.row_label": "riga {line} delle modifiche attese",
    "expected.missing.new_existed": (
        "Atteso {key} come nuovo record ({reference}) ma esisteva già nel ciclo precedente."
    ),
    "expected.missing.new_absent": (
        "Atteso {key} come nuovo record ({reference}) ma non è presente nel ciclo corrente."
    ),
    "expected.missing.removed_present": (
        "Attesa la rimozione di {key} ({reference}) ma è ancora presente nel ciclo corrente."
    ),
    "expected.missing.removed_absent": (
        "Attesa la rimozione di {key} ({reference}) ma non era presente nemmeno nel ciclo precedente."
    ),
    "expected.missing.head": "Atteso che {field} diventasse {expected} ({reference})",
    "expected.missing.neither": "{head} ma il record non è presente in nessuno dei due cicli.",
    "expected.missing.absent": "{head} ma il record è assente dal ciclo corrente.",
    "expected.missing.current": "{head} ma il valore corrente è {current}.",
    "expected.load.missing_columns": (
        "File delle modifiche attese: colonne mancanti {missing}. Obbligatorie: {required}; facoltativa: reference."
    ),
    "expected.load.bad_rows": "File delle modifiche attese: le righe {lines} hanno un numero errato di campi.",
    "expected.load.problems": "File delle modifiche attese: {problems}.",
    "expected.load.more": "; e altri {count}",
    "expected.load.empty_id": "riga {line}: employee_id vuoto",
    "expected.load.bad_field": "riga {line}: il campo '{field}' non è tra {allowed}",
    "expected.load.value_required": "riga {line}: expected_value è obbligatorio per {field}",
    "expected.load.value_forbidden": "riga {line}: expected_value deve essere vuoto per {field}",
    "expected.load.duplicate": "riga {line}: {key} / {field} compare più di una volta",
    # --- note del motore e riga di comando ------------------------------------------
    "note.rows_skipped": (
        "Alcune righe sono state saltate. Le segnalazioni sul ciclo di vita possono riflettere "
        "export incompleti; verifica i file di origine."
    ),
    "note.duplicates_excluded": (
        "Gli employee_id duplicati sono stati esclusi dal confronto tra i cicli; "
        "verifica alla fonte tutte le righe candidate."
    ),
    "note.expected": (
        "Modifiche attese: {listed} elencate, {matched} corrispondenti (declassate a info salvo IBAN), "
        "{mismatched} applicate con un valore diverso, {missing} non trovate."
    ),
    "cli.records": "Record elaborati: {current} (ciclo precedente: {previous})",
    "cli.counts": "Nuovi: {new}  Rimossi: {removed}  Variazioni: {changes}",
    "cli.severities": "Critici: {critical}  Avvisi: {warnings}  Info: {info}",
    "cli.review": "Record da revisionare: {count}",
    "cli.note": "Nota: {note}",
    "cli.decided": (
        "Segnalazioni con una decisione registrata: {decided} ({accepted} accettate, {needs_action} da correggere)"
    ),
    "cli.written": "Report scritti in {path}",
    "cli.error": "Errore: {error}",
    "cli.write_error": (
        "Errore: impossibile scrivere entrambi i report. Controlla la cartella di destinazione e i permessi; "
        "potrebbe esistere un report parziale."
    ),
    # --- spiegazioni ----------------------------------------------------------------
    "explain.text": (
        "Cosa è cambiato: {what}\nPerché è stato segnalato: {why}\nRegola attivata: {rule}\n"
        "Verifiche suggerite:\n{actions}"
    ),
    "explain.salary.why_no_pct": (
        "Il valore precedente era zero o mancante, quindi non si può calcolare una percentuale. "
        "Ogni variazione da una base vuota viene sottoposta a conferma umana."
    ),
    "explain.salary.why_critical": (
        "Una variazione del {pct}% supera la soglia critica configurata del {critical}%."
    ),
    "explain.salary.why_warning": (
        "Una variazione del {pct}% supera la soglia di avviso del {warning}% "
        "ma non quella critica del {critical}%."
    ),
    "explain.salary.why_info": (
        "Una variazione del {pct}% rientra nella tolleranza del {warning}%; elencata per completezza."
    ),
    "explain.salary.rule": "salary_change (avviso oltre {warning}%, critico oltre {critical}%)",
    "explain.salary.actions_info": ("Nessuna azione necessaria, salvo che la variazione sia inattesa per questo dipendente.",),
    "explain.salary.actions": (
        "Verificare se una modifica contrattuale è stata approvata e da chi.",
        "Verificare la data di decorrenza della variazione.",
        "Stabilire se la variazione è permanente o un conguaglio una tantum.",
    ),
    "explain.iban.why": (
        "Le coordinate bancarie sono un dato sensibile. Il motore tratta ogni cambio IBAN come {severity} "
        "e non decide mai da solo se sia legittimo."
    ),
    "explain.iban.rule": "iban_change (severità {severity}, richiede revisione: {review})",
    "explain.iban.actions": (
        "Confermare che la richiesta di modifica sia arrivata dal canale approvato e corrisponda a un'istruzione firmata.",
        "Verificare che l'intestatario del nuovo IBAN sia il dipendente.",
        "Controllare se l'IBAN precedente è stato usato nell'ultimo ciclo e se c'è un pagamento in sospeso.",
    ),
    "explain.new.why": "L'employee_id non esiste nel ciclo precedente.",
    "explain.new.rule": "lifecycle.new_record (severità {severity})",
    "explain.new.actions": (
        "Confermare che l'assunzione sia completa nel sistema di origine.",
        "Verificare che non si tratti di un dipendente già presente reinserito con un nuovo ID.",
    ),
    "explain.removed.why": "L'employee_id esiste nel ciclo precedente ma non nell'export corrente.",
    "explain.removed.rule": "lifecycle.removed_record (severità {severity})",
    "explain.removed.actions": (
        "Confermare che la cessazione sia stata gestita e che nel sistema di origine sia registrata una data di fine.",
        "Verificare che il record non sia stato escluso da un filtro dell'export anziché da una cessazione reale.",
    ),
    "explain.date.why": "Le date del rapporto di lavoro determinano requisiti e decorrenze; una variazione viene sottoposta a conferma.",
    "explain.date.rule": "lifecycle.{rule} (severità {severity})",
    "explain.date.actions": (
        "Confermare la nuova data rispetto al contratto firmato o alla comunicazione di cessazione.",
        "Verificare se anche i campi collegati (tipo contratto, ore, retribuzione) dovevano cambiare.",
    ),
    "explain.contract.why": "{field} è diverso tra i due cicli.",
    "explain.contract.rule": "contract_changes.{field} (severità {severity})",
    "explain.contract.actions.contract_type": (
        "Confermare che la modifica contrattuale sia stata firmata e la sua decorrenza.",
        "Verificare che ore e retribuzione siano coerenti con il nuovo tipo di contratto.",
    ),
    "explain.contract.actions.working_hours": (
        "Confermare che la variazione di orario sia stata concordata e da quale data.",
        "Verificare se la retribuzione è stata adeguata in proporzione.",
    ),
    "explain.contract.actions.department": (
        "Confermare il trasferimento con il responsabile del reparto di destinazione.",
        "Verificare centri di costo o approvazioni che dipendono dal reparto.",
    ),
    "explain.duplicate.key_why": (
        "La chiave del record deve essere univoca; due righe con lo stesso ID non possono essere abbinate in modo affidabile."
    ),
    "explain.duplicate.key_actions": (
        "Individuare la riga corretta e rimuovere o unire l'altra alla fonte.",
        "Verificare se l'export ha unito una tabella che produce più righe per dipendente.",
    ),
    "explain.duplicate.value_why": (
        "Due record diversi condividono lo stesso {field}: di solito indica un errore di inserimento o di export."
    ),
    "explain.duplicate.value_action": "Verificare a quale dipendente appartiene davvero il campo {field} e correggere l'altro record.",
    "explain.duplicate.value_action_2": "Confermare che i due record non siano la stessa persona inserita due volte.",
    "explain.duplicate.rule": "duplicates.{field} (severità {severity})",
    "explain.missing.why": "{field} è tra i required_fields; il record non può essere elaborato senza.",
    "explain.missing.rule": "required_fields / missing_data (severità {severity})",
    "explain.missing.actions": (
        "Recuperare il valore mancante dal sistema di origine e rifare l'export.",
        "Decidere se il record può essere elaborato in questo ciclo senza quel dato.",
    ),
    "explain.invalid.invalid_number": "Il valore non è leggibile come numero.",
    "explain.invalid.invalid_date": "Il valore non è una data reale nei formati attesi ({formats}).",
    "explain.invalid.negative_salary": "Una retribuzione mensile non può essere negativa.",
    "explain.invalid.end_before_start": "Un rapporto di lavoro non può terminare prima di iniziare.",
    "explain.invalid.malformed_email": "L'indirizzo email non rispetta il formato atteso.",
    "explain.invalid.malformed_row": (
        "La riga ha un numero di campi diverso dall'intestazione e non è stata letta."
    ),
    "explain.invalid.fallback": "Il valore non può essere corretto.",
    "explain.invalid.rule": "invalid_values.{rule} (severità {severity})",
    "explain.invalid.actions": (
        "Correggere il valore nel sistema di origine e rifare l'export.",
        "Verificare se lo stesso errore riguarda altre righe dell'export.",
    ),
    "explain.bonus.why": (
        "I bonus oltre il {warning} della retribuzione mensile sono avvisi, oltre il {critical} sono critici."
    ),
    "explain.bonus.rule": "bonus (rapporto di avviso {warning_ratio}, rapporto critico {critical_ratio})",
    "explain.bonus.actions": (
        "Confermare che l'importo del bonus sia stato approvato per questo ciclo.",
        "Verificare errori di unità, per esempio un importo annuale inserito come mensile.",
    ),
    "explain.overtime.why_below": "Lo straordinario è sotto il minimo configurato di {minimum} ore.",
    "explain.overtime.why_above": (
        "Lo straordinario oltre {warning} ore è un avviso, oltre {critical} ore è critico."
    ),
    "explain.overtime.rule": (
        "overtime (minimo {minimum}, avviso oltre {warning}, critico oltre {critical})"
    ),
    "explain.overtime.actions": (
        "Verificare le ore con il cartellino o il sistema di rilevazione presenze.",
        "Verificare errori di inserimento come un segno sbagliato o una cifra fuori posto.",
    ),
    "explain.generic.why": "La regola {rule} è scattata con severità {severity}.",
    "explain.generic.actions": ("Verificare il record rispetto al sistema di origine.",),
    "explain.expected_missing.why": (
        "Il file delle modifiche attese elenca per questo record una modifica approvata che non risulta "
        "nel ciclo corrente."
    ),
    "explain.expected_missing.rule": "expected_changes.missing (severità {severity})",
    "explain.expected_missing.actions": (
        "Verificare se la modifica è stata applicata nel sistema di origine dopo l'estrazione dell'export.",
        "Verificare se l'approvazione è stata ritirata o rinviata; aggiornare il file delle modifiche attese.",
    ),
    "explain.expectation.iban_why": (
        "{why} Questa modifica è elencata tra quelle attese ({reference}); i cambi IBAN vengono comunque confermati da una persona."
    ),
    "explain.expectation.iban_actions": (
        "Confermare che il riferimento dell'approvazione sia autentico e riguardi questo dipendente.",
        "Verificare il nuovo intestatario prima del prossimo ciclo di pagamento.",
    ),
    "explain.expectation.matched_why": (
        "Elencata tra le modifiche attese ({reference}) e il valore applicato corrisponde, "
        "quindi la severità è stata abbassata a info. Senza l'aspettativa: {why}"
    ),
    "explain.expectation.matched_actions": ("Nessuna azione necessaria, salvo che sia errato il documento di approvazione.",),
    "explain.expectation.mismatch_why": (
        "{why} Per questo campo era attesa una modifica, ma verso {expected}, non verso il valore applicato."
    ),
    "explain.expectation.mismatch_action": (
        "Confrontare il valore applicato con il documento di approvazione e stabilire quale dei due è errato."
    ),
    # --- AI facoltativa -------------------------------------------------------------
    "ai.unavailable_setup": "Spiegazione AI non disponibile: imposta ANTHROPIC_API_KEY e installa il pacchetto anthropic.",
    "ai.unavailable_key": "Spiegazione AI non disponibile: la chiave API è stata rifiutata.",
    "ai.unavailable_rate": "Spiegazione AI non disponibile: limite di richieste raggiunto, riprova tra poco.",
    "ai.unavailable_status": "Spiegazione AI non disponibile: l'API ha risposto con stato {status}.",
    "ai.unavailable_network": "Spiegazione AI non disponibile: impossibile raggiungere l'API.",
    "ai.unavailable_failed": "Spiegazione AI non disponibile: richiesta fallita; vale la spiegazione da modello.",
    "ai.unavailable_refusal": "Spiegazione AI non disponibile per questa segnalazione; vale la spiegazione da modello.",
    "ai.unavailable_empty": "Spiegazione AI non disponibile: il modello non ha restituito testo.",
    "ai.language_instruction": "Write in Italian.",
    # --- interfaccia ----------------------------------------------------------------
    "ui.subtitle": "Automatizza i controlli deterministici. Fai emergere le eccezioni. Lascia le decisioni alle persone.",
    "ui.rules_error": "Impossibile caricare il file delle regole: {error}",
    "ui.rules_changed": "Le regole sono cambiate. Esegui di nuovo la riconciliazione per applicarle.",
    "ui.start_hint": "Carica gli export del ciclo precedente e di quello corrente, oppure carica i dati demo, per iniziare.",
    "ui.demo_notice": "Dati demo sintetici. Non rappresentano persone o conti bancari reali.",
    "ui.comparing": "**Confronto tra** `{previous}` (precedente) **e** `{current}` (corrente)",
    "ui.expected_entries": "Modifiche attese: {count} voci da `{name}`.",
    "ui.note": "Nota: {note}",
    "ui.sidebar.rules": "Regole in vigore",
    "ui.sidebar.loaded_from": "Caricate da `{path}`",
    "ui.sidebar.language": "Lingua",
    "ui.sidebar.rule": "Regola",
    "ui.sidebar.value": "Valore",
    "ui.sidebar.salary_warning": "Retribuzione: avviso oltre",
    "ui.sidebar.salary_critical": "Retribuzione: critico oltre",
    "ui.sidebar.bonus_warning": "Bonus: avviso oltre",
    "ui.sidebar.bonus_critical": "Bonus: critico oltre",
    "ui.sidebar.of_salary": "{value} della retribuzione",
    "ui.sidebar.overtime_warning": "Straordinari: avviso oltre",
    "ui.sidebar.overtime_critical": "Straordinari: critico oltre",
    "ui.sidebar.iban_change": "Cambio IBAN",
    "ui.sidebar.duplicate_id": "employee_id duplicato",
    "ui.sidebar.required_fields": "Campi obbligatori: {fields}",
    "ui.sidebar.masked_fields": "Mascherati nell'interfaccia e negli export: {fields}",
    "ui.sidebar.formats": "Formati in ingresso: date {dates}; separatore decimale '{decimal}'; separatore delle migliaia '{thousands}'.",
    "ui.sidebar.history": "Storico delle revisioni",
    "ui.sidebar.history_disabled": "Disattivato nel file delle regole. Le decisioni non vengono conservate tra le esecuzioni.",
    "ui.sidebar.history_enabled": (
        "Le decisioni sono salvate in `{path}` ({count} registrate). Una segnalazione conserva la sua decisione "
        "quando ricompare in un ciclo successivo con gli stessi valori."
    ),
    "ui.sidebar.privacy": "Privacy",
    "ui.sidebar.privacy_text": (
        "I file sono elaborati in memoria solo per questa sessione. Su disco non viene salvato nulla, "
        "tranne le decisioni di revisione che registri, e nessun servizio esterno viene contattato "
        "se non richiedi esplicitamente una spiegazione AI."
    ),
    "ui.sidebar.reset": "Azzera sessione",
    "ui.inputs.title": "1. Scegli i due cicli",
    "ui.inputs.previous": "Ciclo precedente (CSV o Excel)",
    "ui.inputs.current": "Ciclo corrente (CSV o Excel)",
    "ui.inputs.expected": "Modifiche attese (facoltativo, CSV o Excel)",
    "ui.inputs.expected_help": (
        "Colonne: employee_id, field, expected_value, reference (facoltativa). field è uno tra {fields}. "
        "Una modifica che corrisponde a una voce viene declassata a info (eccetto i cambi IBAN); "
        "una voce che non si è verificata diventa una segnalazione."
    ),
    "ui.inputs.run": "Esegui riconciliazione",
    "ui.inputs.demo": "Carica dati demo",
    "ui.error.previous": "Ciclo precedente ({name}): {error}",
    "ui.error.current": "Ciclo corrente ({name}): {error}",
    "ui.error.expected": "Modifiche attese ({name}): {error}",
    "ui.error.unexpected": (
        "Si è verificato un errore durante la riconciliazione. Controlla che entrambi i file siano export "
        "validi con le colonne previste e riprova."
    ),
    "ui.summary.title": "2. Riepilogo",
    "ui.summary.records": "Record elaborati",
    "ui.summary.records_help": "{count} nel ciclo precedente",
    "ui.summary.new": "Nuovi record",
    "ui.summary.removed": "Record rimossi",
    "ui.summary.critical": "Segnalazioni critiche",
    "ui.summary.warnings": "Avvisi",
    "ui.summary.changes": "Variazioni rilevate",
    "ui.summary.review": "Record da revisionare",
    "ui.summary.decided": (
        "{decided} segnalazioni hanno già una decisione da un'esecuzione precedente: "
        "{accepted} accettate (escluse dal conteggio da revisionare) e {needs_action} da correggere."
    ),
    "ui.queue.title": "3. Coda di revisione",
    "ui.queue.severity": "Severità",
    "ui.queue.category": "Categoria",
    "ui.queue.review_required": "Revisione richiesta",
    "ui.queue.review_all": "Tutte le segnalazioni",
    "ui.queue.review_yes": "Revisione richiesta",
    "ui.queue.review_no": "Nessuna revisione",
    "ui.queue.status": "Stato revisione",
    "ui.queue.search": "ID dipendente contiene",
    "ui.queue.shown": "{shown} di {total} segnalazioni mostrate. Spunta la casella a sinistra di una riga per vederne i dettagli.",
    "ui.queue.none": "Nessuna segnalazione dai controlli configurati.",
    "ui.queue.no_match": "Nessuna segnalazione corrisponde ai filtri.",
    "ui.column.employee": "ID dipendente",
    "ui.column.cycle": "Ciclo",
    "ui.column.source_row": "Riga origine",
    "ui.column.category": "Categoria",
    "ui.column.field": "Campo",
    "ui.column.previous": "Precedente",
    "ui.column.current": "Corrente",
    "ui.column.change": "Variazione",
    "ui.column.severity": "Severità",
    "ui.column.review_required": "Revisione richiesta",
    "ui.column.status": "Stato",
    "ui.column.expected": "Attesa",
    "ui.column.explanation": "Spiegazione",
    "ui.column.changed": "Cambiato",
    "ui.yes": "Sì",
    "ui.no": "No",
    "ui.expected.matches": "corrisponde: {reference}",
    "ui.expected.not_applied": "non applicata",
    "ui.expected.differs": "diverso, atteso {expected}",
    "ui.detail.title": "4. Dettaglio segnalazione",
    "ui.detail.hint": "Spunta una riga nella coda di revisione per vedere cosa è cambiato, perché è stato segnalato e cosa verificare.",
    "ui.detail.header": "**{record}** · {category} · {severity} · Revisione richiesta: **{review}**",
    "ui.detail.what": "**Cosa è cambiato**",
    "ui.detail.why": "**Perché è stato segnalato**",
    "ui.detail.rule": "**Regola attivata**",
    "ui.detail.actions": "**Azione suggerita all'operatore**",
    "ui.detail.disclaimer": (
        "Il motore rileva; non decide. Conferma la variazione con la fonte autorevole prima di agire."
    ),
    "ui.detail.snapshot": "Scheda del record (entrambi i cicli)",
    "ui.detail.not_compared": "non confrontato",
    "ui.detail.changed_yes": "sì",
    "ui.decision.title": "**Decisione di revisione**",
    "ui.decision.disabled": "Lo storico delle revisioni è disattivato nel file delle regole, quindi le decisioni non vengono salvate.",
    "ui.decision.current": "Decisione attuale: {status}{who} il {when}.{note}",
    "ui.decision.by": " di {reviewer}",
    "ui.decision.note_suffix": " Nota: {note}",
    "ui.decision.status": "Stato",
    "ui.decision.note": "Nota (facoltativa)",
    "ui.decision.reviewer": "Revisore (facoltativo)",
    "ui.decision.save": "Salva decisione",
    "ui.decision.help": (
        "Accettata: verificata, esce dalla coda e resta accettata se la stessa segnalazione ricompare "
        "con gli stessi valori. Da correggere: problema noto, resta in coda finché non viene corretto. "
        "Aperta: nessuna decisione."
    ),
    "ui.ai.title": "**Facoltativo: spiega con l'AI**",
    "ui.ai.not_configured": (
        "Non configurato. Imposta `ANTHROPIC_API_KEY` e installa il pacchetto `anthropic` per ottenere "
        "una riformulazione in linguaggio naturale di questa segnalazione. L'applicazione non ne ha bisogno."
    ),
    "ui.ai.button": "Spiega questa segnalazione",
    "ui.ai.spinner": "Chiedo al modello di riformulare la segnalazione...",
    "ui.ai.disclaimer": (
        "Testo generato. Riformula la segnalazione deterministica e non giudica se la variazione sia corretta."
    ),
    "ui.export.title": "5. Esporta",
    "ui.export.full": "Scarica report completo",
    "ui.export.queue": "Scarica coda di revisione",
    "ui.export.caption": (
        "Report completo: {total} segnalazioni con il loro stato di revisione. "
        "Coda di revisione: {queue} segnalazioni che richiedono una decisione umana e non ancora accettate."
    ),
}

# Guida completa: account secondario e installazione di Deepal Alternative

Guida passo passo per collegare la tua auto Changan/Deepal a Home Assistant con l'integrazione
**Deepal Alternative**. Copre l'intero processo: dalla creazione dell'account secondario nell'app My
Changan all'installazione dell'integrazione con HACS e alla sua configurazione.

## Indice

1. [Perché usare un account secondario](#perché-usare-un-account-secondario)
2. [Requisiti preliminari](#requisiti-preliminari)
3. [Parte 1: account secondario in My Changan](#parte-1-account-secondario-in-my-changan)
4. [Parte 2: installazione dell'integrazione](#parte-2-installazione-dellintegrazione)
5. [Note e risoluzione dei problemi](#note-e-risoluzione-dei-problemi)

## Perché usare un account secondario

L'integrazione accede alla piattaforma ufficiale My Changan. Un singolo account non può mantenere
due sessioni attive contemporaneamente: se Home Assistant accede con il tuo account principale,
l'app del telefono può essere disconnessa e, se accedi di nuovo all'app, la sessione di Home
Assistant viene invalidata.

La soluzione consigliata è creare un **account secondario**, condividere l'auto dall'account
principale e usare in Home Assistant solo quello secondario. Così il tuo account principale continua
a funzionare normalmente sul telefono.

## Requisiti preliminari

- Un veicolo Deepal compatibile (S05, S07) collegato a un account My Changan.
- Accesso all'app **My Changan** con l'account principale.
- Un'email o un numero di telefono diverso per l'account secondario.
- Home Assistant 2026.3.0 o successivo.
- [HACS](https://hacs.xyz/docs/use/download/download/) installato. Se non ce l'hai ancora, segui le
  istruzioni ufficiali di installazione su <https://hacs.xyz/docs/use/download/download/>.

## Parte 1: account secondario in My Changan

### 1. Creare l'account secondario

1. Apri l'app **My Changan** e crea un nuovo account con un'email o un numero di telefono diverso da
   quello del tuo account principale.
2. Annota le credenziali (email/telefono e codice di accesso): saranno quelle che userai in Home
   Assistant.

### 2. Condividere il veicolo dall'account principale

1. Esci dall'account secondario e accedi all'app con l'**account principale**.
2. Tocca il pulsante **condividi** nella schermata principale.
3. Invita l'account secondario appena creato, indicando un periodo di validità permanente.

### 3. Accettare l'accesso e creare la password di controllo

1. Esci dall'**account principale** nell'app e accedi con l'**account secondario**.
2. Accetta l'accesso all'auto condivisa.
3. Vai al **centro personale** (profilo) e tocca **La mia auto**.
4. Seleziona l'auto condivisa.
5. Tocca **Password di controllo del veicolo** e crea una password (PIN). Annotala: è il PIN che
   Home Assistant richiederà per i comandi di portiere, finestrini e bagagliaio.

> Se non trovi questa opzione nella tua versione dell'app, prova ad abbassare i finestrini dall'app:
> ti chiederà di creare il PIN di controllo. Crealo e verifica che il comando funzioni.

### 4. Tornare all'account principale

1. Esci dall'account secondario e accedi di nuovo con l'**account principale** sul telefono.
2. L'account principale resta il proprietario del veicolo; quello secondario si usa solo in Home
   Assistant.

## Parte 2: installazione dell'integrazione

### 5. Installare HACS (se non ce l'hai ancora)

HACS è il gestore delle integrazioni personalizzate di Home Assistant. Se non l'hai ancora
installato, segui la guida ufficiale: <https://hacs.xyz/docs/use/download/download/>. Una volta
installato, appare la scheda **HACS** nella barra laterale di Home Assistant.

### 6. Aggiungere il repository a HACS

1. In Home Assistant, apri la scheda **HACS**.
2. Apri il menu a tre punti (⋮) in alto a destra e scegli **Repository personalizzati**.
3. Incolla l'URL del repository:
   `https://github.com/Sunek0/ha-deepal-alternative`
4. In **Categoria**, seleziona **Integrazione** e premi **Aggiungi**.

### 7. Installare Deepal Alternative e riavviare

1. In HACS, cerca **Deepal Alternative** (puoi usare la ricerca della scheda o la categoria
   **Integrazioni**).
2. Apri la scheda e premi **Scarica**.
3. **Riavvia Home Assistant** per caricare la nuova integrazione.

### 8. Aggiungere l'integrazione

1. Vai in **Impostazioni → Dispositivi e servizi**.
2. Premi **Aggiungi integrazione** e cerca **Deepal Alternative**.
3. In **Piattaforma**, scegli **International (Europe)** (l'opzione SDA (China) è solo per account
   della Cina continentale con access token).
4. In **Metodo di accesso**, scegli come accede il tuo account secondario:
   - **Email code**: viene inviato un codice di verifica all'email.
   - **Phone/SMS code**: viene inviato un codice di verifica via SMS al cellulare.
5. Compila i campi del modulo:
   - **Paese di vendita**: il paese registrato nel tuo account My Changan (per esempio, Spagna).
   - **Email** o **Numero di cellulare** (senza prefisso) dell'account **secondario**.
6. Attendi il codice di verifica (email o SMS) e inseriscilo in **Codice di verifica**.
7. L'integrazione convalida l'account e crea un dispositivo per veicolo. Fatto.

### 9. Salvare il PIN di controllo remoto

Questo passaggio è **necessario solo** per usare i comandi firmati (blocco portiere, finestrini e
bagagliaio) e perché Home Assistant crei le relative entità:

1. Vai in **Impostazioni → Dispositivi e servizi → Deepal Alternative**.
2. Premi **Configura**.
3. In **PIN di controllo remoto**, inserisci la password creata al passaggio 3 con l'account
   secondario.
4. Salva. Le entità di portiere, finestrini e bagagliaio appaiono sul dispositivo dell'auto.

### 10. Verificare che funzioni

- Apri la pagina del dispositivo del veicolo: dovresti vedere i sensori di batteria, autonomia,
  ricarica e le altre telemetrie.
- Prova un comando sicuro (per esempio, accendere le luci o il clima) e conferma che l'auto
  risponda.
- I comandi che dipendono dal PIN (portiere, finestrini, bagagliaio) sono firmati con il PIN creato
  con l'account secondario; se falliscono, ricontrolla il passaggio 9.

## Note e risoluzione dei problemi

- **Non riesco a controllare nulla**: controlla prima se l'app ufficiale riesce a farlo con lo stesso
  account. A volte l'auto rifiuta i comandi remoti finché non è stata guidata per qualche minuto.
- **"Remote control PIN is not set" anche se ho già salvato il PIN**: il PIN non è stato creato con
  l'account usato da Home Assistant. Accedi all'app con l'account secondario, crea il PIN
  (passaggio 3) e salvalo di nuovo nelle opzioni dell'integrazione.
- **Home Assistant chiede di riautenticarsi**: la sessione è stata invalidata dall'app o da un altro
  dispositivo. Accedi di nuovo; con l'account secondario è molto meno frequente.
- **I valori sembrano vecchi**: l'auto comunica la telemetria solo quando è sveglia; l'integrazione
  mostra l'ultima lettura nota finché non torna a comunicare.
- **Avviso**: progetto non ufficiale, senza alcun rapporto con Changan Automobile. I comandi remoti
  agiscono sull'auto reale: assicurati che sia sicuro prima di usare serrature, finestrini,
  bagagliaio, clima, luci o clacson.

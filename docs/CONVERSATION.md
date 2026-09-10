# Conversation recap

Sintesi fedele del filo di design (non un dump grezzo). Date intorno a settembre 2026.

## 1. Idea iniziale

Partenza: agente vocale locale che scrive codice, con pet e chat UI. Poi curiosità su come è fatto ChatGPT Codex + voice / “Astra”: sistema a layer (voce full-duplex, modello frontier, harness coding), non un singolo modello.

Conclusione precoce: eguagliare Astra in locale è irrealistico; ha senso una build open utile.

## 2. Hardware e proposte

Target: **Bosgame M5**. Stack proposte: Ollama, Open WebUI, OpenHands, Odysseus, confronti OpenCode / OpenHands / **oh-my-pi (omp)**.

Chiarimento: **omp c’è già**. L’obiettivo vero non è un coding agent da terminale, ma un **assistente che controlla il PC e fa vedere cosa fa**.

## 3. Semplificazione

Taglio verso: cervello (Qwen) + esecutore OS + voce. Licenze / rivendita: Apache/MIT ok con notice; niente marchi altrui.

Runtime reale dell’operatore: **llama.cpp** + GGUF **HauhauCS Qwen3.8-27B Uncensored Aggressive MTP** (non Ollama come primario).

## 4. Critica e buchi

Punti deboli onesti: controllo PC sotto Astra; log terminale ≠ overlay; latenza voce; percentuali “% di Astra” inventate.

Correzioni: overlay, accessibilità, policy stretta, text-first.

## 5. Design lock

- Prodotto = **conduttore**, non pet e non clone Astra.
- Loop: classify → un passo → announce → act → observe → reply.
- Contratti in questo repo: `turn-cycle`, `gui-loop`, `overlay`, `policy`, `adapters`.
- Linux Wayland + AT-SPI; visione fallback; WSL solo per llama.cpp (brain), non per mouse/overlay.
- Policy fuori dal modello; Uncensored = più rischio OS, non più bravura.
- omp = tool codice; GUI = adapter host.
- Voce dopo che il ciclo testo funziona.

## 6. Verdetto

Sì, si costruisce qualcosa di reale e locale. No, non “Astra in open source”. La strada è il contratto host + un modello + omp, text-first.

Vedi anche [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) e [notes.md](notes.md).

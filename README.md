# CLAUDE_MANAGED_AGENTS

Ein erster [Claude Managed Agent](https://platform.claude.com/docs/en/managed-agents/overview) als Code: ein **Rechercheagent**, der eine Frage in Teilfragen zerlegt, im Web nach guten Quellen sucht und einen Bericht mit Quellenangaben schreibt.

Bei Managed Agents betreibt Anthropic die Agentenschleife und die Sandbox, in der die Tools des Agenten laufen. Du definierst nur den Agenten und startest Sessions. Das Produkt ist in der Beta. Abgerechnet werden Tokens plus die Laufzeit der Session, und die Session-Historie bleibt gespeichert, bis du sie löschst.

## Aufbau

| Datei | Zweck |
|---|---|
| `agents/deep-researcher/agent.md` | Der Agent: Modell, Tools und System-Prompt. Wird einmal mit `ant apply` angelegt. |
| `agents/deep-researcher/environment.yaml` | Die Cloud-Sandbox mit den Websites, die der Agent lesen darf. |
| `claude-lock.json` | Schreibt `ant apply` beim ersten Lauf. Enthält die IDs. **Bitte committen.** |
| `research.py` | Startet pro Frage eine Session, zeigt live an, was der Agent tut, und lädt den Bericht herunter. |
| `tests/` | Offline-Tests, die keinen API-Schlüssel brauchen. |

Agent und Environment werden **einmal** angelegt. Jeder Aufruf von `research.py` erzeugt nur eine neue Session, die auf dieselbe Agent-ID verweist.

## Einrichtung

1. **Python-Abhängigkeiten** (Python 3.10 oder neuer):

   ```sh
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Anthropic CLI `ant`** installieren (Version 1.30 oder neuer):

   ```sh
   brew install anthropics/tap/ant        # macOS
   # Linux/Windows: https://github.com/anthropics/anthropic-cli/releases
   ```

3. **Anmelden**, entweder mit `ant auth login` (öffnet den Browser, kein Schlüssel nötig) oder mit einem API-Schlüssel aus der [Console](https://platform.claude.com/settings/keys):

   ```sh
   export ANTHROPIC_API_KEY=sk-ant-...
   ```

4. **Agent und Environment anlegen.** Führe den Befehl im Repo-Ordner aus. `ant apply` zeigt erst den Plan und fragt dann nach:

   ```sh
   ant apply agents/deep-researcher/agent.md agents/deep-researcher/environment.yaml
   ```

   Danach `claude-lock.json` committen, damit spätere Läufe denselben Agenten aktualisieren, statt einen neuen anzulegen.

## Benutzen

```sh
python research.py "Welche Vor- und Nachteile haben Wärmepumpen in Altbauten?"
```

Das Skript gibt einen Link zur Console aus, unter dem du die Session live verfolgen kannst. Der Agent bekommt die Frage als **Outcome**: Ein separater Bewerter prüft den Bericht gegen eine Checkliste (`RUBRIC` in `research.py`), und der Agent bessert nach, bis alle Punkte erfüllt sind oder `--max-iterations` erreicht ist (Standard 3). Der fertige Bericht landet in `outputs/<session-id>/report.md`.

Falls ein Tool-Aufruf eine Freigabe braucht, fragt das Skript im Terminal nach. Ohne Terminal, etwa in einem Cronjob, lehnt es solche Aufrufe ab.

## Anpassen

- **Websites, die der Agent lesen darf:** Die Sandbox nutzt `limited` Networking. Damit liefern `web_search` und `web_fetch` nur Seiten von den Hosts unter `allowed_hosts` in `environment.yaml`. Die Liste ist nur ein Startpunkt, also trag die Quellen ein, die zu deinen Fragen passen. Statt der Liste geht auch `networking: {type: unrestricted}`. Dann darf der Agent jede Seite lesen, aber auch die ganze Sandbox hat vollen Internetzugang. Gib einer solchen Session deshalb keine Geheimnisse oder sensiblen Dateien mit.
- **Verhalten des Agenten:** System-Prompt oder Modell in `agent.md` ändern und `ant apply` erneut ausführen. Das erzeugt eine neue Version desselben Agenten.
- **Qualitätsmaßstab:** `RUBRIC` in `research.py` anpassen. Jede Zeile wird einzeln bewertet, also möglichst konkret formulieren.
- **Anderer Agent:** Die Rechercheaufgabe ist ein Platzhalter. Für eine andere Aufgabe den System-Prompt in `agent.md`, die Tools und die Rubrik austauschen.

## Tests

```sh
pip install -r requirements-dev.txt
pytest
```

# AI_BRIEF.md
*Kort lägesbild för AI-samarbete (ChatGPT + Codex). Håll denna fil uppdaterad. Max ~200 rader.*

## Projekt
- Namn: Garmin/Withings ingest + Coach
- Branch: <fyll i>  |  HEAD: <short hash>  |  Python: <version>
- Data-rot: `<path>`  (t.ex. `./data`)
- Tidszon: Europe/Stockholm  |  Cutover: none (strict calendar)

## Aktivt krav
- **ID:** <REQ-ID>
- **Titel:** <titel>
- **Status:** todo | doing | done
- **Syfte (2–3 rader):** <kort sammanfattning>
- **Icke-mål:** 
  - <punkt>
  - <punkt>

## Offentliga kontrakt (sedan senaste brief)
*Endast ändringar som påverkar användare, filformat eller CLI.*
- CLI: `<kommando>` ändring: <beskrivning>  (**CONTRACT**)
- Schema: `<path/to/file_or_parquet>` nycklar/typer ändring: <beskrivning>  (**CONTRACT**)
- API: `module.func(args)->ret` ändring: <beskrivning>  (**CONTRACT**)

## Nyckelfiler (aktuellt arbete)
- `src/...` – <syfte>
- `src/...` – <syfte>
- `tests/...` – <syfte>
- `assets/...` – <syfte>

## Öppna frågor / Risker
- <fråga eller risk>
- <fråga eller risk>

## Nästa steg (1–5)
1. <konkret uppgift>
2. <konkret uppgift>
3. <konkret uppgift>

## Senaste commits (kort)
- <h> <YYYY-MM-DD> <meddelande>
- <h> <YYYY-MM-DD> <meddelande>
- <h> <YYYY-MM-DD> <meddelande>

## Tester & hälsa
- **Failing tests:** <antal> (lista node ids)
- **Täckning (om tillgänglig):** <siffra> %
- **Snabbkörning:** `pytest -q tests/<delmapp>`

## Kör / Bygg (snabbkommandon)
```bash
uv pip install -e .
uv run agentlab withings fetch --start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> --out-root ./data --dry-run --resume --skip-existing
uv run python -m agentlab.cli.garmin_fetch --help
```
*Loggar ska alltid visa:*  
`INFO Run manifest: {path}` och `INFO Run totals: {...endpoints.{written,success,error,skipped}...}`

## Säkerhet & Sekretess (checklista)
- [ ] `secrets/` är git-ignorerat; tokenfiler `chmod 600`
- [ ] Inga tokens/PII i loggar eller artefakter
- [ ] Manifest och meta följer invariants (atomiska writes, idempotens)

---
*Instruktion till ChatGPT:* När denna brief klistras in i chatten, använd den som källa för sammanhang och leverera Codex-prompter enligt `docs/ai/CHATGPT_PLAYBOOK.md`.

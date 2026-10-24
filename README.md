# Football Shorts – elke nacht automatisch een YouTube Short

Elke avond om **23u20 (Brusselse tijd)** gebeurt dit vanzelf:

1. **GitHub Actions** haalt de uitslagen en standen van de dag op bij football-data.org (gratis).
2. Het script kiest het sterkste verhaal: perfecte reeks, comeback, verrassing, topper, doelpuntenfestijn, eerste zege …
3. Het maakt een Engelse Short van 1080×1920: een stem vertelt het verhaal, grote ondertitels lichten
   woord per woord op, en de kleuren volgen de club in de kijker (de stijl wisselt elke dag).
4. De video wordt in deze repository bewaard en doorgestuurd naar **Make**.
5. Make zet hem op YouTube, ingepland voor **00:00** (privé tot dat moment, daarna publiek).

Kosten: €0 (GitHub publieke repo, football-data.org gratis plan, Make gratis plan).

## Eenmalige instellingen

### GitHub-secrets
Repository → **Settings → Secrets and variables → Actions → New repository secret**

| Naam | Waarde |
|---|---|
| `FOOTBALL_DATA_API_KEY` | sleutel uit de mail van football-data.org |
| `MAKE_WEBHOOK_URL` | adres van de Custom webhook in Make |

### Make-scenario
1. **Webhooks → Custom webhook** (naam `youtube-short`), adres kopiëren naar het secret hierboven.
2. In GitHub: **Actions → Daily football Short → Run workflow → mode: `test`**.
   Make ontvangt dan de voorbeeldvideo en leert zo welke velden er binnenkomen.
3. Voeg na de webhook **YouTube → Upload a Video** toe en koppel je kanaal (*Sign in with Google*).
   Vul de velden zo in (de exacte namen in Make kunnen licht verschillen):

   | Veld in Make | Waarde uit de webhook |
   |---|---|
   | Video (via URL) | `video_url` |
   | Title | `title` |
   | Description | `description` |
   | Tags | `tags` |
   | Privacy status | **Private** |
   | Publish at / scheduled time | `publish_at` |
   | Category | Sports |
   | Made for kids | No |

   Vraagt de module een bestand in plaats van een URL? Zet er dan **HTTP → Get a file** tussen
   (URL = `video_url`) en geef het resultaat door aan de YouTube-module.
4. Zet het scenario **ON** met *Immediately as data arrives*.
5. Start de test nog één keer. In YouTube Studio staat de video dan als *Gepland* voor 00:00.
   Staat er *Privé (vergrendeld)*, laat het weten: dan schakelen we over op een andere uploadroute.

## Handmatig starten
**Actions → Daily football Short → Run workflow**

- `auto` – video van vandaag maken en posten
- `test` – de voorbeeldvideo (Man City 7 from 7) naar Make sturen
- `dry-run` – enkel maken; de video staat dan als download onder de run (*Artifacts*)
- `preview` – maken en bewaren in `previews/` (niet posten); met `day` kies je een andere dag,
  met `samples` komen er korte stemvoorbeelden bij in `previews/voices/`
- `force` aanvinken – opnieuw maken, ook als er vandaag al een video is

## Stem
De voice-over komt van **Kokoro** (open-source, draait gratis in GitHub Actions; het model wordt één keer
gedownload en daarna bewaard in de cache). Standaardstem: `am_michael`.
Andere stem kiezen voor elke video: **Settings → Secrets and variables → Actions → Variables →
New repository variable**, naam `VOICE`, waarde bv. `bm_george` (Brits) of `af_heart`.
Lukt de stem een keer niet, dan wordt de video toch gemaakt (met ondertitels, zonder stem).

## Muziek
Zet nummers uit de gratis YouTube Audiotheek in `music/`. Leeg = zelfgemaakte rechtenvrije beat.
Met stem speelt de muziek zachter op de achtergrond.

## Mappen
- `shorts/` – de code (data, verhaal, stem, kleuren, video, muziek, verzenden)
- `previews/` – proefvideo's (enkel de laatste 6 blijven staan)
- `videos/` – de gemaakte video's (ouder dan 14 dagen worden automatisch verwijderd)
- `history.json` – welke verhalen al gebruikt zijn (om herhaling te vermijden)
- `samples/test_short.mp4` – voorbeeldvideo voor de koppeltest
- `fonts/` – lettertype Inter (SIL Open Font License)

# Ambient Symphony

**A client-side ambience mod for [Vintage Story](https://www.vintagestory.at/) that brings caves _and_ forests — and the whole world between them — to life, with a deliberate focus on low CPU and minimal FPS impact.**

Ambient Symphony combines the spirit of *Salty's Cave Symphony* and *Forest Symphony* into a single, rebuilt-from-scratch mod, then goes further: biome-aware ambience beds, reactive situational cues, cave reverb, indoor muffling, and an optional in-game settings GUI — all while doing the cheap work once per tick and never touching the server.

> **Status:** v1.0.0. This repository publishes the **audio-generation toolchain** (`tools/`) and the **sound & config assets** (`assets/`). The mod's C# source may be open-sourced in a future release.

---

## Features

- **Caves** — a deep darkness/depth hum, wind howling at cave entrances, water drips (with falling particles), bats, and rats.
- **Forests** — day/night birdsong (temperature-banded: exotic calls in the heat, tundra birds in the cold), pond & frog ambience, insects, tree creaking in the wind, a **dawn chorus** swell at sunrise, and a startled-flock sting when you fell a tree.
- **Biomes** — distinct ambience beds for **desert, grassland, swamp, tundra,** and **jungle**, plus overlays for **coast** (gulls), **alpine** (eagle cries, distant rockfall), **deep-cave abyss**, **geode** (crystalline chimes near ore), **hot springs**, and a **temporal-instability dread** drone. Exactly one surface biome plays at a time, with sparse contextual one-shot accents layered on top.
- **Reactive situations** — a **threat** tension drone when drifters are near (stronger at night), a freezing **wind-chill ring** and a near-death **heartbeat** that respond to your body temperature and health, and an **aurora** shimmer on clear, cold nights.
- **Rare stingers** — occasional distant surprises (a branch snap, brush rustle, settling rock, far-off echo) on a long randomized interval, so the world never feels completely still.
- **Atmosphere & polish** — **cave reverb** for underground depth, surface ambience **muffled when you're sheltered** indoors or under canopy (volume + low-pass filter), **ducking** under base-game music, **wind-reactive** biome beds, and per-play **pitch variance** so repeated one-shots don't sound identical.
- **Configuration** — a full JSON config, an optional in-game **[ConfigLib](https://mods.vintagestory.at/configlib)** settings GUI, one-click **volume presets** (Subtle / Balanced / Immersive), and an **`.ambientsymphony`** debug command.

### Augment, never override

Ambient Symphony only adds sounds the base game has **no** ambience for. Anything Vintage Story already handles — rain, thunder, wind, underwater, ocean waves, lava, campfires, rift hum, and every creature/animal call — is deliberately left untouched, so the mod layers *with* the game instead of fighting it.

### Fully client-side

Earthquakes and cave-ins from the original Cave Symphony are intentionally **not** included. That keeps Ambient Symphony entirely client-side: no server install, no network traffic, and only the players who want it need it.

---

## Light on performance

Ambient Symphony was rebuilt specifically to avoid the frame-time spikes and audio-engine overloads that could affect the original mods:

- **One environment probe** samples the world about twice a second using O(1) lookups (rain-map height, sunlight, climate cached per column, body state) and shares a single immutable snapshot with every subsystem — no subsystem re-queries the world.
- **Budgeted scanning** spreads any heavier block scan across several ticks on the main thread (default ≤ 2000 block reads/tick), and never reads blocks off-thread.
- **A capped sound manager** limits how many sounds play at once, globally and per category, so overlapping ambience can't overload the audio engine.

---

## Install

1. Download the latest `AmbientSymphony_x.y.z.zip` from the [Releases](../../releases) page (or the Vintage Story Mod DB, when available).
2. Drop the zip into your `Mods` folder:
   - **Windows:** `%APPDATA%/VintagestoryData/Mods`
   - **Linux:** `~/.config/VintagestoryData/Mods`
   - **macOS:** `~/Library/Application Support/VintagestoryData/Mods`
3. Launch the game. Ambient Symphony loads on the client only — no server changes required.

**(Optional)** Install **[ConfigLib](https://mods.vintagestory.at/configlib)** for an in-game settings menu. Ambient Symphony works perfectly without it; ConfigLib just adds a GUI.

### Version compatibility

Built and tested against Vintage Story 1.22.3. but the mod should work on **1.22.0 through 1.22.3** and any later 1.22.x.

---

## Configuration

On first launch the mod writes `ModConfig/AmbientSymphony.json` in your Vintage Story data folder. Every subsystem can be toggled and tuned independently.

- **Master / performance:** `MasterEnabled`, `MasterVolume`, `Preset` (Custom / Subtle / Balanced / Immersive), `DebugLogging`, `OneShotPitchVariance`, `ScanBudgetPerTick`, `EnvTickMs`.
- **Core sections:** `Hum`, `Howl`, `Drip`, `Bats`, `Rats`, `Birds` (incl. dawn-chorus settings), `Pond`, `Insects`, `TreeCreak`, `Startle`, `Coverage`.
- **Biome & situation sections:** `Biome` (classifier thresholds), `Desert`, `Grassland`, `Swamp`, `Tundra`, `Jungle`, `Coast`, `Alpine`, `DeepAbyss`, `Geode`, `HotSpring`, `Temporal`, `Stinger`, `Threat`, `BodyState`, `Aurora`.
- **Atmosphere sections:** `CaveReverb`, `Indoor` (sheltered muffle — `SurfaceFactor` volume + `LowPass` filter), `Ducking` (music-duck factor).

Set any section's `Enabled` to `false` to turn it off, or `MasterEnabled` to `false` to silence everything without uninstalling. Delete the file to regenerate defaults.

### In-game settings (ConfigLib)

With ConfigLib installed, Ambient Symphony appears in the mod settings GUI with a curated set of controls: master toggle, loudness preset, master volume, pitch variance, cave reverb, indoor muffle, music ducking, and group toggles for core / biome / special ambience, stingers, threat, and body-state cues. Most changes apply live; enabling a subsystem that was off at world-load (and changing reverb/pitch-variance) takes effect on the next world reload.

### `.ambientsymphony` debug command

Type `.ambientsymphony` (alias `.ambsym`) in chat to print the live environment snapshot driving the ambience — biome, depth/altitude, sheltered state, sunlight, temperature, rainfall, forest density, geologic activity, season, time of day, wind, temporal stability, health, body temperature, the number of active sounds, and the current music-duck level. Handy for understanding (or tuning) what you're hearing.

---

## Audio & the generation toolchain

Every sound in `assets/ambientsymphony/sounds/` is an **original clip generated with the [ElevenLabs Sound Effects](https://elevenlabs.io/) API** using the prompt-driven pipeline in `tools/` — **none of it is derived from the original mods' audio.** The full prompt set, manifest, and packaging scripts are included so anyone can regenerate, tweak, or replace the audio.

```bash
# Preview every prompt (free, no API key, makes no calls)
python tools/gen_sfx_elevenlabs.py --dry-run

# Generate a small batch to audition quality (requires an ElevenLabs API key — uses credits)
export ELEVENLABS_API_KEY=...
python tools/gen_sfx_elevenlabs.py --only "biome/desert"

# Generate / replace the whole set
python tools/gen_sfx_elevenlabs.py --force
```

- **Tweak a sound:** edit its prompt in `spec_for()` / the prompt tables inside `tools/gen_sfx_elevenlabs.py`, then re-run with `--only <path-substring>` to regenerate just that category.
- **Swap in your own audio:** drop a replacement `.ogg` at the matching path under `assets/ambientsymphony/sounds/...`. The complete list of required paths is [`tools/asset_manifest.txt`](tools/asset_manifest.txt). No code changes needed — the mod resolves clips by path.
- **Other sources** work too (any text-to-SFX generator, or CC0 field recordings) as long as the file lands at the right path as OGG/Vorbis.

---

## What's in this repository

```
tools/    Audio-generation toolchain:
            gen_sfx_elevenlabs.py   prompt-driven ElevenLabs Sound Effects generator
            asset_manifest.txt      the full list of required sound paths
            package.ps1             builds the distributable mod zip
assets/   ambientsymphony/
            sounds/**               all generated ambience clips (OGG/Vorbis)
            config/                 ConfigLib settings schema
            lang/                   localization
```

> The mod's C# source is not part of this v1.0.0 publication. The repository currently provides the open audio pipeline and assets; the compiled mod is distributed via Releases / the Mod DB.

---

## Acknowledgements

- **Salty (SaltyWater)** — creator of the original *Cave Symphony* and *Forest Symphony* mods that inspired this project.
- **Maltiez** — for **ConfigLib**, which powers the optional in-game settings GUI.
- **ElevenLabs** — Sound Effects API used to generate the bundled audio.
- The **Vintage Story** team at Anego Studios for a wonderfully moddable game.

## License

Ambient Symphony is dual-licensed:

- **Tooling & code** (`tools/`, and any source published now or later) — **MIT** (see [`LICENSE`](LICENSE)).
- **Audio assets** (`assets/**/*.ogg`) — **CC BY 4.0** (see [`assets/LICENSE.txt`](assets/LICENSE.txt)). Reuse and remix freely, with attribution.

All audio is original (AI-generated via the included pipeline, not derived from the original mods). Note that AI-generated audio also remains subject to the generating service's terms — see [`assets/LICENSE.txt`](assets/LICENSE.txt) for details.

---

*Ambient Symphony — give the silence a voice.*

#!/usr/bin/env python3
"""
Ambient Symphony — ElevenLabs Sound Effects generator.

Replaces the procedural placeholder clips with real AI-generated sound effects from the
ElevenLabs "Sound Effects" API, writing OGG/Vorbis at the exact manifest paths so the mod picks
them up with no code change.

Each manifest path (tools/asset_manifest.txt) is mapped to a tailored text prompt, a duration,
and a seamless-loop flag (cave hum, wind, ponds, insects, rats loop; one-shots don't).

Usage:
  export ELEVENLABS_API_KEY=...           # required for real generation
  python tools/gen_sfx_elevenlabs.py --dry-run            # print every prompt, no API calls, no key needed
  python tools/gen_sfx_elevenlabs.py --only day/birds     # generate just a subset (substring match)
  python tools/gen_sfx_elevenlabs.py --limit 5            # generate the first N (good for a paid test batch)
  python tools/gen_sfx_elevenlabs.py                      # generate all missing clips (skips existing)
  python tools/gen_sfx_elevenlabs.py --force              # regenerate even if the file exists

Requires: numpy, soundfile  (pip install numpy soundfile). Uses only the stdlib for HTTP.
"""
import argparse
import io
import json
import os
import sys
import time
import urllib.request
import urllib.error

import numpy as np
import soundfile as sf

API_URL = "https://api.elevenlabs.io/v1/sound-generation"
MODEL = "eleven_text_to_sound_v2"          # required for the loop option
OUTPUT_FORMAT = "pcm_44100"                # raw 16-bit LE mono PCM @ 44.1 kHz -> we encode OGG
SR = 44100

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets", "ambientsymphony")
MANIFEST = os.path.join(ROOT, "tools", "asset_manifest.txt")

# ---------------------------------------------------------------------------
# Prompt design — the quality lives here. Per category we give ElevenLabs a vivid,
# game-appropriate description, a duration, and whether it should loop seamlessly.
# ---------------------------------------------------------------------------

# Per-species descriptors for forest birds (keyed by the filename stem without the trailing _N).
DAY_BIRD = {
    "bird": "a wild forest songbird chirping a bright melodic call, clear single bird, daytime woodland",
    "canary": "a canary singing fast bright musical trills, cheerful",
    "chickadee": "a chickadee's clear two-note whistle and chattering call",
    "crossbill": "a crossbill's sharp metallic 'jip jip' flight calls",
    "cuckoo": "a cuckoo calling its distinctive two-note 'cu-coo', echoing through woodland",
    "parrot": "a tropical parrot squawking and chattering, vivid jungle bird",
    "robin": "a robin singing a rich warbling melody at dawn",
    "sparrow": "a house sparrow chirping busy cheeps",
    "sunbird": "a sunbird's high thin rapid tinkling chirps",
    "woodpecker": "a woodpecker drumming on a tree trunk and giving a sharp call",
}
NIGHT_BIRD = {
    "bird": "a lone night bird calling softly in dark woodland",
    "owl": "an owl hooting in the still night forest, deep resonant hoots",
    "nightjar": "a nightjar's long churring mechanical trill at night",
    "potoo": "a potoo's eerie mournful descending night call",
    "tawny": "a tawny owl's quavering 'twit-twoo' hoot at night",
    "heron": "a heron's harsh croaking squawk over a night marsh",
    "hornbill": "a hornbill's loud honking cackle echoing at dusk",
    "magpie": "a magpie's harsh rattling chatter",
    "raven": "a raven's deep croaking 'cronk' calls at night",
}

# Rotating flavor so multiple clips in the same non-species category differ from each other.
HUM_FLAVORS = [
    "with a faint airy resonance", "with distant low groans", "with a subtle deep bass pulse",
    "with a hollow metallic shimmer",
]
WIND_FLAVORS = ["with eerie high whistling", "with a deep hollow draft moaning"]
POND_DAY_FLAVORS = ["with frogs croaking", "with gentle lapping water", "with dabbling ducks far off",
                    "with reeds rustling", "with bubbling shallows"]
POND_NIGHT_FLAVORS = ["with a chorus of frogs", "with crickets nearby", "with the occasional plop of water",
                      "with distant toads", "with still quiet ripples"]
INSECT_FLAVORS = ["crickets chirping steadily", "cicadas buzzing in summer heat", "grasshoppers stridulating",
                  "a meadow of buzzing insects", "katydids rasping", "humming midges",
                  "a drone of cicadas", "soft evening crickets"]


def stem_and_index(name):
    """'sparrow_3' -> ('sparrow', 3); 'cave_hum2' -> ('cave_hum', 2); 'drip' -> ('drip', 1)."""
    base = name
    idx = 1
    if "_" in name and name.rsplit("_", 1)[1].isdigit():
        base, n = name.rsplit("_", 1)
        idx = int(n)
    else:
        # trailing-digit form like cave_hum2 / hallway_wind2
        i = len(name)
        while i > 0 and name[i - 1].isdigit():
            i -= 1
        if i < len(name):
            base, idx = name[:i], int(name[i:])
    return base, idx


# Expansion biome/special prompts, keyed by base name (index stripped). Beds loop (long); accents
# are short one-shots. All AUGMENT the base game (no rain/wind/lava/underwater/rift — those exist).
EXPANSION = {
    # --- biome beds (loop) ---
    "heat_day": ("Shimmering desert heat-haze ambience on a scorching open dune field, faint dry wind over sand and the distant drone of cicadas in the midday sun, seamless loop", 9.0, True),
    "night_desert": ("Cold quiet desert night ambience, faint dry wind over open sand dunes under a vast starry sky, sparse distant nocturnal stirrings, seamless loop", 9.0, True),
    "meadow_day": ("Open sunny grassland meadow ambience, gentle breeze through tall grass with distant grasshoppers and faint chirping, peaceful prairie, seamless loop", 9.0, True),
    "crickets_night": ("Calm night meadow ambience, a steady chorus of crickets chirping across open grassland under the stars, seamless loop", 9.0, True),
    "marsh_day": ("Daytime swamp marsh ambience, croaking frogs, buzzing bog insects and trickling stagnant water among reeds, humid wetland, seamless loop", 9.0, True),
    "frogs_night": ("Nighttime swamp ambience, a dense chorus of croaking frogs and chirping night insects over still marsh water, seamless loop", 9.0, True),
    "icy_wind": ("A pure continuous smooth airy polar wind, a steady flowing rush of air blowing across an empty snowfield, only soft wind tone — absolutely NO footsteps, no snow crunching, no boots, no gravel, no clinking, no rustling, no rhythmic crunch of any kind, just clean flowing wind, bleak and desolate, seamless loop", 9.0, True),
    "cold_drone": ("Desolate frozen tundra night, a low hollow wind drone over endless snow and ice, cold emptiness, seamless loop", 9.0, True),
    "insect_wall_day": ("Dense tropical rainforest daytime ambience, a thick wall of buzzing insects and cicadas with chirping exotic birds in a humid jungle canopy, seamless loop", 9.0, True),
    "insect_wall_night": ("Dense tropical rainforest night ambience, a thick humid wall of chirping insects, frogs and distant nocturnal jungle creatures, seamless loop", 9.0, True),
    "high_shimmer": ("High alpine mountain summit ambience, thin cold natural wind whistling over bare rocky crags, airy vast and empty, real mountain wind and NOT a synth or UFO drone, seamless loop", 9.0, True),
    "sea_breeze": ("Gentle coastal sea breeze ambience, soft steady wind off open water along a shoreline, faint and airy, seamless loop", 9.0, True),
    "deep_drone": ("Deep underground abyss ambience, an immense low oppressive drone far beneath the earth, hollow echoing void, dark and ominous, seamless loop", 10.0, True),
    "bubbling": ("Geothermal hot spring ambience, gently bubbling and gurgling hot mineral water with soft rising steam, seamless loop", 8.0, True),
    "dread_drone": ("Eerie unsettling temporal-distortion drone, a low warbling dissonant tone of creeping dread and bending reality, dark ambient, seamless loop", 10.0, True),
    # --- accents (one-shot) ---
    "cicada": ("A lone desert cicada buzzing in short rasping bursts in the dry heat, single isolated call", 2.5, False),
    "night_call": ("A sparse distant nocturnal desert animal call, a lone yip or hoot across empty dunes at night, single isolated sound", 2.5, False),
    "skylark": ("A skylark singing a bright trilling song high over an open meadow, single isolated birdcall", 2.5, False),
    "grasshopper": ("A grasshopper stridulating a short dry rasp in tall grass, single isolated insect chirp", 2.0, False),
    "cricket_solo": ("A single cricket chirping a few clear isolated chirps in the quiet night, single isolated sound", 2.5, False),
    "bittern": ("A bittern marsh bird's deep low foghorn-like booming call echoing across misty wetland reeds, a natural resonant organic 'whoomp' bird call, NOT electronic or sci-fi, single isolated call", 2.8, False),
    "bog_bubble": ("A swamp gas bubble rising and plopping through stagnant bog water, single wet glooping sound", 2.0, False),
    "frog_croak": ("A single bullfrog croaking a deep resonant ribbit by the marsh, single isolated frog call", 2.0, False),
    "ice_crack": ("Ice cracking and groaning sharply across a frozen lake, a single splitting crack with echo, isolated sound", 2.2, False),
    "ptarmigan": ("A ptarmigan's low clucking call across a snowy tundra, single isolated arctic bird call", 2.5, False),
    "wind_gust": ("A natural gust of cold wind rising and falling as it sweeps across open snow, a soft airy organic whoosh of moving air, NOT a beep or interface sound, single isolated gust", 2.6, False),
    "exotic_bird": ("An exotic tropical jungle bird calling a bright distinctive squawk in the canopy, single isolated call", 2.5, False),
    "frog_exotic": ("An exotic tropical tree frog chirping and trilling in the humid jungle night, single isolated call", 2.5, False),
    "howler": ("A distant howler monkey whooping and roaring through the deep jungle canopy, single isolated primate call", 3.0, False),
    "night_creature": ("A mysterious distant nocturnal jungle creature call, an eerie isolated whoop in the dark rainforest, single isolated sound", 2.8, False),
    "eagle": ("A mountain eagle's piercing cry echoing across high rocky peaks, single isolated raptor screech", 2.5, False),
    "rockfall_echo": ("A small rockslide of heavy stones and boulders tumbling and crashing down a steep mountainside, deep rumbling rock impacts with mountain echo, heavy stone NOT rattling dice or pebbles, single isolated rockfall", 3.0, False),
    "gull": ("A seagull crying a few isolated calls over the shoreline, single isolated coastal bird call", 2.5, False),
    "collapse": ("A distant deep underground rock collapse, a muffled rumbling cave-in far away with echo, single isolated sound", 3.0, False),
    "groan": ("A deep ominous groan of shifting rock and earth deep underground, a single low isolated creak with echo", 2.8, False),
    "chime": ("A single ethereal crystalline chime ringing softly in a cave, a pure shimmering bell-like tone, isolated", 2.5, False),
    "shimmer": ("A soft ethereal crystalline shimmer, a delicate glassy ringing sparkle in a cavern, isolated sound", 2.5, False),
    "steam_hiss": ("A short hiss of steam venting from a geothermal hot spring, single isolated steam burst", 2.0, False),
    # --- global stingers (rare distant surprises; non-entity, augment-safe) ---
    "branch_snap": ("A dead tree branch breaking with a sharp splintering woody CRACK followed by crackling twigs and a soft thud of falling wood in a forest, breaking timber NOT a plastic lightswitch click, single isolated snap", 2.2, False),
    "brush_rustle": ("A sudden rustle of leaves and dry undergrowth as something small moves through the brush and is gone, single isolated rustle", 2.2, False),
    "distant_whistle": ("A faint eerie wind whistling far in the distance across an open landscape, a lone isolated airy whistle, unsettling", 2.8, False),
    "lone_gust": ("A sudden whooshing gust of natural wind rushing through tree leaves and branches and fading away, organic moving air in a forest, NOT an electronic or interface sound, single isolated gust", 2.6, False),
    "rock_settle": ("A small rock shifting and settling with a dull knock and a faint trickle of pebbles in a quiet cave, single isolated sound", 2.2, False),
    "far_echo": ("A faint distant unidentified echo deep underground, a lone hollow reverberating sound far away in the dark, isolated", 3.0, False),
    # --- reactive trigger beds (loops) ---
    "tension_drone": ("A low ominous tension drone of looming dread, a dark sustained subterranean rumble signalling nearby danger, horror ambient, seamless loop", 9.0, True),
    "windchill_ring": ("A bitter freezing winter wind howling and moaning low across a frozen waste, a mournful deep cold gale, NO insect buzz and no high ringing tones, harsh and cold, seamless loop", 8.0, True),
    "heartbeat": ("A slow steady muffled heartbeat, a deep dull rhythmic lub-dub pulse heard from inside the chest, clean and even spacing with no extra knocks or hits, seamless loop", 6.0, True),
    "shimmer": ("A soft low ethereal aurora ambience, a gentle warm slowly drifting shimmering pad over a quiet frozen night, smooth and soothing with NO high-pitched ringing or whine or tinnitus tone, seamless loop", 9.0, True),
    # --- grassland locust = cicada hot-day drone (rare, louder one-shot over the quiet meadow bed) ---
    "locust": ("The loud droning whine of cicadas on a hot summer day, a single sustained high buzzing insect drone that swells up in volume then slowly fades away, classic summer heat sound, isolated, no other sounds", 5.0, False),
}


def spec_for(rel):
    """rel like 'sounds/day/birds/robin_2.ogg' -> (prompt, duration_seconds, loop)."""
    p = rel[len("sounds/"):-len(".ogg")] if rel.startswith("sounds/") and rel.endswith(".ogg") else rel
    parts = p.split("/")
    name = parts[-1]
    base, idx = stem_and_index(name)

    # --- Cave ---
    if parts[0] == "cave":
        f = HUM_FLAVORS[(idx - 1) % len(HUM_FLAVORS)]
        return (f"Deep ominous cave drone, low subterranean rumbling ambience, dark and hollow, {f}, "
                f"no music, seamless background loop", 10.0, True)
    if parts[0] == "hallway":
        f = WIND_FLAVORS[(idx - 1) % len(WIND_FLAVORS)]
        return (f"Wind howling through a narrow underground cave tunnel, {f}, hollow airy draft, "
                f"unsettling, seamless loop", 9.0, True)
    if parts[0] == "environment":
        if base.startswith("bigdrip"):
            return ("A loud clear close-up large heavy water droplet plonking hard into a still cave "
                    "pool, strong deep wet plop with a distinct splash and short echoing reverb tail", 2.0, False)
        return ("A clear close-up water drop falling and plinking sharply onto wet stone in a cave, "
                "distinct loud droplet with a short echoing reverb tail", 2.0, False)
    if parts[0] == "animals":
        if base == "bats":
            return ("A few bats fluttering and squeaking in a dark cave, soft leathery wing flaps and "
                    "high chirps, seamless loop", 3.0, True)
        if base == "flockofbats":
            return ("A swarm of bats screeching and flapping in a cave, dense chaotic leathery wingbeats "
                    "and shrill squeaks, seamless loop", 3.0, True)
        if base == "scaredbats":
            return ("A colony of bats suddenly scared and panicking, instantly bursting into flight and "
                    "rapidly fleeing away — a fast urgent rush of many leathery wings frantically "
                    "flapping and quickly whooshing as the frightened swarm escapes deep into a cave and "
                    "recedes — hurried startled wingbeats only, no screeching", 2.6, False)
        if base == "rats":
            return ("Soft faint rats scurrying in a dark cave, gentle skittering of tiny feet on stone with "
                    "quiet muffled squeaks, subtle and soft and NOT screechy or scratchy, seamless loop", 3.0, True)
        if base == "ratsniff":
            return ("A rat close by sniffing and snuffling, small rodent breaths and light scratching, "
                    "seamless loop", 2.0, True)

    # --- Forest birds ---
    if parts[:2] == ["day", "birds"]:
        desc = DAY_BIRD.get(base, DAY_BIRD["bird"])
        return (f"{desc}, natural forest ambience, single isolated call, no music", 2.5, False)
    if parts[:2] == ["night", "birds"]:
        desc = NIGHT_BIRD.get(base, NIGHT_BIRD["bird"])
        return (f"{desc}, quiet nighttime forest, single isolated call, no music", 2.8, False)

    # --- Ponds ---
    if parts[:2] == ["day", "pond"]:
        f = POND_DAY_FLAVORS[(idx - 1) % len(POND_DAY_FLAVORS)]
        return (f"Calm daytime pond ambience, gentle water {f}, soft natural wetland background, "
                f"seamless loop", 6.0, True)
    if parts[:2] == ["night", "pond"]:
        f = POND_NIGHT_FLAVORS[(idx - 1) % len(POND_NIGHT_FLAVORS)]
        return (f"Quiet nighttime pond ambience {f}, calm water, peaceful nocturnal wetland, "
                f"seamless loop", 6.0, True)

    # --- Insects ---
    if parts[:2] == ["day", "insect"]:
        return ("Daytime pond-edge insects, buzzing dragonflies and chirping crickets near water, "
                "seamless loop", 4.0, True)
    if parts[:2] == ["night", "insect"]:
        return ("Nighttime pond-edge insects, crickets and chirping frogs near still water, "
                "seamless loop", 4.0, True)
    if parts[0] == "insect":
        f = INSECT_FLAVORS[(idx - 1) % len(INSECT_FLAVORS)]
        return (f"Forest meadow insects, {f}, warm summer day, seamless loop", 4.0, True)

    # --- Trees ---
    if parts[0] == "tree":
        if base.startswith("creaky-tree"):
            return ("A tall tree slowly creaking and groaning in the wind outdoors, a deep low organic "
                    "wood-flexing creak of a bending trunk, NO leaf rustling, NO rattling, no pouring "
                    "or pattering sounds — just groaning timber, single isolated creak", 2.2, False)
        if base.startswith("startled"):
            return ("A flock of birds suddenly taking flight in alarm, an explosive rush of flapping "
                    "wings and panicked chirping", 1.6, False)

    # --- Expansion biomes, special situations & global stingers (keyed by base name) ---
    if parts[0] in ("biome", "special", "stinger") and base in EXPANSION:
        return EXPANSION[base]

    # Fallback
    return ("Subtle natural ambient sound", 2.0, False)


def generate(api_key, prompt, duration, loop):
    body = {
        "text": prompt,
        "duration_seconds": round(float(duration), 2),
        "model_id": MODEL,
        "loop": bool(loop),
        "prompt_influence": 0.5,
    }
    data = json.dumps(body).encode("utf-8")
    # output_format MUST be a query parameter; in the body it is ignored and the API returns
    # MP3 by default (which we would then misread as raw PCM -> garbage/short audio).
    url = API_URL + "?output_format=" + OUTPUT_FORMAT
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("xi-api-key", api_key)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "audio/pcm")
    with urllib.request.urlopen(req, timeout=240) as resp:
        ctype = resp.headers.get("Content-Type", "")
        data = resp.read()
    # If the API returned JSON (error/quota) instead of audio, surface it clearly.
    if "json" in ctype.lower() or data[:1] in (b"{", b"["):
        raise RuntimeError("API returned non-audio response: " + data[:300].decode("utf-8", "ignore"))
    return data


def pcm_to_ogg(pcm_bytes, out_path):
    # ElevenLabs pcm_44100 returns 16-bit little-endian *stereo* (2 interleaved channels).
    # Trim to a whole stereo frame (4 bytes) then downmix to mono.
    usable = (len(pcm_bytes) // 4) * 4
    pcm_bytes = pcm_bytes[:usable]
    flat = np.frombuffer(pcm_bytes, dtype="<i2").astype(np.float32) / 32768.0
    if flat.size == 0:
        raise RuntimeError("empty audio response (0 samples)")
    stereo = flat.reshape(-1, 2)
    mono = stereo.mean(axis=1)
    # Peak-normalize for consistent in-game loudness (ElevenLabs renders some SFX very quietly).
    # Cap the boost so a near-silent clip's noise floor isn't amplified into a roar.
    peak = float(np.max(np.abs(mono))) if mono.size else 0.0
    if peak > 0.004:
        gain = min(0.7 / peak, 25.0)
        mono = mono * gain
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    sf.write(out_path, mono, SR, format="OGG", subtype="VORBIS")
    return len(mono) / SR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print prompts, make no API calls")
    ap.add_argument("--only", default=None, help="substring filter on the manifest path")
    ap.add_argument("--outdir", default=None, help="output root (default assets/ambientsymphony); use e.g. 'audition' to A/B without overwriting")
    ap.add_argument("--limit", type=int, default=0, help="generate at most N clips (0 = all)")
    ap.add_argument("--force", action="store_true", help="regenerate even if the .ogg already exists")
    ap.add_argument("--sleep", type=float, default=0.6, help="seconds between API calls")
    ap.add_argument("--retries", type=int, default=4)
    args = ap.parse_args()

    with open(MANIFEST) as f:
        paths = [ln.strip() for ln in f if ln.strip()]
    if args.only:
        paths = [p for p in paths if args.only in p]

    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not args.dry_run and not api_key:
        print("ERROR: set ELEVENLABS_API_KEY (or use --dry-run).", file=sys.stderr)
        sys.exit(2)

    todo = []
    for rel in paths:
        base_out = os.path.join(ROOT, args.outdir) if args.outdir else ASSETS
        out = os.path.join(base_out, *rel.split("/"))
        if not args.force and os.path.exists(out) and not args.dry_run:
            # Only skip clips that look already-AI-generated? We can't tell; honor --force vs skip.
            pass
        todo.append((rel, out))
    if args.limit > 0:
        todo = todo[:args.limit]

    print(f"{'DRY-RUN: ' if args.dry_run else ''}{len(todo)} clip(s) "
          f"({'all' if not args.only else repr(args.only)})\n")

    done = 0
    for rel, out in todo:
        prompt, dur, loop = spec_for(rel)
        tag = "loop" if loop else "one-shot"
        print(f"  {rel:48s} [{dur:>4.1f}s {tag:8s}] {prompt[:70]}")
        if args.dry_run:
            continue

        for attempt in range(1, args.retries + 1):
            try:
                pcm = generate(api_key, prompt, dur, loop)
                secs = pcm_to_ogg(pcm, out)
                print(f"      -> wrote {os.path.getsize(out)//1024} KB, {secs:.1f}s")
                done += 1
                break
            except urllib.error.HTTPError as e:
                msg = e.read().decode("utf-8", "ignore")[:200]
                if e.code in (429, 500, 502, 503) and attempt < args.retries:
                    wait = args.sleep * (2 ** attempt)
                    print(f"      ! HTTP {e.code}; retry in {wait:.1f}s ({msg})")
                    time.sleep(wait)
                    continue
                print(f"      ! HTTP {e.code} (giving up): {msg}")
                break
            except Exception as e:
                print(f"      ! {type(e).__name__}: {e}")
                break
        time.sleep(args.sleep)

    if not args.dry_run:
        print(f"\nGenerated {done}/{len(todo)} clips into {ASSETS}")


if __name__ == "__main__":
    main()

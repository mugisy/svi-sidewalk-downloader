# 🛤️ Sidewalk Pavement Image Downloader

A Python tool that automatically downloads Google Street View images focused on **sidewalk pavement surfaces** along any walking route. Instead of capturing road-facing views, the camera is deliberately aimed 90° left and right of the walking direction — isolating the footpath for research, inspection, or dataset collection.

---

## How It Works

```
Origin ──────────────────────────────► Destination
         ↑        ↑        ↑
      sample   sample   sample          (every step_m metres)
      point    point    point
        ↙ ↘     ↙ ↘     ↙ ↘
      left right left right left right  (Street View images)
```

1. **Route** — Google Directions API returns the walking polyline between your two points.
2. **Sample** — The route is walked at a fixed interval (e.g. every 10 m), generating sample coordinates.
3. **Panorama lookup** — For each coordinate, the nearest Street View panorama is found (within 50 m).
4. **Download** — Two images are saved per panorama: one looking left of travel, one looking right. Duplicate panoramas are skipped automatically.

---

## Requirements

### Python version

Python **3.10 or newer** is required (the code uses `X | Y` union type hints).

Check your version:

```bash
python --version
```

### Google Maps API key

You need a Google Maps Platform API key with the following three APIs **enabled**:

| API | Used for |
|---|---|
| Directions API | Fetching the walking route polyline |
| Street View Static API | Downloading the images |
| Street View Metadata API | Looking up panorama IDs |

> **How to get a key:**
> 1. Go to [console.cloud.google.com](https://console.cloud.google.com)
> 2. Create or select a project → **APIs & Services** → **Enable APIs**
> 3. Search for and enable each of the three APIs above
> 4. Go to **Credentials** → **Create Credentials** → **API Key**
> 5. (Recommended) Restrict the key to only the three APIs above

⚠️ The Street View Static API is a **paid** service. Google provides a monthly $200 free credit. Each image download costs approximately $0.007. See [Google Maps pricing](https://mapsplatform.google.com/pricing/) for details.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/mugisy/svi-sidewalk-downloader.git
cd svi-sidewalk-downloader
```

### 2. (Recommended) Create a virtual environment

```bash
# Create a new python environment (3.10+)
conda create -n sidewalk-download python
conda activate sidewalk-download
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

The `requirements.txt` contains:

```
requests>=2.28
polyline>=2.0
```

---

## Usage

### Option A — Interactive mode (recommended for beginners)

Run the script directly. It will guide you through every setting with prompts, defaults, and validation:

```bash
python sidewalk_downloader.py
```

Example session:

```
╔══════════════════════════════════════════════════╗
║   Sidewalk Pavement Image Downloader             ║
╚══════════════════════════════════════════════════╝

── Authentication ──────────────────────────────────
  Google Maps API key: ••••••••••••

── Route ───────────────────────────────────────────
  Enter coordinates as  lat,lon  or a text address.
  Origin (start point): 22.3736126,114.2612061
  Destination (end point): 22.3736207,114.2609948

── Sampling ────────────────────────────────────────
  Sampling interval in metres [10.0, ≥ 1.0]: 10

── Camera ──────────────────────────────────────────
  Pitch: tilt angle in degrees (negative = looking down).
  Pitch [-30, -90–90]: -30
  FOV: horizontal field-of-view in degrees (10–120).
  Field of view [60, 10–120]: 60

── Output ──────────────────────────────────────────
  Output directory [sidewalk_pavement]:

──────────────────────────────────────────────────
  Review your settings
──────────────────────────────────────────────────
  api_key       ••••••••zMrA
  origin        22.3736126,114.2612061
  destination   22.3736207,114.2609948
  output_dir    sidewalk_pavement
  step_m        10.0
  pitch         -30
  fov           60
──────────────────────────────────────────────────
  Proceed? [Y/n]:
```

### Option B — Import as a module (for scripts and notebooks)

```python
from sidewalk_downloader import download_sidewalk_images

result = download_sidewalk_images(
    api_key="YOUR_GOOGLE_MAPS_API_KEY",
    origin="22.3736126,114.2612061",       # lat,lon or text address
    destination="22.3736207,114.2609948",  # lat,lon or text address
    output_dir="sidewalk_pavement",        # folder to save images
    step_m=10.0,                           # sample every 10 metres
    pitch=-30,                             # camera tilt (° from horizontal)
    fov=60,                                # field of view in degrees
    verbose=True,                          # print progress
)

print(result)
# DownloadResult(
#   output_dir = 'sidewalk_pavement'
#   saved      = 14 image(s)
#   skipped    = 2 duplicate panorama(s)
#   failed     = 0 error(s)
# )

# Access saved file paths directly
for path in result.saved:
    print(path)
```

---

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `api_key` | `str` | — | Google Maps API key (**required**) |
| `origin` | `str` | — | Start point as `"lat,lon"` or text address (**required**) |
| `destination` | `str` | — | End point as `"lat,lon"` or text address (**required**) |
| `output_dir` | `str` | `"sidewalk_pavement"` | Folder where images are saved (created if missing) |
| `step_m` | `float` | `10.0` | Distance in metres between sample points along the route |
| `image_size` | `str` | `"640x640"` | Pixel dimensions of downloaded images |
| `pitch` | `int` | `-30` | Camera vertical tilt in degrees. `0` = horizontal, `-90` = straight down |
| `fov` | `int` | `60` | Horizontal field of view in degrees. Range: `10`–`120` |
| `verbose` | `bool` | `True` | Print step-by-step progress to the console |

### Choosing good values

**`step_m` — sampling interval**
- `5–10 m` gives dense, overlapping coverage. Good for short routes or detailed inspection.
- `20–30 m` gives sparser coverage. Good for long routes where fewer images are needed.
- Very small values (< 5 m) will often hit the same Street View panorama repeatedly; duplicates are skipped automatically.

**`pitch` — camera tilt**
- `-30` (default) points the camera slightly downward — ideal for capturing pavement texture.
- `-60` to `-90` for a more top-down view of the surface.
- `0` for a level, horizon-facing view.

**`fov` — field of view**
- `60` (default) gives a natural perspective, similar to a standard camera lens.
- `90–120` gives a wider angle, capturing more of the surrounding context.
- `10–30` gives a narrow, zoomed-in view of the pavement surface.

---

## Output

Images are saved as `.png` files in the output directory, named by the panorama's coordinates and side:

```
sidewalk_pavement/
├── 22.373601_114.261100_left.png
├── 22.373601_114.261100_right.png
├── 22.373598_114.261050_left.png
├── 22.373598_114.261050_right.png
└── ...
```

The filename format is: `{lat}_{lon}_{left|right}.png`

---

## Repository Structure

```
sidewalk-downloader/
├── sidewalk_downloader.py   # Main script and importable module
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

---

## Troubleshooting

**`Directions API returned status 'REQUEST_DENIED'`**
Your API key is missing or the Directions API is not enabled. Double-check your key and confirm all three APIs are active in the Google Cloud Console.

**`Directions API returned status 'ZERO_RESULTS'`**
Google could not find a walking route between your two points. This can happen if the points are in different countries, over water, or in an area with no mapped pedestrian paths. Try a shorter or different route.

**All sample points report "No panorama near …"**
Street View coverage may be sparse in that area. Try increasing the `radius_m` parameter inside `_fetch_panorama()` (default is 50 m), or choose a route in a more densely mapped area.

**Images download but appear grey / blank**
Google returns a grey placeholder image when Street View is unavailable at a location, rather than an HTTP error. This is a data-availability issue on Google's side for that specific panorama.

**`ModuleNotFoundError: No module named 'polyline'`**
Run `pip install -r requirements.txt` (ideally inside your virtual environment).

---

## API Cost Estimate

Each run makes the following API calls:

| Call | Cost (approx.) |
|---|---|
| 1 × Directions API request | $0.005 |
| N × Street View Metadata requests | $0.007 per request |
| N × Street View Static image downloads | $0.007 per image |

For a 100 m route sampled every 10 m (~10 unique panoramas), expect roughly **$0.15** in API usage. The monthly $200 free credit from Google typically covers substantial testing.

---

## License

MIT License. See `LICENSE` for details.

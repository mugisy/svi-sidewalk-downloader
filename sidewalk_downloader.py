"""
sidewalk_downloader.py
======================
Downloads Google Street View images of sidewalk pavements along a
walking route between two coordinates.

Images are captured by pointing the camera 90 degrees left (West) and right (East) 
of the walking direction (North) and increasing latitude and longitude, ensuring 
the view focuses on the footpath rather than the road surface.

Run directly to be guided through all settings interactively:

    python sidewalk_downloader.py

Or import and call programmatically:

    from sidewalk_downloader import download_sidewalk_images

    result = download_sidewalk_images(
        api_key="YOUR_GOOGLE_MAPS_API_KEY",
        origin="22.3736126,114.2612061",
        destination="22.3736207,114.2609948",
        step_m=10,
        pitch=-30,
        fov=60,
    )
    print(result)
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Iterator

import polyline
import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EARTH_RADIUS_M = 6_371_000  # metres
DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
STREETVIEW_METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
STREETVIEW_IMAGE_URL = "https://maps.googleapis.com/maps/api/streetview"

SIDEWALK_OFFSETS: dict[str, int] = {"left": -90, "right": 90}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DownloadResult:
    """Summary returned by :func:`download_sidewalk_images`."""

    output_dir: str
    saved: list[str] = field(default_factory=list)
    skipped: int = 0           # panoramas already downloaded (deduplication)
    failed: int = 0            # HTTP or API errors

    @property
    def total(self) -> int:
        return len(self.saved) + self.failed

    def __str__(self) -> str:
        return (
            f"DownloadResult(\n"
            f"  output_dir = '{self.output_dir}'\n"
            f"  saved      = {len(self.saved)} image(s)\n"
            f"  skipped    = {self.skipped} duplicate panorama(s)\n"
            f"  failed     = {self.failed} error(s)\n"
            f")"
        )


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in metres between two coordinates."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the compass bearing (0–360°) from point 1 to point 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _interpolate_segment(
    lat1: float, lon1: float, lat2: float, lon2: float, step_m: float = 10.0
) -> Iterator[tuple[float, float]]:
    """
    Yield (lat, lon) sample points spaced *step_m* metres apart
    along the straight segment from (lat1, lon1) to (lat2, lon2).
    """
    dist = _haversine_distance(lat1, lon1, lat2, lon2)
    steps = int(dist // step_m)
    for i in range(steps + 1):
        f = i / max(steps, 1)
        yield lat1 + (lat2 - lat1) * f, lon1 + (lon2 - lon1) * f


# ---------------------------------------------------------------------------
# Google Maps API helpers
# ---------------------------------------------------------------------------

def _fetch_route(origin: str, destination: str, api_key: str) -> list[tuple[float, float]]:
    """
    Query the Google Directions API for a walking route.

    Parameters
    ----------
    origin, destination:
        Either ``"lat,lon"`` strings or free-text addresses.
    api_key:
        Google Maps API key with Directions API enabled.

    Returns
    -------
    list of (lat, lon) tuples decoded from the overview polyline.

    Raises
    ------
    RuntimeError
        If the Directions API returns a non-OK status.
    """
    params = {
        "origin": origin,
        "destination": destination,
        "mode": "walking",
        "key": api_key,
    }
    response = requests.get(DIRECTIONS_URL, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    if data["status"] != "OK":
        raise RuntimeError(
            f"Directions API returned status '{data['status']}': "
            f"{data.get('error_message', 'no details')}"
        )

    encoded = data["routes"][0]["overview_polyline"]["points"]
    return polyline.decode(encoded)  # list of (lat, lon)


def _fetch_panorama(
    lat: float, lon: float, api_key: str, radius_m: int = 50
) -> tuple[str | None, float | None, float | None]:
    """
    Query the Street View Metadata API for the nearest panorama.

    Returns
    -------
    (pano_id, pano_lat, pano_lon) or (None, None, None) if not found.
    """
    params = {
        "location": f"{lat},{lon}",
        "radius": radius_m,
        "key": api_key,
    }
    resp = requests.get(STREETVIEW_METADATA_URL, params=params, timeout=10)
    resp.raise_for_status()
    meta = resp.json()

    if meta["status"] == "OK":
        loc = meta["location"]
        return meta["pano_id"], loc["lat"], loc["lng"]
    return None, None, None


def _download_image(
    pano_id: str,
    heading: float,
    filepath: str,
    api_key: str,
    size: str = "640x640",
    pitch: int = -30,
    fov: int = 60,
) -> bool:
    """
    Download one Street View image and write it to *filepath*.

    Returns
    -------
    True on success, False on HTTP error.
    """
    params = {
        "size": size,
        "pano": pano_id,
        "heading": heading,
        "pitch": pitch,
        "fov": fov,
        "key": api_key,
    }
    resp = requests.get(STREETVIEW_IMAGE_URL, params=params, timeout=15)
    if resp.status_code == 200:
        with open(filepath, "wb") as fh:
            fh.write(resp.content)
        return True
    return False


# ---------------------------------------------------------------------------
# Public pipeline function
# ---------------------------------------------------------------------------

def download_sidewalk_images(
    api_key: str,
    origin: str,
    destination: str,
    output_dir: str = "sidewalk_pavement",
    step_m: float = 10.0,
    image_size: str = "640x640",
    pitch: int | list[int] = -30,
    fov: int | list[int] = 60,
    verbose: bool = True,
) -> DownloadResult:
    """
    Download Street View sidewalk-pavement images along a walking route.

    The camera heading is offset 90° left and right of the walking direction
    so that images show the footpath surface, not the road.

    Parameters
    ----------
    api_key : str
        Google Maps API key with Directions, Street View Static, and
        Street View Metadata APIs enabled.
    origin : str
        Start point as ``"lat,lon"`` or a text address.
    destination : str
        End point as ``"lat,lon"`` or a text address.
    output_dir : str, optional
        Directory where images are saved (created if absent).
        Default: ``"sidewalk_pavement"``.
    step_m : float, optional
        Sampling interval along the route in metres. Default: ``10``.
    image_size : str, optional
        Pixel dimensions of downloaded images, e.g. ``"640x640"``.
        Default: ``"640x640"``.
    pitch : int or list[int], optional
        Camera tilt in degrees (negative = looking down). Pass a single
        int or a list to capture multiple tilt angles per point.
        Default: ``-30``.
    fov : int or list[int], optional
        Horizontal field-of-view in degrees. Pass a single int or a list
        to capture multiple zoom levels per point. Default: ``60``.
    verbose : bool, optional
        Print progress messages. Default: ``True``.

    Returns
    -------
    DownloadResult
        Dataclass with lists of saved file paths plus skipped / failed counts.

    Examples
    --------
    >>> result = download_sidewalk_images(
    ...     api_key="YOUR_KEY",
    ...     origin="22.3736126,114.2612061",
    ...     destination="22.3736207,114.2609948",
    ... )
    >>> print(result)
    """
    result = DownloadResult(output_dir=output_dir)
    os.makedirs(output_dir, exist_ok=True)
    seen_panos: set[str] = set()

    pitches = pitch if isinstance(pitch, list) else [pitch]
    fovs = fov if isinstance(fov, list) else [fov]

    # ------------------------------------------------------------------
    # Fetch walking route
    # ------------------------------------------------------------------
    if verbose:
        print(f"[1/3] Fetching walking route: {origin!r} → {destination!r}")

    route = _fetch_route(origin, destination, api_key)

    if verbose:
        print(f"      Route decoded: {len(route)} waypoint(s)")

    # ------------------------------------------------------------------
    # Sample route at fixed intervals
    # ------------------------------------------------------------------
    if verbose:
        print(f"[2/3] Sampling route every {step_m} m and querying panoramas …")

    sample_points: list[tuple[float, float, float]] = []  # (lat, lon, bearing)

    for (lat1, lon1), (lat2, lon2) in zip(route, route[1:]):
        brg = _bearing(lat1, lon1, lat2, lon2)
        for lat, lon in _interpolate_segment(lat1, lon1, lat2, lon2, step_m):
            sample_points.append((lat, lon, brg))

    if verbose:
        print(f"      {len(sample_points)} sample point(s) generated")

    # ------------------------------------------------------------------
    # Download sidewalk images
    # ------------------------------------------------------------------
    if verbose:
        print(f"[3/3] Downloading images to '{output_dir}' …")

    for idx, (lat, lon, brg) in enumerate(sample_points, start=1):
        pano_id, plat, plon = _fetch_panorama(lat, lon, api_key)

        if pano_id is None:
            if verbose:
                print(f"  [{idx}/{len(sample_points)}] No panorama near ({lat:.6f}, {lon:.6f})")
            continue

        if pano_id in seen_panos:
            result.skipped += 1
            continue
        seen_panos.add(pano_id)

        for side, offset in SIDEWALK_OFFSETS.items():
            heading = (brg + offset) % 360

            for p in pitches:
                for f in fovs:
                    # Include pitch/fov in filename to avoid overwriting
                    # when multiple values are requested
                    suffix = f"_p{p}_f{f}" if len(pitches) > 1 or len(fovs) > 1 else ""
                    filename = os.path.join(
                        output_dir, f"{plat:.6f}_{plon:.6f}_{side}{suffix}.png"
                    )

                    success = _download_image(
                        pano_id, heading, filename, api_key,
                        size=image_size, pitch=p, fov=f,
                    )

                    if success:
                        result.saved.append(filename)
                        if verbose:
                            print(f"  [{idx}/{len(sample_points)}] Saved  {filename}")
                    else:
                        result.failed += 1
                        if verbose:
                            print(f"  [{idx}/{len(sample_points)}] FAILED pano={pano_id} side={side} pitch={p} fov={f}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    if verbose:
        print()
        print("Done.")
        print(result)

    return result


# ---------------------------------------------------------------------------
# Interactive prompt helpers
# ---------------------------------------------------------------------------

def _prompt_str(question: str, default: str | None = None) -> str:
    """
    Prompt the user for a string value.

    Re-prompts on empty input unless a *default* is provided, in which case
    pressing Enter accepts the default.
    """
    hint = f" [{default}]" if default is not None else ""
    while True:
        value = input(f"{question}{hint}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        print("  ✗  This field is required. Please enter a value.")


def _prompt_float(
    question: str,
    default: float,
    min_val: float | None = None,
    max_val: float | None = None,
) -> float:
    """
    Prompt the user for a float value, showing the default and valid range.

    Re-prompts on invalid input or out-of-range values.
    """
    range_hint = ""
    if min_val is not None and max_val is not None:
        range_hint = f", {min_val}\u2013{max_val}"
    elif min_val is not None:
        range_hint = f", \u2265 {min_val}"
    elif max_val is not None:
        range_hint = f", \u2264 {max_val}"

    hint = f" [{default}{range_hint}]"
    while True:
        raw = input(f"{question}{hint}: ").strip()
        if not raw:
            return default
        try:
            value = float(raw)
        except ValueError:
            print(f"  \u2717  '{raw}' is not a valid number. Please try again.")
            continue
        if min_val is not None and value < min_val:
            print(f"  \u2717  Value must be \u2265 {min_val}.")
            continue
        if max_val is not None and value > max_val:
            print(f"  \u2717  Value must be \u2264 {max_val}.")
            continue
        return value


# def _prompt_int(
#     question: str,
#     default: int,
#     min_val: int | None = None,
#     max_val: int | None = None,
# ) -> int:
#     """Thin wrapper around _prompt_float that coerces the result to int."""
#     return int(_prompt_float(question, default, min_val, max_val))


def _prompt_int_or_list(
    question: str,
    default: int,
    min_val: int | None = None,
    max_val: int | None = None,
) -> int | list[int]:
    """
    Prompt for a single int or a comma-separated list of ints, e.g.:
        -30
        -30, -15, 5
        [-30, -15, 5]

    Re-prompts on invalid input or out-of-range values.
    """
    range_hint = ""
    if min_val is not None and max_val is not None:
        range_hint = f", {min_val}\u2013{max_val}"
    elif min_val is not None:
        range_hint = f", \u2265 {min_val}"
    elif max_val is not None:
        range_hint = f", \u2264 {max_val}"

    hint = f" [{default}{range_hint}]"
    while True:
        raw = input(f"{question}{hint}: ").strip()
        if not raw:
            return default

        # Allow optional surrounding brackets: [1, 2, 3]
        cleaned = raw.strip("[]")
        parts = [p.strip() for p in cleaned.split(",") if p.strip()]

        values: list[int] = []
        valid = True
        for part in parts:
            try:
                v = int(float(part))
            except ValueError:
                print(f"  \u2717  '{part}' is not a valid number. Please try again.")
                valid = False
                break
            if min_val is not None and v < min_val:
                print(f"  \u2717  Value {v} must be \u2265 {min_val}.")
                valid = False
                break
            if max_val is not None and v > max_val:
                print(f"  \u2717  Value {v} must be \u2264 {max_val}.")
                valid = False
                break
            values.append(v)

        if not valid or not values:
            continue

        return values[0] if len(values) == 1 else values


def _confirm(settings: dict) -> bool:
    """Print a summary of collected settings and ask the user to confirm."""
    print()
    print("\u2500" * 50)
    print("  Review your settings")
    print("\u2500" * 50)
    col_w = max(len(k) for k in settings) + 2
    for key, value in settings.items():
        print(f"  {key:<{col_w}} {value}")
    print("\u2500" * 50)
    answer = input("  Proceed? [Y/n]: ").strip().lower()
    return answer in ("", "y", "yes")


def _prompt_settings() -> dict:
    """
    Interactively collect all pipeline settings from the user.

    Returns
    -------
    dict with keys: api_key, origin, destination, output_dir,
                    step_m, pitch, fov.
    """
    print()
    print("\u2554" + "\u2550" * 50 + "\u2557")
    print("\u2551   Sidewalk Pavement Image Downloader             \u2551")
    print("\u255a" + "\u2550" * 50 + "\u255d")
    print()

    # --- Required fields ---
    print("\u2500\u2500 Authentication \u2500" * 2 + "\u2500" * 15)
    api_key = _prompt_str("  Google Maps API key")

    print()
    print("\u2500\u2500 Route " + "\u2500" * 43)
    print("  Enter coordinates as  lat,lon  or a text address.")
    origin = _prompt_str("  Origin (start point)")
    destination = _prompt_str("  Destination (end point)")

    print()
    print("\u2500\u2500 Sampling " + "\u2500" * 40)
    step_m = _prompt_float(
        "  Sampling interval in metres",
        default=10.0,
        min_val=1.0,
    )

    print()
    print("\u2500\u2500 Camera " + "\u2500" * 42)
    print("  Pitch: tilt angle in degrees (negative = looking down).")
    print("  Enter a single value, or a comma-separated list, e.g. -30, -15, 5")
    pitch = _prompt_int_or_list(
        "  Pitch",
        default=-30,
        min_val=-30,
        max_val=10,
    )

    print("  FOV: horizontal field-of-view in degrees (10\u2013120).")
    print("  Enter a single value, or a comma-separated list, e.g. 60, 90")
    fov = _prompt_int_or_list(
        "  Field of view",
        default=60,
        min_val=60,
        max_val=120,
    )

    print()
    print("\u2500\u2500 Output " + "\u2500" * 42)
    output_dir = _prompt_str("  Output directory", default="sidewalk_pavement")

    return dict(
        api_key=api_key,
        origin=origin,
        destination=destination,
        output_dir=output_dir,
        step_m=step_m,
        pitch=pitch,
        fov=fov,
    )


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    while True:
        settings = _prompt_settings()

        display = {"api_key": "\u2022" * 8 + settings["api_key"][-4:]}
        display.update({k: v for k, v in settings.items() if k != "api_key"})

        if _confirm(display):
            break
        print("\n  Starting over \u2014 please re-enter your settings.\n")

    download_sidewalk_images(**settings)

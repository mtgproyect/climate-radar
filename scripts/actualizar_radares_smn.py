#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Actualiza el catálogo modular de imágenes de radar del SMN.

Principio de diseño:
- consulta inventarios oficiales;
- publica únicamente nombres y URLs remotas;
- no descarga ni guarda imágenes en GitHub;
- conserva el último cuadro válido cuando un producto falla.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import unicodedata
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests


CONFIG_PATH = Path("config/productos.json")
OUTPUT_PATH = Path("docs/manifiesto.json")

RADAR_PAGE_URL = "https://ws2.smn.gob.ar/radar"
INVENTORY_BASE_URL = "https://ws1.smn.gob.ar/v1/images/radar/"
STATIC_BASE_URL = "https://estaticos.smn.gob.ar/vmsr/radar/"

ARGENTINA_TZ = ZoneInfo("America/Argentina/Buenos_Aires")

MAX_FRAMES = 24
ANIMATION_FRAMES = 12
FRESH_MINUTES = 30
DELAYED_MINUTES = 180

BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}

PRODUCT_ID_RE = re.compile(
    r"^(?:COMP_(?:ARG|CEN|NOR)|(?:ANG|PAR|PER|RMA\d+)_240)$"
)

TIMESTAMP_PATTERNS = (
    re.compile(r"(?P<date>\d{8})[_-](?P<time>\d{6})Z", re.IGNORECASE),
    re.compile(r"(?P<date>\d{8})(?P<time>\d{6})Z", re.IGNORECASE),
)

IMAGE_EXTENSION_RE = re.compile(
    r"\.(?:png|jpe?g|webp|gif)$",
    re.IGNORECASE,
)


class TokenRejected(RuntimeError):
    """El inventario rechazó el JWT temporal."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Actualizar catálogo remoto de radares del SMN."
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.5,
        help="Pausa entre inventarios.",
    )
    parser.add_argument(
        "--http-attempts",
        type=int,
        default=4,
        help="Intentos HTTP por solicitud.",
    )
    parser.add_argument(
        "--retry-base-seconds",
        type=float,
        default=2.0,
        help="Base exponencial de reintentos.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=35.0,
        help="Timeout HTTP.",
    )
    return parser.parse_args()


def now_argentina() -> datetime:
    return datetime.now(ARGENTINA_TZ)


def iso_argentina(value: datetime | None = None) -> str:
    current = value or now_argentina()
    return current.isoformat(timespec="seconds")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_existing() -> dict[str, Any] | None:
    if not OUTPUT_PATH.exists():
        return None

    try:
        value = load_json(OUTPUT_PATH)
    except (OSError, ValueError):
        return None

    return value if isinstance(value, dict) else None


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_config() -> dict[str, Any]:
    value = load_json(CONFIG_PATH)

    if not isinstance(value, dict):
        raise RuntimeError("La configuración no es un objeto JSON.")

    products = value.get("products")
    if not isinstance(products, list) or not products:
        raise RuntimeError("La configuración no contiene productos.")

    return value


def request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    *,
    attempts: int,
    retry_base_seconds: float,
    timeout_seconds: float,
    headers: dict[str, str],
) -> requests.Response:
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            response = session.request(
                method,
                url,
                headers=headers,
                timeout=timeout_seconds,
            )

            if response.status_code in (408, 425, 429, 500, 502, 503, 504):
                raise requests.HTTPError(
                    f"HTTP temporal {response.status_code}",
                    response=response,
                )

            return response

        except requests.RequestException as exc:
            last_error = exc

            if attempt >= attempts:
                break

            wait_seconds = retry_base_seconds * (2 ** (attempt - 1))
            print(
                f"Reintento {attempt}/{attempts} para {url} "
                f"en {wait_seconds:.1f} s: {exc}"
            )
            time.sleep(wait_seconds)

    raise RuntimeError(
        f"No se pudo consultar {url}: {last_error}"
    )


def extract_token(page_html: str) -> str | None:
    patterns = (
        r"localStorage\.setItem\(\s*['\"]token['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)",
        r"localStorage\.setItem\(\s*`token`\s*,\s*`([^`]+)`\s*\)",
        r"['\"]token['\"]\s*:\s*['\"]([^'\"]+)['\"]",
        r"(eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)",
    )

    for pattern in patterns:
        match = re.search(pattern, page_html)
        if not match:
            continue

        token = match.group(1).strip()
        if token.count(".") == 2 and len(token) > 40:
            return token

    return None


def parse_products_from_page(page_html: str) -> dict[str, str]:
    """Extrae IDs y rótulos si la página los incluye en el HTML."""
    discovered: dict[str, str] = {}

    option_re = re.compile(
        r"<option[^>]*value=['\"]([^'\"]+)['\"][^>]*>(.*?)</option>",
        re.IGNORECASE | re.DOTALL,
    )

    for product_id, raw_label in option_re.findall(page_html):
        product_id = product_id.strip()
        if not PRODUCT_ID_RE.fullmatch(product_id):
            continue

        label = re.sub(r"<[^>]+>", " ", raw_label)
        label = html.unescape(re.sub(r"\s+", " ", label)).strip()
        if label:
            discovered[product_id] = label

    for product_id in re.findall(
        r"(?:COMP_(?:ARG|CEN|NOR)|(?:ANG|PAR|PER|RMA\d+)_240)",
        page_html,
    ):
        if PRODUCT_ID_RE.fullmatch(product_id):
            discovered.setdefault(product_id, product_id)

    return discovered


def get_radar_page(
    session: requests.Session,
    *,
    attempts: int,
    retry_base_seconds: float,
    timeout_seconds: float,
) -> tuple[str, str]:
    response = request_with_retry(
        session,
        "GET",
        RADAR_PAGE_URL,
        attempts=attempts,
        retry_base_seconds=retry_base_seconds,
        timeout_seconds=timeout_seconds,
        headers={
            **BASE_HEADERS,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    response.raise_for_status()

    token = extract_token(response.text)
    if not token:
        raise RuntimeError(
            "No se encontró el JWT temporal en la página oficial de radar."
        )

    return token, response.text


def inventory_headers(token: str) -> dict[str, str]:
    return {
        **BASE_HEADERS,
        "Accept": "application/json",
        "Authorization": f"JWT {token}",
        "Origin": "https://www.smn.gob.ar",
        "Referer": RADAR_PAGE_URL,
    }


def request_inventory(
    session: requests.Session,
    product_id: str,
    token: str,
    *,
    attempts: int,
    retry_base_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    url = INVENTORY_BASE_URL + product_id

    response = request_with_retry(
        session,
        "GET",
        url,
        attempts=attempts,
        retry_base_seconds=retry_base_seconds,
        timeout_seconds=timeout_seconds,
        headers=inventory_headers(token),
    )

    if response.status_code in (401, 403):
        raise TokenRejected(
            f"El inventario {product_id} rechazó el token."
        )

    if response.status_code == 404:
        raise RuntimeError(f"Producto no encontrado: {product_id}")

    response.raise_for_status()

    try:
        value = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"El inventario {product_id} no devolvió JSON válido."
        ) from exc

    if not isinstance(value, dict):
        raise RuntimeError(
            f"El inventario {product_id} no es un objeto JSON."
        )

    return value


def find_inventory_object(value: dict[str, Any]) -> dict[str, Any]:
    if isinstance(value.get("list"), list):
        return value

    for key in ("data", "result", "results", "item"):
        child = value.get(key)
        if isinstance(child, dict) and isinstance(child.get("list"), list):
            return child

    raise RuntimeError("La respuesta no contiene la lista de imágenes.")


def parse_frame(filename: str) -> dict[str, Any] | None:
    filename = filename.strip()

    if not IMAGE_EXTENSION_RE.search(filename):
        return None

    match = None
    for pattern in TIMESTAMP_PATTERNS:
        match = pattern.search(filename)
        if match:
            break

    if not match:
        return None

    try:
        utc_dt = datetime.strptime(
            match.group("date") + match.group("time"),
            "%Y%m%d%H%M%S",
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return None

    local_dt = utc_dt.astimezone(ARGENTINA_TZ)

    return {
        "filename": filename,
        "url": STATIC_BASE_URL + filename,
        "timestamp_utc": (
            utc_dt.isoformat(timespec="seconds").replace("+00:00", "Z")
        ),
        "timestamp_argentina": local_dt.isoformat(timespec="seconds"),
    }


def classify_status(
    latest_local: datetime | None,
    *,
    query_ok: bool,
    has_frames: bool,
) -> tuple[str, int | None]:
    if not query_ok:
        return ("stale" if has_frames else "error"), None

    if latest_local is None:
        return "no_data", None

    age_minutes = max(
        0,
        int((now_argentina() - latest_local).total_seconds() // 60),
    )

    if age_minutes <= FRESH_MINUTES:
        return "ok", age_minutes
    if age_minutes <= DELAYED_MINUTES:
        return "delayed", age_minutes
    return "stale", age_minutes


def previous_product_map(
    manifest: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if not manifest:
        return {}

    products = manifest.get("products")
    if not isinstance(products, list):
        return {}

    return {
        str(product["id"]): product
        for product in products
        if isinstance(product, dict) and product.get("id")
    }


def normalize_label(value: str) -> str:
    value = re.sub(r"\([^)]*\)", " ", value)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        character
        for character in value
        if not unicodedata.combining(character)
    )
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def merge_products(
    config: dict[str, Any],
    discovered: dict[str, str],
) -> list[dict[str, Any]]:
    """
    Combina la configuración de respaldo con los valores publicados en la
    página oficial.

    El nombre oficial tiene prioridad para corregir posibles reasignaciones
    de ID sin duplicar el mismo radar.
    """
    configured = [
        deepcopy(item)
        for item in config["products"]
        if isinstance(item, dict) and item.get("id")
    ]

    by_id = {str(item["id"]): item for item in configured}
    by_name = {
        normalize_label(str(item.get("name", ""))): item
        for item in configured
        if item.get("name")
    }

    next_order = max(
        (int(item.get("order", 0)) for item in configured),
        default=100,
    ) + 1

    for product_id, label in discovered.items():
        if product_id in by_id:
            if label != product_id:
                by_id[product_id]["official_label"] = label
            continue

        normalized_label = normalize_label(label)
        matched = by_name.get(normalized_label)

        if matched is not None:
            old_id = str(matched["id"])
            by_id.pop(old_id, None)

            matched["fallback_id"] = old_id
            matched["id"] = product_id
            matched["official_label"] = label
            matched["discovered_automatically"] = True

            by_id[product_id] = matched
            continue

        item = {
            "id": product_id,
            "name": label,
            "type": (
                "mosaic" if product_id.startswith("COMP_") else "radar"
            ),
            "province": None,
            "order": next_order,
            "discovered_automatically": True,
        }
        next_order += 1
        configured.append(item)
        by_id[product_id] = item
        by_name[normalized_label] = item

    # Elimina duplicados que pudieran quedar por una reasignación.
    unique: dict[str, dict[str, Any]] = {}
    for item in configured:
        unique[str(item["id"])] = item

    result = list(unique.values())
    result.sort(
        key=lambda item: (
            int(item.get("order", 9999)),
            str(item.get("name", "")),
        )
    )
    return result


def build_product_from_inventory(
    definition: dict[str, Any],
    inventory_response: dict[str, Any],
) -> dict[str, Any]:
    inventory = find_inventory_object(inventory_response)
    raw_list = inventory.get("list", [])

    frames_by_name: dict[str, dict[str, Any]] = {}

    for raw_item in raw_list:
        if not isinstance(raw_item, str):
            continue

        frame = parse_frame(raw_item)
        if frame:
            frames_by_name[frame["filename"]] = frame

    frames = sorted(
        frames_by_name.values(),
        key=lambda frame: frame["timestamp_utc"],
    )[-MAX_FRAMES:]

    latest = frames[-1] if frames else None
    latest_local = (
        datetime.fromisoformat(latest["timestamp_argentina"])
        if latest
        else None
    )
    status, age_minutes = classify_status(
        latest_local,
        query_ok=True,
        has_frames=bool(frames),
    )

    api_region = inventory.get("region")
    api_product = inventory.get("product")
    api_id = inventory.get("id")

    if str(definition.get("type")) == "mosaic":
        name = str(
            definition.get("official_label")
            or definition.get("name")
            or api_region
            or definition["id"]
        )
    else:
        name = str(
            api_region
            or definition.get("official_label")
            or definition.get("name")
            or definition["id"]
        )

    return {
        "id": str(definition["id"]),
        "name": name,
        "type": str(definition.get("type") or "radar"),
        "province": definition.get("province"),
        "status": status,
        "age_minutes": age_minutes,
        "updated_at": (
            latest["timestamp_argentina"] if latest else None
        ),
        "counts": {
            "frames": len(frames),
            "animation_frames": min(len(frames), ANIMATION_FRAMES),
        },
        "latest": latest,
        "animation_frames": frames[-ANIMATION_FRAMES:],
        "frames": frames,
        "source": {
            "inventory_endpoint": INVENTORY_BASE_URL
            + str(definition["id"]),
            "static_base_url": STATIC_BASE_URL,
            "api_id": api_id,
            "api_product": api_product,
            "api_region": api_region,
        },
        "last_error": None,
    }


def build_failed_product(
    definition: dict[str, Any],
    previous: dict[str, Any] | None,
    message: str,
) -> dict[str, Any]:
    if previous:
        product = deepcopy(previous)
        product["status"] = "stale"
        product["last_error"] = message
        product["age_minutes"] = None
        return product

    return {
        "id": str(definition["id"]),
        "name": str(definition.get("name") or definition["id"]),
        "type": str(definition.get("type") or "radar"),
        "province": definition.get("province"),
        "status": "error",
        "age_minutes": None,
        "updated_at": None,
        "counts": {
            "frames": 0,
            "animation_frames": 0,
        },
        "latest": None,
        "animation_frames": [],
        "frames": [],
        "source": {
            "inventory_endpoint": INVENTORY_BASE_URL
            + str(definition["id"]),
            "static_base_url": STATIC_BASE_URL,
            "api_id": None,
            "api_product": None,
            "api_region": None,
        },
        "last_error": message,
    }


def manifest_signature(manifest: dict[str, Any] | None) -> str | None:
    if not manifest:
        return None

    compact_products = []

    for product in manifest.get("products", []):
        if not isinstance(product, dict):
            continue

        compact_products.append(
            {
                "id": product.get("id"),
                "name": product.get("name"),
                "status": product.get("status"),
                "frames": [
                    frame.get("filename")
                    for frame in product.get("frames", [])
                    if isinstance(frame, dict)
                ],
                "last_error": product.get("last_error"),
            }
        )

    compact = {
        "enabled": manifest.get("enabled"),
        "default_product_id": manifest.get("default_product_id"),
        "products": compact_products,
    }

    return json.dumps(
        compact,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def build_manifest(
    products: list[dict[str, Any]],
    default_product_id: str,
) -> dict[str, Any]:
    statuses = [
        str(product.get("status"))
        for product in products
    ]

    available = sum(
        1 for product in products if product.get("latest")
    )
    errors = sum(
        1 for status in statuses if status == "error"
    )
    stale_or_error = sum(
        1 for status in statuses if status in {"stale", "error"}
    )

    overall_status = "ok"
    if available == 0:
        overall_status = "error"
    elif stale_or_error or "no_data" in statuses:
        overall_status = "partial"

    generated_at = iso_argentina()

    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "last_success_at": (
            generated_at if overall_status == "ok" else None
        ),
        "enabled": True,
        "status": overall_status,
        "default_product_id": default_product_id,
        "source": {
            "name": "Servicio Meteorológico Nacional",
            "radar_page": RADAR_PAGE_URL,
            "inventory_base_url": INVENTORY_BASE_URL,
            "static_base_url": STATIC_BASE_URL,
        },
        "storage": {
            "mode": "remote_urls_only",
            "stored_image_count": 0,
        },
        "freshness": {
            "fresh_minutes": FRESH_MINUTES,
            "delayed_minutes": DELAYED_MINUTES,
        },
        "counts": {
            "products": len(products),
            "mosaics": sum(
                1 for product in products
                if product.get("type") == "mosaic"
            ),
            "radars": sum(
                1 for product in products
                if product.get("type") == "radar"
            ),
            "available": available,
            "ok": statuses.count("ok"),
            "delayed": statuses.count("delayed"),
            "stale": statuses.count("stale"),
            "no_data": statuses.count("no_data"),
            "errors": errors,
        },
        "products": products,
    }


def main() -> int:
    args = parse_args()
    config = load_config()
    previous_manifest = read_existing()
    previous_by_id = previous_product_map(previous_manifest)

    session = requests.Session()

    try:
        token, radar_page_html = get_radar_page(
            session,
            attempts=args.http_attempts,
            retry_base_seconds=args.retry_base_seconds,
            timeout_seconds=args.timeout_seconds,
        )
    except Exception as exc:
        print(f"No se pudo iniciar la actualización: {exc}")
        return 1

    discovered = parse_products_from_page(radar_page_html)
    definitions = merge_products(config, discovered)

    print(
        f"Productos configurados/descubiertos: {len(definitions)}"
    )

    products: list[dict[str, Any]] = []

    for index, definition in enumerate(definitions, start=1):
        product_id = str(definition["id"])
        print(
            f"[{index}/{len(definitions)}] Consultando {product_id}..."
        )

        try:
            try:
                response = request_inventory(
                    session,
                    product_id,
                    token,
                    attempts=args.http_attempts,
                    retry_base_seconds=args.retry_base_seconds,
                    timeout_seconds=args.timeout_seconds,
                )
            except TokenRejected:
                print("JWT rechazado. Solicitando uno nuevo...")
                token, _ = get_radar_page(
                    session,
                    attempts=args.http_attempts,
                    retry_base_seconds=args.retry_base_seconds,
                    timeout_seconds=args.timeout_seconds,
                )
                response = request_inventory(
                    session,
                    product_id,
                    token,
                    attempts=args.http_attempts,
                    retry_base_seconds=args.retry_base_seconds,
                    timeout_seconds=args.timeout_seconds,
                )

            product = build_product_from_inventory(
                definition,
                response,
            )
            products.append(product)

            print(
                f"  {product['name']}: "
                f"{product['counts']['frames']} cuadros, "
                f"estado {product['status']}."
            )

        except Exception as exc:
            message = str(exc)
            print(f"  Error: {message}")

            products.append(
                build_failed_product(
                    definition,
                    previous_by_id.get(product_id),
                    message,
                )
            )

        if index < len(definitions):
            time.sleep(max(0.0, args.sleep_seconds))

    manifest = build_manifest(
        products,
        str(config.get("default_product_id") or "COMP_ARG"),
    )

    previous_signature = manifest_signature(previous_manifest)
    new_signature = manifest_signature(manifest)

    if previous_signature == new_signature:
        print(
            "El SMN todavía no publicó cuadros o estados nuevos. "
            "No se modifica el manifiesto."
        )
        return 0

    write_json_atomic(OUTPUT_PATH, manifest)

    print(
        "Catálogo actualizado: "
        f"{manifest['counts']['available']}/"
        f"{manifest['counts']['products']} productos con imágenes."
    )
    print(
        "Almacenamiento: solo URLs remotas; "
        "0 imágenes guardadas en GitHub."
    )

    return 0 if manifest["counts"]["available"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())

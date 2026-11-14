"""
import_places.py - Remplit la table places depuis OpenStreetMap (Atlantique).

Usage, depuis backend/ avec DATABASE_URL défini :
    python scripts/import_places.py
"""

import os
import sys

import osmnx as ox
import psycopg

PLACE = "Atlantique, Bénin"
TAGS = {
    "amenity": ["marketplace", "school", "hospital", "clinic", "university",
                "place_of_worship", "bus_station"],
    "place": ["neighbourhood", "suburb", "village", "town"],
}


def main() -> None:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        sys.exit("DATABASE_URL manquant")

    gdf = ox.features_from_place(PLACE, tags=TAGS)
    gdf = gdf[gdf.geometry.notna()]

    rows = []
    for _, row in gdf.iterrows():
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        point = row.geometry if row.geometry.geom_type == "Point" else row.geometry.centroid
        amenity = row.get("amenity")
        category = amenity if isinstance(amenity, str) else row.get("place")
        rows.append((name.strip(), category, point.x, point.y))

    with psycopg.connect(dsn) as conn:
        conn.execute("truncate places restart identity")
        with conn.cursor() as cur:
            cur.executemany(
                "insert into places (name, category, geom) values "
                "(%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography)",
                rows,
            )
    print(f"{len(rows)} lieux importés")


if __name__ == "__main__":
    main()
"use client";

import { useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type PlaceHit = { id: number; name: string; lat: number; lon: number };

type Props = {
  label: string;
  placeholder: string;
  onSelect: (place: PlaceHit) => void;
};

export default function SearchBox({ label, placeholder, onSelect }: Props) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<PlaceHit[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const justPicked = useRef(false);

  useEffect(() => {
    if (justPicked.current) {
      justPicked.current = false;
      return;
    }
    if (q.trim().length < 2) {
      setHits([]);
      setOpen(false);
      return;
    }
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true);
      fetch(`${API}/places?${new URLSearchParams({ q: q.trim() })}`, {
        signal: ctrl.signal,
      })
        .then((r) => (r.ok ? r.json() : []))
        .then((d: PlaceHit[]) => {
          setHits(d);
          setOpen(true);
        })
        .catch((e) => {
          if (e.name !== "AbortError") setHits([]);
        })
        .finally(() => {
          if (!ctrl.signal.aborted) setLoading(false);
        });
    }, 300); // délai de 300 ms pour ne pas saturer l'API
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [q]);

  return (
    <div style={{ position: "relative", marginBottom: 8 }}>
      <input
        aria-label={label}
        placeholder={placeholder}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => hits.length > 0 && setOpen(true)}
        style={{
          width: "100%",
          padding: "8px 10px",
          border: "1px solid #d1d5db",
          borderRadius: 8,
          fontSize: 14,
        }}
      />
      {open && (
        <ul
          style={{
            position: "absolute",
            zIndex: 20,
            left: 0,
            right: 0,
            margin: 0,
            padding: 0,
            listStyle: "none",
            background: "#fff",
            border: "1px solid #d1d5db",
            borderRadius: 8,
            maxHeight: 220,
            overflowY: "auto",
          }}
        >
          {loading && <li style={{ padding: 8 }}>Recherche…</li>}
          {!loading && hits.length === 0 && (
            <li style={{ padding: 8 }}>Aucun lieu trouvé</li>
          )}
          {hits.map((h) => (
            <li
              key={h.id}
              style={{ padding: 8, cursor: "pointer" }}
              onMouseDown={() => {
                justPicked.current = true;
                setQ(h.name);
                setOpen(false);
                onSelect(h);
              }}
            >
              {h.name}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
#!/usr/bin/env bash
# Refuser les fichiers Python > 1500 lignes.
# Les fichiers déjà au-dessus sont tolérés (snapshot), mais ne peuvent pas grossir.
set -euo pipefail

MAX_LINES=1500
SNAPSHOT_FILE="scripts/.monster_baseline.txt"
fail=0

# Lire la baseline (fichiers tolérés en l'état)
declare -A baseline=()
if [ -f "$SNAPSHOT_FILE" ]; then
    while IFS=$'\t' read -r path lines; do
        [ -n "$path" ] && baseline["$path"]=$lines
    done < "$SNAPSHOT_FILE"
fi

for f in "$@"; do
    # Ne compter que les fichiers existants
    [ -f "$f" ] || continue
    n=$(wc -l < "$f" | tr -d ' ')

    if [ "$n" -le "$MAX_LINES" ]; then
        continue
    fi

    # Au-dessus de la limite : autorisé seulement si déjà dans baseline ET pas plus long
    base=${baseline["$f"]:-0}
    if [ "$base" -ge "$n" ] && [ "$base" -gt 0 ]; then
        # Toléré : n'a pas grossi par rapport au snapshot
        continue
    fi

    echo "❌ $f : $n lignes (> $MAX_LINES). Découper avant de committer." >&2
    if [ "$base" -gt 0 ]; then
        echo "   (baseline = $base lignes, ce commit ferait grossir le fichier)" >&2
    fi
    fail=1
done

exit $fail

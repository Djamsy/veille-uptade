#!/usr/bin/env bash
# Refuser les noms qui trahissent le pattern "je recrée à côté".
set -euo pipefail

fail=0
patterns='(_v[0-9]+\.py$|_new\.py$|_unified\.py$|_no_ollama\.py$| copie\.py$|_copy\.py$|_old\.py$|_backup\.py$| [0-9]+\.py$)'

for f in "$@"; do
    if echo "$f" | grep -qE "$patterns"; then
        echo "❌ $f : nom interdit (variante de fichier laissée à côté de l'original)." >&2
        echo "   → remplace l'original ou nomme par fonctionnalité, pas par version." >&2
        fail=1
    fi
done

exit $fail

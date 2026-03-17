#!/bin/bash
echo "Récupération des composants depuis les fichiers RTF..."

for file in app/dashboard/*.rtf; do
    if [[ -f "$file" ]]; then
        basename=$(basename "$file" .rtf)
        echo "Récupération de $basename..."
        
        # Extraire le contenu entre les balises de code TypeScript
        # (cette méthode peut nécessiter un ajustement selon le contenu exact)
        output_file="app/dashboard/recovered_$basename"
        echo "// Récupéré depuis $file" > "$output_file"
        echo "" >> "$output_file"
        
        # Afficher les premières lignes pour vérification
        head -20 "$file"
        echo "---"
    fi
done

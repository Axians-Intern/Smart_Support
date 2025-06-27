from flask import Flask, render_template, request
import requests
import sqlite3
import os
import re

app = Flask(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2"

# === Database schema for the AI ===
schema = """
Table: ressources
- id, nom, prenom, email, id_entreprise, type, id_profil, ecole, specialite, date_debut_carriere, created_at, updated_at

Table: certifications
- id, id_formation, id_constructeur, id_ressource, d_obtention, d_fin_validite

Table: formations
- id, libelle, id_constructeur, id_sous_expertise, nb_heures, id_domaine

Table: diplomes
- id, id_ressource, libelle, ecole, date_obtention

Table: experiences_pro
- id, id_ressource, client, libelle_projet, date_debut, date_fin

Table: competences
- id, id_sous_expertise, id_constructeur, id_solution, id_ressource, note_avv, note_integration, note_support

Table: entreprises
- id, libelle, id_ce, id_direction

Table: direction
- id, libelle

Table: expertises
- id, libelle

Table: domaines
- id, libelle

Table: constructeur
- id, libelle, strategique

Table: sous_expertises
- id, id_expertise, libelle

Table: solutions
- id, id_constructeur, id_sous_expertises, libelle

Table: z_lov
- id, code, libelle

Table: z_lov_value
- id, id_lov, code, libelle

Table: organismes_preconises
- id, nom

Table: alembic_version
- version_num
"""

# Improved prompt for better LLM output
def build_prompt(message):
    return f"""
Tu es un assistant expert SQL.

Voici le schéma simplifié de la base de données :
{schema}

Ta tâche :
- Lis le message ci-dessous et génère une requête SQL, compatible uniquement avec SQLite, pour répondre à la question.
- Utilise toujours les noms de tables et colonnes dans le schéma.
- N’invente jamais de nouvelles tables ou colonnes.
- Si la question ne concerne pas la base, ou que tu n’es pas sûr, réponds uniquement « Je ne sais pas ».
- Si la question est confuse, réponds uniquement « Je ne sais pas ».
- Ta réponse DOIT ÊTRE une requête SQL brute, jamais du texte.
- Ne mets jamais de commentaires, ni de code block.

**Exemples :**

Q: Quels employés ont le certificat CCNA ?
R: SELECT r.nom, r.prenom FROM ressources r JOIN certifications c ON r.id = c.id_ressource JOIN formations f ON c.id_formation = f.id WHERE f.libelle = 'CCNA';

Q : Liste tous les certificats obtenus par Oumaima BAHIL
R : SELECT f.libelle AS certificat FROM certifications c JOIN formations f ON c.id_formation = f.id JOIN ressources r ON c.id_ressource = r.id WHERE r.prenom = 'Oumaima' AND r.nom = 'BAHIL';

Q: Meow
R: Je ne sais pas
Q : Liste tous les employés  
R :
SELECT nom, prenom FROM ressources;

Q : Donne tous les certificats obtenus par Rihab NIKH  
R :
SELECT f.libelle AS certificat
FROM certifications c
JOIN formations f ON c.id_formation = f.id
JOIN ressources r ON c.id_ressource = r.id
WHERE r.prenom = 'Rihab' AND r.nom = 'NIKH';

Q : Liste toutes les formations disponibles  
R :
SELECT libelle FROM formations;

Q : Liste tous les diplômes de Ahmed Zouhair  
R :
SELECT d.libelle AS diplome, d.ecole, d.date_obtention
FROM diplomes d
JOIN ressources r ON d.id_ressource = r.id
WHERE r.prenom = 'Ahmed' AND r.nom = 'Zouhair';

Q : Quelles sont les expériences professionnelles de Oumaima BAHIL ?  
R :
SELECT e.client, e.libelle_projet, e.date_debut, e.date_fin
FROM experiences_pro e
JOIN ressources r ON e.id_ressource = r.id
WHERE r.prenom = 'Oumaima' AND r.nom = 'BAHIL';

Q : Donne les compétences de Yassine Karimi  
R :
SELECT c.id_sous_expertise, c.note_avv, c.note_integration, c.note_support
FROM competences c
JOIN ressources r ON c.id_ressource = r.id
WHERE r.prenom = 'Yassine' AND r.nom = 'Karimi';

Q : Liste toutes les entreprises  
R :
SELECT libelle FROM entreprises;

Q : Liste toutes les directions  
R :
SELECT libelle FROM direction;

Q : Liste toutes les expertises  
R :
SELECT libelle FROM expertises;

Q : Liste tous les domaines  
R :
SELECT libelle FROM domaines;

Q : Liste tous les constructeurs  
R :
SELECT libelle, strategique FROM constructeur;

Q : Liste toutes les sous-expertises  
R :
SELECT libelle FROM sous_expertises;

Q : Liste toutes les solutions disponibles  
R :
SELECT libelle FROM solutions;

Q : Liste tous les codes et libellés de z_lov  
R :
SELECT code, libelle FROM z_lov;

Q : Liste tous les codes de valeurs pour z_lov_value  
R :
SELECT code, libelle FROM z_lov_value;

Q : Liste tous les organismes préconisés  
R :
SELECT nom FROM organismes_preconises;

Q : Donne le numéro de version alembic  
R :
SELECT version_num FROM alembic_version;

-- 🟦 Guide pour les jointures sur ce schéma

-- 1️⃣ Jointure Ressources ↔ Certifications ↔ Formations
-- But : Obtenir les certificats d’un employé.
SELECT f.libelle AS certificat
FROM certifications c
JOIN formations f ON c.id_formation = f.id
JOIN ressources r ON c.id_ressource = r.id
WHERE r.nom = 'NOM' AND r.prenom = 'PRENOM';
-- certifications relie un employé (id_ressource) à une formation (id_formation).
-- On joint les trois pour trouver les certificats d’un employé précis.

-- 2️⃣ Jointure Ressources ↔ Diplômes
-- But : Trouver les diplômes d’un employé.
SELECT d.libelle, d.ecole, d.date_obtention
FROM diplomes d
JOIN ressources r ON d.id_ressource = r.id
WHERE r.nom = 'NOM' AND r.prenom = 'PRENOM';
-- diplomes référence directement l’employé par id_ressource.

-- 3️⃣ Jointure Ressources ↔ Experiences_pro
-- But : Voir les expériences pro d’un employé.
SELECT e.client, e.libelle_projet, e.date_debut, e.date_fin
FROM experiences_pro e
JOIN ressources r ON e.id_ressource = r.id
WHERE r.nom = 'NOM' AND r.prenom = 'PRENOM';

-- 4️⃣ Jointure Ressources ↔ Entreprises
-- But : Savoir dans quelle entreprise travaille un employé.
SELECT r.nom, r.prenom, e.libelle AS entreprise
FROM ressources r
JOIN entreprises e ON r.id_entreprise = e.id;

-- 5️⃣ Jointure Competences ↔ Ressources
-- But : Voir les compétences d’un employé.
SELECT c.id_sous_expertise, c.note_avv, c.note_integration, c.note_support
FROM competences c
JOIN ressources r ON c.id_ressource = r.id
WHERE r.nom = 'NOM' AND r.prenom = 'PRENOM';

-- 6️⃣ Jointure sous_expertises ↔ expertises
-- But : Lister toutes les sous-expertises d’une expertise.
SELECT s.libelle AS sous_expertise, e.libelle AS expertise
FROM sous_expertises s
JOIN expertises e ON s.id_expertise = e.id;

-- 7️⃣ Jointure solutions ↔ constructeur
-- But : Lister toutes les solutions par constructeur.
SELECT s.libelle AS solution, c.libelle AS constructeur
FROM solutions s
JOIN constructeur c ON s.id_constructeur = c.id;

-- Pour lister les infos d’une table reliée par une colonne qui contient un identifiant (id_ressource, id_formation, etc.), utilise JOIN avec la clé correspondante.
-- Si la question demande un “détail” (nom, label, etc.), il faut rejoindre la table contenant ce détail.

-- Résumé visuel :
-- Pour retrouver l’info :
-- - Identifie la clé étrangère (colonne qui référence une autre table, ex. id_ressource)
-- - JOIN sur cette colonne avec la clé primaire de l’autre table (id)
-- - Ajoute le filtre selon la question (WHERE...)
-Quand le message contient deux mots pour une personne, le premier mot correspond au nom, le second au prénom

Utilise toujours LOWER() ou LIKE dans les clauses WHERE sur nom/prénom pour ignorer la casse.
Q: {message}
"""

def call_qwen2(prompt):
    data = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }
    try:
        response = requests.post(OLLAMA_URL, json=data)
        response.raise_for_status()
        result_json = response.json()
        reply = result_json["response"]
        return reply.strip(), None
    except Exception as e:
        return None, f"❌ Erreur de réponse IA : {e}"

def clean_sql(raw_sql):
    # Remove code block markers and 'sql'
    lines = raw_sql.strip().splitlines()
    lines = [line for line in lines if not line.strip().startswith("```") and line.strip() != "sql"]
    return "\n".join(lines).strip()

def fix_sqlite_intervals(sql):
    # Replace MySQL/Postgres interval with SQLite format
    pattern = r"DATE\((.*?)\)\s*-\s*INTERVAL\s*'(\d+)\s*(year|month|day|years|months|days)'\s*"
    def replacer(match):
        date_expr = match.group(1)
        amount = match.group(2)
        unit = match.group(3)
        if not unit.endswith('s'):
            unit += 's'
        return f"DATE({date_expr}, '-{amount} {unit}')"
    return re.sub(pattern, replacer, sql, flags=re.IGNORECASE)

@app.route("/", methods=["GET", "POST"])
def index():
    sql = result = ""
    confirmation = False

    if request.method == "POST":
        message = request.form.get("mail_message", "").strip()

        if not message:
            result = "❌ Veuillez écrire un message."
            confirmation = True
            return render_template("index.html", sql=sql, result=result, confirmation=confirmation)

        greetings = [
            "hello", "hi", "bonjour", "salut", "coucou", "cava", "cava?", "meow", "yo", "hey", "cc", "wesh"
        ]
        if message.lower() in greetings:
            result = "👋 Hello! Pose-moi une question sur la base de données (ex : 'Quels sont les employés ayant le certificat CCNA ?')"
            sql = ""
            confirmation = True
            return render_template("index.html", sql=sql, result=result, confirmation=confirmation)

        full_prompt = build_prompt(message)
        sql, error_ia = call_qwen2(full_prompt)

        if sql:
            sql = clean_sql(sql)
            sql = sql.replace("resources", "ressources").replace("Resources", "ressources")
            sql = fix_sqlite_intervals(sql)

        # PROTECT: Don't execute if not a SELECT, or LLM says "Je ne sais pas", or if no table from schema
        if error_ia:
            result = error_ia
        elif "je ne sais pas" in sql.lower():
            result = "😅 Désolé, je ne sais pas répondre à cette question."
        elif not sql.lower().startswith("select"):
            result = "❌ L’IA n’a pas généré une requête SQL valide."
        elif not any(t in sql.lower() for t in [
            "ressources", "certifications", "formations", "diplomes", "experiences_pro",
            "competences", "entreprises", "direction", "expertises", "domaines", "constructeur",
            "sous_expertises", "solutions", "z_lov", "z_lov_value", "organismes_preconises"
        ]):
            result = "❌ La requête ne correspond à aucune table connue."
        else:
            try:
                conn = sqlite3.connect("app.db")
                cursor = conn.cursor()
                cursor.execute(sql)
                rows = cursor.fetchall()
                columns = [description[0] for description in cursor.description]
                conn.close()

                if rows:
                    # Remove duplicate rows for clean display
                    unique_rows = []
                    for row in rows:
                        if row not in unique_rows:
                            unique_rows.append(row)
                    rows = unique_rows

                    # Pretty HTML table with nulls as empty cells
                    result = "<table><tr>"
                    for col in columns:
                        result += f"<th>{col}</th>"
                    result += "</tr>"
                    for row in rows:
                        result += "<tr>"
                        for cell in row:
                            result += f"<td>{cell if cell is not None else ''}</td>"
                        result += "</tr>"
                    result += "</table>"
                else:
                    result = "Aucun résultat trouvé."
            except Exception as e:
                result = f"❌ Erreur SQL : {e}"

        confirmation = True

    return render_template("index.html", sql=sql, result=result, confirmation=confirmation)

if __name__ == "__main__":
    app.run(debug=True)

from flask import Flask, render_template, request
import requests
import sqlite3
import os
import re

app = Flask(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "phi3"

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
# To get employees certified in a formation, use:
# ressources JOIN certifications ON ressources.id = certifications.id_ressource
#             JOIN formations ON certifications.id_formation = formations.id
# and filter formations.libelle by the certification name (example: 'CCNA')
"""

def call_phi3(prompt):
    data = {
        "model": "phi3",
        "prompt": prompt,
        "stream": False
    }
    try:
        response = requests.post(OLLAMA_URL, json=data)
        response.raise_for_status()
        result_json = response.json()
        print("🧠 Réponse JSON brute de l'IA :", result_json)
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

        # Add: handle greetings or irrelevant messages
        greetings = [
            "hello", "hi", "bonjour", "salut", "coucou", "cava", "cava?", "meow", "yo", "hey", "cc", "wesh"
        ]
        if message.lower() in greetings:
            result = "👋 Hello! Pose-moi une question sur la base de données (ex : 'Quels sont les employees ayant certificat CCNA ?')"
            sql = ""
            confirmation = True
            return render_template("index.html", sql=sql, result=result, confirmation=confirmation)

        full_prompt = f"""
Tu es un expert SQL.

Voici le schéma simplifié de la base de données :

{schema}

IMPORTANT :
- Utilise uniquement les noms de tables et de colonnes exactement comme dans le schéma ci-dessus.
- N’invente jamais de nouveaux noms de tables ou colonnes.
- Si la question concerne des personnes, la table s’appelle ‘ressources’ (et pas ‘resources’).
- Génère du SQL **compatible uniquement avec SQLite** (pas MySQL, ni Postgres).
- Pour les dates, utilise les fonctions SQLite (par exemple, DATE(), datetime(), julianday()).
- Si tu ne sais pas, dis-le.

Lis attentivement le message suivant, et génère une requête SQL SQLite valide **sans erreur** pour y répondre :

\"{message}\"

Ta réponse doit être une requête SQL uniquement, sans commentaire.
Quand la question est “liste”, ne donne que le strict minimum (nom, prénom).
Ne mets pas de code block, juste le SQL brut.
Si tu n’as pas compris la question, réponds par "Je ne sais pas".
Si la question n'a aucun sens, ou ne concerne pas la base, réponds toujours par "Je ne sais pas".
Ne mets pas de code block, juste le SQL brut.
"""

        sql, error_ia = call_phi3(full_prompt)

        if sql:
            sql = clean_sql(sql)
            sql = sql.replace("resources", "ressources").replace("Resources", "ressources")
            sql = fix_sqlite_intervals(sql)
            print("🟢 SQL FINAL:", sql)

        if error_ia:
            result = error_ia
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

"""Serveur Smart Grid : Flask + RDFLib.

Lancer :  python app.py   →  http://localhost:5000/api/health
Chaque membre a son Blueprint dans modules/<domaine>/.
"""
from flask import Flask, jsonify, request
from flask_cors import CORS

import store
from modules import batiments, mesure, production, reseau, stockage

app = Flask(__name__)
app.json.ensure_ascii = False
app.json.sort_keys = False
CORS(app)

for module in (production, stockage, batiments, reseau, mesure):
    app.register_blueprint(module.bp)


@app.get("/")
def index():
    """Page d'accueil de l'API : la liste des routes disponibles."""
    routes = sorted(
        f"{' '.join(sorted(r.methods - {'HEAD', 'OPTIONS'}))} {r.rule}"
        for r in app.url_map.iter_rules() if r.rule.startswith("/api")
    )
    return jsonify({
        "api": "Smart Grid · Flask + RDFLib",
        "triplets": len(store.graph),
        "interface": "http://localhost:4200",
        "routes": routes,
    })


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "triplets": len(store.graph)})


@app.post("/api/sparql")
def sparql():
    """Console SPARQL en lecture seule (SELECT / ASK), partagée par l'équipe."""
    query = (request.get_json(force=True) or {}).get("query", "")
    head = query.upper()
    if any(k in head for k in ("INSERT", "DELETE", "LOAD", "CLEAR", "DROP", "CREATE")):
        return jsonify({"error": "Seules les requêtes SELECT et ASK sont acceptées ici"}), 400
    try:
        if "ASK" in head and "SELECT" not in head:
            return jsonify({"boolean": store.ask(query)})
        return jsonify({"rows": store.select(query)})
    except Exception as exc:  # erreur de syntaxe SPARQL
        return jsonify({"error": str(exc)}), 400


@app.post("/api/reset")
def reset():
    """Recharge l'ontologie Protégé d'origine (annule toutes les modifications CRUD)."""
    store.load(reset=True)
    return jsonify({"status": "ok", "triplets": len(store.graph)})


store.load()

if __name__ == "__main__":
    app.run(port=5000, debug=True)

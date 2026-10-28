"""API REST du module Production (Membre 1 · Wala Rezgui).

À compléter : mettre les requêtes SPARQL dans un fichier queries.py (voir
modules/reseau/queries.py pour un exemple de CRUD complet avec RDFLib).
"""
from flask import Blueprint, jsonify

bp = Blueprint("production", __name__, url_prefix="/api/production")


@bp.get("/")
def statut():
    return jsonify({"module": "production", "membre": "Wala Rezgui", "statut": "à implémenter"})

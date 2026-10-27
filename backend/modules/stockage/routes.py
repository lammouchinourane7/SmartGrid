"""API REST du module Stockage (Membre 2 · Takoua Naceur).

À compléter : mettre les requêtes SPARQL dans un fichier queries.py (voir
modules/reseau/queries.py pour un exemple de CRUD complet avec RDFLib).
"""
from flask import Blueprint, jsonify

bp = Blueprint("stockage", __name__, url_prefix="/api/stockage")


@bp.get("/")
def statut():
    return jsonify({"module": "stockage", "membre": "Takoua Naceur", "statut": "à implémenter"})

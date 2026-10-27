"""API REST du module Bâtiments (Membre 3 · Abir Mosrati).

À compléter : mettre les requêtes SPARQL dans un fichier queries.py (voir
modules/reseau/queries.py pour un exemple de CRUD complet avec RDFLib).
"""
from flask import Blueprint, jsonify

bp = Blueprint("batiments", __name__, url_prefix="/api/batiments")


@bp.get("/")
def statut():
    return jsonify({"module": "batiments", "membre": "Abir Mosrati", "statut": "à implémenter"})

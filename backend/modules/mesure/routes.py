"""API REST du module Mesure (Membre 5 · Ibtihel Mechergui).

À compléter : mettre les requêtes SPARQL dans un fichier queries.py (voir
modules/reseau/queries.py pour un exemple de CRUD complet avec RDFLib).
"""
from flask import Blueprint, jsonify

bp = Blueprint("mesure", __name__, url_prefix="/api/mesure")


@bp.get("/")
def statut():
    return jsonify({"module": "mesure", "membre": "Ibtihel Mechergui", "statut": "à implémenter"})

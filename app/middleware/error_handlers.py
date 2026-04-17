from flask import jsonify
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError
from app.extensions import db


def register_error_handlers(app):
    @app.errorhandler(ValidationError)
    def handle_validation_error(e):
        return jsonify({"error": "Datos inválidos", "details": e.messages}), 400

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(e):
        db.session.rollback()
        return jsonify({"error": "Registro duplicado o restricción violada"}), 409

    @app.errorhandler(404)
    def handle_not_found(e):
        return jsonify({"error": "Recurso no encontrado"}), 404

    @app.errorhandler(400)
    def handle_bad_request(e):
        return jsonify({"error": str(e)}), 400

    @app.errorhandler(500)
    def handle_internal_error(e):
        return jsonify({"error": "Error interno del servidor"}), 500

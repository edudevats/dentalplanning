from flask import Blueprint

frontend_bp = Blueprint('frontend', __name__)

from . import routes  # noqa: E402, F401

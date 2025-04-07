# --- ui_routes.py ---
from flask import Blueprint, render_template

ui_bp = Blueprint('ui', __name__)

@ui_bp.route('/')
def index():
    return render_template('index.html')

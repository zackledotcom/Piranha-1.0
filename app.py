
from flask import Flask
from flask_socketio import SocketIO
import os
from routes import routes_bp

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.register_blueprint(routes_bp)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8000, debug=True)

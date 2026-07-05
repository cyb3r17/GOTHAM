import os

from flask import Flask

from profile_similarity.api.routes import bp


def create_app() -> Flask:
    app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"), static_folder=os.path.join(os.path.dirname(__file__), "..", "static"))
    app.register_blueprint(bp)
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)

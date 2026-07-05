from flask import Blueprint, jsonify, render_template, request, Flask
from dotenv import load_dotenv


from profile_similarity.matcher.ranking import rank_profiles
from profile_similarity.preprocessor import normalize_profile, parse_plain_text_profile
from profile_similarity.features.stylometry import stylometry_similarity
from profile_similarity.calibration import calibrate_probability

from windows_use import Agent, Browser
from windows_use.providers.openai import ChatOpenAI
from openai import OpenAI

bp = Blueprint("main", __name__)


@bp.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@bp.route("/compare", methods=["POST"])
def compare_profiles():
    payload = request.get_json(silent=True) or {}
    profile1 = payload.get("profile1", {})
    profile2 = payload.get("profile2", {})
    # If the client sent raw text (because JSON.parse failed), try parsing it
    if isinstance(profile1, str):
        try:
            profile1 = parse_plain_text_profile(profile1)
        except Exception:
            profile1 = {}
    if isinstance(profile2, str):
        try:
            profile2 = parse_plain_text_profile(profile2)
        except Exception:
            profile2 = {}

    # Normalize noisy inputs into the canonical shape expected by the matcher
    profile1 = normalize_profile(profile1)
    profile2 = normalize_profile(profile2)
    result = rank_profiles(profile1, profile2)
    return jsonify(result)


@bp.route("/stylometry", methods=["POST"])
def stylometry_check():
    payload = request.get_json(silent=True) or {}
    a = payload.get("profile1") or payload.get("text1") or ""
    b = payload.get("profile2") or payload.get("text2") or ""
    # accept raw pasted dumps
    if isinstance(a, str):
        try:
            a = parse_plain_text_profile(a)
        except Exception:
            a = {}
    if isinstance(b, str):
        try:
            b = parse_plain_text_profile(b)
        except Exception:
            b = {}
    a = normalize_profile(a)
    b = normalize_profile(b)
    score, reason = stylometry_similarity(a, b)
    prob = calibrate_probability(float(score))
    return jsonify({"stylometry_score": float(score), "probability": float(prob), "reason": reason})

app = Flask(__name__)


json_command = """
Return the data in JSON format.
{
    "username": string,
    "name": string,
    "bio": string,
    "posts": [
        {
            "caption": string,
            "hashtags": [string],
            "timestamp": string
        }
    ],
    "profile_image_url": string
}.
"""


def things_to_do(link):
    return [
        "Open Firefox.",
        f"Go to {link}",
        (
            "Extract description, posts, and profile image and all possible "
            "text data and metadata on images"
        ),
    ]


def get_data_from_unscrapable_website(links_to_search):
    final_results = []

    load_dotenv()

    llm_with_tools = ChatOpenAI(
        model="gpt-5.4-mini-2026-03-17"
    )

    client = OpenAI()

    agent = Agent(
        llm=llm_with_tools,
        browser=Browser.EDGE,
    )

    for link_to_search in links_to_search:
        instructions = things_to_do(link_to_search)

        for i in range(len(instructions) - 1):
            result = agent.invoke(task=instructions[i])

            response = client.responses.create(
                model="gpt-5.4-mini-2026-03-17",
                instructions=(
                    "Extract and summarise the relevant information from "
                    "the output of the agent in as few words as possible."
                ),
                input=str(result),
            )

            instructions[i + 1] = (
                response.output_text + " " + instructions[i + 1]
            )

            print(response.output_text)

        result = agent.invoke(
            task=instructions[len(instructions) - 1]
        )

        response = client.responses.create(
            model="gpt-5.4-mini-2026-03-17",
            instructions=json_command,
            input=str(result),
        )

        final_results.append(response.output_text)

    return final_results


@app.route("/scrape", methods=["POST"])
def scrape():
    payload = request.get_json(silent=True) or {}

    links = payload.get("links", [])

    if not isinstance(links, list):
        return jsonify({
            "error": "'links' must be a list of URLs."
        }), 400

    if not links:
        return jsonify({
            "error": "At least one link is required."
        }), 400

    try:
        results = get_data_from_unscrapable_website(links)

        return jsonify({
            "results": results
        }), 200

    except Exception as error:
        return jsonify({
            "error": str(error)
        }), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
    )
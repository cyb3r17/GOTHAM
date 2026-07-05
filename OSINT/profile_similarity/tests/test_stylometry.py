from profile_similarity.preprocessor import parse_plain_text_profile, normalize_profile
from profile_similarity.features.stylometry import stylometry_similarity


def make_text_a():
    return '''name: alice (username: alice123)
followers: 10
posts: 2

post1:
--date: 1 day ago
--caption: "I love data science and python programming"

post2:
--date: 2 days ago
--caption: "Working on an open source visualization project"'''


def make_text_b_same():
    # same author, similar style
    return '''name: alice (username: alice123)
followers: 11
posts: 2

post1:
--date: 2 hours ago
--caption: "I love data science and python programming"

post2:
--date: 3 hours ago
--caption: "Working on an open source visualization project"'''


def make_text_c_other():
    return '''name: bob (username: bob42)
followers: 100
posts: 2

post1:
--date: 1 day ago
--caption: "Check out my football highlights from yesterday"

post2:
--date: 2 days ago
--caption: "Cooking pasta tonight, recipe attached"'''


def test_stylometry_same_author():
    a = parse_plain_text_profile(make_text_a())
    b = parse_plain_text_profile(make_text_b_same())
    na = normalize_profile(a)
    nb = normalize_profile(b)
    score, reason = stylometry_similarity(na, nb)
    assert score > 0.7, f"Expected high stylometry score for same author, got {score}"


def test_stylometry_different_author():
    a = parse_plain_text_profile(make_text_a())
    c = parse_plain_text_profile(make_text_c_other())
    na = normalize_profile(a)
    nc = normalize_profile(c)
    score, reason = stylometry_similarity(na, nc)
    assert score < 0.6, f"Expected lower stylometry score for different authors, got {score}"

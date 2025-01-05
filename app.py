from flask import Flask, render_template, request, jsonify
import requests
import spacy
from spellchecker import SpellChecker
import re



app = Flask(__name__)

nlp_el = spacy.load('el_core_news_sm')
nlp_en = spacy.load('en_core_web_sm')

spell_el = SpellChecker(language=None)
spell_en = SpellChecker()

greek_words = ["καλημέρα", "σπίτι", "δουλειά", "αγάπη", "βιβλίο"]
spell_el.word_frequency.load_words(greek_words)

API_KEY = '9038d6f1e43e4ddc85a674d32318f01a'

def detect_language_and_models(query):
    if any(ord(char) > 127 for char in query):
        return 'el', nlp_el, spell_el
    return 'en', nlp_en, spell_en

def process_query(query, nlp_model):
    query = translate_operators_and_wildcards(query)
    doc = nlp_model(query)
    lemmas = [token.lemma_ for token in doc if not token.is_stop]
    return ' '.join(lemmas)

def translate_operators_and_wildcards(query):
    query = query.replace("AND", "+").replace("OR", "|")
    query = re.sub(r'(\w+)\*', r'\1', query)
    return query

def correct_spelling_with_languagetool(query, language_code):
    url = "https://api.languagetoolplus.com/v2/check"
    params = {
        'text': query,
        'language': language_code,
    }
    response = requests.post(url, data=params)
    results = response.json()

    corrected_query = query
    for match in results.get('matches', []):
        start = match['offset']
        end = start + match['length']
        if match['replacements']:
            suggestion = match['replacements'][0]['value']
            corrected_query = corrected_query[:start] + suggestion + corrected_query[end:]

    return corrected_query

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query')
    page = int(request.args.get('page', 1))
    sort = request.args.get('sort', 'date')

    if not query:
        return jsonify({'error': 'Το ερώτημα αναζήτησης δεν μπορεί να είναι κενό.'}), 400

    language, nlp_model, spell_checker = detect_language_and_models(query)
    language_code = 'el' if language == 'el' else 'en'

    corrected_query = correct_spelling_with_languagetool(query, language_code)

    lemmatized_query = process_query(corrected_query, nlp_model)

    url = f'https://newsapi.org/v2/everything?qInTitle={lemmatized_query}&apiKey={API_KEY}&language={language_code}&pageSize=10&page={page}'

    if sort == 'date':
        url += '&sortBy=publishedAt'
    elif sort == 'significance':
        url += '&sortBy=relevancy'

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        if 'articles' not in data:
            return jsonify({'message': 'Δεν βρέθηκαν ειδήσεις.'}), 200

        articles = data.get('articles', [])

        return jsonify({
            'articles': articles,
            'corrected_query': corrected_query,
            'page': page,
            'total_results': data.get('totalResults', 0)
        })

    except requests.exceptions.HTTPError as http_err:
        return jsonify({'error': f'HTTP error occurred: {http_err}'}), response.status_code
    except requests.exceptions.RequestException as req_err:
        return jsonify({'error': f'Request error occurred: {req_err}'}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=8080)
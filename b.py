import difflib
import re
from flask import Flask, request, jsonify
import requests
import logging
import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.neighbors import NearestNeighbors

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger('pymongo').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

JIKAN_ANIME_URL = 'https://api.jikan.moe/v4/anime?q='
DB_CONNECTION_STRING = "mongodb+srv://anshgaigawali:anshtini@cluster2.l7iru.mongodb.net/animechatbot?retryWrites=true&w=majority&appName=Cluster2"
client = MongoClient(DB_CONNECTION_STRING)
db = client['animechatbot']

def preprocess_input(user_input):
    anime_title = re.sub(r"(tell me about|info on|information about|let's talk about|give me details on|what can you say about|do you know about)?\s*", "", user_input, flags=re.IGNORECASE).strip()
    return anime_title

def fetch_anime_info(anime_title):
    try:
        search_title = requests.utils.quote(anime_title)
        response = requests.get(f"{JIKAN_ANIME_URL}{search_title}")
        response.raise_for_status()
        response_data = response.json()
        
        if not response_data.get("data"):
            return f"I couldn't find any information on {anime_title}.", None, None

        closest_match = None
        highest_similarity = 0.0
        for anime in response_data["data"]:
            title = anime.get('title', 'Title not available')
            similarity = difflib.SequenceMatcher(None, anime_title.lower(), title.lower()).ratio()
            if similarity > highest_similarity:
                highest_similarity = similarity
                closest_match = anime

        if highest_similarity > 0.7:
            synopsis = closest_match.get('synopsis', 'Synopsis not available.')
            url = closest_match.get('url', '#')
            image_url = closest_match.get('images', {}).get('jpg', {}).get('image_url', None)
            trailer_url = closest_match.get('trailer', {}).get('url', None)
            response_text = f""" **Title:** {closest_match['title']} 
                                **Synopsis:** {synopsis} 
                                **Episodes:** {closest_match.get('episodes', 'N/A')} 
                                **Score:** {closest_match.get('score', 'N/A')} 
                                **Status:** {closest_match.get('status', 'N/A')} 
                                **More info:** [MyAnimeList]({url}) """
            return response_text.strip(), image_url, trailer_url
        
        return f"No exact match found for {anime_title}.", None, None

    except requests.RequestException as e:
        return f"An error occurred while fetching the anime data for {anime_title}.", None, None

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No input data provided'}), 400

        user_input = data.get('input')
        user_id = data.get('user_id', None)
        response_text, image_url, trailer_url = fetch_anime_info(user_input)

        if user_id:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$push": {"history": {
                    "user_input": data['input'],
                    "response": response_text,
                    "timestamp": timestamp,
                    "image_url": image_url,
                    "trailer_url": trailer_url
                }}}
            )

        return jsonify({'response': response_text, 'image_url': image_url, 'trailer_url': trailer_url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def fetch_anime_suggestions(partial_input):
    try:
        search_title = requests.utils.quote(partial_input, safe='')
        response = requests.get(f"{JIKAN_ANIME_URL}{search_title}")
        logger.debug(f"API Request URL: {response.url}")
        response.raise_for_status()
        response_data = response.json()
        logger.debug(f"Response Data: {response_data}")

        if not response_data.get('data'):
            logger.error(f"No data found for: {partial_input}")
            return []

        titles_set = set()
        for anime in response_data['data']:
            title = anime.get('title', 'Unknown Title')
            if title.lower() not in [item.lower() for item in titles_set]:
                titles_set.add(title)

        return list(titles_set)

    except requests.RequestException as e:
        logger.error(f"Error fetching suggestions: {e}")
        return []

@app.route('/search-assistance', methods=['POST'])
def search_assistance():
    try:
        data = request.get_json()
        user_input = data['input'].strip()
        suggestions = fetch_anime_suggestions(user_input)
        logger.debug(f"Suggestions provided: {suggestions}")
        return jsonify({'suggestions': suggestions})
    except Exception as e:
        logger.error(f"Exception in search assistance: {e}")
        return jsonify({'error': str(e)}), 500

def fetch_user_anime_interactions():
    user_anime_ratings = db.user_anime_ratings.find()
    user_ids = []
    anime_ids = []
    ratings = []
    for record in user_anime_ratings:
        user_ids.append(record['user_id'])
        anime_ids.append(record['anime_id'])
        ratings.append(record['rating'])

    interactions_df = pd.DataFrame({'user_id': user_ids, 'anime_id': anime_ids, 'rating': ratings})
    logger.debug(f"User-Anime Interactions DataFrame: {interactions_df}")

    return interactions_df

def fetch_anime_data_for_cf():
    anime_data = db.anime_data.find()
    anime_ids = []
    titles = []
    for record in anime_data:
        anime_ids.append(record['anime_id'])
        titles.append(record['title'])
    return pd.DataFrame({'anime_id': anime_ids, 'title': titles})

@app.route('/recommend_cf', methods=['POST'])
def recommend_cf():
    try:
        data = request.get_json()
        user_id = data.get('user_id')

        interactions_df = fetch_user_anime_interactions()
        anime_df = fetch_anime_data_for_cf()

        user_item_matrix = interactions_df.pivot(index='user_id', columns='anime_id', values='rating').fillna(0)
        user_item_matrix_csr = csr_matrix(user_item_matrix.values)

        if user_id not in user_item_matrix.index:
            logger.error(f"User {user_id} not found in interactions data.")
            return jsonify({'error': f"User {user_id} not found in interactions data."})

        knn = NearestNeighbors(metric='cosine', algorithm='brute')
        knn.fit(user_item_matrix_csr)

        user_index = list(user_item_matrix.index).index(user_id)
        distances, indices = knn.kneighbors(user_item_matrix.iloc[user_index, :].values.reshape(1, -1), n_neighbors=6)

        similar_users = [user_item_matrix.index[i] for i in indices.flatten()]
        similar_users = similar_users[1:]

        recommendations = interactions_df[interactions_df['user_id'].isin(similar_users)]
        recommendations = recommendations.groupby('anime_id').rating.mean().reset_index()
        recommendations = recommendations.sort_values(by='rating', ascending=False).head(5)

        recommended_anime = anime_df[anime_df['anime_id'].isin(recommendations['anime_id'])]

        logger.debug(f"Recommendations: {recommended_anime}")

        return jsonify(recommended_anime.to_dict(orient='records'))
    except Exception as e:
        logger.error(f"Error in collaborative filtering recommendation endpoint: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/recommend_based_on_history', methods=['POST'])
def recommend_based_on_history():
    try:
        data = request.get_json()
        user_id = data.get('user_id')

        user_doc = db.users.find_one({"_id": ObjectId(user_id)})
        if not user_doc or "history" not in user_doc:
            logger.error(f"No history found for user {user_id}.")
            return jsonify({'error': f"No history found for user {user_id}."})

        history = user_doc["history"]
        anime_titles = [item['user_input'] for item in history]

        logger.debug(f"User History: {anime_titles}")

        recommendations = []
        for title in anime_titles:
            response = requests.get(f"{JIKAN_ANIME_URL}{title}")
            response.raise_for_status()
            response_data = response.json().get('data', [])
            recommendations.extend(response_data)

        return jsonify(recommendations)
    except Exception as e:
        logger.error(f"Error in recommendation based on history endpoint: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Get the assigned port or use 5000 by default
    app.run(host="0.0.0.0", port=port, debug=True)


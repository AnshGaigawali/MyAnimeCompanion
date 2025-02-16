import os
import re
import json
import streamlit as st
import requests
from pymongo import MongoClient
import bcrypt
import logging
import datetime
from bson.objectid import ObjectId

def preprocess_input(user_input):
    anime_title = re.sub(r"(tell me about|info on|information about|let's talk about|give me details on|what can you say about|do you know about)?\s*", "", user_input, flags=re.IGNORECASE).strip()
    anime_title = re.sub(r"[^\w\s]", "", anime_title).strip()
    return anime_title

def apply_css(file_name): 
    with open(file_name) as f: 
        css_content = f.read() 
        st.markdown(f'<style>{css_content}</style>', unsafe_allow_html=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FLASK_API_URL = "https://myanimecompanion.onrender.com"
DB_CONNECTION_STRING = "mongodb+srv://anshgaigawali:anshtini@cluster2.l7iru.mongodb.net/animechatbot?retryWrites=true&w=majority&appName=Cluster2"
client = MongoClient(DB_CONNECTION_STRING)
db = client['animechatbot']
users_collection = db['users']

def signup(email, password):
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    user = {"email": email, "password": hashed_password}
    result = users_collection.insert_one(user)
    logger.info(f"User inserted with id: {result.inserted_id}")
    st.success(f"Account created for {email}")

def login(email, password):
    user = users_collection.find_one({"email": email})
    if user and bcrypt.checkpw(password.encode('utf-8'), user["password"]):
        st.success(f"Logged in as {email}")
        return str(user["_id"])
    st.error("Invalid credentials")
    return None

def logout():
    st.session_state["user_id"] = None
    st.success("You have been logged out successfully.")

def delete_account(user_id):
    result = users_collection.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count > 0:
        st.success("Account deleted successfully.")
        st.session_state["user_id"] = None
    else:
        st.error("Failed to delete the account. Please try again.")

def chatbot(input_text, user_id=None, is_suggestion=False):
    preprocessed_text = input_text if is_suggestion else preprocess_input(input_text)
    response = requests.post(f"{FLASK_API_URL}/chat", json={"input": preprocessed_text, "user_id": user_id})
    response_json = response.json()
    response_text = response_json.get('response', "I'm sorry, I couldn't find any information.")
    image_url = response_json.get('image_url')
    trailer_url = response_json.get('trailer_url')
    return response_text, image_url, trailer_url

def search_assistance(input_text):
    response = requests.post(f"{FLASK_API_URL}/search-assistance", json={"input": input_text})
    response_data = response.json()
    return response_data.get('suggestions', [])

def get_recommendations(user_id):
    response = requests.post(f"{FLASK_API_URL}/recommend_based_on_history", json={"user_id": user_id})
    response_data = response.json()
    return response_data

def authentication_page():
    st.header("Anime Chatbot Authentication")
    auth_mode = st.radio("Choose an option", ["Sign In", "Sign Up", "Logout"])

    if auth_mode == "Sign In":
        st.markdown("<h2 class='stSubheader'>Sign In</h2>", unsafe_allow_html=True)
        with st.form(key='sign_in_form'):
            email = st.text_input("Email")
            password = st.text_input("Password", type='password')
            submit_button = st.form_submit_button(label='Sign In')

            if submit_button:
                user_id = login(email, password)
                if user_id:
                    st.session_state["user_id"] = user_id
    elif auth_mode == "Sign Up":
        st.markdown("<h2 class='stSubheader'>Sign Up</h2>", unsafe_allow_html=True)
        with st.form(key='sign_up_form'):
            email = st.text_input("Email")
            password = st.text_input("Password", type='password')
            submit_button = st.form_submit_button(label='Sign Up')

            if submit_button:
                signup(email, password)
    elif auth_mode == "Logout":
        st.markdown("<h2 class='stSubheader'>Logout</h2>", unsafe_allow_html=True)
        if st.session_state["user_id"]:
            if st.button("Confirm Logout"):
                logout()
        else:
            st.warning("You need to log in to log out.")

def display_anime_info(response_text, image_url=None, trailer_url=None):
    anime_title_match = re.search(r'<h2><strong>Title:</strong></h2>(.*?)<br>', response_text)
    anime_title = anime_title_match.group(1).strip() if anime_title_match else "Anime Character"
    
    formatted_response = response_text.replace("**Title:**", "<h2><strong>Title:</strong></h2>")
    formatted_response = formatted_response.replace("**Episodes:**", "<h3><strong>Episodes:</strong></h3>")
    formatted_response = formatted_response.replace("**Score:**", "<h3><strong>Score:</strong></h3>")
    formatted_response = formatted_response.replace("**Status:**", "<h3><strong>Status:</strong></h3>")
    formatted_response = formatted_response.replace("**Synopsis:**", "<h3><strong>Synopsis:</strong></h3>")
    
    formatted_response = formatted_response.replace("\n", "<br>")
    
    formatted_response = re.sub(r'(http[s]?://\S+)', r'<a href="\1" target="_blank">Click Here for More Info</a>)', formatted_response)
    html_response = f"""
    <div style='text-align: left; font-family: Arial, sans-serif; line-height: 1.5; margin-bottom:20px;'>
        {formatted_response}
    </div>
    """
    st.markdown(html_response, unsafe_allow_html=True)
    
    if image_url:
        st.markdown(f"<div style='text-align: center;'><img src='{image_url}' alt='{anime_title}' style='max-width: 100%; height: auto; margin-bottom: 20px;' /></div>", unsafe_allow_html=True)
        
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    if trailer_url:
        st.video(trailer_url, format="video/mp4", start_time=0)

def display_recommendations(recommendations):
    st.header("Recommended Animes")
    if isinstance(recommendations, list):
        for rec in recommendations:
            if isinstance(rec, dict) and 'title' in rec:
                st.markdown(f"**{rec['title']}**")
            else:
                st.error("Unexpected recommendation format. Please check the backend response.")
    else:
        st.error("Invalid recommendations data. Please check the backend response.")

def main():
    st.markdown("<h1 class='stHeader'>Anime Chatbot with Streamlit</h1>", unsafe_allow_html=True)

    theme_mode = st.sidebar.selectbox("Select Theme Mode:", ["Light Mode", "Dark Mode"])
    
    if theme_mode == "Dark Mode":
        apply_css("dark_mode.css")
    else:
        apply_css("light_mode.css")

    menu = ["Home", "Authentication", "Conversation History", "Delete History", "Delete Account", "About"]
    choice = st.sidebar.selectbox("Menu", menu)

    if "user_id" not in st.session_state:
        st.session_state["user_id"] = None

    if choice == "Authentication":
        authentication_page()
    if choice == "Home":
        if st.session_state["user_id"]:
            st.header("Welcome to the Anime Chatbot. Write the name of the anime you want to know about.")
            user_input = st.text_input("You:")
            if user_input:
                suggestions = search_assistance(user_input)
                selected_anime = st.selectbox("Top Results:", options=suggestions)
                if st.button("Search"):
                    if selected_anime:
                        response_text, image_url, trailer_url = chatbot(selected_anime, st.session_state["user_id"], is_suggestion=True)
                        display_anime_info(response_text, image_url, trailer_url)
                    else:
                        st.warning("Please enter an anime name to get suggestions.")
            
            st.header("Your Anime Recommendations")
            if st.button("Get Recommendations"):
                recommendations = get_recommendations(st.session_state["user_id"])
                display_recommendations(recommendations)
                
        else:
            st.warning("You need to log in to chat with the bot.")
            st.info("Please go to the Authentication section.")
    elif choice == "Conversation History":
        if st.session_state["user_id"]:
            st.header("Conversation History")
            user_doc = users_collection.find_one({"_id": ObjectId(st.session_state["user_id"])})
            if user_doc and "history" in user_doc and user_doc["history"]:
                user_history = user_doc["history"]
                for history in user_history:
                    st.text(f"User: {history['user_input']}\nChatbot: {history['response']}\nTimestamp: {history['timestamp']}")
                    st.markdown("---")
            else:
                st.warning("No conversation history found for this user.")
        else:
            st.warning("You need to log in to see conversation history.")
    elif choice == "Delete History":
        if st.session_state["user_id"]:
            st.header("Delete Conversation History")
            user_doc = users_collection.find_one({"_id": ObjectId(st.session_state["user_id"])})
            if user_doc and "history" in user_doc and user_doc["history"]:
                if st.button("Delete history"):
                    users_collection.update_one({"_id": ObjectId(st.session_state["user_id"])}, {"$set": {"history": []}})
                    st.success("Conversation history deleted for the current user.")
            else:
                st.warning("No conversation history to delete.")
        else:
            st.warning("You need to log in to delete history.")
    elif choice == "Delete Account":
        if st.session_state["user_id"]:
            st.header("Delete Account")
            if st.button("Confirm Delete Account"):
                delete_account(st.session_state["user_id"])
        else:
            st.warning("You need to log in to delete your account.")
    elif choice == "About":
        st.header("About")
        st.write("This project demonstrates an anime-specific chatbot built using NLP techniques, Streamlit for frontend, and Flask for backend.")
        st.subheader("Overview:")
        st.write("""
        1. **Dataset**: The chatbot is using Jikan API to fetch anime data.
        2. **Model**: Logistic Regression to classify user queries into different anime categories.
        3. **Interface**: The Streamlit interface allows users to interact with the chatbot seamlessly.
        4. **Purpose**: The chatbot helps users find information about their favorite animes including details like title, type, description, and more.
        """)
        st.subheader("Additional Information:")
        st.write("Feel free to explore and ask about different anime titles!")

if __name__ == '__main__':
    main()

import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import re
import os
import json
import sys
import io
import string
from langdetect import detect, DetectorFactory

# Set seed for reproducibility in langdetect
DetectorFactory.seed = 0

# --- Import from your scraper script ---
try:
    from google_maps_scraper import (
        scrape_reviews_function,
        process_reviews_function,
        save_reviews_function,
        detect_review_language as scraper_detect_review_language, # Rename to avoid conflict with langdetect.detect
        GoogleMapsReviewScraper,
        ReviewTextProcessor
    )
    SCRAPER_AVAILABLE = True
except ImportError as e:
    st.error(f"""
    Error: Could not import scraper functions from `google_maps_scraper.py`.
    Please ensure `google_maps_scraper.py` is in the same directory as `streamlit_app.py`.
    Details: {e}
    """)
    SCRAPER_AVAILABLE = False
    # Fallback to dummy functions if scraper is not available
    def scrape_reviews_function(url, num_reviews):
        st.warning("Scraper functions not available. Using dummy data.")
        return [
            {"name": "Dummy Reviewer 1", "date": "2023-01-15", "rating": 5, "text": "This is a great place! Highly recommend."},
            {"name": "Dummy Reviewer 2", "date": "2023-02-01", "rating": 4, "text": "Good experience overall, but service was a bit slow."},
            {"name": "Dummy Reviewer 3", "date": "2023-03-20", "rating": 2, "text": "Not satisfied. The product broke after a week."},
            {"name": "Dummy Reviewer 4", "date": "2 months ago", "rating": 5, "text": "Amazing food and friendly staff."},
            {"name": "Dummy Reviewer 5", "date": "1 week ago", "rating": 3, "text": "It was okay, nothing special."},
        ][:num_reviews]

    def process_reviews_function(reviews):
        return reviews

    def save_reviews_function(reviews, filename):
        df = pd.DataFrame(reviews)
        try:
            df.to_csv(filename, index=False, encoding='utf-8-sig')
            return True
        except Exception as e:
            st.error(f"Error saving reviews: {e}")
            return False

    def scraper_detect_review_language(text): # Using the renamed function
        try:
            return detect(text)
        except:
            return "unknown"
    
    class GoogleMapsReviewScraper:
        def __init__(self):
            st.warning("Scraper not available.")
            self.driver = None
        def scrape_reviews(self, url, num_reviews):
            return scrape_reviews_function(url, num_reviews)

    class ReviewTextProcessor:
        def __init__(self):
            pass
        def process(self, reviews):
            return process_reviews_function(reviews)

# Override langdetect.detect with scraper's version if available, or keep the original for processing tab.
# For consistency, the Streamlit app will use the detect_review_language from the scraper if it's available,
# otherwise it will use the langdetect.detect or its own simple heuristic.
if SCRAPER_AVAILABLE:
    _detect_language_for_analyzer = scraper_detect_review_language
else:
    def _detect_language_for_analyzer(text):
        try:
            return detect(text)
        except:
            return "unknown"

class ReviewAnalyzerWebApp:
    def __init__(self):
        # Initialize instance variables from session state for persistence
        self.reviews_df = st.session_state.get('reviews_df', None)
        self.filtered_reviews = st.session_state.get('filtered_reviews', None)
        self.all_reviews = st.session_state.get('all_reviews', [])
        
        self.workspace_data = st.session_state.get('workspace_data', {})
        self.space_data = st.session_state.get('space_data', {})
        self.list_data = st.session_state.get('list_data', {})

        st.set_page_config(layout="wide", page_title="Google Maps Review Analyzer & Scraper")

    def parse_date(self, date_str):
        if not date_str or date_str == 'N/A':
            return None

        try:
            original_date_str = date_str
            date_str = date_str.strip().lower()

            if 'ago' in date_str:
                now = datetime.now()
                if 'minute' in date_str:
                    minutes = re.findall(r'(\d+)\s*minute', date_str)
                    if minutes: return now - timedelta(minutes=int(minutes[0]))
                elif 'hour' in date_str:
                    hours = re.findall(r'(\d+)\s*hour', date_str)
                    if hours: return now - timedelta(hours=int(hours[0]))
                elif 'day' in date_str and 'week' not in date_str:
                    days = re.findall(r'(\d+)\s*day', date_str)
                    if days: return now - timedelta(days=int(days[0]))
                    elif 'a day ago' in date_str: return now - timedelta(days=1)
                elif 'week' in date_str:
                    weeks = re.findall(r'(\d+)\s*week', date_str)
                    if weeks: return now - timedelta(weeks=int(weeks[0]))
                    elif 'a week ago' in date_str: return now - timedelta(weeks=1)
                elif 'month' in date_str:
                    months = re.findall(r'(\d+)\s*month', date_str)
                    if months: return now - timedelta(days=int(months[0])*30)
                    elif 'a month ago' in date_str: return now - timedelta(days=30)
            
            date_formats = [
                '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%B %d, %Y', '%b %d, %Y',
            ]
            for fmt in date_formats:
                try: return datetime.strptime(date_str, fmt)
                except ValueError: continue
            return None
        except Exception as e:
            return None

    def get_priority_from_rating(self, rating):
        try:
            rating_num = float(rating)
            if rating_num <= 2: return 1  # Urgent
            elif rating_num <= 3: return 2  # High
            elif rating_num <= 4: return 3  # Normal
            else: return 4  # Low
        except:
            return 3  # Normal

    def setup_scraper_tab(self):
        st.header("Google Maps Review Scraper")
        st.markdown("Enter a Google Maps URL and the number of reviews to scrape.")

        if not SCRAPER_AVAILABLE:
            st.error("""
            **Scraper functionality is limited because `google_maps_scraper.py` could not be loaded.**
            Please ensure the file is in the same directory and all its dependencies (`selenium`, `camel-tools`, `textblob`) are installed.
            """)
            st.info("For local testing, ensure `chromedriver` is in your PATH and Chrome browser is installed.")
        else:
            st.warning("""
            **Warning:** The scraping functionality uses `selenium` which requires a Chrome browser and ChromeDriver.
            This part of the application will likely **NOT work** when hosted on most free cloud platforms (e.g., Streamlit Community Cloud) due to environment limitations.
            It will work if you run Streamlit locally and have Chrome/ChromeDriver properly set up.
            """)

        url = st.text_input("Google Maps Place URL:", key="scraper_url_input")
        num_reviews = st.number_input("Number of Reviews:", min_value=1, value=50, max_value=10000, key="num_reviews_input")

        if st.button("Start Scraping", key="start_scraping_button"):
            if not url:
                st.error("Please enter a Google Maps URL")
                return

            if not SCRAPER_AVAILABLE:
                st.error("Scraper functions are not available. Cannot start scraping.")
                return

            with st.spinner("Scraping reviews... This might take a while."):
                # Initialize scraper within the Streamlit context
                scraper_instance = GoogleMapsReviewScraper()
                reviews = scraper_instance.scrape_reviews(url, num_reviews)
                scraper_instance.close() # Ensure driver is closed

            if reviews:
                self.all_reviews = process_reviews_function(reviews)
                st.session_state['all_reviews'] = self.all_reviews
                st.success(f"Successfully scraped {len(self.all_reviews)} reviews!")
                
            else:
                st.error("No reviews were scraped. Please check the URL.")
        
        # Always display scraped reviews if available in session state
        if self.all_reviews:
            st.subheader("Scraped Reviews (First 5):")
            
            display_reviews = []
            for i, review in enumerate(self.all_reviews[:5]):
                display_reviews.append(f"**Review {i+1}:**\nName: {review.get('name', 'N/A')}\nDate: {review.get('date', 'N/A')}\nRating: {review.get('rating', 'N/A')}\nText: {review.get('text', 'N/A')[:200]}{'...' if len(review.get('text', '')) > 200 else ''}")
            
            st.markdown("\n\n".join(display_reviews))

            col1, col2 = st.columns(2)
            with col1:
                df_to_save = pd.DataFrame(self.all_reviews)
                csv = df_to_save.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="Download Scraped Reviews CSV",
                    data=csv,
                    file_name="scraped_reviews.csv",
                    mime="text/csv",
                    key="download_scraped_csv"
                )
            with col2:
                if st.button("Use for Analysis", key="use_for_analysis_button"):
                    if self.all_reviews:
                        self.reviews_df = pd.DataFrame(self.all_reviews)
                        st.session_state['reviews_df'] = self.reviews_df
                        st.session_state['file_loaded_status'] = f"{len(self.all_reviews)} reviews loaded from scraper"
                        st.success(f"Loaded {len(self.all_reviews)} reviews for analysis.")
                        st.rerun() # Rerun to update analyzer tab
                    else:
                        st.warning("No reviews available to use for analysis.")

    def setup_analyzer_tab(self):
        st.header("Review Keyword & Time Filter")

        st.subheader("Load Reviews")
        uploaded_file = st.file_uploader("Upload CSV File", type="csv", key="file_uploader")
        
        if uploaded_file is not None:
            self.reviews_df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
            st.session_state['reviews_df'] = self.reviews_df
            st.session_state['file_loaded_status'] = f"Loaded: {uploaded_file.name} ({len(self.reviews_df)} reviews)"
            st.success(st.session_state['file_loaded_status'])
        elif 'reviews_df' in st.session_state and st.session_state['reviews_df'] is not None:
            self.reviews_df = st.session_state['reviews_df']
            st.info(st.session_state.get('file_loaded_status', 'No file loaded'))
        else:
            st.warning("No file loaded. Please upload a CSV or scrape reviews first.")
            self.reviews_df = None

        if self.reviews_df is not None:
            st.subheader("Filter Parameters")
            
            language_filter = st.radio(
                "Language Filter:",
                ("All Languages", "English Only", "Arabic Only", "Mixed Content"),
                key="lang_filter_radio"
            )
            lang_map = {
                "All Languages": "all",
                "English Only": "english",
                "Arabic Only": "arabic",
                "Mixed Content": "mixed"
            }
            selected_language = lang_map[language_filter]

            keyword_input = st.text_input("Keyword to Search (comma-separated):", key="keyword_input")
            days = st.slider("Time Period (days from today):", min_value=1, max_value=365, value=30, key="days_slider")
            max_results = st.number_input("Max Results:", min_value=1, value=100, max_value=1000, key="max_results_input")

            if st.button("Search Reviews", key="search_reviews_button") or (
                self.reviews_df is not None and 
                (st.session_state.get('filtered_reviews') is None or not st.session_state.get('filtered_reviews'))
            ):
                if self.reviews_df is None:
                    st.error("Please load a CSV file first or use scraped reviews.")
                    return

                keywords = [k.strip() for k in keyword_input.split(',') if k.strip()]

                if not keywords and keyword_input:
                    st.error("Please enter a keyword to search, or leave blank to skip keyword filtering.")
                    return
                
                with st.spinner("Searching reviews..."):
                    filtered_df = self.reviews_df.copy()

                    # Step 1: Filter by time period
                    cutoff_date = datetime.now() - timedelta(days=days)
                    
                    filtered_df['parsed_date'] = filtered_df['date'].apply(self.parse_date)
                    filtered_df = filtered_df[filtered_df['parsed_date'].notna()]
                    filtered_df = filtered_df[filtered_df['parsed_date'] >= cutoff_date]

                    # Apply keyword filtering if keywords are provided
                    if keywords:
                        keyword_condition = False
                        for kw in keywords:
                            kw_lower = kw.lower()
                            keyword_condition |= (filtered_df['text'].str.lower().str.contains(kw_lower, na=False) |
                                                  filtered_df['name'].str.lower().str.contains(kw_lower, na=False))
                        filtered_df = filtered_df[keyword_condition]
                    
                    # Step 3: Filter by language
                    if selected_language != "all":
                        filtered_df['detected_lang'] = filtered_df['text'].apply(_detect_language_for_analyzer)
                        if selected_language == "mixed":
                            filtered_df = filtered_df[filtered_df['detected_lang'] == "mixed"]
                        else:
                            filtered_df = filtered_df[filtered_df['detected_lang'] == selected_language]

                    # Step 4: Limit results
                    self.filtered_reviews = filtered_df.head(max_results).to_dict('records')
                    st.session_state['filtered_reviews'] = self.filtered_reviews
                
                self.display_search_results(keyword_input, days, selected_language)

    def display_search_results(self, keyword_input, days, language_filter):
        lang_desc = {
            "all": "all languages",
            "english": "English only",
            "arabic": "Arabic only",
            "mixed": "mixed content"
        }.get(language_filter, language_filter)

        if not self.filtered_reviews:
            st.warning(f"No reviews found containing '{keyword_input}' in {lang_desc} from the last {days} days.")
            st.markdown(f"""
            DEBUG INFO:
            - Total reviews in dataset: {len(self.reviews_df) if self.reviews_df is not None else 0}
            - Search keyword: '{keyword_input}'
            - Time filter: {days} days
            - Language filter: {lang_desc}
            - Number of reviews after all filters: 0
            """)
        else:
            st.success(f"Found {len(self.filtered_reviews)} reviews containing '{keyword_input}' in {lang_desc} from the last {days} days:")
            st.markdown("---")
            for i, review in enumerate(self.filtered_reviews):
                review_text = review.get('text', 'N/A')
                title_text = review.get('name', 'N/A')
                detected_lang = _detect_language_for_analyzer(review_text)

                st.markdown(f"**Review {i+1}:** [{detected_lang.upper()}]")
                st.markdown(f"**Name:** {title_text}")
                st.markdown(f"**Date:** {review.get('date', 'N/A')}")
                st.markdown(f"**Rating:** {review.get('rating', 'N/A')}")
                st.markdown(f"**Review:** {review_text}")
                st.markdown("---")
            
            df_to_export = pd.DataFrame(self.filtered_reviews)
            csv = df_to_export.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="Export Filtered Results (CSV)",
                data=csv,
                file_name="filtered_reviews.csv",
                mime="text/csv",
                key="download_filtered_csv"
            )

    def setup_clickup_tab(self):
        st.header("ClickUp Integration")

        api_token = st.text_input("ClickUp API Token:", type="password", key="clickup_token_input")

        # Session state for ClickUp data
        if 'clickup_headers' not in st.session_state:
            st.session_state['clickup_headers'] = None
        if 'workspace_data' not in st.session_state:
            st.session_state['workspace_data'] = {}
        if 'space_data' not in st.session_state:
            st.session_state['space_data'] = {}
        if 'list_data' not in st.session_state:
            st.session_state['list_data'] = {}
        if 'clickup_status' not in st.session_state:
            st.session_state['clickup_status'] = "Not connected"
        if 'clickup_status_text_log' not in st.session_state:
            st.session_state['clickup_status_text_log'] = ""

        # Test Connection and Load Workspaces
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Test ClickUp Connection", key="test_connection_button"):
                if api_token:
                    headers = {"Authorization": api_token}
                    try:
                        response = requests.get("https://api.clickup.com/api/v2/user", headers=headers, timeout=10)
                        if response.status_code == 200:
                            user_data = response.json()
                            username = user_data.get('user', {}).get('username', 'Unknown')
                            st.session_state['clickup_status'] = f"Connected as: {username}"
                            st.session_state['clickup_headers'] = headers
                            st.success(f"Connected to ClickUp! User: {username}")
                        else:
                            st.session_state['clickup_status'] = f"Connection failed: {response.status_code}"
                            st.error(f"Failed to connect to ClickUp. Status: {response.status_code}")
                    except requests.exceptions.Timeout:
                        st.session_state['clickup_status'] = "Connection timed out"
                        st.error("Connection timed out. Please check your internet connection.")
                    except Exception as e:
                        st.session_state['clickup_status'] = f"Connection failed: {str(e)}"
                        st.error(f"Connection failed: {str(e)}")
                else:
                    st.error("Please enter your ClickUp API token.")
        with col2:
            if st.button("Load Workspaces", key="load_workspaces_button"):
                if st.session_state['clickup_headers']:
                    try:
                        response = requests.get("https://api.clickup.com/api/v2/team", headers=st.session_state['clickup_headers'])
                        if response.status_code == 200:
                            teams = response.json()["teams"]
                            workspace_names = [(team["name"], team["id"]) for team in teams]
                            st.session_state['workspace_data'] = {name: team_id for name, team_id in workspace_names}
                            st.success(f"Loaded {len(workspace_names)} workspaces.")
                        else:
                            st.error(f"Failed to load workspaces: {response.text}")
                    except Exception as e:
                        st.error(f"Failed to connect to ClickUp: {str(e)}")
                else:
                    st.warning("Please test connection first.")
        
        st.info(f"ClickUp Status: {st.session_state['clickup_status']}")

        # Workspace selection
        workspace_names_list = list(st.session_state['workspace_data'].keys())
        selected_workspace = st.selectbox("Select Workspace:", [""] + workspace_names_list, key="workspace_select")
        
        if selected_workspace and st.session_state['workspace_data'] and st.button("Load Spaces", key="load_spaces_button"):
            team_id = st.session_state['workspace_data'][selected_workspace]
            try:
                response = requests.get(f"https://api.clickup.com/api/v2/team/{team_id}/space", headers=st.session_state['clickup_headers'])
                if response.status_code == 200:
                    spaces = response.json()["spaces"]
                    space_names = [(space["name"], space["id"]) for space in spaces]
                    st.session_state['space_data'] = {name: space_id for name, space_id in space_names}
                    st.success(f"Loaded {len(space_names)} spaces for {selected_workspace}.")
                else:
                    st.error(f"Failed to load spaces: {response.text}")
            except Exception as e:
                st.error(f"Failed to load spaces: {str(e)}")
        
        # Space selection
        space_names_list = list(st.session_state['space_data'].keys())
        selected_space = st.selectbox("Select Space:", [""] + space_names_list, key="space_select")

        if selected_space and st.session_state['space_data'] and st.button("Load Lists", key="load_lists_button"):
            space_id = st.session_state['space_data'][selected_space]
            try:
                response = requests.get(f"https://api.clickup.com/api/v2/space/{space_id}/list", headers=st.session_state['clickup_headers'])
                if response.status_code == 200:
                    lists = response.json()["lists"]
                    list_names = [(lst["name"], lst["id"]) for lst in lists]
                    st.session_state['list_data'] = {name: list_id for name, list_id in list_names}
                    st.success(f"Loaded {len(list_names)} lists for {selected_space}.")
                else:
                    st.error(f"Failed to load lists: {response.text}")
            except Exception as e:
                st.error(f"Failed to load lists: {str(e)}")
        
        # List selection
        list_names_list = list(st.session_state['list_data'].keys())
        selected_list = st.selectbox("Select List:", [""] + list_names_list, key="list_select")

        st.subheader("Upload Data to ClickUp")
        data_type = st.radio("Choose data to upload:", ("Filtered Data", "All Loaded Data"), key="upload_data_type")
        place_name = st.text_input("Place Name for Reviews (e.g., 'Restaurant ABC'):", key="place_name_input")

        if st.button("Upload Reviews to ClickUp", key="upload_to_clickup_button"):
            if not api_token or not selected_list:
                st.error("Please enter API token and select a ClickUp List.")
                return
            if not place_name:
                st.error("Please enter a place name for the reviews.")
                return
            
            list_id = st.session_state['list_data'].get(selected_list)
            if not list_id:
                st.error("Please select a valid ClickUp list.")
                return

            data_to_upload = []
            if data_type == "Filtered Data":
                if 'filtered_reviews' in st.session_state and st.session_state['filtered_reviews']:
                    data_to_upload = st.session_state['filtered_reviews']
                else:
                    st.error("No filtered reviews available to upload. Please perform a search first.")
                    return
            else: # All Loaded Data
                if 'reviews_df' in st.session_state and not st.session_state['reviews_df'].empty:
                    data_to_upload = st.session_state['reviews_df'].to_dict('records')
                else:
                    st.error("No reviews loaded to upload. Please load a CSV or scrape reviews first.")
                    return

            if data_to_upload:
                st.session_state['clickup_status_text_log'] = f"Starting upload of {len(data_to_upload)} individual review tasks...\n"
                st.session_state['clickup_status_text_log'] += "=" * 50 + "\n"
                progress_bar = st.progress(0)
                successful_uploads = 0

                headers = st.session_state['clickup_headers']
                if headers is None:
                    st.error("ClickUp API headers not set. Please test connection first.")
                    return

                for i, review in enumerate(data_to_upload):
                    task_name = f"{place_name} - Review {i + 1}"
                    description = f"**Review from {place_name}**\n\n"
                    description += f"**Name:** {review.get('name', 'N/A')}\n"
                    description += f"**Date:** {review.get('date', 'N/A')}\n"
                    description += f"**Rating:** {review.get('rating', 'N/A')}\n"
                    description += f"**Review:** {review.get('text', 'N/A')}\n"

                    task_data = {
                        "name": task_name,
                        "description": description,
                        "status": "to do",
                        "priority": self.get_priority_from_rating(review.get('rating', 0)),
                        "tags": []
                    }

                    try:
                        response = requests.post(
                            f"https://api.clickup.com/api/v2/list/{list_id}/task",
                            headers=headers,
                            json=task_data,
                            timeout=10
                        )
                        if response.status_code == 200:
                            successful_uploads += 1
                            st.session_state['clickup_status_text_log'] += f"✅ Uploaded Review {i + 1}: {task_name}\n"
                        else:
                            st.session_state['clickup_status_text_log'] += f"❌ Failed to upload Review {i + 1}: {task_name} - {response.status_code} - {response.text}\n"
                    except requests.exceptions.Timeout:
                        st.session_state['clickup_status_text_log'] += f"❌ Failed to upload Review {i + 1}: {task_name} - Timeout\n"
                    except Exception as e:
                        st.session_state['clickup_status_text_log'] += f"❌ Failed to upload Review {i + 1}: {task_name} - Error: {str(e)}\n"
                    
                    progress_bar.progress((i + 1) / len(data_to_upload))
                    st.session_state['clickup_status_text_log'] = st.session_state['clickup_status_text_log'] # Rerun to update log

                st.session_state['clickup_status_text_log'] += "=" * 50 + "\n"
                st.session_state['clickup_status_text_log'] += f"Final Upload Summary: {successful_uploads} out of {len(data_to_upload)} reviews uploaded.\n"
                if successful_uploads == len(data_to_upload):
                    st.success(f"Successfully uploaded {successful_uploads} reviews to ClickUp!")
                    st.session_state['clickup_status'] = f"Upload Complete: {successful_uploads} reviews uploaded"
                else:
                    st.warning(f"Uploaded {successful_uploads} out of {len(data_to_upload)} reviews (partial success).")
                    st.session_state['clickup_status'] = f"Upload Partial: {successful_uploads}/{len(data_to_upload)} reviews uploaded"
            else:
                st.warning("No data to upload to ClickUp.")
        
        st.markdown("---")
        st.subheader("ClickUp Integration Log")
        st.text_area("Log:", value=st.session_state['clickup_status_text_log'], height=300, key="clickup_log_display")


    def run(self):
        st.title("Google Maps Review Analyzer & Scraper")

        tab1, tab2, tab3 = st.tabs(["Scrape Reviews", "Analyze Reviews", "ClickUp Integration"])

        with tab1:
            self.setup_scraper_tab()
        with tab2:
            self.setup_analyzer_tab()
        with tab3:
            self.setup_clickup_tab()

if __name__ == "__main__":
    app = ReviewAnalyzerWebApp()
    app.run()

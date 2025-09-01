# -*- coding: utf-8 -*-
import time
import csv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import sys
import io
import string

# Force UTF-8 encoding for stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Text preprocessing imports
try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False
    print("Note: textblob not available. Install with: pip install textblob")

try:
    from camel_tools.utils.normalize import normalize_alef_maksura_ar, normalize_alef_ar, normalize_teh_marbuta_ar
    from camel_tools.dialectid import DialectIdentifier
    from camel_tools.utils.dediac import dediac_ar
    CAMEL_AVAILABLE = True
    print("✓ CAMeL Tools loaded successfully")
except ImportError:
    CAMEL_AVAILABLE = False
    print("Note: CAMeL Tools not available. Install with: pip install camel-tools")

try:
    import langdetect
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    print("Note: langdetect not available. Install with: pip install langdetect")

class ReviewTextProcessor:
    def __init__(self):
        self.setup_camel_tools()

    def setup_camel_tools(self):
        """Initialize CAMeL Tools components"""
        if CAMEL_AVAILABLE:
            try:
                # Initialize dialect identifier
                self.dialect_id = DialectIdentifier.pretrained()
                print("✓ CAMeL Tools dialect identifier loaded")
            except Exception as e:
                print(f"Warning: Could not load CAMeL Tools dialect identifier: {e}")
                self.dialect_id = None
        else:
            self.dialect_id = None

    def detect_language(self, text):
        """Detect language of text"""
        if not text or len(text.strip()) < 3:
            return 'unknown'

        try:
            if LANGDETECT_AVAILABLE:
                return langdetect.detect(text)
            else:
                # Simple heuristic
                arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
                english_chars = len(re.findall(r'[a-zA-Z]', text))

                if arabic_chars > english_chars:
                    return 'ar'
                elif english_chars > arabic_chars:
                    return 'en'
                else:
                    return 'mixed'
        except:
            return 'unknown'

    def normalize_arabic_text(self, text):
        """Normalize Arabic text using CAMeL Tools"""
        if not CAMEL_AVAILABLE or not text:
            return text

        try:
            # Remove diacritics
            text = dediac_ar(text)

            # Normalize different forms of Alef
            text = normalize_alef_ar(text)

            # Normalize Alef Maksura
            text = normalize_alef_maksura_ar(text)

            # Normalize Teh Marbuta
            text = normalize_teh_marbuta_ar(text)

            return text.strip()

        except Exception as e:
            print(f"Warning: Arabic normalization failed: {e}")
            return text

    def identify_arabic_dialect(self, text):
        """Identify Arabic dialect using CAMeL Tools"""
        if not CAMEL_AVAILABLE or not self.dialect_id or not text:
            return 'unknown'

        try:
            predictions = self.dialect_id.predict([text])
            return predictions[0].top if predictions else 'unknown'
        except Exception as e:
            print(f"Warning: Dialect identification failed: {e}")
            return 'unknown'

    def correct_english_text(self, text):
        """Correct English text with confidence checking"""
        if not TEXTBLOB_AVAILABLE or not text:
            return text

        try:
            blob = TextBlob(text)
            corrected = str(blob.correct())

            # Only apply correction if the change makes sense
            original_words = text.lower().split()
            corrected_words = corrected.lower().split()

            # Check if too many words changed (likely false positives)
            if len(original_words) != len(corrected_words):
                return text  # Keep original if word count changed

            changes = sum(1 for o, c in zip(original_words, corrected_words) if o != c)
            change_ratio = changes / len(original_words) if original_words else 0

            # If more than 30% of words changed, probably wrong
            if change_ratio > 0.3:
                return text  # Keep original

            # Check for common false positives
            false_positives = {
                'nice': 'vice',
                'malls': 'walls',
                'mall': 'wall',
                'brands': 'bands',
                'halal': 'hall',
                'options': 'option',
                'if': 'of',
                'upscale': 'scale'
            }

            for original, wrong_correction in false_positives.items():
                if original in text.lower() and wrong_correction in corrected.lower():
                    return text  # Keep original to avoid false positive

            return corrected

        except Exception as e:
            print(f"Warning: English correction failed: {e}")
            return text

    def process_mixed_text(self, text):
        """Process mixed Arabic-English text"""
        if not text:
            return text

        try:
            # Split text into words
            words = text.split()
            processed_words = []

            for word in words:
                # Check if word is primarily Arabic
                arabic_chars = len(re.findall(r'[\u0600-\u06FF]', word))
                english_chars = len(re.findall(r'[a-zA-Z]', word))

                if arabic_chars > 0 and english_chars == 0:
                    # Pure Arabic word - normalize
                    processed_word = self.normalize_arabic_text(word)
                elif english_chars > 0 and arabic_chars == 0:
                    # Pure English word - keep as is (spell correction handled separately)
                    processed_word = word
                else:
                    # Mixed or other - keep as is
                    processed_word = word

                processed_words.append(processed_word)

            return ' '.join(processed_words)

        except Exception as e:
            print(f"Warning: Mixed text processing failed: {e}")
            return text

    def clean_reviewer_name(self, name):
        """Clean reviewer name (Arabic/English/Mixed)"""
        if not name or name == 'N/A':
            return name

        try:
            # Remove extra whitespace
            name = re.sub(r'\s+', ' ', name).strip()

            # Capitalize properly for English parts
            words = name.split()
            cleaned_words = []

            for word in words:
                # Check if word contains Arabic characters
                if re.search(r'[\u0600-\u06FF]', word):
                    # Arabic word - just normalize
                    cleaned_word = self.normalize_arabic_text(word)
                else:
                    # English word - capitalize properly
                    cleaned_word = word.capitalize()

                cleaned_words.append(cleaned_word)

            return ' '.join(cleaned_words)

        except Exception as e:
            print(f"Warning: Name cleaning failed: {e}")
            return name

    def process_arabic_text(self, text):
        """Process Arabic text specifically"""
        if not text:
            return text

        # Normalize using CAMeL Tools
        processed = self.normalize_arabic_text(text)

        # Identify dialect for debugging
        if CAMEL_AVAILABLE and self.dialect_id:
            dialect = self.identify_arabic_dialect(text)
            if dialect != 'unknown':
                print(f"  Detected dialect: {dialect}")

        return processed

    def process_review_text(self, text):
        """Main function to process review text"""
        if not text or text == 'N/A':
            return text

        try:
            # Detect language
            lang = self.detect_language(text)

            if lang == 'ar':
                # Pure Arabic - normalize using CAMeL Tools
                processed_text = self.process_arabic_text(text)

            elif lang == 'en':
                # Pure English - spell correct
                processed_text = self.correct_english_text(text)

            else:
                # Mixed or unknown - process both parts
                processed_text = self.process_mixed_text(text)

                # Try to spell correct English parts
                if TEXTBLOB_AVAILABLE:
                    # Extract English words and correct them
                    english_parts = re.findall(r'[a-zA-Z\s]+', processed_text)
                    for eng_part in english_parts:
                        if len(eng_part.strip()) > 2:
                            corrected = self.correct_english_text(eng_part)
                            processed_text = processed_text.replace(eng_part, corrected)

            # Final cleanup
            processed_text = re.sub(r'\s+', ' ', processed_text).strip()
            return processed_text

        except Exception as e:
            print(f"Warning: Text processing failed: {e}")
            return text

    def preprocess_text(self, text):
        """Unified text preprocessing method - calls process_review_text"""
        return self.process_review_text(text)

    def preprocess_reviews(self, reviews):
        """Preprocess all reviews"""
        if not reviews:
            return reviews

        print("\n" + "="*50)
        print("PREPROCESSING REVIEWS WITH CAMEL TOOLS")
        print("="*50)

        processed_reviews = []

        for i, review in enumerate(reviews, 1):
            print(f"\nProcessing review {i}/{len(reviews)}...")

            processed_review = review.copy()

            # Process reviewer name
            original_name = review['name']
            processed_name = self.clean_reviewer_name(original_name)
            if original_name != processed_name:
                print(f"Name: {original_name} → {processed_name}")
            processed_review['name'] = processed_name

            # Process review text
            original_text = review['text']
            if original_text and original_text != 'N/A':
                processed_text = self.process_review_text(original_text)
                if original_text != processed_text:
                    # Show truncated version for display
                    orig_display = original_text[:50] + "..." if len(original_text) > 50 else original_text
                    proc_display = processed_text[:50] + "..." if len(processed_text) > 50 else processed_text
                    print(f"Text: {orig_display} → {proc_display}")
                processed_review['text'] = processed_text

            processed_reviews.append(processed_review)

        print(f"\n✓ Successfully preprocessed {len(processed_reviews)} reviews!")
        return processed_reviews

    def test_preprocessing(self):
        """Test preprocessing with sample texts"""
        print("\n" + "="*50)
        print("TESTING PREPROCESSING FUNCTIONALITY")
        print("="*50)

        test_cases = [
            # Arabic with slang
            ("المول زين بس الاسعار شوي غالية", "Arabic with slang"),

            # English with typos
            ("The mall is beutiful but expensiv", "English with typos"),

            # Mixed content
            ("المول beautiful والخدمة excellent بس expensive شوي", "Mixed Arabic-English"),

            # Clean English (should not change much)
            ("The mall is nice and clean", "Clean English"),

            # Common false positives we want to avoid
            ("Nice mall with good brands", "Clean English - should not change 'Nice' to 'Vice'"),
            ("Great malls in Riyadh", "Should not change 'malls' to 'walls'"),
            ("Halal restaurants available", "Should not change 'halal' to 'hall'"),
        ]

        for text, description in test_cases:
            print(f"\n--- Testing: {description} ---")
            print(f"Original: {text}")

            try:
                # Test language detection
                lang = self.detect_language(text)
                print(f"Detected language: {lang}")

                # Test processing
                processed = self.process_review_text(text)
                print(f"Processed: {processed}")

                # Show if there were changes
                if text != processed:
                    print("✓ Text was modified")
                else:
                    print("→ No changes made")

            except Exception as e:
                print(f"An error occurred: {e}")

        print("\n" + "="*50)
        print("TESTING COMPLETE")
        print("="*50)

    def show_random_samples(self, reviews, num_samples=5):
        """Show random samples of processed reviews"""
        if not reviews:
            return

        import random

        print(f"\n--- Random Sample of {min(num_samples, len(reviews))} Processed Reviews ---")
        print("-" * 60)

        sample_reviews = random.sample(reviews, min(num_samples, len(reviews)))

        for i, review in enumerate(sample_reviews, 1):
            print(f"\nSample {i}:")
            print(f"Name: {review['name']}")
            print(f"Date: {review['date']}")
            print(f"Rating: {review['rating']}")
            text_display = review['text'][:100] + "..." if len(review['text']) > 100 else review['text']
            print(f"Text: {text_display}")
            print("-" * 40)
        """Test preprocessing with sample texts"""
        print("\n" + "="*50)
        print("TESTING PREPROCESSING FUNCTIONALITY")
        print("="*50)

        test_cases = [
            # Arabic with slang
            ("المول زين بس الاسعار شوي غالية", "Arabic with slang"),

            # English with typos
            ("The mall is beutiful but expensiv", "English with typos"),

            # Mixed content
            ("المول beautiful والخدمة excellent بس expensive شوي", "Mixed Arabic-English"),

            # Clean English (should not change much)
            ("The mall is nice and clean", "Clean English"),

            # Common false positives we want to avoid
            ("Nice mall with good brands", "Clean English - should not change 'Nice' to 'Vice'"),
        ]

        for text, description in test_cases:
            print(f"\n--- Testing: {description} ---")
            print(f"Original: {text}")

            try:
                # Use the correct method name from your class
                processed = self.process_review_text(text)  # Changed from preprocess_text

                if processed != text:
                    print(f"Processed: {processed}")
                    print("✓ Text was modified")
                else:
                    print("✓ No changes needed")

            except Exception as e:
                print(f"❌ Error: {e}")

        # Test name cleaning too
        print(f"\n--- Testing Name Cleaning ---")
        test_names = [
            "mohammed ahmed",
            "SARAH SMITH",
            "محمد الأحمد",
            "john doe",
            "فاطمة العلي"
        ]

        for name in test_names:
            try:
                cleaned = self.clean_reviewer_name(name)
                if cleaned != name:
                    print(f"Name: {name} → {cleaned}")
                else:
                    print(f"Name: {name} (no change needed)")
            except Exception as e:
                print(f"❌ Name cleaning error for '{name}': {e}")


class GoogleMapsReviewScraper:
    def __init__(self):
        self.driver = None
        self.text_processor = ReviewTextProcessor()
        self.setup_driver()

    def setup_driver(self):
        """Setup Chrome driver with UTF-8 support for Arabic names"""
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        chrome_options.add_argument("--lang=en-US")
        chrome_options.add_argument("--accept-lang=en-US,en")

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except Exception as e:
            print(f"Error setting up Chrome driver: {e}")
            return None

    def modify_url_for_english(self, url):
        """Modify URL to force English interface"""
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        query_params['hl'] = ['en']
        query_params['gl'] = ['US']
        new_query = urlencode(query_params, doseq=True)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

    def sort_by_newest(self):
        """Sort reviews by newest first"""
        try:
            print("Sorting reviews by newest first...")

            # Wait for and click the sort dropdown
            sort_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-value='Sort']"))
            )
            self.driver.execute_script("arguments[0].click();", sort_button)
            time.sleep(2)

            # Select "Newest" option
            newest_option = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//div[@role='menuitemradio'][contains(., 'Newest')]"))
            )
            self.driver.execute_script("arguments[0].click();", newest_option)
            time.sleep(3)

            print("✓ Successfully sorted by newest reviews")
            return True

        except Exception as e:
            print(f"Could not sort by newest: {e}")
            return False

    def click_more_buttons(self):
        """Clicks 'More' buttons to expand full review text."""
        try:
            more_buttons_selectors = [
                "button.Jj6La", # Common button class for 'More'
                "button[aria-label^='See more']", # More descriptive aria-label
                "span.LMgQJb", # Some 'More' text might be in a span
                # Add more selectors if needed based on observation
                "span.app-inline-block.font-weight-500", # Another potential 'More' button type
                "button[jsaction*='reviews.expand']", # Specific button with expand action
                "g-review-controls > button", # Generic control button
                "span.google-symbols.Q1oZ3b" # Yet another observation
            ]
            
            # Keep track of how many buttons were clicked in the current iteration
            # This loop will continue as long as new buttons are found and clicked
            # or until a maximum number of attempts is reached.
            total_clicked_count = 0
            attempts_without_new_clicks = 0
            max_no_new_clicks_attempts = 3 # Stop if no new clicks after 3 attempts
            max_total_attempts = 10 # Global safety break for the loop

            for attempt_num in range(max_total_attempts):
                found_and_clicked_in_iteration = False
                current_iteration_clicks = 0

                for selector in more_buttons_selectors:
                    try:
                        # Find all 'More' buttons that are visible and enabled
                        buttons_to_click = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        
                        for button in buttons_to_click:
                            # Check if the button is within the current scrollable view and is interactable
                            if button.is_displayed() and button.is_enabled():
                                try:
                                    # Scroll into view to ensure clickability
                                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                    time.sleep(0.2) # Small wait after scroll
                                    self.driver.execute_script("arguments[0].click();", button)
                                    found_and_clicked_in_iteration = True
                                    current_iteration_clicks += 1
                                    time.sleep(0.5) # Short delay after each click to allow content to load
                                except ElementClickInterceptedException:
                                    # If click is intercepted, try clicking with ActionChains or more forceful JS
                                    ActionChains(self.driver).move_to_element(button).click().perform()
                                    found_and_clicked_in_iteration = True
                                    current_iteration_clicks += 1
                                    time.sleep(0.5)
                                except Exception as e:
                                    print(f"Warning: Error clicking button with selector {selector}: {e}")
                                    # Continue to next button if there's an error
                                    continue
                    except Exception as e:
                        # print(f"Warning: Error finding buttons with selector {selector}: {e}")
                        # Continue to next selector if there's an error
                        continue
                
                if found_and_clicked_in_iteration:
                    total_clicked_count += current_iteration_clicks
                    attempts_without_new_clicks = 0 # Reset counter as we found new buttons
                else:
                    attempts_without_new_clicks += 1
                
                if attempts_without_new_clicks >= max_no_new_clicks_attempts:
                    print(f"No new 'More' buttons found after {max_no_new_clicks_attempts} attempts. Stopping.")
                    break
                
                time.sleep(1) # Small delay before next iteration to allow page to settle
            
            print(f"Finished clicking 'More' buttons. Total expanded: {total_clicked_count}")
        except Exception as e:
            print(f"Critical error in click_more_buttons: {e}")

    def scroll_reviews(self, target_count):
        """Scroll through reviews to load more with improved method"""
        print("Loading reviews...")

        max_attempts = 15
        attempt = 0
        last_count = 0
        no_change_count = 0

        while attempt < max_attempts:
            # Click more buttons first
            self.click_more_buttons()

            # Count current reviews
            review_elements = self.driver.find_elements(By.CSS_SELECTOR, "div[data-review-id]")
            current_count = len(review_elements)

            print(f"Currently loaded: {current_count} reviews (Target: {target_count})")

            if current_count >= target_count:
                print(f"Target reached! Found {current_count} reviews")
                break

            if current_count == last_count:
                no_change_count += 1
                if no_change_count >= 3:
                    print("No new reviews loading, trying different scroll methods...")
                    # Try different scrolling approaches
                    try:
                        # Method 1: Scroll the reviews container
                        self.driver.execute_script("""
                            var container = document.querySelector('div[data-review-id]').parentElement;
                            if (container) {
                                container.scrollTop = container.scrollHeight;
                            }
                        """)
                        time.sleep(2)

                        # Method 2: Page scroll
                        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(2)

                        # Method 3: Find and scroll specific container
                        containers = self.driver.find_elements(By.CSS_SELECTOR, "div[role='main'], .m6QErb")
                        for container in containers:
                            try:
                                self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", container)
                                time.sleep(1)
                            except:
                                continue

                    except Exception as e:
                        print(f"Alternative scroll methods failed: {e}")

                    if no_change_count >= 6:
                        print("No new reviews loading, stopping scroll")
                        break
            else:
                no_change_count = 0

            # Standard scroll method
            try:
                # Find the scrollable reviews container
                self.driver.execute_script("""
                    var reviewsContainer = document.querySelector('.m6QErb[data-value="Sort"]');
                    if (reviewsContainer) {
                        var scrollableParent = reviewsContainer.closest('div[role="main"]') ||
                                             reviewsContainer.closest('.siAUzd') ||
                                             reviewsContainer.parentElement.parentElement;
                        if (scrollableParent) {
                            scrollableParent.scrollTop = scrollableParent.scrollHeight;
                        }
                    }
                """)
            except Exception as e:
                print(f"Scroll error: {e}")

            last_count = current_count
            attempt += 1
            time.sleep(3)

        # Final expansion of review texts
        print("Final expansion of review texts...")
        self.click_more_buttons()

        final_count = len(self.driver.find_elements(By.CSS_SELECTOR, "div[data-review-id]"))
        print(f"Final loaded reviews: {final_count}")
        return True

    def extract_reviews(self, max_reviews):
        """Extract review data from the page with UTF-8 support"""
        reviews = []
        seen_reviews = set()

        review_containers = self.driver.find_elements(By.CSS_SELECTOR, "div[data-review-id]")
        print(f"Found {len(review_containers)} review containers")
        print(f"Extracting data from {max_reviews} reviews...")

        for i, container in enumerate(review_containers):
            if len(reviews) >= max_reviews:
                break

            review_data = {
                'name': 'N/A',
                'date': 'N/A',
                'rating': 'N/A',
                'text': 'N/A'
            }

            try:
                # Extract reviewer name (handles Arabic names with UTF-8)
                try:
                    name_element = container.find_element(By.CSS_SELECTOR, "div.d4r55.fontTitleMedium")
                    review_data['name'] = name_element.text.strip()
                except:
                    pass

                # Extract review date
                try:
                    date_element = container.find_element(By.CSS_SELECTOR, "div.DU9Pgb span.rsqaWe")
                    review_data['date'] = date_element.text.strip()
                except:
                    pass

                # Extract rating
                try:
                    rating_element = container.find_element(By.CSS_SELECTOR, "div.DU9Pgb span.kvMYJc[role='img']")
                    aria_label = rating_element.get_attribute("aria-label")
                    if aria_label:
                        rating_match = re.search(r'(\d+)', aria_label)
                        if rating_match:
                            review_data['rating'] = rating_match.group(1) + " stars"
                except:
                    pass

                # Extract review text
                try:
                    # The text element might be hidden and replaced by a 'More' button click.
                    # We need to get the full text after clicking 'More' buttons.
                    # The current implementation of click_more_buttons should handle this.
                    text_element = container.find_element(By.CSS_SELECTOR, "div.MyEned span.wiI7pd")
                    review_data['text'] = text_element.text.strip()
                except:
                    pass

                # Create unique identifier
                review_id = f"{review_data['name']}_{review_data['date']}_{review_data['rating']}"

                if review_id not in seen_reviews and review_data['name'] != 'N/A':
                    seen_reviews.add(review_id)
                    reviews.append(review_data)
                    print(f"Extracted review {len(reviews)}: {review_data['name'][:20]}...")
                else:
                    print(f"Skipping duplicate or invalid review {i+1}")

            except Exception as e:
                print(f"Error extracting review {i+1}: {e}")
                continue

        return reviews

    def preprocess_reviews(self, reviews):
        """Preprocess all reviews using CAMeL Tools and TextBlob"""
        if not reviews:
            return reviews

        print("\n" + "="*50)
        print("PREPROCESSING REVIEWS WITH CAMEL TOOLS")
        print("="*50)

        processed_reviews = []

        for i, review in enumerate(reviews, 1):
            print(f"\nProcessing review {i}/{len(reviews)}...")

            processed_review = review.copy()

            # Process reviewer name
            original_name = review['name']
            processed_review['name'] = self.text_processor.clean_reviewer_name(original_name)
            if original_name != processed_review['name']:
                print(f"  Name: {original_name} → {processed_review['name']}")

            # Process review text
            original_text = review['text']
            processed_review['text'] = self.text_processor.process_review_text(original_text)
            if original_text != processed_review['text'] and len(original_text) > 0:
                print(f"  Text: {original_text[:50]}... → {processed_review['text'][:50]}...")

            processed_reviews.append(processed_review)

        print(f"\n✓ Successfully preprocessed {len(processed_reviews)} reviews!")
        return processed_reviews

    def scrape_reviews(self, url, num_reviews):
        """Main scraping function with newest first sorting"""
        if not self.driver:
            print("Driver not initialized")
            return []

        try:
            # Modify URL for English interface
            english_url = self.modify_url_for_english(url)
            print("Opening URL...")
            self.driver.get(english_url)
            time.sleep(5)

            # Wait for reviews to be present
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-review-id]"))
                )
                print("Reviews found on page")
            except TimeoutException:
                print("No reviews found on this page")
                return []

            # Sort by newest first
            self.sort_by_newest()
            time.sleep(3)

            # Scroll to load more reviews
            self.scroll_reviews(num_reviews)

            # Extract review data
            reviews = self.extract_reviews(num_reviews)

            # Preprocess reviews using CAMeL Tools
            if reviews:
                reviews = self.preprocess_reviews(reviews)

            return reviews

        except Exception as e:
            print(f"Error during scraping: {e}")
            return []

    def save_to_csv(self, reviews, filename="google_maps_reviews.csv"):
        """Save reviews to CSV file with UTF-8 encoding"""
        if not reviews:
            print("No reviews to save")
            return

        with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
            fieldnames = ['name', 'date', 'rating', 'text']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for review in reviews:
                writer.writerow(review)

        print(f"Reviews saved to {filename}")

    def close(self):
        """Close the driver"""
        if self.driver:
            self.driver.quit()


def detect_review_language(text):
    """Detect if review is Arabic, English, or mixed"""
    if not text or text == 'N/A':
        return 'unknown'

    # Count Arabic and English characters
    arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
    english_chars = len(re.findall(r'[a-zA-Z]', text))

    total_chars = arabic_chars + english_chars

    if total_chars == 0:
        return 'unknown'

    arabic_ratio = arabic_chars / total_chars
    english_ratio = english_chars / total_chars

    # Classification thresholds
    if arabic_ratio > 0.7:
        return 'arabic'
    elif english_ratio > 0.7:
        return 'english'
    elif arabic_ratio > 0.2 and english_ratio > 0.2:
        return 'mixed'
    else:
        return 'unknown'

        
def main():
    print("Google Maps Review Scraper with CAMeL Tools - Newest First")
    print("-" * 60)

    # Check dependencies
    missing_deps = []
    if not CAMEL_AVAILABLE:
        missing_deps.append("camel-tools")
    if not TEXTBLOB_AVAILABLE:
        missing_deps.append("textblob")
    if not LANGDETECT_AVAILABLE:
        missing_deps.append("langdetect")

    if missing_deps:
        print(f"Optional dependencies missing: {', '.join(missing_deps)}")
        print("Install with: pip install " + " ".join(missing_deps))
        print("Continuing with available features...\n")

    # Initialize processor once
    processor = ReviewTextProcessor()

    # Get input from user
    url = input("Enter the Google Maps place URL: ").strip()

    try:
        num_reviews = int(input("Enter the number of reviews to scrape: "))
    except ValueError:
        print("Invalid number. Using default value of 10.")
        num_reviews = 10

    # Initialize scraper
    scraper = GoogleMapsReviewScraper()

    try:
        # Scrape reviews (newest first)
        reviews = scraper.scrape_reviews(url, num_reviews)

        if reviews:
            # Add testing option BEFORE processing
            test_choice = input("\nRun preprocessing tests? (y/n): ").lower()
            if test_choice == 'y':
                processor.test_preprocessing()

            # Process reviews
            processed_reviews = processor.preprocess_reviews(reviews)

            print(f"\nSuccessfully scraped and processed {len(processed_reviews)} reviews!")

            # Display first few reviews as preview
            print("\nPreview of processed reviews (newest first):")
            print("-" * 50)
            for i, review in enumerate(processed_reviews[:3], 1):
                print(f"Review {i}:")
                print(f"Name: {review['name']}")
                print(f"Date: {review['date']}")
                print(f"Rating: {review['rating']}")
                print(f"Text: {review['text'][:100]}..." if len(review['text']) > 100 else f"Text: {review['text']}")
                print("-" * 50)

            # Save to CSV
            filename = input("\nEnter filename for CSV (press Enter for default): ").strip()
            if not filename:
                filename = "google_maps_reviews.csv"

            # Save both original and processed versions option
            save_choice = input("\nSave both original and processed versions? (y/n): ").lower()
            if save_choice == 'y':
                scraper.save_to_csv(reviews, "original_reviews.csv")
                scraper.save_to_csv(processed_reviews, "processed_reviews.csv")
                print("Saved both versions!")
            else:
                scraper.save_to_csv(processed_reviews, filename)

        else:
            print("No reviews were scraped. Please check the URL and try again.")

    except KeyboardInterrupt:
        print("\nScraping interrupted by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        scraper.close()

    if reviews:
        # Add testing option
        test_choice = input("\nRun preprocessing tests? (y/n): ").lower()
        if test_choice == 'y':
            processor = ReviewTextProcessor()
            processor.test_preprocessing()

        # Process reviews
        processed_reviews = processor.preprocess_reviews(reviews)

        # Show samples
        processor.show_random_samples(processed_reviews)

        # Save both original and processed versions
        save_choice = input("\nSave both original and processed versions? (y/n): ").lower()
        if save_choice == 'y':
            scraper.save_to_csv(reviews, "original_reviews.csv")
            scraper.save_to_csv(processed_reviews, "processed_reviews.csv")
        else:
            scraper.save_to_csv(processed_reviews, filename)

def scrape_reviews_function(url, num_reviews):
    """Standalone function to scrape reviews"""
    scraper = GoogleMapsReviewScraper()
    try:
        reviews = scraper.scrape_reviews(url, num_reviews)
        return reviews
    except Exception as e:
        print(f"Error in scraping: {e}")
        return []
    finally:
        scraper.close()

def process_reviews_function(reviews):
    """Standalone function to process reviews"""
    processor = ReviewTextProcessor()
    try:
        processed_reviews = processor.preprocess_reviews(reviews)
        return processed_reviews
    except Exception as e:
        print(f"Error in processing: {e}")
        return reviews

def save_reviews_function(reviews, filename):
    """Standalone function to save reviews"""
    scraper = GoogleMapsReviewScraper()
    try:
        scraper.save_to_csv(reviews, filename)
        return True
    except Exception as e:
        print(f"Error saving: {e}")
        return False

# Make classes available for import
__all__ = ['GoogleMapsReviewScraper', 'ReviewTextProcessor', 'scrape_reviews_function',
           'process_reviews_function', 'save_reviews_function']

# Only run main() if script is executed directly
if __name__ == "__main__":
    main()